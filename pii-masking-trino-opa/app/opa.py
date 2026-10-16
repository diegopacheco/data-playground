import json
import os
import subprocess
import urllib.request

OPA_URL = os.environ.get("OPA_URL", "http://localhost:30401")
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "opa", "policy", "pii", "data.json")


def read_data():
    with urllib.request.urlopen(OPA_URL + "/v1/data/pii", timeout=10) as resp:
        return json.loads(resp.read())["result"]


def write_data(document):
    req = urllib.request.Request(OPA_URL + "/v1/data/pii", data=json.dumps(document).encode(), method="PUT",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).close()


def file_data():
    with open(DATA_FILE) as f:
        return json.load(f)


def decisions(query_id):
    logs = subprocess.run(["podman", "logs", "--since", "2m", "s5-opa"], capture_output=True, text=True, timeout=30)
    out = []
    for line in (logs.stdout + logs.stderr).splitlines():
        if query_id in line:
            entry = json.loads(line)
            out.append({"path": entry["path"], "input": entry["input"], "result": entry.get("result")})
    return out


def trino_started():
    started = '{{.State.StartedAt.UTC.Format "2006-01-02T15:04:05.000Z"}}'
    done = subprocess.run(["podman", "inspect", "-f", started, "s5-trino"], capture_output=True, text=True, timeout=30)
    return done.stdout.strip()
