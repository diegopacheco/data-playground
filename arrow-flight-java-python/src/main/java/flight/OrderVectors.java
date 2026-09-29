package flight;

import java.nio.charset.StandardCharsets;
import java.util.List;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.vector.BigIntVector;
import org.apache.arrow.vector.Float8Vector;
import org.apache.arrow.vector.IntVector;
import org.apache.arrow.vector.VarCharVector;
import org.apache.arrow.vector.VectorLoader;
import org.apache.arrow.vector.VectorSchemaRoot;
import org.apache.arrow.vector.VectorUnloader;
import org.apache.arrow.vector.ipc.message.ArrowRecordBatch;
import org.apache.arrow.vector.types.FloatingPointPrecision;
import org.apache.arrow.vector.types.pojo.ArrowType;
import org.apache.arrow.vector.types.pojo.Field;
import org.apache.arrow.vector.types.pojo.Schema;

public final class OrderVectors {

    public static final Schema SCHEMA = new Schema(List.of(
            Field.nullable("order_id", new ArrowType.Int(64, true)),
            Field.nullable("customer", ArrowType.Utf8.INSTANCE),
            Field.nullable("product", ArrowType.Utf8.INSTANCE),
            Field.nullable("category", ArrowType.Utf8.INSTANCE),
            Field.nullable("quantity", new ArrowType.Int(32, true)),
            Field.nullable("price", new ArrowType.FloatingPoint(FloatingPointPrecision.DOUBLE)),
            Field.nullable("ts", ArrowType.Utf8.INSTANCE)));

    private OrderVectors() {
    }

    public static VectorSchemaRoot toRoot(List<Order> orders, BufferAllocator allocator) {
        VectorSchemaRoot root = VectorSchemaRoot.create(SCHEMA, allocator);
        root.allocateNew();
        BigIntVector id = (BigIntVector) root.getVector("order_id");
        VarCharVector customer = (VarCharVector) root.getVector("customer");
        VarCharVector product = (VarCharVector) root.getVector("product");
        VarCharVector category = (VarCharVector) root.getVector("category");
        IntVector quantity = (IntVector) root.getVector("quantity");
        Float8Vector price = (Float8Vector) root.getVector("price");
        VarCharVector ts = (VarCharVector) root.getVector("ts");
        for (int i = 0; i < orders.size(); i++) {
            Order o = orders.get(i);
            id.setSafe(i, o.orderId());
            customer.setSafe(i, bytes(o.customer()));
            product.setSafe(i, bytes(o.product()));
            category.setSafe(i, bytes(o.category()));
            quantity.setSafe(i, o.quantity());
            price.setSafe(i, o.price());
            ts.setSafe(i, bytes(o.ts()));
        }
        root.setRowCount(orders.size());
        return root;
    }

    public static VectorSchemaRoot transfer(VectorSchemaRoot source, BufferAllocator allocator) {
        VectorSchemaRoot target = VectorSchemaRoot.create(SCHEMA, allocator);
        for (int i = 0; i < source.getFieldVectors().size(); i++) {
            source.getVector(i).makeTransferPair(target.getVector(i)).transfer();
        }
        target.setRowCount(source.getRowCount());
        return target;
    }

    public static void load(VectorSchemaRoot source, VectorSchemaRoot target) {
        try (ArrowRecordBatch batch = new VectorUnloader(source).getRecordBatch()) {
            new VectorLoader(target).load(batch);
        }
    }

    public static boolean compatible(Schema schema) {
        if (schema.getFields().size() != SCHEMA.getFields().size()) {
            return false;
        }
        for (int i = 0; i < schema.getFields().size(); i++) {
            Field a = schema.getFields().get(i);
            Field b = SCHEMA.getFields().get(i);
            if (!a.getName().equals(b.getName()) || !a.getType().equals(b.getType())) {
                return false;
            }
        }
        return true;
    }

    private static byte[] bytes(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }
}
