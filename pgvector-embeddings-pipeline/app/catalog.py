import csv
from pathlib import Path

ORDERS = Path(__file__).resolve().parent.parent / "data" / "orders.csv"

FEATURES = {
    "4K Monitor": "a 27 inch ultra high definition display with sharp colors for coding, design and movies",
    "Bluetooth Speaker": "a portable wireless speaker with deep bass and a twelve hour battery for music anywhere",
    "Board Game": "a strategy game night classic for families and friends around the table",
    "Building Blocks Set": "interlocking plastic bricks that let kids build castles, cars and spaceships",
    "Cast Iron Skillet": "a heavy pan that sears steak, bakes cornbread and lasts for generations in the kitchen",
    "Chef Knife": "a razor sharp eight inch blade forged from steel for slicing, dicing and chopping vegetables",
    "Clean Architecture": "a software engineering book by Robert Martin about boundaries, dependencies and design principles",
    "Coffee Maker": "a drip brewer that prepares twelve cups of hot coffee for busy mornings",
    "Cotton T-Shirt": "a soft breathable crew neck top made from organic cotton for everyday wear",
    "Cycling Helmet": "a lightweight ventilated helmet that protects your head on road and mountain bike rides",
    "Denim Jeans": "classic blue pants with a slim fit and durable stitching",
    "Designing Data-Intensive Applications": "a book by Martin Kleppmann on databases, replication, streaming and distributed systems",
    "Desk Lamp": "an adjustable LED light with warm and cool tones for reading and working at night",
    "Dumbbell Set": "adjustable free weights for strength training and muscle building at the home gym",
    "Dune": "a science fiction novel by Frank Herbert about a desert planet, spice and political intrigue",
    "Mechanical Keyboard": "a tactile clicky keyboard with hot swappable switches for typing and gaming",
    "Plush Bear": "a cuddly soft stuffed teddy bear that toddlers love to hug at bedtime",
    "Puzzle 1000 Pieces": "a jigsaw puzzle with a thousand pieces showing a mountain landscape",
    "Rain Boots": "waterproof rubber footwear that keeps feet dry in puddles and storms",
    "Remote Control Car": "a fast radio controlled racing truck with rechargeable batteries for kids",
    "Running Jacket": "a light windproof and reflective jacket for jogging, marathon training and running in cold weather",
    "Sapiens": "a nonfiction history book by Yuval Noah Harari about how humans conquered the world",
    "Smartwatch": "a wrist wearable that tracks heart rate, sleep, steps and notifications",
    "Soccer Ball": "a match size football for kicking, passing and scoring goals on the field",
    "Tennis Racket": "a graphite racquet with a large sweet spot for serves, volleys and baseline rallies",
    "The Pragmatic Programmer": "a classic book for software developers about craftsmanship, testing and career growth",
    "Throw Pillow": "a decorative cushion that adds color and comfort to the sofa or bed",
    "USB-C Charger": "a fast wall adapter that powers laptops, tablets and phones through a single cable",
    "Wireless Headphones": "over ear noise cancelling headphones with bluetooth for music, calls and travel",
    "Wool Sweater": "a warm knitted pullover made from merino wool for chilly winter days",
    "Yoga Mat": "a non slip cushioned mat for yoga, pilates, stretching and meditation",
}

CATEGORY_TEXT = {
    "books": "It is a great read to learn something new and enjoy quiet time with pages worth reading.",
    "clothing": "It is apparel you can wear every day and combine with the rest of your wardrobe.",
    "electronics": "It is a gadget that connects to your devices and makes digital life easier.",
    "home": "It belongs in the house and makes cooking, living and relaxing at home better.",
    "sports": "It is gear for fitness, exercise and staying active outdoors or at the gym.",
    "toys": "It is a toy that keeps children entertained, creative and playing for hours.",
}

COLORS = ["black", "white", "red", "blue", "green", "gray", "navy", "orange", "purple", "yellow"]
BRANDS = ["Acme", "Nimbus", "Vertex", "Orbit", "Summit", "Lumen", "Harbor", "Pioneer", "Atlas", "Zephyr"]
EDITIONS = ["basic", "plus", "pro", "max", "mini", "limited"]


def load_products():
    stats = {}
    with ORDERS.open() as f:
        for row in csv.DictReader(f):
            s = stats.setdefault(row["product"], {"category": row["category"], "orders": 0, "revenue": 0.0})
            s["orders"] += 1
            s["revenue"] += int(row["quantity"]) * float(row["price"])
    products = []
    for pid, name in enumerate(sorted(stats), start=1):
        s = stats[name]
        description = f"{name} is {FEATURES[name]}. {CATEGORY_TEXT[s['category']]}"
        products.append({
            "id": pid,
            "name": name,
            "category": s["category"],
            "description": description,
            "orders": s["orders"],
            "revenue": round(s["revenue"], 2),
        })
    return products


def document(product):
    return f"{product['name']}. Category: {product['category']}. {product['description']}"


def variants(products):
    rows = []
    for p in products:
        for color in COLORS:
            for brand in BRANDS:
                for edition in EDITIONS:
                    rows.append((len(rows) + 1, p["id"], f"{brand} {p['name']} {edition} edition in {color} for {p['category']}"))
    return rows
