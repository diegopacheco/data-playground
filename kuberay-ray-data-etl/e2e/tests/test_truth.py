from ray_e2e.truth import Aggregate, compare, expected_aggregates


def ev(i: int, category: str, amount: int) -> dict[str, object]:
    return {"event_id": f"e{i}", "batch_id": "b1", "user_id": "u", "category": category, "amount_cents": amount, "ts": 0}


EVENTS = [ev(0, " Books", 100), ev(1, "books", 40), ev(2, "MUSIC ", 5), ev(3, "music", 0), ev(4, "books", -9)]
TRUTH = {("b1", "books"): Aggregate(2, 140, 100), ("b1", "music"): Aggregate(1, 5, 5)}


def test_ground_truth_drops_non_positive_amounts_and_merges_category_spellings() -> None:
    assert expected_aggregates(EVENTS) == TRUTH


def test_matching_output_has_no_problems() -> None:
    assert compare("b1", EVENTS, ["e0", "e1", "e2"], TRUTH) == []


def test_a_replayed_event_is_reported_even_when_the_id_set_matches() -> None:
    problems = compare("b1", EVENTS, ["e0", "e1", "e2", "e2"], TRUTH)
    assert problems == ["b1: 1 duplicated event ids, first e2"]


def test_a_lost_event_is_reported_as_missing_and_as_wrong_aggregates() -> None:
    lost = {("b1", "books"): Aggregate(1, 100, 100), ("b1", "music"): Aggregate(1, 5, 5)}
    problems = compare("b1", EVENTS, ["e0", "e2"], lost)
    assert problems == ["b1: 1 valid input events missing from output", "b1: aggregates differ from ground truth"]


def test_a_double_counted_aggregate_is_caught_even_if_event_rows_are_right() -> None:
    doubled = {("b1", "books"): Aggregate(4, 280, 100), ("b1", "music"): Aggregate(1, 5, 5)}
    assert compare("b1", EVENTS, ["e0", "e1", "e2"], doubled) == ["b1: aggregates differ from ground truth"]
