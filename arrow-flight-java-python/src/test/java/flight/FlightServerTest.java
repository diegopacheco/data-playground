package flight;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import org.apache.arrow.flight.Action;
import org.apache.arrow.flight.AsyncPutListener;
import org.apache.arrow.flight.FlightClient;
import org.apache.arrow.flight.FlightDescriptor;
import org.apache.arrow.flight.FlightRuntimeException;
import org.apache.arrow.flight.FlightServer;
import org.apache.arrow.flight.FlightStream;
import org.apache.arrow.flight.Location;
import org.apache.arrow.flight.Ticket;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.memory.RootAllocator;
import org.apache.arrow.vector.BigIntVector;
import org.apache.arrow.vector.Float8Vector;
import org.apache.arrow.vector.VarCharVector;
import org.apache.arrow.vector.VectorSchemaRoot;
import org.apache.arrow.vector.types.pojo.ArrowType;
import org.apache.arrow.vector.types.pojo.Field;
import org.apache.arrow.vector.types.pojo.Schema;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FlightServerTest {

    private static final long BENCH_ROWS = 150_000;

    private BufferAllocator allocator;
    private OrderStore store;
    private BenchData bench;
    private FlightServer server;
    private FlightClient client;
    private List<Order> orders;

    @BeforeEach
    void start() throws Exception {
        orders = Main.load(Path.of("data/orders.csv"));
        allocator = new RootAllocator();
        store = new OrderStore(orders, allocator);
        bench = new BenchData(orders, BENCH_ROWS, allocator);
        server = FlightServer.builder(allocator, Location.forGrpcInsecure("localhost", 0),
                new OrdersProducer(store, bench, allocator)).build().start();
        client = FlightClient.builder(allocator, Location.forGrpcInsecure("localhost", server.getPort())).build();
    }

    @AfterEach
    void stop() throws Exception {
        client.close();
        server.close();
        store.close();
        bench.close();
        allocator.close();
    }

    @Test
    void ordersStreamCarriesEveryCsvRow() throws Exception {
        assertEquals(200, orders.size());
        assertEquals(orders.size(), countRows(OrdersProducer.ORDERS));
    }

    @Test
    void revenueIsComputedServerSideFromQuantityTimesPrice() throws Exception {
        assertEquals(expectedRevenue(orders), fetchRevenue());
    }

    @Test
    void uploadedOrdersChangeBothStreamsAndResetRestoresTheCsv() throws Exception {
        List<Order> upload = List.of(
                new Order(900001, "Ana Lima", "Chess Board", "games", 2, 10.5, "2026-09-01T10:00:00Z"),
                new Order(900002, "Rui Costa", "Novel", "books", 3, 20.25, "2026-09-01T11:00:00Z"));
        try (VectorSchemaRoot root = OrderVectors.toRoot(upload, allocator)) {
            FlightClient.ClientStreamListener put = client.startPut(FlightDescriptor.path(OrdersProducer.ORDERS), root, new AsyncPutListener());
            put.putNext();
            put.completed();
            put.getResult();
        }
        List<Order> all = new java.util.ArrayList<>(orders);
        all.addAll(upload);
        assertEquals(202, countRows(OrdersProducer.ORDERS));
        assertEquals(expectedRevenue(all), fetchRevenue());
        assertEquals(21.0, fetchRevenue().get("games"));

        client.doAction(new Action(OrdersProducer.RESET)).forEachRemaining(r -> { });
        assertEquals(200, countRows(OrdersProducer.ORDERS));
        assertEquals(expectedRevenue(orders), fetchRevenue());
    }

    @Test
    void uploadWithForeignSchemaIsRejectedAndStoreIsUntouched() throws Exception {
        Schema wrong = new Schema(List.of(Field.nullable("order_id", new ArrowType.Int(64, true))));
        try (VectorSchemaRoot root = VectorSchemaRoot.create(wrong, allocator)) {
            ((BigIntVector) root.getVector(0)).allocateNew(1);
            ((BigIntVector) root.getVector(0)).set(0, 1L);
            root.setRowCount(1);
            FlightClient.ClientStreamListener put = client.startPut(FlightDescriptor.path(OrdersProducer.ORDERS), root, new AsyncPutListener());
            put.putNext();
            put.completed();
            assertThrows(FlightRuntimeException.class, put::getResult);
        }
        assertEquals(200, countRows(OrdersProducer.ORDERS));
    }

    @Test
    void benchStreamIsTheCsvRepeatedWithSequentialIds() throws Exception {
        long rows = 0;
        long lastId = 0;
        try (FlightStream stream = client.getStream(new Ticket(OrdersProducer.BENCH.getBytes(StandardCharsets.UTF_8)))) {
            while (stream.next()) {
                BigIntVector ids = (BigIntVector) stream.getRoot().getVector("order_id");
                for (int i = 0; i < ids.getValueCount(); i++) {
                    assertEquals(rows + i + 1, ids.get(i));
                }
                rows += stream.getRoot().getRowCount();
                lastId = ids.get(ids.getValueCount() - 1);
            }
        }
        assertEquals(BENCH_ROWS, rows);
        assertEquals(BENCH_ROWS, lastId);
        assertEquals(BENCH_ROWS, client.getInfo(FlightDescriptor.path(OrdersProducer.BENCH)).getRecords());
    }

    private long countRows(String ticket) throws Exception {
        long rows = 0;
        try (FlightStream stream = client.getStream(new Ticket(ticket.getBytes(StandardCharsets.UTF_8)))) {
            while (stream.next()) {
                rows += stream.getRoot().getRowCount();
            }
        }
        return rows;
    }

    private Map<String, Double> fetchRevenue() throws Exception {
        Map<String, Double> result = new TreeMap<>();
        try (FlightStream stream = client.getStream(new Ticket(OrdersProducer.REVENUE.getBytes(StandardCharsets.UTF_8)))) {
            while (stream.next()) {
                VarCharVector category = (VarCharVector) stream.getRoot().getVector("category");
                Float8Vector revenue = (Float8Vector) stream.getRoot().getVector("revenue");
                for (int i = 0; i < stream.getRoot().getRowCount(); i++) {
                    result.put(new String(category.get(i), StandardCharsets.UTF_8), revenue.get(i));
                }
            }
        }
        return result;
    }

    private static Map<String, Double> expectedRevenue(List<Order> rows) {
        return rows.stream().collect(Collectors.groupingBy(Order::category, TreeMap::new,
                Collectors.collectingAndThen(Collectors.summingDouble(o -> o.quantity() * o.price()),
                        v -> Math.round(v * 100.0) / 100.0)));
    }
}
