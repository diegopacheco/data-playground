package flight;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.vector.VectorSchemaRoot;

public final class OrderStore implements AutoCloseable {

    private final BufferAllocator allocator;
    private final List<Order> initial;
    private final List<VectorSchemaRoot> batches = new ArrayList<>();

    public OrderStore(List<Order> initial, BufferAllocator allocator) {
        this.allocator = allocator;
        this.initial = List.copyOf(initial);
        reset();
    }

    public synchronized void reset() {
        close();
        batches.add(OrderVectors.toRoot(initial, allocator));
    }

    public synchronized void append(VectorSchemaRoot source) {
        batches.add(OrderVectors.transfer(source, allocator));
    }

    public synchronized <T> T read(Function<List<VectorSchemaRoot>, T> reader) {
        return reader.apply(List.copyOf(batches));
    }

    public synchronized long rows() {
        return batches.stream().mapToLong(VectorSchemaRoot::getRowCount).sum();
    }

    @Override
    public synchronized void close() {
        batches.forEach(VectorSchemaRoot::close);
        batches.clear();
    }
}
