package bench;

public final class OrderTracker {

    private final int partitions;
    private final long[] nextSeq;
    private long received;
    private long gaps;
    private long backwards;
    private long misrouted;

    public OrderTracker(int partitions) {
        this.partitions = partitions;
        this.nextSeq = new long[partitions];
        for (int p = 0; p < partitions; p++) {
            nextSeq[p] = p;
        }
    }

    public void observe(int partition, long seq) {
        received++;
        if (seq % partitions != partition) {
            misrouted++;
            return;
        }
        long expected = nextSeq[partition];
        if (seq < expected) {
            backwards++;
            return;
        }
        gaps += (seq - expected) / partitions;
        nextSeq[partition] = seq + partitions;
    }

    public boolean inOrder() {
        return gaps == 0 && backwards == 0 && misrouted == 0;
    }

    public boolean complete(long sent) {
        if (!inOrder() || received != sent) {
            return false;
        }
        for (int p = 0; p < partitions; p++) {
            if (nextSeq[p] != firstSeqAtOrAfter(p, sent)) {
                return false;
            }
        }
        return true;
    }

    private long firstSeqAtOrAfter(int partition, long bound) {
        if (bound <= partition) {
            return partition;
        }
        long steps = (bound - partition + partitions - 1) / partitions;
        return partition + steps * partitions;
    }

    public long received() {
        return received;
    }

    public long gaps() {
        return gaps;
    }

    public long backwards() {
        return backwards;
    }

    public long misrouted() {
        return misrouted;
    }
}
