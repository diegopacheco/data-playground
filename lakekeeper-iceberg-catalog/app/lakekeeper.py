import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

LAKEKEEPER_URL = os.environ.get("LAKEKEEPER_URL", "http://localhost:26302")
MANAGEMENT = f"{LAKEKEEPER_URL}/management/v1"
WAREHOUSE = "lakehouse"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(f"{MANAGEMENT}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        raise RuntimeError(f"{method} {path} failed with {e.code}: {e.read().decode()}") from e


def info():
    return call("GET", "/info")


def bootstrap():
    if info()["bootstrapped"]:
        return False
    call("POST", "/bootstrap", {"accept-terms-of-use": True})
    return True


def warehouses():
    return call("GET", "/warehouse")["warehouses"]


def find_warehouse(name=WAREHOUSE):
    return next((w for w in warehouses() if w["name"] == name), None)


def warehouse_request(s3_endpoint, access_key, secret_key):
    return {
        "warehouse-name": WAREHOUSE,
        "storage-profile": {
            "type": "s3",
            "bucket": WAREHOUSE,
            "key-prefix": "iceberg",
            "endpoint": s3_endpoint,
            "sts-endpoint": s3_endpoint,
            "region": "us-east-1",
            "path-style-access": True,
            "flavor": "s3-compat",
            "sts-enabled": True,
        },
        "storage-credential": {
            "type": "s3",
            "credential-type": "access-key",
            "access-key-id": access_key,
            "secret-access-key": secret_key,
        },
        "delete-profile": {"type": "hard"},
    }


def ensure_warehouse(s3_endpoint, access_key, secret_key):
    existing = find_warehouse()
    if existing:
        return existing, False
    call("POST", "/warehouse", warehouse_request(s3_endpoint, access_key, secret_key))
    return find_warehouse(), True
