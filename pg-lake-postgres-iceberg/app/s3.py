import datetime
import hashlib
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ENDPOINT = os.environ.get("S3_URL", "http://localhost:27601")
KEY = os.environ.get("S3_KEY", "r11admin")
SECRET = os.environ.get("S3_SECRET", "r11password")
REGION = "us-east-1"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def _sign(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def request(method, path, query=None, body=b""):
    url = urllib.parse.urlsplit(ENDPOINT)
    now = datetime.datetime.now(datetime.UTC)
    stamp, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    canonical_path = urllib.parse.quote(path, safe="/-_.~")
    canonical_query = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(str(v), safe='-_.~')}" for k, v in sorted((query or {}).items()))
    payload = hashlib.sha256(body).hexdigest()
    headers = {"host": url.netloc, "x-amz-content-sha256": payload, "x-amz-date": stamp}
    signed = ";".join(sorted(headers))
    canonical = "\n".join([method, canonical_path, canonical_query, "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed, payload])
    scope = f"{day}/{REGION}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _sign(_sign(_sign(_sign(("AWS4" + SECRET).encode(), day), REGION), "s3"), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = f"AWS4-HMAC-SHA256 Credential={KEY}/{scope}, SignedHeaders={signed}, Signature={signature}"
    target = f"{ENDPOINT}{canonical_path}" + (f"?{canonical_query}" if canonical_query else "")
    req = urllib.request.Request(target, data=body or None, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def ensure_bucket(bucket):
    try:
        request("HEAD", f"/{bucket}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        request("PUT", f"/{bucket}")


def list_objects(bucket, prefix=""):
    out, token = [], None
    while True:
        query = {"list-type": "2", "prefix": prefix}
        if token:
            query["continuation-token"] = token
        root = ET.fromstring(request("GET", f"/{bucket}", query))
        for item in root.findall(f"{NS}Contents"):
            out.append({"key": item.find(f"{NS}Key").text, "size": int(item.find(f"{NS}Size").text)})
        token = root.findtext(f"{NS}NextContinuationToken")
        if root.findtext(f"{NS}IsTruncated") != "true":
            return out


def get_object(bucket, key):
    return request("GET", f"/{bucket}/{key}")


def delete_prefix(bucket, prefix):
    objects = list_objects(bucket, prefix)
    for o in objects:
        request("DELETE", f"/{bucket}/{o['key']}")
    return len(objects)
