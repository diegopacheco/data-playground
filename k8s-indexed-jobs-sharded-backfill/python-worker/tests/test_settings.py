from datetime import date

from backfill.settings import Settings

BASE = {
    "WORKER": "python",
    "RUN_ID": "backfill-python-1",
    "POD_NAME": "backfill-python-1-3-abcde",
    "JOB_COMPLETION_INDEX": "3",
    "START_DAY": "2026-10-01",
    "SUBRANGES": "4",
    "FAIL_INDEX": "3",
    "FATAL_INDEX": "-1",
}


def test_missing_failure_count_annotation_means_first_attempt() -> None:
    s = Settings.from_env(BASE | {"INDEX_FAILURES": ""})
    assert s.attempt == 0
    assert s.index == 3
    assert s.start_day == date(2026, 10, 1)


def test_forced_transient_failure_hits_only_the_first_attempt_of_its_index_so_the_retry_can_succeed() -> None:
    assert Settings.from_env(BASE | {"INDEX_FAILURES": "0"}).must_fail_transiently()
    assert not Settings.from_env(BASE | {"INDEX_FAILURES": "1"}).must_fail_transiently()
    assert not Settings.from_env(BASE | {"JOB_COMPLETION_INDEX": "4", "INDEX_FAILURES": "0"}).must_fail_transiently()


def test_fatal_failure_applies_on_every_attempt_because_retrying_cannot_fix_it() -> None:
    env = BASE | {"FAIL_INDEX": "-1", "FATAL_INDEX": "3"}
    assert Settings.from_env(env | {"INDEX_FAILURES": "0"}).must_fail_fatally()
    assert Settings.from_env(env | {"INDEX_FAILURES": "2"}).must_fail_fatally()
    assert not Settings.from_env(env | {"JOB_COMPLETION_INDEX": "4"}).must_fail_fatally()
