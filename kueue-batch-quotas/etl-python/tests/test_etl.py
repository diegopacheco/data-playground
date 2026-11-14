import json
from pathlib import Path

import pytest

from etl.config import EtlConfig
from etl.sink import mark_started, result_row, write_result
from etl.transform import MAX_AMOUNT_CENTS, REGIONS, generate, splitmix64, summarize

GOLDEN_DIGEST = "62eaacdf12ac7df3806a84e9090d10a7b6ed653cbcf941fa3667093329352ea5"
GOLDEN_TOTALS = {"AMER": 12701464, "APAC": 11792576, "EMEA": 12012574, "LATAM": 12291279}


def cfg_for(tmp: Path, pod: str = "pod-a") -> EtlConfig:
    return EtlConfig("job-1", pod, "finance", 10, 7, 2, tmp)


def test_golden_result_is_the_cross_language_contract_shared_with_the_java_worker() -> None:
    summary = summarize(1000, 7, 3)
    assert summary.digest == GOLDEN_DIGEST
    assert summary.totals == GOLDEN_TOTALS


def test_a_rerun_after_preemption_produces_the_identical_result() -> None:
    assert summarize(500, 11, 4) == summarize(500, 11, 4)


def test_a_different_seed_is_a_different_dataset() -> None:
    assert summarize(500, 11, 1).digest != summarize(500, 12, 1).digest


def test_rounds_only_add_cpu_work_and_never_change_the_totals() -> None:
    light, heavy = summarize(300, 5, 1), summarize(300, 5, 9)
    assert light.totals == heavy.totals
    assert light.digest != heavy.digest


def test_totals_account_for_every_generated_cent() -> None:
    sales = list(generate(2000, 3))
    assert {s.region for s in sales} == set(REGIONS)
    assert all(0 <= s.amount_cents < MAX_AMOUNT_CENTS for s in sales)
    assert sum(summarize(2000, 3, 1).totals.values()) == sum(s.amount_cents for s in sales)


def test_splitmix64_matches_the_reference_first_output_for_seed_zero() -> None:
    assert splitmix64(0) == 0xE220A8397B1DCDAF


def test_config_rejects_empty_work() -> None:
    env = {"JOB_NAME": "j", "POD_NAME": "p", "TEAM": "t", "ETL_ROWS": "0", "ETL_SEED": "1", "ETL_ROUNDS": "1"}
    with pytest.raises(ValueError):
        EtlConfig.from_env(env)


def test_each_attempt_writes_its_own_files_so_a_duplicate_run_is_visible(tmp_path: Path) -> None:
    for pod in ("pod-a", "pod-b"):
        cfg = cfg_for(tmp_path, pod)
        mark_started(cfg, 1)
        write_result(cfg, result_row(cfg, summarize(10, 7, 2), "python", 1, 2))
    files = sorted(p.name for p in (tmp_path / "job-1").iterdir())
    assert files == ["pod-a.json", "pod-a.started", "pod-b.json", "pod-b.started"]


def test_a_killed_attempt_leaves_a_start_marker_but_no_result(tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path)
    mark_started(cfg, 1)
    assert [p.name for p in (tmp_path / "job-1").iterdir()] == ["pod-a.started"]


def test_result_is_complete_json_with_no_temp_file_left(tmp_path: Path) -> None:
    cfg = cfg_for(tmp_path)
    path = write_result(cfg, result_row(cfg, summarize(10, 7, 2), "python", 5, 9))
    row = json.loads(path.read_text())
    assert row["job"] == "job-1" and row["worker"] == "python" and row["rows"] == 10
    assert row["digest"] == summarize(10, 7, 2).digest
    assert not list((tmp_path / "job-1").glob("*.tmp"))
