import json
import sys
import urllib.request

ui, flow_run_id, expected = sys.argv[1], sys.argv[2], dict(a.split("=") for a in sys.argv[3:])

runs = json.load(urllib.request.urlopen(ui + "/api/runs"))
run = next((r for r in runs if r["id"] == flow_run_id), None)
if run is None:
    sys.exit(f"flow run {flow_run_id} not found")
print(f"flow run {run['name']} {run['state']}: " + ", ".join(f"{t['task']}={t['state']} x{t['run_count']}" for t in run["tasks"]))
actual = {t["task"]: f"{t['state']}:{t['run_count']}" for t in run["tasks"]}
wrong = {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}
if run["state"] != "Completed" or wrong:
    sys.exit(f"unexpected states {wrong}")
