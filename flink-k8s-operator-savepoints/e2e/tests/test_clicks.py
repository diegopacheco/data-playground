from flink_e2e.clicks import first_per_user, gaps, last_per_user, parse

LOG = """
2026-11-07 INFO some flink log line
CLICKS job=java version=v1 user=user-0 seq=0 count=1
1> CLICKS job=java version=v1 user=user-1 seq=1 count=1
CLICKS job=java version=v1 user=user-0 seq=10 count=2
"""


def test_parser_reads_lines_with_and_without_subtask_prefix_and_skips_flink_logs() -> None:
    lines = parse(LOG)
    assert [(line.user, line.count) for line in lines] == [("user-0", 1), ("user-1", 1), ("user-0", 2)]


def test_first_and_last_per_user_are_what_the_continuity_check_compares() -> None:
    lines = parse(LOG)
    assert last_per_user(lines)["user-0"].count == 2
    assert first_per_user(lines)["user-0"].count == 1


def test_a_count_that_resets_or_jumps_is_reported_as_a_gap() -> None:
    reset = parse(LOG + "CLICKS job=java version=v2 user=user-0 seq=0 count=1\n")
    assert gaps(reset) == ["user-0: 2 -> 1"]
    assert gaps(parse(LOG)) == []
