from collections.abc import Sequence

from ray_e2e import config


def reset() -> None:
    config.RESULTS.parent.mkdir(parents=True, exist_ok=True)
    config.RESULTS.write_text("")


def table(title: str, header: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    lines = [f"### {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    with config.RESULTS.open("a") as out:
        out.write("\n".join(lines) + "\n\n")


def seconds(ms: int | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f}"


def percentile(values: Sequence[int], p: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]
