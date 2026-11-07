import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pathway as pw

import docindex
import pipeline
from live import LiveTable

DATA = os.environ.get("DATA_DIR", "/data")
UI_PORT = int(os.environ.get("UI_PORT", "8080"))
RETRIEVE_PORT = int(os.environ.get("RETRIEVE_PORT", "8001"))
BROKERS = os.environ.get("KAFKA_BROKERS", "t4-redpanda:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "orders")
INDEX_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


def build():
    window_table, totals_table = pipeline.build(os.path.join(DATA, "orders"), os.path.join(DATA, "regions"), BROKERS, TOPIC)
    docs = docindex.documents(os.path.join(DATA, "docs"))
    docindex.serve(docs, "0.0.0.0", RETRIEVE_PORT)
    return {
        "windows": LiveTable(window_table, ["region", "window_start", "orders", "revenue", "gross", "max_amount"]),
        "totals": LiveTable(totals_table, ["region", "name", "orders", "revenue", "gross"]),
        "docs": LiveTable(docs.select(pw.this.doc, chars=pw.this.text.str.len()), ["doc", "chars"]),
    }


def retrieve(body):
    request = urllib.request.Request(
        f"http://127.0.0.1:{RETRIEVE_PORT}/v1/retrieve",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read()


def handler(tables):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            name = self.path.split("?")[0].removeprefix("/api/")
            if self.path in ("/", "/index.html"):
                with open(INDEX_HTML, "rb") as page:
                    self.send(200, page.read(), "text/html; charset=utf-8")
            elif name in tables:
                self.send(200, json.dumps(tables[name].snapshot()).encode())
            else:
                self.send(404, b'{"error": "not found"}')

        def do_POST(self):
            if self.path != "/api/search":
                self.send(404, b'{"error": "not found"}')
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                status, answer = retrieve(body)
            except urllib.error.HTTPError as error:
                status, answer = error.code, error.read()
            except OSError as error:
                status, answer = 503, json.dumps({"error": str(error)}).encode()
            self.send(status, answer)

    return Handler


def main():
    tables = build()
    server = ThreadingHTTPServer(("0.0.0.0", UI_PORT), handler(tables))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    pw.run(monitoring_level=pw.MonitoringLevel.NONE)


if __name__ == "__main__":
    main()
