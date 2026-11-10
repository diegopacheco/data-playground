import re
import time
from dataclasses import dataclass
from typing import Any

from flink_e2e import config, kube
from flink_e2e.clicks import ClickLine, first_per_user, last_per_user, parse

NAMES = {"java": "clicks-java", "python": "clicks-python"}


@dataclass(frozen=True)
class Transition:
    kind: str
    label: str
    upgrade_mode: str
    before: list[ClickLine]
    after: list[ClickLine]
    parallelism: int
    restored: dict[str, Any] | None
    seconds_to_running: float
    seconds_to_first_count: float


def tm_clicks(name: str, exclude_uids: set[str]) -> list[ClickLine]:
    lines: list[ClickLine] = []
    for pod in kube.running_pods(name, "taskmanager"):
        if pod["metadata"]["uid"] not in exclude_uids:
            lines.extend(parse(kube.logs(pod["metadata"]["name"])))
    return lines


def every_user(lines: list[ClickLine]) -> list[ClickLine] | None:
    return lines if len({line.user for line in lines}) == config.USERS else None


def counter_parallelism(job: dict[str, Any]) -> int:
    return next(v["parallelism"] for v in job["vertices"] if "click-counter" in v["name"])


def deploy_fresh(kind: str, upgrade_mode: str) -> str:
    name = NAMES[kind]
    kube.delete(name)
    obj = kube.manifest(kind)
    obj["spec"]["job"]["upgradeMode"] = upgrade_mode
    kube.apply(obj)
    kube.wait_for(f"{name} job running", lambda: kube.running_job(name))
    kube.wait_for(f"{name} clicks for every user", lambda: every_user(tm_clicks(name, set())))
    kube.wait_for(f"{name} running in operator status", lambda: operator_state(name) == "RUNNING" or None)
    return name


def operator_state(name: str) -> str | None:
    return kube.deployment(name).get("status", {}).get("jobStatus", {}).get("state")


def with_version(args: list[str], version: str) -> list[str]:
    out = list(args)
    out[out.index("--version") + 1] = version
    return out


def transition(kind: str, label: str, job_patch: dict[str, Any]) -> Transition:
    name = NAMES[kind]
    old_job = kube.wait_for(f"{name} job running", lambda: kube.running_job(name))
    old_uids = {p["metadata"]["uid"] for p in kube.pods(name, "taskmanager")}
    upgrade_mode = kube.deployment(name)["spec"]["job"]["upgradeMode"]
    tap = kube.LogTap(name, re.sub(r"[^a-z0-9]+", "-", f"{kind} {upgrade_mode} {label}"))
    began = time.monotonic()
    kube.patch_job(name, job_patch)

    def new_job() -> dict[str, Any] | None:
        job = kube.running_job(name)
        return job if job is not None and job["jid"] != old_job["jid"] else None

    job = kube.wait_for(f"{name} new job running", new_job)
    seconds_to_running = time.monotonic() - began
    kube.wait_for(f"{name} first click after {label}", lambda: tm_clicks(name, old_uids) or None)
    seconds_to_first_count = time.monotonic() - began
    after = kube.wait_for(f"{name} every user after {label}", lambda: every_user(tm_clicks(name, old_uids)))
    before = parse(tap.drain())
    kube.wait_for(f"{name} running in operator status", lambda: operator_state(name) == "RUNNING" or None)
    return Transition(
        kind=kind,
        label=label,
        upgrade_mode=upgrade_mode,
        before=before,
        after=after,
        parallelism=counter_parallelism(job),
        restored=kube.restored_from(name, job["jid"]),
        seconds_to_running=seconds_to_running,
        seconds_to_first_count=seconds_to_first_count,
    )


def record(t: Transition) -> None:
    config.RESULTS.parent.mkdir(parents=True, exist_ok=True)
    new = not config.RESULTS.exists()
    with config.RESULTS.open("a") as out:
        if new:
            out.write("job\ttransition\tupgradeMode\tparallelism\tseconds_to_running\tseconds_to_first_count\tuser-0_count_before_after\tstate_kept\n")
        before, after = last_per_user(t.before), first_per_user(t.after)
        kept = bool(before) and all(user in after and after[user].count == line.count + 1 for user, line in before.items())
        sample = f"{before['user-0'].count}->{after['user-0'].count}"
        out.write(f"{t.kind}\t{t.label}\t{t.upgrade_mode}\t{t.parallelism}\t{t.seconds_to_running:.1f}\t{t.seconds_to_first_count:.1f}\t{sample}\t{kept}\n")
