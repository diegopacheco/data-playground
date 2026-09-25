import os
import time
from cassandra.cluster import Cluster


def connect(attempts=30):
    host = os.environ.get("CASSANDRA_HOST", "localhost")
    port = int(os.environ.get("CASSANDRA_PORT", "9042"))
    for attempt in range(attempts):
        try:
            cluster = Cluster([host], port=port, protocol_version=5)
            return cluster, cluster.connect()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2)


def fetch_revenue(session):
    rows = session.execute("SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category")
    result = [
        {"category": r.category, "total_orders": r.total_orders, "total_quantity": r.total_quantity, "total_revenue": round(r.total_revenue, 2)}
        for r in rows
    ]
    return sorted(result, key=lambda r: r["total_revenue"], reverse=True)
