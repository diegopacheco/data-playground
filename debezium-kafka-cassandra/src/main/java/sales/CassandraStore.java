package sales;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import tools.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class CassandraStore {

    private final CqlSession session;
    private final PreparedStatement upsert;
    private final PreparedStatement delete;
    private final PreparedStatement writeTotals;
    private final PreparedStatement deleteTotals;

    public CassandraStore() {
        session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(Settings.CASSANDRA_HOST, Settings.CASSANDRA_PORT))
                .withLocalDatacenter("datacenter1")
                .build();
        session.execute("CREATE KEYSPACE IF NOT EXISTS sales WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}");
        session.execute("CREATE TABLE IF NOT EXISTS sales.orders (order_id int PRIMARY KEY, customer text, product text, category text, quantity int, price decimal, ts text)");
        session.execute("CREATE TABLE IF NOT EXISTS sales.revenue_by_category (category text PRIMARY KEY, total_orders bigint, total_quantity bigint, total_revenue decimal)");
        upsert = session.prepare("INSERT INTO sales.orders (order_id, customer, product, category, quantity, price, ts) VALUES (?, ?, ?, ?, ?, ?, ?)");
        delete = session.prepare("DELETE FROM sales.orders WHERE order_id = ?");
        writeTotals = session.prepare("INSERT INTO sales.revenue_by_category (category, total_orders, total_quantity, total_revenue) VALUES (?, ?, ?, ?)");
        deleteTotals = session.prepare("DELETE FROM sales.revenue_by_category WHERE category = ?");
    }

    public void upsert(JsonNode row) {
        session.execute(upsert.bind(
                row.get("order_id").asInt(),
                row.get("customer").asString(),
                row.get("product").asString(),
                row.get("category").asString(),
                row.get("quantity").asInt(),
                new BigDecimal(row.get("price").asString()),
                row.get("ts").asString()));
    }

    public void delete(int orderId) {
        session.execute(delete.bind(orderId));
    }

    public void recompute(Set<String> categories) {
        Map<String, Totals> totals = new HashMap<>();
        for (Row row : session.execute("SELECT category, quantity, price FROM sales.orders")) {
            String category = row.getString("category");
            if (!categories.contains(category)) {
                continue;
            }
            BigDecimal line = row.getBigDecimal("price").multiply(BigDecimal.valueOf(row.getInt("quantity")));
            Totals current = totals.getOrDefault(category, new Totals(category, 0, 0, BigDecimal.ZERO));
            totals.put(category, new Totals(category, current.orders() + 1, current.quantity() + row.getInt("quantity"), current.revenue().add(line)));
        }
        for (String category : categories) {
            Totals t = totals.get(category);
            if (t == null) {
                session.execute(deleteTotals.bind(category));
            } else {
                session.execute(writeTotals.bind(category, t.orders(), t.quantity(), t.revenue().setScale(2, RoundingMode.UNNECESSARY)));
            }
        }
    }

    public List<Totals> totals() {
        List<Totals> result = new ArrayList<>();
        for (Row row : session.execute("SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category")) {
            result.add(new Totals(row.getString("category"), row.getLong("total_orders"), row.getLong("total_quantity"), row.getBigDecimal("total_revenue")));
        }
        return result;
    }

    public long orderCount() {
        return session.execute("SELECT COUNT(*) FROM sales.orders").one().getLong(0);
    }
}
