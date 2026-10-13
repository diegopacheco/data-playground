SEED = 42
PRIME = 67108859
HISTORIC_ROWS = 1_000_000
BATCH_ROWS = 1_000_000
LIVE_BATCHES = 12
TOTAL_ROWS = HISTORIC_ROWS + BATCH_ROWS * LIVE_BATCHES
START = "2026-01-01"
SPAN_SECONDS = 30 * 86400
COUNTRIES = ["BR", "US", "DE", "IN", "JP", "FR", "MX", "CA"]
DEVICES = ["mobile", "desktop", "tablet", "tv"]
EVENT_TYPES = ["view", "click", "cart", "purchase", "refund"]


def select(first, rows):
    return f"""
        WITH number AS n,
             ((n + 1) * 48271 + {SEED}) % {PRIME} AS x,
             (x * x + n) % {PRIME} AS h1,
             (h1 * 40503 + x) % {PRIME} AS h2
        SELECT n AS event_id,
               toDateTime('{START} 00:00:00', 'UTC') + intDiv(n * {SPAN_SECONDS}, {TOTAL_ROWS}) AS ts,
               intDiv(h2, 1000) % 50000 AS user_id,
               {COUNTRIES}[h1 % {len(COUNTRIES)} + 1] AS country,
               {DEVICES}[intDiv(h1, 8) % {len(DEVICES)} + 1] AS device,
               {EVENT_TYPES}[intDiv(h1, 32) % {len(EVENT_TYPES)} + 1] AS event_type,
               h2 % 19997 + 1 AS amount
        FROM numbers({first}, {rows})
    """


def dataset():
    return {
        "seed": SEED,
        "prime": PRIME,
        "historic_rows": HISTORIC_ROWS,
        "batch_rows": BATCH_ROWS,
        "live_batches": LIVE_BATCHES,
        "total_rows": TOTAL_ROWS,
        "start": START,
        "span_seconds": SPAN_SECONDS,
        "countries": COUNTRIES,
        "devices": DEVICES,
        "event_types": EVENT_TYPES,
    }
