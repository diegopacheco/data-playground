import shutil
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
RESULTS = ROOT / "results"

NON_BREAKING = "add projection customer_key to stg_orders"
BREAKING = "add filter WHERE price >= 0 to stg_orders"


def fresh(project):
    target = WORK / project
    if target.exists():
        shutil.rmtree(target)
    WORK.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    shutil.copytree(ROOT / project, target)
    data = WORK / "data"
    if data.exists():
        shutil.rmtree(data)
    shutil.copytree(ROOT / "data", data)
    return target


def stg_file(project_dir):
    return project_dir / "models" / "stg_orders.sql"


def apply_non_breaking(project_dir):
    path = stg_file(project_dir)
    sql = path.read_text()
    path.write_text(sql.replace("\nFROM ", ",\n  upper(trim(customer)) AS customer_key\nFROM ", 1))


def apply_breaking(project_dir):
    path = stg_file(project_dir)
    path.write_text(path.read_text().rstrip() + "\nWHERE price >= 0\n")


def revert_breaking(project_dir):
    path = stg_file(project_dir)
    path.write_text(path.read_text().replace("\nWHERE price >= 0\n", "\n"))


def timed(fn):
    start = time.perf_counter()
    value = fn()
    return value, round(time.perf_counter() - start, 3)


def plain(value):
    if isinstance(value, Decimal):
        return round(float(value), 2)
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return value


def records(rows, columns):
    return [{c: plain(v) for c, v in zip(columns, row)} for row in rows]


RESULT_QUERIES = {
    "revenue_by_category": "SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category ORDER BY category",
    "daily_revenue": "SELECT order_date, total_orders, revenue FROM sales.daily_revenue ORDER BY order_date",
}


def read_results(con):
    out = {}
    for name, sql in RESULT_QUERIES.items():
        cur = con.execute(sql)
        out[name] = records(cur.fetchall(), [d[0] for d in cur.description])
    return out
