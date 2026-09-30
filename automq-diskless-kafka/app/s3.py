import datetime
import hashlib
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ENDPOINT = os.environ.get("S3_ENDPOINT", "http://r9-minio:9000")
ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "r9admin")
SECRET_KEY = os.environ.get("S3_SECRET_KEY", "r9password")
REGION = "us-east-1"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def request(method, bucket, query=None):
    url = urllib.parse.urlsplit(ENDPOINT)
    path = f"/{bucket}"
    canonical_query = "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted((query or {}).items()))
    now = datetime.datetime.now(datetime.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()
    headers = {"host": url.netloc, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    signed = ";".join(sorted(headers))
    canonical = "\n".join([method, path, canonical_query, "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed, payload_hash])
    scope = f"{day}/{REGION}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = sign(sign(sign(sign(f"AWS4{SECRET_KEY}".encode(), day), REGION), "s3"), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY}/{scope}, SignedHeaders={signed}, Signature={signature}"
    full = f"{ENDPOINT}{path}" + (f"?{canonical_query}" if canonical_query else "")
    with urllib.request.urlopen(urllib.request.Request(full, method=method, headers=headers), timeout=10) as response:
        return response.read()


def make_bucket(bucket):
    try:
        request("PUT", bucket)
    except urllib.error.HTTPError as error:
        if error.code != 409:
            raise


def list_objects(bucket):
    objects, token = [], None
    while True:
        query = {"list-type": "2", "max-keys": "1000"}
        if token:
            query["continuation-token"] = token
        root = ET.fromstring(request("GET", bucket, query))
        for item in root.findall(f"{NS}Contents"):
            objects.append({"key": item.find(f"{NS}Key").text, "size": int(item.find(f"{NS}Size").text), "modified": item.find(f"{NS}LastModified").text})
        if root.findtext(f"{NS}IsTruncated") != "true":
            return objects
        token = root.findtext(f"{NS}NextContinuationToken")


def kind(key):
    parts = key.split("/")
    if "/wal/" in key:
        return "WAL object"
    if parts[0] == "automq" and len(parts) > 1:
        return f"ops {parts[1]}"
    if parts[0] == "reservation":
        return "node reservation"
    return "stream data object"


def summary(bucket):
    objects = list_objects(bucket)
    kinds = {}
    for item in objects:
        item["kind"] = kind(item["key"])
        entry = kinds.setdefault(item["kind"], {"kind": item["kind"], "objects": 0, "bytes": 0})
        entry["objects"] += 1
        entry["bytes"] += item["size"]
    recent = sorted(objects, key=lambda o: o["modified"], reverse=True)[:20]
    return {"bucket": bucket, "objects": len(objects), "bytes": sum(o["size"] for o in objects), "kinds": sorted(kinds.values(), key=lambda k: -k["bytes"]), "recent": recent}


def written_since(bucket, since):
    fresh = [o for o in list_objects(bucket) if o["modified"] >= since]
    return {"objects": len(fresh), "bytes": sum(o["size"] for o in fresh), "wal_objects": sum(1 for o in fresh if kind(o["key"]) == "WAL object")}
