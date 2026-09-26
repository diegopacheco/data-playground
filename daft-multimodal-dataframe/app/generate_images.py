import csv
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DATA = Path(os.environ.get("DATA_DIR", "/app/data"))

PALETTE = {
    ("red", "light"): (220, 38, 38),
    ("red", "dark"): (127, 29, 29),
    ("orange", "light"): (249, 115, 22),
    ("orange", "dark"): (160, 65, 15),
    ("yellow", "light"): (250, 204, 21),
    ("yellow", "dark"): (133, 100, 4),
    ("green", "light"): (34, 197, 94),
    ("green", "dark"): (20, 83, 45),
    ("blue", "light"): (59, 130, 246),
    ("blue", "dark"): (30, 58, 138),
    ("purple", "light"): (168, 85, 247),
    ("purple", "dark"): (88, 28, 135),
    ("pink", "light"): (236, 72, 153),
    ("white", "light"): (245, 245, 245),
    ("gray", "dark"): (120, 120, 120),
    ("black", "dark"): (24, 24, 27),
}


def mix(color, target, amount):
    return tuple(round(c + (t - c) * amount) for c, t in zip(color, target))


def shape(draw, category, box, fill):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if category == "kitchen":
        draw.ellipse(box, fill=fill)
    elif category == "outdoor":
        draw.polygon([(cx, y0), (x1, y1), (x0, y1)], fill=fill)
    elif category == "books":
        draw.rectangle((cx - (x1 - x0) / 4, y0, cx + (x1 - x0) / 4, y1), fill=fill)
    elif category == "apparel":
        w, h = x1 - x0, y1 - y0
        draw.polygon([(x0, y0), (x1, y0), (x1, y0 + h / 3), (cx + w / 4, y0 + h / 3), (cx + w / 4, y1),
                      (cx - w / 4, y1), (cx - w / 4, y0 + h / 3), (x0, y0 + h / 3)], fill=fill)
    elif category == "home":
        draw.polygon([(cx, y0), (x1, cy), (x1, y1), (x0, y1), (x0, cy)], fill=fill)
    elif category == "fitness":
        draw.polygon([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], fill=fill)
    else:
        draw.rounded_rectangle(box, radius=18, fill=fill)


def card(row):
    pid = int(row["id"])
    width = 320 + (pid * 37 % 5) * 64
    height = 240 + (pid * 53 % 4) * 60
    color = PALETTE[(row["color"], row["tone"])]
    ink = (20, 20, 20) if row["tone"] == "light" else (240, 240, 240)
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    side = min(width, height) * 0.45
    box = (width / 2 - side / 2, height * 0.12, width / 2 + side / 2, height * 0.12 + side)
    shape(draw, row["category"], box, mix(color, ink, 0.35))
    font = ImageFont.load_default(size=max(14, width // 22))
    draw.text((width / 2, height * 0.86), row["name"], fill=ink, font=font, anchor="mm")
    return image


def main():
    rows = list(csv.DictReader((DATA / "products.csv").open(newline="")))
    for row in rows:
        path = DATA / row["image_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        card(row).save(path, format="PNG", optimize=True)
    print(f"generated {len(rows)} images in {DATA / 'images'}", flush=True)


if __name__ == "__main__":
    main()
