import json
import urllib.request

TEMPLATE = "t8-etl"
CRON = "t8-etl-cron"


class Argo:
    def __init__(self, base, namespace):
        self.base = base.rstrip("/")
        self.namespace = namespace

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")

    def submit(self, kind, name, parameters):
        body = {
            "namespace": self.namespace,
            "resourceKind": kind,
            "resourceName": name,
            "submitOptions": {"parameters": [f"{k}={v}" for k, v in parameters.items()]},
        }
        return self.call("POST", f"/api/v1/workflows/{self.namespace}/submit", body)["metadata"]["name"]

    def workflow(self, name):
        return self.call("GET", f"/api/v1/workflows/{self.namespace}/{name}")

    def workflows(self):
        return self.call("GET", f"/api/v1/workflows/{self.namespace}").get("items") or []

    def cron(self, name=CRON):
        return self.call("GET", f"/api/v1/cron-workflows/{self.namespace}/{name}")

    def artifact(self, workflow, node_id, artifact):
        url = f"{self.base}/artifact-files/{self.namespace}/workflows/{workflow}/{node_id}/outputs/{artifact}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()


def steps(wf):
    nodes = (wf.get("status") or {}).get("nodes") or {}
    retried = {c for n in nodes.values() if n.get("type") == "Retry" for c in n.get("children") or []}
    out = []
    for n in nodes.values():
        if n.get("type") not in ("Retry", "Pod", "Skipped") or n["id"] in retried:
            continue
        attempts = [nodes[c] for c in n.get("children") or [] if c in nodes] if n["type"] == "Retry" else [n]
        out.append({
            "id": n["id"],
            "name": n.get("displayName"),
            "template": n.get("templateName"),
            "phase": n.get("phase"),
            "message": n.get("message", ""),
            "started": n.get("startedAt"),
            "finished": n.get("finishedAt"),
            "attempts": [{"id": a["id"], "phase": a.get("phase"), "message": a.get("message", "")} for a in attempts],
            "outputs": {p["name"]: p.get("value") for p in (n.get("outputs") or {}).get("parameters") or []},
        })
    return sorted(out, key=lambda s: (s["started"] or "9", s["name"] or ""))


def summary(wf):
    meta = wf["metadata"]
    status = wf.get("status") or {}
    params = {p["name"]: p.get("value") for p in (wf.get("spec", {}).get("arguments") or {}).get("parameters") or []}
    return {
        "name": meta["name"],
        "phase": status.get("phase", "Pending"),
        "started": status.get("startedAt"),
        "finished": status.get("finishedAt"),
        "progress": status.get("progress", ""),
        "cron": (meta.get("labels") or {}).get("workflows.argoproj.io/cron-workflow", ""),
        "parameters": params,
    }
