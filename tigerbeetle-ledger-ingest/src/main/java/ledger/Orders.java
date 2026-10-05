package ledger;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.TreeSet;

public final class Orders {

    public record Order(long id, String customer, String category, long quantity, long cents) {
    }

    private Orders() {
    }

    public static List<Order> load(Path csv) throws IOException {
        return Files.readAllLines(csv).stream()
                .skip(1)
                .filter(line -> !line.isBlank())
                .map(Orders::parse)
                .toList();
    }

    public static List<String> customers(List<Order> orders) {
        return List.copyOf(new TreeSet<>(orders.stream().map(Order::customer).toList()));
    }

    public static List<String> categories(List<Order> orders) {
        return List.copyOf(new TreeSet<>(orders.stream().map(Order::category).toList()));
    }

    private static Order parse(String line) {
        String[] f = line.split(",");
        long quantity = Long.parseLong(f[4].trim());
        long priceCents = new BigDecimal(f[5].trim()).movePointRight(2).longValueExact();
        return new Order(Long.parseLong(f[0].trim()), f[1].trim(), f[3].trim(), quantity, quantity * priceCents);
    }
}
