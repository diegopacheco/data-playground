import json
import os
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ["CLICKHOUSE_URL"]
DEFAULTS = {
    "wait_end_of_query": 1,
    "output_format_json_quote_64bit_integers": 0,
}


def run(sql, **settings):
    params = urllib.parse.urlencode({**DEFAULTS, **settings})
    request = urllib.request.Request(f"{URL}/?{params}", data=sql.encode())
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            summary = json.loads(response.headers.get("X-ClickHouse-Summary", "{}"))
            return response.read().decode(), {k: int(v) for k, v in summary.items()}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{error.read().decode().strip()}\n{sql.strip()}") from None


def command(sql, **settings):
    return run(sql, **settings)[1]


def rows(sql, **settings):
    body, summary = run(sql + " FORMAT JSON", **settings)
    return json.loads(body)["data"], summary


def text(sql, **settings):
    return run(sql, **settings)[0].rstrip("\n")
