import json
from dataclasses import asdict

from kueue_e2e import config
from kueue_e2e.watch import Tracker


def fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def job_rows(tracker: Tracker) -> list[str]:
    rows = []
    for name, job in tracker.jobs.items():
        submitted = tracker.first(name, "submitted") or 0.0
        admitted = tracker.times(name, "admitted")
        wait = admitted[0] - submitted if admitted else None
        evicted = tracker.times(name, "evicted")
        rows.append(
            f"| {name.split('-', 2)[-1]} | {job.team} | {job.worker} | {job.priority} | {fmt(submitted)} | "
            f"{' / '.join(fmt(a) for a in admitted) or '-'} | {fmt(wait)} | "
            f"{' / '.join(fmt(e) for e in evicted) or '-'} | {fmt(tracker.first(name, 'finished'))} |"
        )
    return rows


def queue_rows(tracker: Tracker) -> list[str]:
    return [
        f"| {queue} | {tracker.max_admitted.get(queue, 0)} | {tracker.max_borrowed.get(queue, 0)}m |"
        for queue in sorted(tracker.max_admitted)
    ]


def render(trackers: list[Tracker]) -> str:
    out = []
    for t in trackers:
        out.append(f"### {t.scenario}\n")
        out.append("Times are seconds since the scenario started, seen by the test polling every 0.5 s.\n")
        out.append("| job | team | worker | priority | submitted | admitted | first wait | evicted | finished |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        out.extend(job_rows(t))
        out.append("\n| cluster queue | max admitted at once | max cpu borrowed |")
        out.append("|---|---|---|")
        out.extend(queue_rows(t))
        out.append("")
    return "\n".join(out)


def write(trackers: list[Tracker]) -> None:
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timeline = [{"scenario": t.scenario, "events": [asdict(e) for e in t.events]} for t in trackers]
    (config.REPORT_DIR / "admission-timeline.json").write_text(json.dumps(timeline, indent=2))
    (config.REPORT_DIR / "admission-report.md").write_text(render(trackers))
