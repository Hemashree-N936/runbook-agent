import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from jsonschema import ValidationError, validate


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _strip_markdown_fence(content: str) -> str:
	lines = content.strip().splitlines()
	if lines and lines[0].strip().startswith("```"):
		lines = lines[1:]
		if lines and lines[-1].strip() == "```":
			lines = lines[:-1]
	return "\n".join(lines).strip()


def parse_runbook(runbook_path: str | Path) -> list[dict]:
	load_dotenv(PROJECT_ROOT / ".env")
	api_key = os.getenv("GROQ_API_KEY")
	if not api_key:
		raise RuntimeError("Error: GROQ_API_KEY is missing from the project .env file.")

	runbook_path = Path(runbook_path)
	try:
		runbook_content = runbook_path.read_text(encoding="utf-8")
	except OSError as exc:
		raise RuntimeError(f"Error reading runbook '{runbook_path}': {exc}") from exc

	schema_path = PROJECT_ROOT / "schema" / "step_schema.json"
	try:
		schema = json.loads(schema_path.read_text(encoding="utf-8"))
	except (OSError, json.JSONDecodeError) as exc:
		raise RuntimeError(f"Error loading JSON schema '{schema_path}': {exc}") from exc

	system_prompt = (
		"You are a runbook parser. Given a markdown runbook with numbered steps, "
		"output a JSON array where each element matches this exact JSON schema:\n"
		f"{json.dumps(schema, indent=2)}\n"
		"Every step's \"args\" object MUST include a \"namespace\" key. "
		"If the runbook doesn't explicitly state a namespace for a step, reuse the "
		"namespace mentioned earlier in the runbook (in this case, always use "
		"\"staging\" unless stated otherwise). "
		'The "tool" field MUST be exactly one of these values, no others: '
		'"get_pod_status", "get_replica_count", "tail_logs", "scale_deployment", '
		'"delete_deployment". Choose the closest match based on what the step describes. '
		'Use these EXACT argument names in "args" for each tool (do not invent alternate names):\n'
		'- get_pod_status: {"namespace"}\n'
		'- get_replica_count: {"namespace", "deployment"}\n'
		'- tail_logs: {"namespace", "deployment", "lines"}\n'
		'- scale_deployment: {"namespace", "deployment", "replicas"}\n'
		'- delete_deployment: {"namespace", "deployment"}\n'
		"For 'risk', 'preconditions', 'rollback', "
		"and 'expected_outcome', infer reasonable values from context. "
		"For reversible actions, also include 'rollback_tool' and "
		"'rollback_args' as the structured inverse action. For a "
		"scale_deployment step that scales to 0 replicas, use "
		"rollback_tool='scale_deployment' and rollback_args with the same "
		"namespace and deployment and replicas=2 unless a different prior "
		"count is stated. For destructive actions that cannot be undone by "
		"re-running a tool, set rollback_tool to null and rollback_args to {}. "
		"Output ONLY a raw JSON object of the form {\"steps\": [...]} where the array contains one object per runbook step, no markdown fences, no explanation."
	)

	for attempt in range(1, 4):
		stage = "calling the Groq API"
		try:
			response = Groq(api_key=api_key).chat.completions.create(
				model="openai/gpt-oss-20b",
				temperature=0,
				response_format={"type": "json_object"},
				messages=[
					{"role": "system", "content": system_prompt},
					{"role": "user", "content": runbook_content},
				],
			)

			stage = "parsing the Groq response as JSON"
			content = response.choices[0].message.content
			if not content:
				raise ValueError("the response was empty")
			parsed_response = json.loads(_strip_markdown_fence(content))
			parsed_steps = (
				parsed_response.get("steps", parsed_response)
				if isinstance(parsed_response, dict)
				else parsed_response
			)

			stage = "validating the Groq response"
			if not isinstance(parsed_steps, list):
				raise ValueError("expected a JSON array of steps")
			for index, step in enumerate(parsed_steps, start=1):
				try:
					validate(instance=step, schema=schema)
				except ValidationError as exc:
					raise ValueError(f"step {index}: {exc.message}") from exc

			return parsed_steps
		except Exception as exc:
			print(
				f"Warning: attempt {attempt}/3 failed while {stage}: {exc}",
				file=sys.stderr,
			)
			if attempt == 3:
				raise RuntimeError(
					f"Failed to process runbook after 3 attempts: {exc}"
				) from exc


def main() -> int:
	if len(sys.argv) < 2:
		print(f"Usage: {Path(sys.argv[0]).name} <runbook.md>", file=sys.stderr)
		return 2

	try:
		parsed_steps = parse_runbook(sys.argv[1])
	except Exception as exc:
		print(str(exc), file=sys.stderr)
		return 1

	print(json.dumps(parsed_steps, indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
