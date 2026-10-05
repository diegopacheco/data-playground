package ledger;

import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public final class Chart {

    private Chart() {
    }

    public static long customer(String name) {
        return Ledger.idOf("customer:" + name);
    }

    public static long category(String name) {
        return Ledger.idOf("revenue:" + name);
    }

    public static long bench(int index) {
        return Ledger.idOf("bench:" + index);
    }

    public static List<Ledger.NewAccount> orderAccounts(List<String> customers, List<String> categories) {
        return Stream.concat(
                customers.stream().map(c -> new Ledger.NewAccount(customer(c), Settings.ORDERS_LEDGER, Settings.CUSTOMER_CODE)),
                categories.stream().map(c -> new Ledger.NewAccount(category(c), Settings.ORDERS_LEDGER, Settings.REVENUE_CODE))
        ).toList();
    }

    public static List<Long> benchIds(int count) {
        return IntStream.range(0, count).mapToObj(Chart::bench).toList();
    }
}
