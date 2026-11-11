package backfill;

import java.time.Instant;
import java.time.LocalDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("backfill_ledger")
public record LedgerEntry(
        @Id Long id,
        String worker,
        String runId,
        int idx,
        LocalDate day,
        String pod,
        int attempt,
        String status,
        long rowsRead,
        Instant startedAt,
        Instant finishedAt) {

    public static LedgerEntry of(Attempt attempt, String status, long rowsRead) {
        Settings s = attempt.settings();
        return new LedgerEntry(null, s.worker(), s.runId(), s.index(), attempt.partition().day(), s.pod(),
                s.attempt(), status, rowsRead, attempt.startedAt(), Instant.now());
    }
}
