import hashlib
from collections.abc import Iterator
from dataclasses import dataclass

MASK = (1 << 64) - 1
REGIONS = ("AMER", "APAC", "EMEA", "LATAM")
MAX_AMOUNT_CENTS = 100_000


@dataclass(frozen=True)
class Sale:
    row_id: int
    region: str
    amount_cents: int


@dataclass(frozen=True)
class Summary:
    rows: int
    totals: dict[str, int]
    digest: str


def splitmix64(x: int) -> int:
    z = (x + 0x9E3779B97F4A7C15) & MASK
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)


def generate(rows: int, seed: int) -> Iterator[Sale]:
    for i in range(rows):
        z = splitmix64((seed + i) & MASK)
        yield Sale(i, REGIONS[z % len(REGIONS)], (z >> 8) % MAX_AMOUNT_CENTS)


def line(sale: Sale) -> bytes:
    return f"{sale.row_id},{sale.region},{sale.amount_cents}".encode()


def summarize(rows: int, seed: int, rounds: int) -> Summary:
    totals = dict.fromkeys(REGIONS, 0)
    state = bytes(32)
    for sale in generate(rows, seed):
        totals[sale.region] += sale.amount_cents
        state = hashlib.sha256(state + line(sale)).digest()
        for _ in range(rounds - 1):
            state = hashlib.sha256(state).digest()
    return Summary(rows, totals, state.hex())
