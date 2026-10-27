import json
import urllib.request
import duckdb
from config import MINIO, REST


def connect():
    con = duckdb.connect()
    for ext in ("iceberg", "httpfs"):
        con.load_extension(ext)
    con.execute("SET TimeZone = 'UTC'")
    con.execute(f"CREATE SECRET (TYPE s3, KEY_ID 's1admin', SECRET 's1password', ENDPOINT '{MINIO}', URL_STYLE 'path', USE_SSL false, REGION 'us-east-1')")
    con.execute(f"ATTACH '' AS lake (TYPE iceberg, ENDPOINT '{REST}', AUTHORIZATION_TYPE 'none')")
    return con


def rows(cur, sql):
    cur.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def http(url, body=None, kind="application/json"):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": kind})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)
