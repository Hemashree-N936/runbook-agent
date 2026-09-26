import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from agent.parser import parse_runbook
from agent.audit_log import log_event
from agent.risk_classifier import classify_risk
from tools.k8s_tools import (
	delete_deployment,
	get_pod_status,
	get_replica_count,
	scale_deployment,
	tail_logs,
)


TOOL_FUNCTIONS = {
	"get_pod_status": get_pod_status,
	"get_replica_count": get_replica_count,
	"tail_logs": tail_logs,
	"scale_deployment": scale_deployment,
	"delete_deployment": delete_deployment,
}


def _run_tool(tool: str, function, args: dict) -> tuple[bool, dict]:
	try:
		result = function(**args)
		print(result)
		if isinstance(result, dict) and result.get("success") is False:
			print(f"ERROR: Tool '{tool}' reported failure: {result.get('error', '')}", file=sys.stderr)
			return False, result
		return True, result
	except Exception as exc:
		print(f"ERROR: Tool '{tool}' failed: {exc}", file=sys.stderr)
		return False, {"success": False, "error": str(exc)}


def _read_approval(prompt: str) -> str:
	try:
		return input(prompt).strip().lower()
	except EOFError:
		return ""


def execute_steps(steps: list[dict]) -> tuple[int, int, int, int, int, int]:
	ran = 0
	approved = 0
	rejected = 0
	errored = 0
	rollback_executed = 0
	rollback_skipped = 0
	completed_reversible: list[dict] = []
	stopped_due_to_failure = False

	for step in steps:
		tool = step.get("tool", "")
		args = step.get("args", {})
		print(f"Step {step.get('id', '?')}: {step.get('description', '')}")

		try:
			risk = classify_risk(step)
		except Exception as exc:
			print(f"ERROR: Could not classify step risk: {exc}", file=sys.stderr)
			log_event(step, "unknown", "error", {"error": str(exc)})
			errored += 1
			stopped_due_to_failure = True
			break

		function = TOOL_FUNCTIONS.get(tool)
		if function is None:
			print(f"ERROR: Unknown tool '{tool}'; treating it as destructive.", file=sys.stderr)
			log_event(step, risk, "error", {"error": f"Unknown tool '{tool}'"})
			errored += 1
			stopped_due_to_failure = True
			break

		if risk == "destructive":
			rollback = step.get("rollback")
			if rollback is None:
				rollback = "No rollback available"
			print("Destructive step requires approval:")
			print(f"Description: {step.get('description', '')}")
			print(f"Tool: {tool}")
			print(f"Args: {args}")
			print(f"Rollback: {rollback}")

			answer = _read_approval("Approve this destructive step? [y/n/e=edit]: ")
			if answer == "e":
				try:
					edited_args = json.loads(input("Enter replacement args as JSON: "))
					if not isinstance(edited_args, dict):
						raise ValueError("replacement args must be a JSON object")
				except (json.JSONDecodeError, EOFError, ValueError) as exc:
					print(f"ERROR: Invalid replacement args: {exc}", file=sys.stderr)
					log_event(step, risk, "error", {"error": str(exc)})
					errored += 1
					continue

				answer = _read_approval("Approve with new args? [y/n]: ")
				if answer == "y":
					approved += 1
					succeeded, result = _run_tool(tool, function, edited_args)
					if succeeded:
						log_event(step, risk, "approved_edited", result, approver="user")
					else:
						log_event(step, risk, "error", result)
						errored += 1
						stopped_due_to_failure = True
						break
				else:
					if answer != "n":
						print("Unrecognized response; it was treated as a rejection.")
					print("Skipped by user.")
					log_event(step, risk, "rejected", None, approver="user")
					rejected += 1
			elif answer == "y":
				approved += 1
				succeeded, result = _run_tool(tool, function, args)
				if succeeded:
					log_event(step, risk, "approved", result, approver="user")
				else:
					log_event(step, risk, "error", result)
					errored += 1
					stopped_due_to_failure = True
					break
			else:
				if answer != "n":
					print("Unrecognized response; it was treated as a rejection.")
				print("Skipped by user.")
				log_event(step, risk, "rejected", None, approver="user")
				rejected += 1
			continue

		succeeded, result = _run_tool(tool, function, args)
		if succeeded:
			log_event(step, risk, "executed", result)
			ran += 1
			if risk in ("read_only", "reversible"):
				completed_reversible.append(step)
		else:
			log_event(step, risk, "error", result)
			errored += 1
			stopped_due_to_failure = True
			break

	if stopped_due_to_failure and completed_reversible:
		for step in reversed(completed_reversible):
			rollback_tool = step.get("rollback_tool")
			if rollback_tool is None:
				continue

			rollback_args = step.get("rollback_args", {})
			print(
				f"ROLLBACK AVAILABLE for step {step.get('id', '?')}: "
				f"would run {rollback_tool} with {rollback_args}"
			)
			answer = _read_approval("Run this rollback? [y/n]: ")
			if answer == "y":
				rollback_function = TOOL_FUNCTIONS.get(rollback_tool)
				if rollback_function is None:
					result = {"success": False, "error": f"Unknown tool '{rollback_tool}'"}
					print(f"ERROR: {result['error']}", file=sys.stderr)
				else:
					_, result = _run_tool(rollback_tool, rollback_function, rollback_args)
				rollback_executed += 1
				log_event(step, "reversible", "rollback_executed", result)
			else:
				print("Rollback skipped by user.")
				rollback_skipped += 1
				log_event(step, "reversible", "rollback_skipped", None, approver="user")

	return ran, approved, rejected, errored, rollback_executed, rollback_skipped


def main() -> int:
	if len(sys.argv) < 2:
		print(f"Usage: {Path(sys.argv[0]).name} <runbook.md>", file=sys.stderr)
		return 2

	try:
		steps = parse_runbook(sys.argv[1])
	except Exception as exc:
		print(f"ERROR: Could not parse runbook: {exc}", file=sys.stderr)
		return 1

	ran, approved, rejected, errored, rollback_executed, rollback_skipped = execute_steps(steps)
	print(
		f"Summary: {ran} steps ran, {approved} approved, {rejected} rejected, "
		f"{errored} errored, {rollback_executed} rollback_executed, "
		f"{rollback_skipped} rollback_skipped."
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
