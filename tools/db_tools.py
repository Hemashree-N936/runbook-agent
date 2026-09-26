def run_sql(query: str, database: str = "app_db") -> dict:
	print(f"[SIMULATED] Would execute SQL against '{database}': {query}")
	return {
		"success": True,
		"output": f"Simulated execution of: {query}",
		"error": "",
	}


if __name__ == "__main__":
	print(run_sql("DROP TABLE old_sessions;"))
