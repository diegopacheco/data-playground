from harness.topology import fully_in_sync, leaders_per_broker, parse_describe, replicas_per_broker

DESCRIBE = """Topic: orders\tTopicId: abc\tPartitionCount: 3\tReplicationFactor: 3\tConfigs: min.insync.replicas=2
\tTopic: orders\tPartition: 1\tLeader: 4\tReplicas: 4,5,3\tIsr: 4,5,3\tElr: \tLastKnownElr:
\tTopic: orders\tPartition: 0\tLeader: 3\tReplicas: 3,4,5\tIsr: 3,4\tElr: \tLastKnownElr:
\tTopic: orders\tPartition: 2\tLeader: 6\tReplicas: 6,3,4\tIsr: 6,3,4\tElr: \tLastKnownElr:
"""


def test_every_partition_line_is_parsed_and_the_header_is_ignored() -> None:
    partitions = parse_describe(DESCRIBE)
    assert [p.partition for p in partitions] == [0, 1, 2]
    assert partitions[2].replicas == (6, 3, 4)
    assert partitions[0].isr == (3, 4)


def test_replica_counts_show_whether_a_new_broker_received_partitions() -> None:
    partitions = parse_describe(DESCRIBE)
    assert replicas_per_broker(partitions) == {3: 3, 4: 3, 5: 2, 6: 1}
    assert leaders_per_broker(partitions) == {3: 1, 4: 1, 6: 1}


def test_a_partition_missing_a_replica_from_isr_is_not_in_sync() -> None:
    partitions = parse_describe(DESCRIBE)
    assert not fully_in_sync(partitions)
    assert fully_in_sync(partitions[1:])


def test_offline_leader_is_not_in_sync() -> None:
    offline = parse_describe("Topic: orders\tPartition: 0\tLeader: -1\tReplicas: 3,4,5\tIsr: \n")
    assert offline[0].leader == -1
    assert not fully_in_sync(offline)
