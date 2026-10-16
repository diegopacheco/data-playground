import http.client
import threading

LOCAL = threading.local()


class HttpError(Exception):
    pass


def call(port, method, path, body=None, headers=None):
    conns = LOCAL.__dict__.setdefault("conns", {})
    if port not in conns:
        conns[port] = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    conn = conns[port]
    try:
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        data = response.read()
    except (http.client.HTTPException, OSError):
        conn.close()
        del conns[port]
        raise
    if response.status >= 300:
        raise HttpError(f"{response.status} {data.decode(errors='replace')[:1000]}")
    return data
