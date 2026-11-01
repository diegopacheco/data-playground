import random

SEED = 42
POINTS_PER_CITY = 4000
RESOLUTIONS = [6, 7, 8, 9]
GRID_STEP = 0.008

CITIES = {
    "sf": {
        "name": "San Francisco",
        "box": (37.70, -122.52, 37.82, -122.36),
        "hotspots": [
            (37.7880, -122.4075, 0.006, 0.30),
            (37.7785, -122.3950, 0.005, 0.20),
            (37.7599, -122.4148, 0.006, 0.20),
            (37.8037, -122.4368, 0.005, 0.15),
        ],
        "region": [(37.7950, -122.4200), (37.7950, -122.3930), (37.7760, -122.3880), (37.7700, -122.4050), (37.7800, -122.4250)],
    },
    "nyc": {
        "name": "New York",
        "box": (40.68, -74.04, 40.80, -73.92),
        "hotspots": [
            (40.7549, -73.9840, 0.007, 0.35),
            (40.7075, -74.0113, 0.005, 0.20),
            (40.7081, -73.9571, 0.006, 0.15),
            (40.7736, -73.9566, 0.006, 0.15),
        ],
        "region": [(40.7680, -73.9930), (40.7640, -73.9730), (40.7460, -73.9720), (40.7400, -73.9900), (40.7520, -74.0060)],
    },
    "london": {
        "name": "London",
        "box": (51.48, -0.20, 51.56, -0.02),
        "hotspots": [
            (51.5136, -0.1365, 0.005, 0.25),
            (51.5155, -0.0922, 0.005, 0.20),
            (51.5246, -0.0786, 0.004, 0.15),
            (51.5308, -0.1238, 0.004, 0.15),
            (51.5055, -0.1160, 0.004, 0.10),
        ],
        "region": [(51.5230, -0.1450), (51.5250, -0.1150), (51.5100, -0.1050), (51.5020, -0.1250), (51.5080, -0.1480)],
    },
}


def city_points(rng, key, city):
    s, w, n, e = city["box"]
    hotspots = city["hotspots"]
    weights = [h[3] for h in hotspots]
    background = 1 - sum(weights)
    points = []
    while len(points) < POINTS_PER_CITY:
        if rng.random() < background:
            lat, lng = rng.uniform(s, n), rng.uniform(w, e)
        else:
            hlat, hlng, sd, _ = rng.choices(hotspots, weights)[0]
            lat, lng = rng.gauss(hlat, sd), rng.gauss(hlng, sd * 1.3)
        if not (s <= lat <= n and w <= lng <= e):
            continue
        points.append({
            "id": f"{key}-{len(points) + 1}",
            "city": key,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "fare_cents": 300 + int(rng.expovariate(1 / 1400)),
            "wait_s": 30 + int(rng.expovariate(1 / 240)),
        })
    return points


def generate():
    rng = random.Random(SEED)
    return [p for key, city in CITIES.items() for p in city_points(rng, key, city)]


POINTS = generate()
