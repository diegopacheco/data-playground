package backfill;

import java.util.Map;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Component;

@Component
public class EventSource implements RangeReader {

    private final JdbcClient jdbc;

    public EventSource(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Map<String, Stats> read(TimeRange range) {
        Accumulator acc = new Accumulator();
        jdbc.sql("select category, amount_cents from events where ts >= ? and ts < ?")
                .params(range.start(), range.end())
                .query((RowCallbackHandler) rs -> acc.add(rs.getString(1), rs.getLong(2)));
        return acc.result();
    }
}
