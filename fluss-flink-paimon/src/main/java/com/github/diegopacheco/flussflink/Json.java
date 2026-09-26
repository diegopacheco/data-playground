package com.github.diegopacheco.flussflink;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.Map;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.function.Function;

public final class Json {

    private Json() {
    }

    public static String str(Object value) {
        if (value == null) {
            return "null";
        }
        return "\"" + String.valueOf(value).replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ") + "\"";
    }

    public static <T> String array(Collection<T> items, Function<T, String> mapper) {
        StringJoiner json = new StringJoiner(",", "[", "]");
        items.forEach(item -> json.add(mapper.apply(item)));
        return json.toString();
    }

    public static String orders(Collection<Order> orders) {
        return array(orders, Order::toJson);
    }

    public static String categories(Collection<Order> orders) {
        Map<String, long[]> counts = new TreeMap<>();
        Map<String, BigDecimal> revenue = new TreeMap<>();
        for (Order o : orders) {
            long[] c = counts.computeIfAbsent(o.category(), k -> new long[2]);
            c[0]++;
            c[1] += o.quantity();
            revenue.merge(o.category(), o.revenue(), BigDecimal::add);
        }
        return array(counts.keySet(), k -> "{\"category\":" + str(k) + ",\"orders\":" + counts.get(k)[0]
                + ",\"units\":" + counts.get(k)[1] + ",\"revenue\":" + revenue.get(k).setScale(2).toPlainString() + "}");
    }

    public static String totals(Collection<Order> orders) {
        BigDecimal revenue = orders.stream().map(Order::revenue).reduce(BigDecimal.ZERO, BigDecimal::add).setScale(2);
        long units = orders.stream().mapToLong(Order::quantity).sum();
        return "{\"orders\":" + orders.size() + ",\"units\":" + units + ",\"revenue\":" + revenue.toPlainString() + "}";
    }
}
