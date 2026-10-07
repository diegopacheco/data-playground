import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("REGISTRY_URL", "http://localhost:27501") + "/apis/registry/v3"
CONTENT_TYPES = {"AVRO": "application/json", "PROTOBUF": "application/x-protobuf"}


class RuleViolation(Exception):
    def __init__(self, body):
        super().__init__(body.get("title", "rule violation"))
        self.body = body
        self.causes = [c.get("description", "") for c in body.get("causes") or []]


def call(method, path, body=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            text = res.read().decode()
            return text if raw else (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        e.close()
        payload = json.loads(text) if text.startswith("{") else {"title": text, "status": e.code}
        if payload.get("name") == "RuleViolationException":
            raise RuleViolation(payload)
        if e.code == 404:
            return None
        raise RuntimeError(f"{method} {path} -> {e.code} {text[:300]}")


def info():
    return call("GET", "/system/info")


def delete_group(group):
    call("DELETE", f"/groups/{group}")


def content(schema, artifact_type):
    return {"content": schema, "contentType": CONTENT_TYPES[artifact_type]}


def create_artifact(group, artifact, artifact_type, schema, mode):
    created = call("POST", f"/groups/{group}/artifacts", {
        "artifactId": artifact, "artifactType": artifact_type,
        "firstVersion": {"content": content(schema, artifact_type)}})
    call("POST", f"/groups/{group}/artifacts/{artifact}/rules", {"ruleType": "COMPATIBILITY", "config": mode})
    return created["version"]


def add_version(group, artifact, artifact_type, schema, dry_run=False):
    suffix = "?dryRun=true" if dry_run else ""
    return call("POST", f"/groups/{group}/artifacts/{artifact}/versions{suffix}", {"content": content(schema, artifact_type)})


def check(group, artifact, artifact_type, schema):
    try:
        add_version(group, artifact, artifact_type, schema, dry_run=True)
        return {"accepted": True, "causes": []}
    except RuleViolation as v:
        return {"accepted": False, "causes": v.causes}


def versions(group, artifact):
    found = call("GET", f"/groups/{group}/artifacts/{artifact}/versions?limit=100")
    return found["versions"] if found else []


def rule(group, artifact):
    found = call("GET", f"/groups/{group}/artifacts/{artifact}/rules/COMPATIBILITY")
    return found["config"] if found else None


def artifacts(group):
    found = call("GET", f"/groups/{group}/artifacts?limit=100")
    return found["artifacts"] if found else []


def schema_by_global_id(global_id):
    return call("GET", f"/ids/globalIds/{global_id}", raw=True)


def version_content(group, artifact, version):
    return call("GET", f"/groups/{group}/artifacts/{artifact}/versions/{version}/content", raw=True)
