import json
import os
from urllib.request import Request, urlopen

PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:8082")
RESULT_TOPIC = os.environ.get("RESULT_TOPIC", "revenue_by_category")
ACCEPT = "application/vnd.kafka.json.v2+json"


def fetch_records(offset):
    url = f"{PROXY_URL}/topics/{RESULT_TOPIC}/partitions/0/records?offset={offset}&timeout=500&max_bytes=1048576"
    with urlopen(Request(url, headers={"Accept": ACCEPT}), timeout=10) as response:
        return json.load(response)


def read_changelog():
    events, offset = [], 0
    while True:
        batch = fetch_records(offset)
        if not batch:
            return events
        events.extend(r["value"] for r in batch)
        offset = batch[-1]["offset"] + 1


def apply_changelog(events):
    state = {}
    for event in events:
        if event["op"] == "d":
            state.pop(event["before"]["category"], None)
        else:
            state[event["after"]["category"]] = event["after"]
    return sorted(state.values(), key=lambda r: r["total_revenue"], reverse=True)


def revenue():
    events = read_changelog()
    return {"changelog_events": len(events), "categories": apply_changelog(events)}
