import json
import urllib.parse
import urllib.request
from typing import Any


def call(method: str, url: str, params: dict[str, str] | None = None) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read()
    return json.loads(body) if body else None


def get(url: str, params: dict[str, str] | None = None) -> Any:
    return call("GET", url, params)
