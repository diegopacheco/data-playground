package microbatch;

import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class EventStore {

    private final JdbcClient jdbc;
    private final JdbcTemplate template;

    public EventStore(JdbcClient jdbc, JdbcTemplate template) {
        this.jdbc = jdbc;
        this.template = template;
    }

    public OffsetDateTime cutoff(int lagSeconds) {
        return jdbc.sql("SELECT clock_timestamp() - make_interval(secs => :lag)")
                .param("lag", (double) lagSeconds)
                .query(OffsetDateTime.class)
                .single();
    }

    public List<Event> pageAfter(Watermark watermark, OffsetDateTime cutoff, int limit) {
        return jdbc.sql("""
                SELECT id, account, amount_cents, updated_at
                FROM source_events
                WHERE (updated_at, id) > (:ts, :id) AND updated_at <= :cutoff
                ORDER BY updated_at, id
                LIMIT :limit
                """)
                .param("ts", watermark.updatedAt())
                .param("id", watermark.id())
                .param("cutoff", cutoff)
                .param("limit", limit)
                .query(Event.class)
                .list();
    }

    public void upsert(String table, List<Event> events) {
        String sql = "INSERT INTO " + table + " (id, account, amount_cents, updated_at) VALUES (?, ?, ?, ?) "
                + "ON CONFLICT (id) DO UPDATE SET account = EXCLUDED.account, "
                + "amount_cents = EXCLUDED.amount_cents, updated_at = EXCLUDED.updated_at";
        List<Object[]> rows = events.stream()
                .map(e -> new Object[] {e.id(), e.account(), e.amountCents(), e.updatedAt()})
                .toList();
        template.batchUpdate(sql, rows);
    }
}
