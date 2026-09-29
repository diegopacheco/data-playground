package flight;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.apache.arrow.flight.FlightServer;
import org.apache.arrow.flight.Location;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.memory.RootAllocator;

public final class Main {

    public static void main(String[] args) throws Exception {
        int flightPort = Integer.parseInt(env("FLIGHT_PORT", "21300"));
        int httpPort = Integer.parseInt(env("HTTP_PORT", "21301"));
        long benchRows = Long.parseLong(env("BENCH_ROWS", "1000000"));
        List<Order> orders = load(Path.of(env("ORDERS_CSV", "data/orders.csv")));

        BufferAllocator allocator = new RootAllocator();
        OrderStore store = new OrderStore(orders, allocator);
        BenchData bench = new BenchData(orders, benchRows, allocator);
        FlightServer server = FlightServer.builder(allocator, Location.forGrpcInsecure("0.0.0.0", flightPort),
                new OrdersProducer(store, bench, allocator)).build().start();
        CsvHttpServer http = new CsvHttpServer(httpPort, bench.csv());
        http.start();
        System.out.printf("flight grpc://0.0.0.0:%d orders=%d bench=%d csv http://0.0.0.0:%d/bench.csv%n",
                flightPort, store.rows(), bench.rows(), httpPort);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                http.close();
                server.shutdown();
                server.awaitTermination();
                store.close();
                bench.close();
                allocator.close();
            } catch (Exception e) {
                System.err.println("shutdown failed: " + e.getMessage());
            }
        }));
        server.awaitTermination();
    }

    public static List<Order> load(Path csv) throws Exception {
        try (var lines = Files.lines(csv)) {
            return lines.skip(1).filter(l -> !l.isBlank()).map(Order::parse).toList();
        }
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
