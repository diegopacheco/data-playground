package com.github.diegopacheco.flinkcassandra;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class CassandraStore implements AutoCloseable {

    private final CqlSession session;
    private PreparedStatement insert;

    public CassandraStore() {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "localhost");
        int port = Integer.parseInt(System.getenv().getOrDefault("CASSANDRA_PORT", "12042"));
        this.session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, port))
                .withLocalDatacenter("datacenter1")
                .build();
    }

    public void createSchema() {
        session.execute("CREATE KEYSPACE IF NOT EXISTS sales WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}");
        session.execute("CREATE TABLE IF NOT EXISTS sales.revenue_by_category (category text PRIMARY KEY, total_orders bigint, total_quantity bigint, total_revenue double)");
    }

    public void save(CategoryStats stats) {
        if (insert == null) {
            insert = session.prepare("INSERT INTO sales.revenue_by_category (category, total_orders, total_quantity, total_revenue) VALUES (?, ?, ?, ?)");
        }
        CategoryStats r = stats.rounded();
        session.execute(insert.bind(r.category(), r.totalOrders(), r.totalQuantity(), r.totalRevenue()));
    }

    public List<CategoryStats> findAll() {
        List<CategoryStats> result = new ArrayList<>();
        for (Row row : session.execute("SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category")) {
            result.add(new CategoryStats(row.getString("category"), row.getLong("total_orders"), row.getLong("total_quantity"), row.getDouble("total_revenue")));
        }
        result.sort(Comparator.comparingDouble(CategoryStats::totalRevenue).reversed());
        return result;
    }

    @Override
    public void close() {
        session.close();
    }
}
