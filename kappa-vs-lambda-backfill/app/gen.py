import random

STORES = ["braga", "faro", "lisbon", "porto"]
DAYS = ["2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]
PHASES = {
    1: {"on_time": DAYS[:4], "per_day": 900, "late": {}, "resend_old": 0},
    2: {"on_time": [DAYS[4]], "per_day": 600, "late": {DAYS[0]: 60, DAYS[1]: 40}, "resend_old": 25},
    3: {"on_time": [DAYS[4]], "per_day": 300, "late": {DAYS[2]: 30}, "resend_old": 10},
    4: {"on_time": [DAYS[4]], "per_day": 150, "late": {DAYS[0]: 15, DAYS[3]: 10}, "resend_old": 10},
}
DUPLICATE_RATE = 0.03


def event(rng, tag, day, seq):
    ts = f"{day}T{rng.randrange(24):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}Z"
    return {
        "event_id": f"{tag}-{day}-{seq:04d}",
        "ts": ts,
        "store": rng.choice(STORES),
        "kind": "refund" if rng.random() < 0.15 else "sale",
        "amount_cents": rng.randrange(500, 25000),
    }


def with_resends(rng, fresh):
    out = []
    for e in fresh:
        out.append(e)
        if rng.random() < DUPLICATE_RATE:
            out.append(dict(e))
    return out


def phase_events(phase):
    rng = random.Random(20260926 + phase)
    cfg = PHASES[phase]
    fresh = []
    for day in cfg["on_time"]:
        fresh += sorted((event(rng, f"p{phase}", day, i) for i in range(cfg["per_day"])), key=lambda e: e["ts"])
    for day, n in cfg["late"].items():
        fresh += [event(rng, f"late{phase}", day, i) for i in range(n)]
    out = with_resends(rng, fresh)
    history = [e for p in range(1, phase) for e in phase_events(p)]
    out += [dict(rng.choice(history)) for _ in range(cfg["resend_old"])]
    return out


def live_events(kind, count, tag):
    rng = random.Random()
    day = DAYS[0] if kind == "late" else DAYS[-1]
    return with_resends(rng, [event(rng, tag, day, i) for i in range(count)])
