package flight;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.vector.VectorSchemaRoot;

public final class BenchData implements AutoCloseable {

    public static final String HEADER = "order_id,customer,product,category,quantity,price,ts";
    private static final int BATCH_SIZE = 65_536;

    private final List<VectorSchemaRoot> batches = new ArrayList<>();
    private final Path csv;
    private final long rows;

    public BenchData(List<Order> base, long rows, BufferAllocator allocator) throws IOException {
        this.rows = rows;
        this.csv = Files.createTempFile("bench-orders", ".csv");
        try (BufferedWriter out = Files.newBufferedWriter(csv, StandardCharsets.UTF_8)) {
            out.write(HEADER);
            out.write('\n');
            for (long start = 0; start < rows; start += BATCH_SIZE) {
                List<Order> chunk = new ArrayList<>();
                for (long i = start; i < Math.min(rows, start + BATCH_SIZE); i++) {
                    Order o = row(base, i);
                    chunk.add(o);
                    out.write(o.toCsv());
                    out.write('\n');
                }
                batches.add(OrderVectors.toRoot(chunk, allocator));
            }
        }
    }

    public static Order row(List<Order> base, long i) {
        return base.get((int) (i % base.size())).withId(i + 1);
    }

    public List<VectorSchemaRoot> batches() {
        return batches;
    }

    public Path csv() {
        return csv;
    }

    public long rows() {
        return rows;
    }

    public long bytes() {
        return batches.stream().mapToLong(b -> b.getFieldVectors().stream().mapToLong(v -> v.getBufferSize()).sum()).sum();
    }

    @Override
    public void close() throws IOException {
        batches.forEach(VectorSchemaRoot::close);
        Files.deleteIfExists(csv);
    }
}
