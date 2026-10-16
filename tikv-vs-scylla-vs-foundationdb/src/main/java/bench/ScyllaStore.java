package bench;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfigLoader;
import com.datastax.oss.driver.api.core.cql.BatchStatementBuilder;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

public final class ScyllaStore implements Store {

    private final CqlSession session;
    private PreparedStatement insert;
    private PreparedStatement read;
    private PreparedStatement range;

    public ScyllaStore() {
        DriverConfigLoader config = DriverConfigLoader.programmaticBuilder()
                .withDuration(DefaultDriverOption.REQUEST_TIMEOUT, Duration.ofSeconds(30))
                .withDuration(DefaultDriverOption.CONNECTION_INIT_QUERY_TIMEOUT, Duration.ofSeconds(10))
                .build();
        session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(Settings.SCYLLA_HOST, 9042))
                .withLocalDatacenter("datacenter1")
                .withConfigLoader(config)
                .build();
        session.execute("CREATE KEYSPACE IF NOT EXISTS s6 WITH replication = {'class': 'NetworkTopologyStrategy', 'datacenter1': 1}");
        session.execute("CREATE TABLE IF NOT EXISTS s6.kv (bucket int, k text, v blob, PRIMARY KEY ((bucket), k))");
        insert = session.prepare("INSERT INTO s6.kv (bucket, k, v) VALUES (?, ?, ?)");
        read = session.prepare("SELECT v FROM s6.kv WHERE bucket = ? AND k = ?");
        range = session.prepare("SELECT k, v FROM s6.kv WHERE bucket = ? AND k >= ? LIMIT ?");
    }

    @Override
    public String name() {
        return "scylladb";
    }

    @Override
    public String api() {
        return "CQL prepared statements, clustering-key range inside a " + Settings.SCYLLA_BUCKET_ROWS + "-row partition";
    }

    @Override
    public String version() {
        return session.execute("SELECT version FROM system.versions").one().getString("version");
    }

    @Override
    public void reset() {
        session.execute("TRUNCATE s6.kv");
    }

    @Override
    public void load(List<Entry> batch) {
        BatchStatementBuilder builder = new BatchStatementBuilder(DefaultBatchType.UNLOGGED);
        for (Entry entry : batch) {
            builder.addStatement(insert.bind(bucket(entry.key()), entry.key(), ByteBuffer.wrap(entry.value())));
        }
        session.execute(builder.build());
    }

    @Override
    public byte[] get(String key) {
        Row row = session.execute(read.bind(bucket(key), key)).one();
        return row == null ? null : array(row.getByteBuffer("v"));
    }

    @Override
    public List<Entry> scan(String start, int limit) {
        List<Entry> entries = new ArrayList<>(limit);
        int bucket = bucket(start);
        for (int partition = bucket; partition <= bucket + 1 && entries.size() < limit; partition++) {
            for (Row row : session.execute(range.bind(partition, start, limit - entries.size()))) {
                entries.add(new Entry(row.getString("k"), array(row.getByteBuffer("v"))));
            }
        }
        return entries;
    }

    @Override
    public void close() {
        session.close();
    }

    static int bucket(String key) {
        return (int) (Long.parseLong(key.substring(4, 16)) / Settings.SCYLLA_BUCKET_ROWS);
    }

    private static byte[] array(ByteBuffer buffer) {
        byte[] bytes = new byte[buffer.remaining()];
        buffer.get(bytes);
        return bytes;
    }
}
