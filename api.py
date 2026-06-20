from flask import Flask, jsonify
import json
import os

app = Flask(__name__)
RESULTS_FILE = "impact_pulse_results.json"

def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r") as f:
            return json.load(f)
    return []

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "crawler": "running"})

@app.route("/api/results")
def get_results():
    return jsonify(load_results())

@app.route("/api/summary")
def get_summary():
    results = load_results()
    total = len(results)
    positive = len([r for r in results if r.get("sentiment") in ["positive","advocacy"]])
    negative = len([r for r in results if r.get("sentiment") in ["negative","critical"]])
    alerts = len([r for r in results if r.get("alert_level") in ["critical","watch"]])
    programs = {}
    for r in results:
        for p in r.get("programs_confirmed", []):
            programs[p] = programs.get(p, 0) + 1
    return jsonify({"total_mentions": total, "positive": positive, "negative": negative, "alerts": alerts, "programs": programs, "latest": results[-5:] if results else []})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
