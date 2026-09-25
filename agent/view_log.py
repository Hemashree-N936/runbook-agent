import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from agent.audit_log import read_log


def main() -> None:
	for entry in sorted(read_log(), key=lambda item: item["timestamp"]):
		print(
			f"[{entry['timestamp']}] {entry['step_id']} | {entry['risk']} | "
			f"{entry['action']} | {entry['tool']} | {entry['approver']}"
		)


if __name__ == "__main__":
	main()
