import json
import os
import urllib.request

DRUID_URL = os.environ.get("DRUID_URL", "http://localhost:23200")


def sql(query):
    body = json.dumps({"query": query}).encode()
    request = urllib.request.Request(
        f"{DRUID_URL}/druid/v2/sql",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)
