#!/usr/bin/env bash
set -euo pipefail

POLARIS_URL="${POLARIS_URL:-http://localhost:20902}"
ROOT_CREDENTIAL="${ROOT_CREDENTIAL:-root:i9s3cr3t}"
CREDENTIAL_FILE="${CREDENTIAL_FILE:-.run/polaris.env}"
CATALOG="i9_catalog"
PRINCIPAL="i9_engine"
PRINCIPAL_ROLE="i9_engine_role"
CATALOG_ROLE="i9_catalog_rw"
S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:20900}"
MGMT="$POLARIS_URL/api/management/v1"
RESPONSE="$(dirname "$CREDENTIAL_FILE")/polaris-response.json"
mkdir -p "$(dirname "$CREDENTIAL_FILE")"

json_field() {
  python3 -c 'import json,sys
d=json.load(sys.stdin)
for k in sys.argv[1:]: d=d[k]
print(d)' "$@"
}

token() {
  curl -sf "$POLARIS_URL/api/catalog/v1/oauth/tokens" --user "$1" -H "Polaris-Realm: POLARIS" \
    -d grant_type=client_credentials -d scope=PRINCIPAL_ROLE:ALL | json_field access_token
}

ROOT_TOKEN="$(token "$ROOT_CREDENTIAL")"

call() {
  local method path body code
  method="$1"
  path="$2"
  body="${3:-}"
  code="$(curl -s -o "$RESPONSE" -w '%{http_code}' -X "$method" "$MGMT$path" \
    -H "Authorization: Bearer $ROOT_TOKEN" -H "Content-Type: application/json" ${body:+-d "$body"})"
  case "$code" in
    2*|409) printf "%-6s %-70s %s\n" "$method" "$path" "$code" ;;
    *) printf "ERROR %s %s returned %s: %s\n" "$method" "$path" "$code" "$(cat "$RESPONSE")" >&2; exit 1 ;;
  esac
}

call POST /catalogs "{\"catalog\":{\"name\":\"$CATALOG\",\"type\":\"INTERNAL\",
  \"properties\":{\"default-base-location\":\"s3://i9-warehouse\",\"polaris.config.drop-with-purge.enabled\":\"true\"},
  \"storageConfigInfo\":{\"storageType\":\"S3\",\"allowedLocations\":[\"s3://i9-warehouse\"],
  \"endpoint\":\"$S3_ENDPOINT\",\"endpointInternal\":\"http://i9-minio:9000\",
  \"pathStyleAccess\":true,\"stsUnavailable\":true,\"region\":\"us-east-1\"}}}"

call POST /principal-roles "{\"principalRole\":{\"name\":\"$PRINCIPAL_ROLE\"}}"
call POST "/catalogs/$CATALOG/catalog-roles" "{\"catalogRole\":{\"name\":\"$CATALOG_ROLE\"}}"
call PUT "/catalogs/$CATALOG/catalog-roles/$CATALOG_ROLE/grants" '{"grant":{"type":"catalog","privilege":"CATALOG_MANAGE_CONTENT"}}'
call PUT "/principal-roles/$PRINCIPAL_ROLE/catalog-roles/$CATALOG" "{\"catalogRole\":{\"name\":\"$CATALOG_ROLE\"}}"

if [ -f "$CREDENTIAL_FILE" ] && token "$(sed -n 's/^POLARIS_CREDENTIAL=//p' "$CREDENTIAL_FILE")" >/dev/null 2>&1; then
  printf "principal %s already has working credentials in %s\n" "$PRINCIPAL" "$CREDENTIAL_FILE"
else
  curl -s -o /dev/null -X DELETE "$MGMT/principals/$PRINCIPAL" -H "Authorization: Bearer $ROOT_TOKEN"
  created="$(curl -sf -X POST "$MGMT/principals" -H "Authorization: Bearer $ROOT_TOKEN" \
    -H "Content-Type: application/json" -d "{\"principal\":{\"name\":\"$PRINCIPAL\"}}")"
  client_id="$(printf "%s" "$created" | json_field credentials clientId)"
  client_secret="$(printf "%s" "$created" | json_field credentials clientSecret)"
  mkdir -p "$(dirname "$CREDENTIAL_FILE")"
  printf "POLARIS_CREDENTIAL=%s:%s\n" "$client_id" "$client_secret" >"$CREDENTIAL_FILE"
  printf "principal %s created with client id %s\n" "$PRINCIPAL" "$client_id"
fi

call PUT "/principals/$PRINCIPAL/principal-roles" "{\"principalRole\":{\"name\":\"$PRINCIPAL_ROLE\"}}"
