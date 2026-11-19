import time

from harness import apps, kafka
from harness.kube import wait_for

RATE = 200
WARMUP_SECONDS = 10
COOLDOWN_SECONDS = 10


def roll_finished(old_uids: set[str]) -> bool:
    pods = kafka.broker_pods()
    replaced = all(p["metadata"]["uid"] not in old_uids for p in pods)
    return replaced and len(pods) == len(old_uids) and kafka.ready_broker_count() == len(old_uids) and not kafka.rolling_restart_pending()


def test_every_order_produced_during_a_broker_rolling_restart_is_consumed() -> None:
    assert kafka.kafka_ready()
    old_uids = set(kafka.broker_pod_uids().values())
    assert len(old_uids) == 3
    restarts_before = apps.consumer_restarts()
    run_id = f"roll-{int(time.time())}"

    apps.start_run(run_id, RATE)
    time.sleep(WARMUP_SECONDS)
    kafka.request_rolling_restart()
    roll_seconds = wait_for("all broker pods replaced", lambda: roll_finished(old_uids), timeout=900)
    sent_during_roll = apps.run_stats(run_id)["sent"]
    time.sleep(COOLDOWN_SECONDS)
    stats = apps.stop_run(run_id)

    assert stats["failed"] == 0, stats["lastError"]
    assert stats["acked"] == stats["sent"]
    assert sent_during_roll > RATE * (WARMUP_SECONDS + roll_seconds) * 0.8

    catch_up = wait_for(
        "consumer caught up",
        lambda: apps.consumer_summary(run_id)["distinct"] >= stats["acked"],
        timeout=300,
    )
    summary = apps.consumer_summary(run_id)
    assert summary["distinct"] == stats["acked"]
    assert summary["received"] >= summary["distinct"]
    assert apps.consumer_restarts() == restarts_before
    assert kafka.kafka_ready()

    print(
        f"\nRESULT rolling restart: run={run_id} rate={RATE}/s roll={roll_seconds:.0f}s "
        f"produced={stats['sent']} acked={stats['acked']} failed={stats['failed']} "
        f"consumed={summary['received']} distinct={summary['distinct']} "
        f"duplicates={summary['received'] - summary['distinct']} consumer_catch_up={catch_up:.0f}s"
    )
