from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

from agent.web_executor import (
	get_status,
	run_runbook_in_background,
	submit_decision,
)


PROJECT_ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(PROJECT_ROOT), static_url_path="")


@app.before_request
def deny_hidden_files():
	if any(part.startswith(".") for part in request.path.split("/") if part):
		abort(404)


@app.get("/")
def dashboard():
	return send_from_directory(PROJECT_ROOT, "dashboard.html")


@app.post("/run")
def run():
	data = request.get_json(silent=True) or {}
	runbook_text = data.get("runbook_text", "")
	started = run_runbook_in_background(runbook_text)
	if not started:
		return jsonify({"error": "A runbook is already running"}), 409
	return jsonify({"started": True})


@app.get("/status")
def status():
	return jsonify(get_status())


@app.post("/approve")
def approve():
	return jsonify({"ok": submit_decision("approved")})


@app.post("/reject")
def reject():
	return jsonify({"ok": submit_decision("rejected")})


if __name__ == "__main__":
	app.run(debug=False, port=5000)