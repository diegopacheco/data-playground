import os
from pathlib import Path

from flight_client import OrdersClient

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ORDERS_CSV = DATA / "orders.csv"
NEW_ORDERS_CSV = DATA / "new_orders.csv"
FLIGHT_PORT = int(os.environ.get("FLIGHT_PORT", "21300"))
HTTP_PORT = int(os.environ.get("HTTP_PORT", "21301"))
UI_PORT = int(os.environ.get("UI_PORT", "21302"))
FLIGHT_URL = f"grpc://localhost:{FLIGHT_PORT}"
CSV_URL = f"http://localhost:{HTTP_PORT}/bench.csv"


def client():
    return OrdersClient(FLIGHT_URL, CSV_URL)
