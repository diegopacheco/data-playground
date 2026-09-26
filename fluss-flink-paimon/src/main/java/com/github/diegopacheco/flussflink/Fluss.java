package com.github.diegopacheco.flussflink;

import org.apache.fluss.client.Connection;
import org.apache.fluss.client.ConnectionFactory;
import org.apache.fluss.client.admin.Admin;
import org.apache.fluss.client.lookup.Lookuper;
import org.apache.fluss.client.metadata.LakeSnapshot;
import org.apache.fluss.client.table.Table;
import org.apache.fluss.client.table.scanner.batch.BatchScanner;
import org.apache.fluss.client.table.writer.UpsertWriter;
import org.apache.fluss.config.Configuration;
import org.apache.fluss.exception.LakeTableSnapshotNotExistException;
import org.apache.fluss.metadata.DatabaseDescriptor;
import org.apache.fluss.metadata.Schema;
import org.apache.fluss.metadata.TableDescriptor;
import org.apache.fluss.metadata.TablePath;
import org.apache.fluss.row.GenericRow;
import org.apache.fluss.row.InternalRow;
import org.apache.fluss.types.DataTypes;
import org.apache.fluss.utils.CloseableIterator;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

public final class Fluss implements AutoCloseable {

    public static final TablePath ORDERS = TablePath.of(Settings.DATABASE, Settings.TABLE);

    private final Connection connection;
    private final Admin admin;

    private Fluss() {
        Configuration conf = new Configuration();
        conf.setString("bootstrap.servers", Settings.BOOTSTRAP);
        connection = ConnectionFactory.createConnection(conf);
        admin = connection.getAdmin();
    }

    public static Fluss connect(int tries) throws Exception {
        for (int i = 1; ; i++) {
            try {
                Fluss fluss = new Fluss();
                fluss.ensureTable();
                return fluss;
            } catch (Exception e) {
                if (i >= tries) {
                    throw e;
                }
                System.out.println("fluss not ready (" + e.getMessage().lines().findFirst().orElse("") + "), retry " + i + "/" + tries);
                Thread.sleep(1000);
            }
        }
    }

    public void ensureTable() throws Exception {
        admin.createDatabase(Settings.DATABASE, DatabaseDescriptor.EMPTY, true).get();
        Schema schema = Schema.newBuilder()
                .column("order_id", DataTypes.INT())
                .column("customer", DataTypes.STRING())
                .column("product", DataTypes.STRING())
                .column("category", DataTypes.STRING())
                .column("quantity", DataTypes.INT())
                .column("price", DataTypes.DECIMAL(10, 2))
                .column("ts", DataTypes.STRING())
                .primaryKey("order_id")
                .build();
        TableDescriptor descriptor = TableDescriptor.builder()
                .schema(schema)
                .distributedBy(1, "order_id")
                .property("table.datalake.enabled", "true")
                .property("table.datalake.freshness", Settings.FRESHNESS)
                .build();
        admin.createTable(ORDERS, descriptor, true).get();
    }

    public void dropTable() throws Exception {
        admin.dropTable(ORDERS, true).get();
    }

    public int upsert(List<Order> orders) throws Exception {
        try (Table table = connection.getTable(ORDERS)) {
            UpsertWriter writer = table.newUpsert().createWriter();
            CompletableFuture<?>[] acks = orders.stream().map(o -> writer.upsert(o.toFluss())).toArray(CompletableFuture[]::new);
            CompletableFuture.allOf(acks).get(60, TimeUnit.SECONDS);
        }
        return orders.size();
    }

    public Optional<Order> lookup(int id) throws Exception {
        try (Table table = connection.getTable(ORDERS)) {
            Lookuper lookuper = table.newLookup().createLookuper();
            InternalRow row = lookuper.lookup(GenericRow.of(id)).get(30, TimeUnit.SECONDS).getSingletonRow();
            return Optional.ofNullable(row).map(Order::fromFluss);
        }
    }

    public List<Order> scan() throws Exception {
        List<Order> orders = new ArrayList<>();
        try (Table table = connection.getTable(ORDERS); BatchScanner scanner = table.newScan().createBatchScanner()) {
            while (true) {
                try (CloseableIterator<InternalRow> batch = scanner.pollBatch(Duration.ofSeconds(10))) {
                    if (batch == null) {
                        break;
                    }
                    batch.forEachRemaining(row -> orders.add(Order.fromFluss(row)));
                }
            }
        }
        return orders;
    }

    public Optional<LakeSnapshot> lakeSnapshot() throws Exception {
        try {
            return Optional.of(admin.getLatestLakeSnapshot(ORDERS).get());
        } catch (ExecutionException e) {
            if (e.getCause() instanceof LakeTableSnapshotNotExistException) {
                return Optional.empty();
            }
            throw e;
        }
    }

    @Override
    public void close() throws Exception {
        connection.close();
    }
}
