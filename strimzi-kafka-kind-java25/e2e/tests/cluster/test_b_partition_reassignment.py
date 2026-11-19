from harness import kafka
from harness.kube import wait_for
from harness.topology import fully_in_sync, render, replicas_per_broker

TOPIC = "orders"
REASSIGN_TIMEOUT = 1200


def scaled_to(count: int) -> bool:
    return len(kafka.broker_ids()) == count and kafka.ready_broker_count() == count


def test_cruise_control_moves_partitions_onto_a_new_broker_and_off_again() -> None:
    original = kafka.broker_ids()
    assert len(original) == 3
    before = kafka.describe_topic(TOPIC)
    assert all(set(p.replicas) <= set(original) for p in before)

    kafka.scale_brokers(4)
    scale_up = wait_for("broker pool at 4", lambda: scaled_to(4), timeout=600)
    new_broker = (set(kafka.broker_ids()) - set(original)).pop()
    assert new_broker not in replicas_per_broker(kafka.describe_topic(TOPIC))
    cc_restart = wait_for(
        "cruise control restarted with the new broker capacity",
        lambda: kafka.cruise_control_restarted_after(f"{kafka.BROKER_PODSET}-{new_broker}"),
        timeout=600,
    )

    kafka.rebalance("add-brokers", "add-brokers", [new_broker])
    add_seconds = wait_for("add-brokers rebalance Ready", lambda: kafka.rebalance_done("add-brokers"), REASSIGN_TIMEOUT, 5)
    add_result = kafka.rebalance_status("add-brokers").get("optimizationResult", {})
    after = kafka.describe_topic(TOPIC)

    assert replicas_per_broker(after).get(new_broker, 0) > 0
    assert all(len(p.replicas) == 3 for p in after)
    assert fully_in_sync(after)

    kafka.rebalance("remove-brokers", "remove-brokers", [new_broker])
    remove_seconds = wait_for("remove-brokers rebalance Ready", lambda: kafka.rebalance_done("remove-brokers"), REASSIGN_TIMEOUT, 5)
    drained = kafka.describe_topic(TOPIC)
    assert new_broker not in replicas_per_broker(drained)
    kafka.scale_brokers(3)
    scale_down = wait_for("broker pool back at 3", lambda: scaled_to(3), timeout=600)
    assert kafka.broker_ids() == original
    assert fully_in_sync(kafka.describe_topic(TOPIC))
    assert kafka.kafka_ready()

    print(f"\nRESULT partitions of {TOPIC} before (brokers {original}):\n{render(before)}")
    print(f"RESULT partitions of {TOPIC} after add-brokers [{new_broker}]:\n{render(after)}")
    print(
        f"RESULT reassignment: scale_up={scale_up:.0f}s cruise_control_restart={cc_restart:.0f}s add_brokers_rebalance={add_seconds:.0f}s "
        f"replica_moves={add_result.get('numReplicaMovements')} leader_moves={add_result.get('numLeaderMovements')} "
        f"data_to_move_mb={add_result.get('dataToMoveMB')} remove_brokers_rebalance={remove_seconds:.0f}s "
        f"scale_down={scale_down:.0f}s"
    )
