import pytest

from lag_consumer.config import load


def test_slowdown_defaults_to_zero_so_a_normal_deploy_is_never_slowed() -> None:
    assert load({"PG_PASSWORD": "p"}).slowdown_ms == 0


def test_slowdown_flag_is_read_from_the_environment() -> None:
    assert load({"PG_PASSWORD": "p", "SLOWDOWN_MS": "2500"}).slowdown_ms == 2500


def test_negative_slowdown_is_rejected() -> None:
    with pytest.raises(ValueError):
        load({"PG_PASSWORD": "p", "SLOWDOWN_MS": "-1"})


def test_missing_database_password_fails_loud_at_startup() -> None:
    with pytest.raises(KeyError):
        load({})
