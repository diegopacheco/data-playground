package bench;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

public final class Dataset {

    private Dataset() {
    }

    public static List<Order> generate(Path baseCsv, int rows) throws IOException {
        List<Order> base = Files.readAllLines(baseCsv).stream().skip(1).filter(l -> !l.isBlank()).map(Order::parse).toList();
        List<Order> out = new ArrayList<>(rows);
        for (int i = 0; i < rows; i++) {
            Order b = base.get(i % base.size());
            int quantity = b.quantity() + (i / base.size()) % 5;
            out.add(new Order(i + 1L, b.customer(), b.product(), b.category(), quantity, b.price(), b.ts()));
        }
        return out;
    }

    public static void write(Path file, List<Order> orders) throws IOException {
        List<String> lines = new ArrayList<>(orders.size() + 1);
        lines.add("order_id,customer,product,category,quantity,price,ts");
        orders.forEach(o -> lines.add(o.csv()));
        Files.write(file, lines);
    }

    public static List<String> categories(List<Order> orders) {
        TreeSet<String> set = new TreeSet<>();
        orders.forEach(o -> set.add(o.category()));
        return List.copyOf(set);
    }
}
