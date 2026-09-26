import time


def write_greeting_line(text: str, filepath: str = "demo_output.txt") -> dict:
	with open(filepath, "a", encoding="utf-8") as output_file:
		output_file.write(f"{text}\n")
	time.sleep(1)
	return {"success": True, "output": f"Wrote: {text}", "error": ""}
