package sales;

import com.datastax.oss.driver.api.core.CqlSession;

import java.net.InetSocketAddress;

public final class Cassandra {

    private Cassandra() {
    }

    public static CqlSession connect() {
        CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(Settings.CASSANDRA_HOST, Settings.CASSANDRA_PORT))
                .withLocalDatacenter("datacenter1")
                .build();
        session.execute("CREATE KEYSPACE IF NOT EXISTS sales WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}");
        session.execute("CREATE TABLE IF NOT EXISTS sales.revenue_by_category (category text PRIMARY KEY, total_orders bigint, total_quantity bigint, total_revenue double)");
        return session;
    }
}
