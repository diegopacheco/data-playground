import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from coldstart import cluster, config, lab
from coldstart.timeline import cold_start

EVENTS = 40


def each_variant(check: Any) -> None:
    with ThreadPoolExecutor(len(config.VARIANTS)) as pool:
        for future in [pool.submit(check, v) for v in config.VARIANTS]:
            future.result()


def delivered_exactly_once(variant: str) -> None:
    lab.reset(variant)
    orders = lab.make_orders(EVENTS)
    lab.produce(variant, orders)
    lab.wait_records(variant, {o["id"] for o in orders})
    time.sleep(config.SETTLE_S)
    handled = lab.records(variant)
    counts = Counter(r["id"] for r in handled)
    assert set(counts) == {o["id"] for o in orders}, f"{variant}: ids differ"
    assert len(handled) == EVENTS, f"{variant}: duplicates {[i for i, c in counts.items() if c > 1]}"
    by_id = {r["id"]: r for r in handled}
    for order in orders:
        got = by_id[order["id"]]
        assert got["totalCents"] == order["quantity"] * order["unitPriceCents"], f"{variant}: wrong total"
        assert got["sku"] == order["sku"].strip().upper(), f"{variant}: wrong sku"
        assert got["variant"] == variant


def scales_to_zero_and_back(variant: str) -> None:
    cluster.wait_for_zero(variant)
    orders = lab.make_orders(1)
    lab.produce(variant, orders)
    record = lab.wait_records(variant, {orders[0]["id"]})[0]
    timeline = cold_start(record)
    assert timeline.scale_up_ms > 0, f"{variant}: a process that predates the event handled it"
    assert record["pod"] in cluster.pod_names(variant), f"{variant}: no new pod for the event"
    idle = cluster.wait_for_zero(variant)
    assert idle < config.ZERO_TIMEOUT_S


def test_every_event_on_the_topic_is_delivered_and_processed_exactly_once_by_every_variant() -> None:
    each_variant(delivered_exactly_once)


def test_every_variant_scales_to_zero_when_idle_and_a_new_event_starts_a_fresh_pod() -> None:
    each_variant(scales_to_zero_and_back)
