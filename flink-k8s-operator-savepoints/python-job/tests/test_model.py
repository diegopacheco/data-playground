import pytest

from clicks_py.model import line, next_count, parse_args, user_for


def test_same_sequence_number_always_maps_to_the_same_user_so_replays_are_deterministic() -> None:
    assert user_for(1234, 10) == "user-4"
    assert user_for(1234, 10) == user_for(1234, 10)


def test_users_are_visited_round_robin_so_every_key_gets_clicks() -> None:
    assert {user_for(seq, 10) for seq in range(10)} == {f"user-{i}" for i in range(10)}


def test_count_starts_at_one_when_there_is_no_state() -> None:
    assert next_count(None) == 1


def test_count_continues_from_restored_state() -> None:
    assert next_count(41) == 42


def test_output_line_matches_the_java_job_so_one_parser_reads_both() -> None:
    assert line("python", "v2", "user-0", 50, 6) == "CLICKS job=python version=v2 user=user-0 seq=50 count=6"


def test_version_comes_from_job_args_and_unknown_flink_args_are_ignored() -> None:
    args = parse_args(["--version", "v2", "-pym", "clicks_py.job"])
    assert (args.version, args.users, args.rate) == ("v2", 10, 20)


def test_zero_users_is_rejected() -> None:
    with pytest.raises(ValueError):
        user_for(1, 0)
