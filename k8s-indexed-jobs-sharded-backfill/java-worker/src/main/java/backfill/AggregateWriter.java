package backfill;

import java.util.Map;
import java.util.TreeMap;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class AggregateWriter {

    private final JdbcClient jdbc;
    private final LedgerRepository ledger;
    private final TransactionTemplate tx;

    public AggregateWriter(JdbcClient jdbc, LedgerRepository ledger, TransactionTemplate tx) {
        this.jdbc = jdbc;
        this.ledger = ledger;
        this.tx = tx;
    }

    public void writePartition(Attempt attempt, Map<String, Stats> aggregates, long rowsRead) {
        Settings s = attempt.settings();
        tx.executeWithoutResult(status -> {
            jdbc.sql("delete from daily_aggregates where worker = ? and day = ?")
                    .params(s.worker(), attempt.partition().day())
                    .update();
            new TreeMap<>(aggregates).forEach((category, st) -> jdbc.sql(
                    "insert into daily_aggregates (worker, day, category, event_count, amount_total, amount_min, amount_max, run_id) "
                            + "values (?, ?, ?, ?, ?, ?, ?, ?)")
                    .params(s.worker(), attempt.partition().day(), category, st.count(), st.total(), st.min(), st.max(), s.runId())
                    .update());
            if (s.mustFailTransiently()) {
                throw new TransientFailure("forced transient failure on index " + s.index());
            }
            ledger.save(LedgerEntry.of(attempt, "ok", rowsRead));
        });
    }

    public void recordFailure(Attempt attempt, String status) {
        ledger.save(LedgerEntry.of(attempt, status, 0));
    }
}
