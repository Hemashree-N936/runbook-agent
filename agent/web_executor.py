import copy
import threading
from pathlib import Path
from typing import Any

from agent.audit_log import log_event
from agent.executor import TOOL_FUNCTIONS
from agent.parser import parse_runbook
from agent.risk_classifier import classify_risk


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_status_lock = threading.Lock()

current_status: dict = {
	"current_step": None,
	"description": None,
	"state": "idle",
	"risk": None,
	"tool": None,
	"args": None,
	"rollback_tool": None,
	"rollback_args": None,
}
approval_event = threading.Event()
approval_decision: str | None = None
run_summary: dict | None = None
run_lock = threading.Lock()


def get_status() -> dict:
	with _status_lock:
		status = copy.deepcopy(current_status)
		status["run_summary"] = copy.deepcopy(run_summary)
		return status


def submit_decision(decision: str) -> bool:
	global approval_decision

	if decision not in ("approved", "rejected"):
		return False
	with _status_lock:
		if current_status["state"] not in (
			"waiting_approval",
			"waiting_rollback_approval",
		) or approval_event.is_set():
			return False
		approval_decision = decision
		approval_event.set()
		return True


def _set_status(**updates: Any) -> None:
	with _status_lock:
		current_status.update(updates)


def _wait_for_decision(state: str, **status_updates: Any) -> str:
	global approval_decision

	with _status_lock:
		approval_event.clear()
		approval_decision = None
		current_status.update(status_updates)
		current_status["state"] = state
	approval_event.wait()
	with _status_lock:
		decision = approval_decision
	return decision or "rejected"


def _run_tool(tool: str, args: dict) -> tuple[bool, Any]:
	function = TOOL_FUNCTIONS.get(tool)
	if function is None:
		return False, {"success": False, "error": f"Unknown tool '{tool}'"}
	try:
		result = function(**args)
		if isinstance(result, dict) and result.get("success") is False:
			return False, result
		return True, result
	except Exception as exc:
		return False, {"success": False, "error": str(exc)}


def run_runbook_in_background(runbook_text: str) -> bool:
	global run_summary

	if not run_lock.acquire(blocking=False):
		return False

	runbook_path = PROJECT_ROOT / "runbooks" / "_web_submitted.md"
	try:
		runbook_path.parent.mkdir(parents=True, exist_ok=True)
		runbook_path.write_text(runbook_text, encoding="utf-8")
		with _status_lock:
			current_status.update(
				{
					"current_step": None,
					"description": "Parsing runbook",
					"state": "running",
					"risk": None,
					"tool": None,
					"args": None,
					"rollback_tool": None,
					"rollback_args": None,
				}
			)
			run_summary = None
	except Exception as exc:
		_set_status(state="error", description=str(exc))
		run_lock.release()
		return False

	def run() -> None:
		global run_summary

		try:
			steps = parse_runbook(runbook_path)
			with _status_lock:
				run_summary = {
					"ran": 0,
					"approved": 0,
					"rejected": 0,
					"errored": 0,
					"rollback_executed": 0,
					"rollback_skipped": 0,
				}

			completed_reversible: list[dict] = []
			stopped_due_to_failure = False

			for step in steps:
				tool = step.get("tool", "")
				args = step.get("args", {})
				step_id = step.get("id", "?")
				description = step.get("description", "")
				rollback_tool = step.get("rollback_tool")
				rollback_args = step.get("rollback_args", {})
				try:
					risk = classify_risk(step)
				except Exception as exc:
					log_event(step, "unknown", "error", {"error": str(exc)})
					with _status_lock:
						run_summary["errored"] += 1
					stopped_due_to_failure = True
					break

				_set_status(
					current_step=step_id,
					description=description,
					state="running",
					risk=risk,
					tool=tool,
					args=copy.deepcopy(args),
					rollback_tool=rollback_tool,
					rollback_args=copy.deepcopy(rollback_args),
				)

				if risk == "destructive":
					decision = _wait_for_decision(
						"waiting_approval",
						current_step=step_id,
						description=description,
						risk=risk,
						tool=tool,
						args=copy.deepcopy(args),
						rollback_tool=rollback_tool,
						rollback_args=copy.deepcopy(rollback_args),
					)
					if decision == "rejected":
						log_event(step, risk, "rejected", None, approver="user")
						with _status_lock:
							run_summary["rejected"] += 1
						continue

					with _status_lock:
						run_summary["approved"] += 1
					succeeded, result = _run_tool(tool, args)
					if succeeded:
						log_event(step, risk, "approved", result, approver="user")
					else:
						log_event(step, risk, "error", result)
						with _status_lock:
							run_summary["errored"] += 1
						stopped_due_to_failure = True
						break
					continue

				succeeded, result = _run_tool(tool, args)
				if succeeded:
					log_event(step, risk, "executed", result)
					with _status_lock:
						run_summary["ran"] += 1
					if risk in ("read_only", "reversible"):
						completed_reversible.append(step)
				else:
					log_event(step, risk, "error", result)
					with _status_lock:
						run_summary["errored"] += 1
					stopped_due_to_failure = True
					break

			if stopped_due_to_failure:
				for step in reversed(completed_reversible):
					rollback_tool = step.get("rollback_tool")
					if rollback_tool is None:
						continue
					rollback_args = step.get("rollback_args", {})
					decision = _wait_for_decision(
						"waiting_rollback_approval",
						current_step=step.get("id", "?"),
						description=step.get("description", ""),
						risk="reversible",
						tool=step.get("tool", ""),
						args=copy.deepcopy(step.get("args", {})),
						rollback_tool=rollback_tool,
						rollback_args=copy.deepcopy(rollback_args),
					)
					if decision == "approved":
						_, result = _run_tool(rollback_tool, rollback_args)
						log_event(step, "reversible", "rollback_executed", result)
						with _status_lock:
							run_summary["rollback_executed"] += 1
					else:
						log_event(step, "reversible", "rollback_skipped", None, approver="user")
						with _status_lock:
							run_summary["rollback_skipped"] += 1

			_set_status(state="done", description=None)
		except Exception as exc:
			_set_status(state="error", description=str(exc))
		finally:
			run_lock.release()

	try:
		threading.Thread(target=run, daemon=True).start()
	except Exception as exc:
		_set_status(state="error", description=str(exc))
		run_lock.release()
		return False
	return True
