package com.github.diegopacheco.flussflink;

import org.apache.flink.types.Row;
import org.apache.fluss.row.BinaryString;
import org.apache.fluss.row.Decimal;
import org.apache.fluss.row.GenericRow;
import org.apache.fluss.row.InternalRow;

import java.math.BigDecimal;

public record Order(int id, String customer, String product, String category, int quantity, BigDecimal price, String ts) {

    public static final String COLUMNS = "order_id, customer, product, category, quantity, price, ts";

    public static Order fromCsv(String line) {
        String[] f = line.split(",", -1);
        return new Order(Integer.parseInt(f[0].trim()), f[1], f[2], f[3], Integer.parseInt(f[4].trim()), new BigDecimal(f[5].trim()), f[6].trim());
    }

    public static Order fromFluss(InternalRow row) {
        return new Order(row.getInt(0), row.getString(1).toString(), row.getString(2).toString(), row.getString(3).toString(),
                row.getInt(4), row.getDecimal(5, 10, 2).toBigDecimal(), row.getString(6).toString());
    }

    public static Order fromFlink(Row row) {
        return new Order((Integer) row.getField(0), (String) row.getField(1), (String) row.getField(2), (String) row.getField(3),
                (Integer) row.getField(4), (BigDecimal) row.getField(5), (String) row.getField(6));
    }

    public GenericRow toFluss() {
        return GenericRow.of(id, BinaryString.fromString(customer), BinaryString.fromString(product), BinaryString.fromString(category),
                quantity, Decimal.fromBigDecimal(price, 10, 2), BinaryString.fromString(ts));
    }

    public BigDecimal revenue() {
        return price.multiply(BigDecimal.valueOf(quantity));
    }

    public String toJson() {
        return "{\"order_id\":" + id + ",\"customer\":" + Json.str(customer) + ",\"product\":" + Json.str(product)
                + ",\"category\":" + Json.str(category) + ",\"quantity\":" + quantity + ",\"price\":" + price.toPlainString()
                + ",\"ts\":" + Json.str(ts) + "}";
    }
}
