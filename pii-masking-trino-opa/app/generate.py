import csv
import os
from datetime import date, timedelta

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FIRST = ["Ana", "Ben", "Caio", "Dora", "Emil", "Fay", "Gus", "Hana", "Ivo", "Jun"]
DOMAINS = ["mail.test", "post.test", "inbox.test"]
COUNTRIES = ["BR", "US", "DE", "PT", "JP"]
PRODUCTS = ["keyboard", "monitor", "headset", "webcam", "dock", "mouse"]
CUSTOMERS = 40
ORDERS = 120


def customer(i):
    first = FIRST[i % len(FIRST)]
    return [
        i,
        f"{first} Synthetic{i:03d}",
        f"{first.lower()}.{i:03d}@{DOMAINS[i % len(DOMAINS)]}",
        f"900-{i:02d}-{(i * 7) % 25:04d}",
        f"+00-555-{1000 + i}",
        COUNTRIES[i % len(COUNTRIES)],
        f"4000-0000-{i:04d}-{1000 + (i * 13) % 30:04d}",
        f"{(i * 13725) % 500000 / 100:.2f}",
    ]


def order(j):
    customer_id = (j * 7) % CUSTOMERS + 1
    return [
        j,
        customer_id,
        COUNTRIES[customer_id % len(COUNTRIES)],
        PRODUCTS[j % len(PRODUCTS)],
        f"{((j * 1937) % 40000 + 500) / 100:.2f}",
        (date(2026, 1, 1) + timedelta(days=j % 90)).isoformat(),
    ]


def write(name, header, rows):
    with open(os.path.join(DATA, name), "w", newline="") as f:
        out = csv.writer(f, lineterminator="\n")
        out.writerow(header)
        out.writerows(rows)


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    write("customers.csv", ["customer_id", "name", "email", "national_id", "phone", "country", "credit_card", "balance"],
          [customer(i) for i in range(1, CUSTOMERS + 1)])
    write("orders.csv", ["order_id", "customer_id", "country", "product", "amount", "order_date"],
          [order(j) for j in range(1, ORDERS + 1)])
    print(f"wrote {CUSTOMERS} customers and {ORDERS} orders")
