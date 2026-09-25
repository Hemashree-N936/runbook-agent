import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "audit_log.jsonl"


def log_event(
	step: dict,
	risk: str,
	action: str,
	result: dict | None,
	approver: str = "system",
) -> None:
	event = {
		"timestamp": datetime.now(timezone.utc).isoformat(),
		"step_id": step["id"],
		"description": step["description"],
		"tool": step["tool"],
		"args": step["args"],
		"risk": risk,
		"action": action,
		"approver": approver,
		"result": result,
	}

	AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
	with AUDIT_LOG_PATH.open("a", encoding="utf-8") as log_file:
		log_file.write(json.dumps(event) + "\n")


def read_log() -> list[dict]:
	try:
		with AUDIT_LOG_PATH.open(encoding="utf-8") as log_file:
			return [json.loads(line) for line in log_file]
	except FileNotFoundError:
		return []
