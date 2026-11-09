from datetime import UTC, datetime, timedelta, timezone

from loader.watermark import Event, Watermark

T = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def event(event_id: int, at: datetime) -> Event:
    return Event(event_id, "acc", 100, at)


def test_empty_page_keeps_watermark_so_no_row_is_skipped() -> None:
    current = Watermark(T, 7)
    assert current.advance([]) == current


def test_equal_timestamps_advance_by_id_so_the_rest_of_the_tie_is_still_pending() -> None:
    assert Watermark(T, 1).advance([event(2, T), event(3, T)]) == Watermark(T, 3)


def test_later_timestamp_wins_even_with_smaller_id_because_updates_keep_their_old_id() -> None:
    nxt = Watermark(T, 50).advance([event(51, T), event(4, T + timedelta(seconds=1))])
    assert nxt == Watermark(T + timedelta(seconds=1), 4)


def test_never_moves_backwards_so_a_replayed_old_page_cannot_reopen_a_gap() -> None:
    current = Watermark(T + timedelta(seconds=10), 9)
    assert current.advance([event(1, T), event(2, T + timedelta(seconds=5))]) == current


def test_same_instant_in_different_offsets_is_the_same_timestamp() -> None:
    same_instant = T.astimezone(timezone(timedelta(hours=-3)))
    assert Watermark(T, 5).advance([event(6, same_instant)]).id == 6
