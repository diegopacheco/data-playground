from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Settings:
    worker: str
    run_id: str
    pod: str
    index: int
    attempt: int
    start_day: date
    sub_ranges: int
    fail_index: int
    fatal_index: int

    @staticmethod
    def from_env(env: Mapping[str, str]) -> Settings:
        return Settings(
            worker=env["WORKER"],
            run_id=env["RUN_ID"],
            pod=env["POD_NAME"],
            index=int(env["JOB_COMPLETION_INDEX"]),
            attempt=int(env.get("INDEX_FAILURES") or "0"),
            start_day=date.fromisoformat(env["START_DAY"]),
            sub_ranges=int(env.get("SUBRANGES") or "4"),
            fail_index=int(env.get("FAIL_INDEX") or "-1"),
            fatal_index=int(env.get("FATAL_INDEX") or "-1"),
        )

    def must_fail_transiently(self) -> bool:
        return self.index == self.fail_index and self.attempt == 0

    def must_fail_fatally(self) -> bool:
        return self.index == self.fatal_index
