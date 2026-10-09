#!/usr/bin/env bash
set -euo pipefail

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  initdb -D "$PGDATA" -U postgres --locale=C.UTF-8 --auth=trust >/dev/null
  cat >>"$PGDATA/postgresql.conf" <<EOF
listen_addresses = '*'
port = 5432
shared_buffers = 128MB
dynamic_shared_memory_type = mmap
shared_preload_libraries = 'pg_extension_base'
pg_lake_iceberg.default_location_prefix = 's3://${LAKE_BUCKET}/iceberg/'
pg_lake_engine.host = 'host=/var/run/pgduck port=5332'
EOF
  echo "host all all 0.0.0.0/0 trust" >>"$PGDATA/pg_hba.conf"
fi

cat >/var/run/pgduck/init.sql <<EOF
CREATE OR REPLACE SECRET minio (TYPE s3, SCOPE 's3://${LAKE_BUCKET}', USE_SSL false, KEY_ID '${S3_KEY}', SECRET '${S3_SECRET}', URL_STYLE 'path', ENDPOINT '${S3_ENDPOINT}', REGION 'us-east-1');
EOF

pgduck_server --unix_socket_directory /var/run/pgduck --port 5332 --cache_dir /var/lib/pglake/cache --memory_limit "${DUCK_MEMORY:-512MB}" --init_file_path /var/run/pgduck/init.sql &
duck=$!
for _ in $(seq 1 30); do
  [ -S /var/run/pgduck/.s.PGSQL.5332 ] && break
  sleep 1
done
postgres -D "$PGDATA" &
pg=$!
trap 'kill -TERM $pg $duck 2>/dev/null; wait $pg; exit 0' TERM INT
wait -n $pg $duck
kill -TERM $pg $duck 2>/dev/null || true
exit 1
