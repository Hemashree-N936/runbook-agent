def classify_risk(step: dict) -> str:
	tool = step["tool"].lower()

	if tool == "run_sql":
		return "destructive"
	if any(keyword in tool for keyword in ("delete", "drop", "terminate", "remove")):
		return "destructive"
	if any(keyword in tool for keyword in ("scale", "restart", "rollback", "pause", "resume")):
		return "reversible"
	if any(keyword in tool for keyword in ("get", "list", "describe", "logs", "status")):
		return "read_only"
	return "destructive"


if __name__ == "__main__":
	tool_names = [
		"get_pod_status",
		"tail_logs",
		"scale_deployment",
		"delete_deployment",
		"run_sql_migration",
		"some_unknown_tool",
	]
	for tool_name in tool_names:
		print(tool_name, classify_risk({"tool": tool_name}))
