import os
import duckdb

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "21000")
PG_DB = os.environ.get("PG_DB", "i10catalog")
PG_USER = os.environ.get("PG_USER", "i10")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "i10password")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "localhost:21001")
S3_KEY = os.environ.get("S3_KEY", "i10admin")
S3_SECRET = os.environ.get("S3_SECRET", "i10password")
BUCKET = os.environ.get("BUCKET", "i10-lake")

PG_DSN = f"dbname={PG_DB} host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD}"
ORDERS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "orders.csv")
ORDERS_CSV = f"""read_csv('{ORDERS}', header = true, columns = {{
    'order_id': 'INTEGER', 'customer': 'VARCHAR', 'product': 'VARCHAR', 'category': 'VARCHAR',
    'quantity': 'INTEGER', 'price': 'DECIMAL(10,2)', 'ts': 'TIMESTAMP'}})"""


def connect():
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    for ext in ("ducklake", "postgres", "httpfs"):
        con.install_extension(ext)
        con.load_extension(ext)
    con.execute(f"""
        CREATE SECRET s3lake (TYPE s3, KEY_ID '{S3_KEY}', SECRET '{S3_SECRET}', ENDPOINT '{S3_ENDPOINT}',
        URL_STYLE 'path', USE_SSL false, REGION 'us-east-1')
    """)
    con.execute(f"ATTACH 'ducklake:postgres:{PG_DSN}' AS lake (DATA_PATH 's3://{BUCKET}/')")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres, READ_ONLY)")
    return con


def commit(con, message, *statements):
    con.execute("BEGIN")
    con.execute("CALL lake.set_commit_message('i10', ?)", [message])
    for sql in statements:
        con.execute(sql)
    con.execute("COMMIT")


def rows(con, sql, params=None):
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
