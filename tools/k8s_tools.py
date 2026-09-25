import subprocess


def _run_kubectl(args: list[str]) -> dict:
	try:
		result = subprocess.run(
			["kubectl", *args],
			capture_output=True,
			text=True,
		)
		return {
			"success": result.returncode == 0,
			"output": result.stdout,
			"error": result.stderr,
		}
	except Exception as exc:
		return {"success": False, "output": "", "error": str(exc)}


def get_pod_status(namespace: str) -> dict:
	return _run_kubectl(["get", "pods", "-n", namespace])


def get_replica_count(namespace: str, deployment: str) -> dict:
	return _run_kubectl(
		["get", "deployment", deployment, "-n", namespace, "-o", "jsonpath={.status.replicas}"]
	)


def tail_logs(namespace: str, deployment: str, lines: int = 20) -> dict:
	return _run_kubectl(
		["logs", f"deployment/{deployment}", "-n", namespace, f"--tail={lines}"]
	)


def scale_deployment(namespace: str, deployment: str, replicas: int) -> dict:
	return _run_kubectl(
		["scale", f"deployment/{deployment}", "-n", namespace, f"--replicas={replicas}"]
	)


def delete_deployment(namespace: str, deployment: str) -> dict:
	return _run_kubectl(["delete", "deployment", deployment, "-n", namespace])


if __name__ == "__main__":
	print(get_pod_status("staging"))
