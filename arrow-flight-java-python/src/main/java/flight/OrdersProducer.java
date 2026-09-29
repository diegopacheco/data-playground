package flight;

import java.nio.charset.StandardCharsets;
import java.util.List;
import org.apache.arrow.flight.Action;
import org.apache.arrow.flight.ActionType;
import org.apache.arrow.flight.CallStatus;
import org.apache.arrow.flight.Criteria;
import org.apache.arrow.flight.FlightDescriptor;
import org.apache.arrow.flight.FlightEndpoint;
import org.apache.arrow.flight.FlightInfo;
import org.apache.arrow.flight.FlightStream;
import org.apache.arrow.flight.NoOpFlightProducer;
import org.apache.arrow.flight.PutResult;
import org.apache.arrow.flight.Result;
import org.apache.arrow.flight.Ticket;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.vector.VectorSchemaRoot;

public final class OrdersProducer extends NoOpFlightProducer {

    public static final String ORDERS = "orders";
    public static final String REVENUE = "revenue_by_category";
    public static final String BENCH = "bench";
    public static final String RESET = "reset";

    private final OrderStore store;
    private final BenchData bench;
    private final BufferAllocator allocator;

    public OrdersProducer(OrderStore store, BenchData bench, BufferAllocator allocator) {
        this.store = store;
        this.bench = bench;
        this.allocator = allocator;
    }

    @Override
    public void listFlights(CallContext context, Criteria criteria, StreamListener<FlightInfo> listener) {
        for (String name : List.of(ORDERS, REVENUE, BENCH)) {
            listener.onNext(info(name));
        }
        listener.onCompleted();
    }

    @Override
    public FlightInfo getFlightInfo(CallContext context, FlightDescriptor descriptor) {
        return info(name(descriptor));
    }

    @Override
    public void getStream(CallContext context, Ticket ticket, ServerStreamListener listener) {
        switch (new String(ticket.getBytes(), StandardCharsets.UTF_8)) {
            case ORDERS -> store.read(batches -> stream(batches, listener));
            case REVENUE -> {
                try (VectorSchemaRoot revenue = store.read(batches -> Revenue.compute(batches, allocator))) {
                    listener.start(revenue);
                    listener.putNext();
                    listener.completed();
                }
            }
            case BENCH -> stream(bench.batches(), listener);
            default -> listener.error(CallStatus.NOT_FOUND.withDescription("unknown ticket").toRuntimeException());
        }
    }

    @Override
    public Runnable acceptPut(CallContext context, FlightStream flightStream, StreamListener<PutResult> ackStream) {
        return () -> {
            if (!ORDERS.equals(name(flightStream.getDescriptor()))) {
                ackStream.onError(CallStatus.INVALID_ARGUMENT.withDescription("only orders accepts uploads").toRuntimeException());
                return;
            }
            if (!OrderVectors.compatible(flightStream.getSchema())) {
                ackStream.onError(CallStatus.INVALID_ARGUMENT.withDescription("schema must be " + OrderVectors.SCHEMA).toRuntimeException());
                return;
            }
            while (flightStream.next()) {
                store.append(flightStream.getRoot());
            }
            ackStream.onCompleted();
        };
    }

    @Override
    public void doAction(CallContext context, Action action, StreamListener<Result> listener) {
        if (!RESET.equals(action.getType())) {
            listener.onError(CallStatus.NOT_FOUND.withDescription("unknown action").toRuntimeException());
            return;
        }
        store.reset();
        listener.onNext(new Result(Long.toString(store.rows()).getBytes(StandardCharsets.UTF_8)));
        listener.onCompleted();
    }

    @Override
    public void listActions(CallContext context, StreamListener<ActionType> listener) {
        listener.onNext(new ActionType(RESET, "restore orders to the CSV content"));
        listener.onCompleted();
    }

    private FlightInfo info(String name) {
        FlightDescriptor descriptor = FlightDescriptor.path(name);
        FlightEndpoint endpoint = new FlightEndpoint(new Ticket(name.getBytes(StandardCharsets.UTF_8)));
        return switch (name) {
            case ORDERS -> new FlightInfo(OrderVectors.SCHEMA, descriptor, List.of(endpoint), -1, store.rows());
            case REVENUE -> new FlightInfo(Revenue.SCHEMA, descriptor, List.of(endpoint), -1, -1);
            case BENCH -> new FlightInfo(OrderVectors.SCHEMA, descriptor, List.of(endpoint), bench.bytes(), bench.rows());
            default -> throw CallStatus.NOT_FOUND.withDescription("unknown flight " + name).toRuntimeException();
        };
    }

    private static String name(FlightDescriptor descriptor) {
        if (!descriptor.isCommand() && descriptor.getPath().size() == 1) {
            return descriptor.getPath().get(0);
        }
        throw CallStatus.INVALID_ARGUMENT.withDescription("descriptor must be a single path").toRuntimeException();
    }

    private Void stream(List<VectorSchemaRoot> batches, ServerStreamListener listener) {
        try (VectorSchemaRoot root = VectorSchemaRoot.create(OrderVectors.SCHEMA, allocator)) {
            listener.start(root);
            for (VectorSchemaRoot batch : batches) {
                OrderVectors.load(batch, root);
                listener.putNext();
            }
            listener.completed();
        }
        return null;
    }
}
