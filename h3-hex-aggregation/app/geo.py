import math

EARTH_KM = 6371.0088


def haversine_km(a, b):
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def inside(lat, lng, polygon):
    hit = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def rect_area_km2(south, west, north, east):
    return EARTH_KM ** 2 * math.radians(east - west) * (math.sin(math.radians(north)) - math.sin(math.radians(south)))


def spread(values):
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return {"min": min(values), "max": max(values), "mean": mean, "cv": sd / mean}
