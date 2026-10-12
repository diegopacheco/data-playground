import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

OM_URL = os.environ.get("OM_URL", "http://r14-openmetadata:8585")
ADMIN_EMAIL = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
ADMIN_PASSWORD = os.environ.get("OM_ADMIN_PASSWORD", "admin")


class OpenMetadataError(Exception):
    pass


class OpenMetadata:
    def __init__(self, url=OM_URL):
        self.url = url.rstrip("/")
        self.token = None
        self.token_at = 0

    def raw(self, method, path, body=None, content_type="application/json", auth=True):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": content_type, "Accept": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + self.access_token()
        request = urllib.request.Request(self.url + "/api/v1" + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            raise OpenMetadataError(f"{method} {path} -> {e.code} {e.read().decode()[:400]}") from None

    def access_token(self):
        if self.token is None or time.time() - self.token_at > 1800:
            password = base64.b64encode(ADMIN_PASSWORD.encode()).decode()
            self.token = self.raw("POST", "/users/login", {"email": ADMIN_EMAIL, "password": password}, auth=False)["accessToken"]
            self.token_at = time.time()
        return self.token

    def get(self, path, **params):
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return self.raw("GET", path + ("?" + query if query else ""))

    def put(self, path, body):
        return self.raw("PUT", path, body)

    def post(self, path, body):
        return self.raw("POST", path, body)

    def patch(self, path, operations):
        return self.raw("PATCH", path, operations, "application/json-patch+json")

    def find(self, path):
        try:
            return self.get(path)
        except OpenMetadataError as e:
            if " 404 " in str(e):
                return None
            raise

    def version(self):
        return self.get("/system/version")

    def bot_token(self, bot="ingestion-bot"):
        user = self.get(f"/bots/name/{bot}")["botUser"]
        return self.get(f"/users/auth-mechanism/{user['id']}")["config"]["JWTToken"]

    def table(self, fqn, fields="columns,tags,owners,tableConstraints"):
        return self.get("/tables/name/" + urllib.parse.quote(fqn, safe=""), fields=fields)

    def tables(self, database_fqn, fields="columns,tags,owners"):
        rows, after = [], None
        while True:
            page = self.get("/tables", database=database_fqn, fields=fields, limit=100, after=after)
            rows += page["data"]
            after = page.get("paging", {}).get("after")
            if not after:
                return rows

    def lineage(self, fqn, depth=1):
        return self.get("/lineage/table/name/" + urllib.parse.quote(fqn, safe=""), upstreamDepth=depth, downstreamDepth=depth)

    def search(self, q, index="table_search_index", size=25):
        return self.get("/search/query", q=q, index=index, size=size, **{"from": 0})
