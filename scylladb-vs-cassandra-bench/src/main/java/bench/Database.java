package bench;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.concurrent.CompletionStage;

public final class Database implements AutoCloseable {

    private final String name;
    private final CqlSession session;
    private PreparedStatement insert;
    private PreparedStatement read;
    private PreparedStatement aggregate;

    public Database(String name, int port) {
        this.name = name;
        DriverConfigLoader config = DriverConfigLoader.programmaticBuilder()
                .withDuration(DefaultDriverOption.REQUEST_TIMEOUT, Duration.ofSeconds(30))
                .withDuration(DefaultDriverOption.CONNECTION_INIT_QUERY_TIMEOUT, Duration.ofSeconds(10))
                .withDuration(DefaultDriverOption.CONTROL_CONNECTION_AGREEMENT_TIMEOUT, Duration.ofSeconds(30))
                .withInt(DefaultDriverOption.CONNECTION_MAX_REQUESTS, 2048)
                .build();
        this.session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(Settings.HOST, port))
                .withLocalDatacenter("datacenter1")
                .withConfigLoader(config)
                .build();
    }

    public String name() {
        return name;
    }

    public String version() {
        try {
            Row row = session.execute("SELECT version FROM system.versions").one();
            if (row != null) return row.getString("version");
        } catch (RuntimeException ignored) {
        }
        return session.execute("SELECT release_version FROM system.local").one().getString("release_version");
    }

    public void resetSchema() {
        session.execute("DROP KEYSPACE IF EXISTS bench");
        session.execute("CREATE KEYSPACE bench WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 1}");
        session.execute("CREATE TABLE bench.orders (category text, order_id bigint, customer text, product text, quantity int, price decimal, ts text, PRIMARY KEY ((category), order_id))");
        insert = session.prepare("INSERT INTO bench.orders (category, order_id, customer, product, quantity, price, ts) VALUES (?, ?, ?, ?, ?, ?, ?)");
        read = session.prepare("SELECT order_id, customer, product, quantity, price, ts FROM bench.orders WHERE category = ? AND order_id = ?");
        aggregate = session.prepare("SELECT count(*) AS orders, sum(quantity) AS quantity, sum(price) AS price_sum, min(price) AS min_price, max(price) AS max_price FROM bench.orders WHERE category = ?");
    }

    public CompletionStage<Boolean> insert(Order o) {
        return session.executeAsync(insert.bind(o.category(), o.orderId(), o.customer(), o.product(), o.quantity(), o.price(), o.ts()))
                .thenApply(rs -> rs.wasApplied());
    }

    public CompletionStage<Boolean> read(Order o) {
        return session.executeAsync(read.bind(o.category(), o.orderId()))
                .thenApply(rs -> {
                    Row row = rs.one();
                    return row != null && row.getInt("quantity") == o.quantity();
                });
    }

    public CompletionStage<Boolean> aggregate(String category) {
        return session.executeAsync(aggregate.bind(category)).thenApply(rs -> rs.one() != null);
    }

    public Aggregate aggregateNow(String category) {
        Row row = session.execute(aggregate.bind(category)).one();
        return new Aggregate(category, row.getLong("orders"), row.getInt("quantity"),
                row.getBigDecimal("price_sum"), row.getBigDecimal("min_price"), row.getBigDecimal("max_price"));
    }

    @Override
    public void close() {
        session.close();
    }
}
