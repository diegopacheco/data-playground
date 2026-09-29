package flight;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.vector.BigIntVector;
import org.apache.arrow.vector.Float8Vector;
import org.apache.arrow.vector.IntVector;
import org.apache.arrow.vector.VarCharVector;
import org.apache.arrow.vector.VectorSchemaRoot;
import org.apache.arrow.vector.types.FloatingPointPrecision;
import org.apache.arrow.vector.types.pojo.ArrowType;
import org.apache.arrow.vector.types.pojo.Field;
import org.apache.arrow.vector.types.pojo.Schema;

public final class Revenue {

    public static final Schema SCHEMA = new Schema(List.of(
            Field.nullable("category", ArrowType.Utf8.INSTANCE),
            Field.nullable("orders", new ArrowType.Int(64, true)),
            Field.nullable("units", new ArrowType.Int(64, true)),
            Field.nullable("revenue", new ArrowType.FloatingPoint(FloatingPointPrecision.DOUBLE))));

    private static final class Totals {
        long orders;
        long units;
        double revenue;
    }

    private Revenue() {
    }

    public static VectorSchemaRoot compute(List<VectorSchemaRoot> batches, BufferAllocator allocator) {
        Map<String, Totals> totals = aggregate(batches);
        VectorSchemaRoot root = VectorSchemaRoot.create(SCHEMA, allocator);
        root.allocateNew();
        VarCharVector category = (VarCharVector) root.getVector("category");
        BigIntVector orders = (BigIntVector) root.getVector("orders");
        BigIntVector units = (BigIntVector) root.getVector("units");
        Float8Vector revenue = (Float8Vector) root.getVector("revenue");
        int i = 0;
        for (Map.Entry<String, Totals> e : totals.entrySet()) {
            category.setSafe(i, e.getKey().getBytes(StandardCharsets.UTF_8));
            orders.setSafe(i, e.getValue().orders);
            units.setSafe(i, e.getValue().units);
            revenue.setSafe(i, Math.round(e.getValue().revenue * 100.0) / 100.0);
            i++;
        }
        root.setRowCount(i);
        return root;
    }

    private static Map<String, Totals> aggregate(List<VectorSchemaRoot> batches) {
        Map<String, Totals> totals = new TreeMap<>();
        for (VectorSchemaRoot batch : batches) {
            VarCharVector category = (VarCharVector) batch.getVector("category");
            IntVector quantity = (IntVector) batch.getVector("quantity");
            Float8Vector price = (Float8Vector) batch.getVector("price");
            for (int row = 0; row < batch.getRowCount(); row++) {
                Totals t = totals.computeIfAbsent(new String(category.get(row), StandardCharsets.UTF_8), k -> new Totals());
                t.orders++;
                t.units += quantity.get(row);
                t.revenue += quantity.get(row) * price.get(row);
            }
        }
        return totals;
    }
}
