import csv
import os
import random
from datetime import date, timedelta
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))

NAMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabi", "Hugo", "Iris", "Joao", "Kira", "Leo",
         "Maya", "Nico", "Olga", "Pedro", "Quinn", "Rosa", "Sam", "Tania", "Ugo", "Vera", "Walt", "Xena",
         "Yuri", "Zoe", "Alba", "Beto", "Cris", "Dora", "Enzo", "Fabi", "Gil", "Helo", "Ivo", "Jade"]
CITIES = ["Porto Alegre", "Sao Paulo", "Lisbon", "Austin", "Berlin", "Toronto"]
CATALOG = {
    "books": ["Graph Theory", "Designing Data Apps", "SQL Deep Dive", "Cypher Handbook"],
    "coffee": ["Espresso Beans", "French Press", "Pour Over Kit", "Milk Frother"],
    "games": ["Chess Set", "Go Board", "Puzzle Cube", "Card Deck"],
    "audio": ["Headphones", "Speaker", "Microphone", "Audio Cable"],
    "outdoor": ["Tent", "Backpack", "Water Bottle", "Headlamp"],
    "office": ["Desk Lamp", "Notebook", "Standing Mat", "Monitor Arm"],
}


def build(seed=2026):
    rnd = random.Random(seed)
    customers = [(i + 1, name, rnd.choice(CITIES)) for i, name in enumerate(NAMES)]
    products, pid = [], 0
    for category, names in CATALOG.items():
        for name in names:
            pid += 1
            products.append((pid, name, category, rnd.randrange(900, 25000, 100)))
    ids = [c[0] for c in customers]
    follows = set()
    for cid in ids:
        for other in rnd.sample([i for i in ids if i != cid], rnd.randint(1, 3)):
            follows.add((cid, other))
    categories = list(CATALOG)
    orders, oid, start = [], 0, date(2026, 1, 1)
    for cid in ids:
        liked = rnd.sample(categories, 2)
        for _ in range(rnd.randint(3, 7)):
            category = liked[0] if rnd.random() < 0.55 else liked[1] if rnd.random() < 0.7 else rnd.choice(categories)
            product = rnd.choice([p for p in products if p[2] == category])
            oid += 1
            orders.append((oid, cid, product[0], rnd.randint(1, 3), product[3], start + timedelta(days=rnd.randint(0, 240))))
    return customers, products, sorted(follows), orders


def write(name, header, rows):
    with open(DATA / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    customers, products, follows, orders = build()
    write("customers.csv", ["customer_id", "name", "city"], customers)
    write("products.csv", ["product_id", "name", "category", "price_cents"], products)
    write("follows.csv", ["follower_id", "followed_id"], follows)
    write("orders.csv", ["order_id", "customer_id", "product_id", "quantity", "price_cents", "order_date"], orders)
    print(f"customers={len(customers)} products={len(products)} follows={len(follows)} orders={len(orders)}")
