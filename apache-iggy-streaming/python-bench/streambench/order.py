class OrderTracker:
    def __init__(self, partitions: int) -> None:
        self.partitions = partitions
        self.next_seq = list(range(partitions))
        self.received = 0
        self.gaps = 0
        self.backwards = 0
        self.misrouted = 0

    def partition_of(self, seq: int) -> int:
        return seq % self.partitions

    def observe(self, partition: int, seq: int) -> None:
        self.received += 1
        if self.partition_of(seq) != partition:
            self.misrouted += 1
            return
        expected = self.next_seq[partition]
        if seq < expected:
            self.backwards += 1
            return
        self.gaps += (seq - expected) // self.partitions
        self.next_seq[partition] = seq + self.partitions

    def in_order(self) -> bool:
        return self.gaps == 0 and self.backwards == 0 and self.misrouted == 0

    def complete(self, sent: int) -> bool:
        return self.in_order() and self.received == sent and all(
            self.next_seq[p] == self.first_seq_at_or_after(p, sent) for p in range(self.partitions)
        )

    def first_seq_at_or_after(self, partition: int, bound: int) -> int:
        if bound <= partition:
            return partition
        steps = -(-(bound - partition) // self.partitions)
        return partition + steps * self.partitions
