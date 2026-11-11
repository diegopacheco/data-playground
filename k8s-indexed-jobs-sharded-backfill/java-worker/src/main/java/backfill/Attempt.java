package backfill;

import java.time.Instant;

public record Attempt(Settings settings, Partition partition, Instant startedAt) {
}
