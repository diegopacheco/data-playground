import time
from dataclasses import dataclass
from string import Template

from kueue_e2e import config
from kueue_e2e.kube import kubectl


@dataclass(frozen=True)
class EtlJob:
    name: str
    team: str
    worker: str
    priority: str
    seed: int

    @property
    def namespace(self) -> str:
        return config.TEAMS[self.team][0]

    @property
    def cluster_queue(self) -> str:
        return config.TEAMS[self.team][1]

    @property
    def rows(self) -> int:
        return config.ROWS

    @property
    def rounds(self) -> int:
        return config.ROUNDS


def run_id() -> str:
    return str(time.time_ns() // 1_000_000 % 100_000_000)


def make(run: str, index: int, team: str, worker: str, priority: str = "etl-low") -> EtlJob:
    seed = config.SEEDS[index % len(config.SEEDS)]
    return EtlJob(f"etl-{run}-{index:02d}-{team}-{worker}", team, worker, priority, seed)


def render(job: EtlJob, run: str) -> str:
    return Template(config.JOB_TEMPLATE.read_text()).substitute(
        JOB_NAME=job.name,
        NAMESPACE=job.namespace,
        RUN_ID=run,
        PRIORITY=job.priority,
        IMAGE=config.IMAGES[job.worker],
        TEAM=job.team,
        ROWS=job.rows,
        SEED=job.seed,
        ROUNDS=job.rounds,
    )


def submit(job: EtlJob, run: str) -> None:
    kubectl("apply", "-f", "-", stdin=render(job, run))
