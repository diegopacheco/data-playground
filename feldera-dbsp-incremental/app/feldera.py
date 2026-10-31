import http.client
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

URL = os.environ.get("FELDERA_URL", "http://localhost:31201")
PIPELINE = "incremental"
PROGRAM = (Path(__file__).resolve().parent.parent / "sql" / "program.sql").read_text()
BASE = f"{URL}/v0/pipelines/{PIPELINE}"


class FelderaError(Exception):
    pass


def request(path, method="GET", body=None, content_type="application/json", timeout=120):
    req = urllib.request.Request(BASE + path, data=body, method=method, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FelderaError(f"{method} {path} -> {e.code}: {e.read()[:500].decode(errors='replace')}") from e


def status():
    try:
        return json.loads(request(""))
    except FelderaError:
        return None


def wait_for(check, what, seconds):
    deadline = time.time() + seconds
    state = None
    while time.time() < deadline:
        state = status()
        if state and check(state):
            return state
        time.sleep(0.5)
    raise FelderaError(f"timed out waiting for {what}: {(state or {}).get('deployment_error')}")


def deploy():
    state = status()
    if not state or state["program_code"] != PROGRAM:
        if state and state["deployment_status"] != "Stopped":
            stop()
        body = {"name": PIPELINE, "program_code": PROGRAM, "runtime_config": {"workers": 2}}
        request("", "PUT", json.dumps(body).encode())
    state = wait_for(lambda s: s["program_status"] not in ("Pending", "CompilingSql", "SqlCompiled", "CompilingRust"), "compilation", 600)
    if state["program_status"] != "Success":
        raise FelderaError(f"compilation failed: {json.dumps(state['program_error'])[:2000]}")
    return state


def stop():
    request("/stop?force=true", "POST")
    wait_for(lambda s: s["deployment_status"] == "Stopped", "stop", 120)


def restart_empty():
    state = status()
    if state["deployment_status"] != "Stopped":
        stop()
    if status()["storage_status"] != "Cleared":
        request("/clear", "POST")
        wait_for(lambda s: s["storage_status"] == "Cleared", "clear storage", 120)
    request("/start", "POST")
    return wait_for(lambda s: s["deployment_status"] == "Running" and reachable(), "start", 120)


def reachable():
    try:
        stats()
        return True
    except FelderaError:
        return False


def ensure_running():
    deploy()
    deadline = time.time() + 120
    while time.time() < deadline:
        state = status()
        if state["deployment_status"] == "Running" and reachable():
            return state
        if state["deployment_status"] == "Stopped" and state["deployment_desired_status"] == "Stopped":
            request("/start", "POST")
        time.sleep(0.5)
    raise FelderaError(f"pipeline did not reach Running: {status().get('deployment_error')}")


def wait_token(token, seconds=300):
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = json.loads(request(f"/completion_status?token={quote(token)}"))
        if state["status"] == "complete":
            return state.get("step", 0)
    raise FelderaError("timed out waiting for completion token")


def push(table, updates):
    body = json.dumps(updates).encode()
    token = json.loads(request(f"/ingress/{table}?format=json&update_format=insert_delete&array=true", "POST", body))["token"]
    return wait_token(token)


def push_csv(table, text):
    token = json.loads(request(f"/ingress/{table}?format=csv", "POST", text.encode(), "text/csv"))["token"]
    return wait_token(token)


def query(sql):
    body = request(f"/query?sql={quote(sql)}&format=json")
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def stats():
    return json.loads(request("/stats"))


class Listener:
    def __init__(self, view):
        self.view = view
        self.steps = []
        self.pending = []
        self.last_step = -1
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.conn = None
        threading.Thread(target=self.run, daemon=True).start()
        if not self.ready.wait(10):
            raise FelderaError(f"egress stream for {view} did not open")

    def run(self):
        url = urlparse(URL)
        self.conn = http.client.HTTPConnection(url.hostname, url.port, timeout=600)
        self.conn.request("POST", f"/v0/pipelines/{PIPELINE}/egress/{self.view}?format=json&backpressure=true")
        resp = self.conn.getresponse()
        self.ready.set()
        try:
            for line in resp:
                if line.strip():
                    self.chunk(json.loads(line))
        except (OSError, ValueError, http.client.HTTPException):
            pass

    def chunk(self, msg):
        with self.lock:
            for change in msg.get("json_data") or []:
                for kind, row in change.items():
                    self.pending.append({"weight": 1 if kind == "insert" else -1, "row": row})
            if "processed_steps" in msg:
                self.last_step = max(self.last_step, msg["processed_steps"])
                if self.pending:
                    self.steps.append({"step": msg["processed_steps"], "changes": self.pending})
                    self.pending = []

    def changes(self):
        with self.lock:
            return [c for s in self.steps for c in s["changes"]] + list(self.pending)

    def caught_up(self, step, seconds=30):
        deadline = time.time() + seconds
        while time.time() < deadline:
            with self.lock:
                if self.last_step >= step:
                    return
            time.sleep(0.005)
        raise FelderaError(f"egress stream for {self.view} did not reach step {step}")

    def close(self):
        if self.conn and self.conn.sock:
            self.conn.sock.shutdown(socket.SHUT_RDWR)
            self.conn.close()
