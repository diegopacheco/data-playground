import pytest

from loader.config import settings_from_env


def test_target_table_is_derived_from_job_so_each_loader_owns_its_table() -> None:
    assert settings_from_env({"JOB": "python"}).target_table == "target_python"


def test_job_name_is_rejected_when_it_could_inject_sql_into_the_table_name() -> None:
    with pytest.raises(ValueError):
        settings_from_env({"JOB": "python; DROP TABLE source_events"})


def test_zero_page_size_is_rejected_because_the_load_loop_would_never_advance() -> None:
    with pytest.raises(ValueError):
        settings_from_env({"PAGE_SIZE": "0"})


def test_connection_is_tagged_with_the_job_so_a_running_batch_is_visible_in_pg_stat_activity() -> None:
    assert "application_name=loader-python" in settings_from_env({}).conninfo
