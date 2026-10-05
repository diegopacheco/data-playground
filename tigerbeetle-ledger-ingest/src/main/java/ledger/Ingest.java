package ledger;

import java.nio.file.Files;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class Ingest {

    private Ingest() {
    }

    public static void main(String[] args) throws Exception {
        List<Orders.Order> orders = Orders.load(Settings.ORDERS_CSV);
        List<String> customers = Orders.customers(orders);
        List<String> categories = Orders.categories(orders);
        List<Ledger.NewTransfer> transfers = orders.stream()
                .map(o -> new Ledger.NewTransfer(o.id(), Chart.customer(o.customer()), Chart.category(o.category()),
                        o.cents(), Settings.ORDERS_LEDGER, Settings.ORDER_CODE))
                .toList();
        try (Ledger ledger = Ledger.connect()) {
            Ledger.Outcome accounts = ledger.createAccounts(Chart.orderAccounts(customers, categories));
            System.out.printf("accounts: %d created, %d already existed (%d customers, %d categories)%n",
                    accounts.created(), accounts.existing(), customers.size(), categories.size());
            long start = System.nanoTime();
            Ledger.Outcome outcome = ledger.createTransfers(transfers, 1);
            double seconds = (System.nanoTime() - start) / 1e9;
            System.out.printf("transfers: %d created, %d already existed, %d batches, %.3fs%n",
                    outcome.created(), outcome.existing(), outcome.batches(), seconds);
            Map<Long, Ledger.Balance> balances = ledger.lookup(categories.stream().map(Chart::category).toList());
            System.out.printf("%-12s %15s%n", "category", "credits_cents");
            for (String c : categories) {
                System.out.printf("%-12s %15d%n", c, balances.get(Chart.category(c)).creditsPosted());
            }
            Files.createDirectories(Settings.RUN_DIR);
            Files.writeString(Settings.RUN_DIR.resolve("ingest.json"), String.format(Locale.ROOT,
                    "{\"orders\":%d,\"created\":%d,\"existing\":%d,\"batches\":%d,\"seconds\":%.6f}",
                    orders.size(), outcome.created(), outcome.existing(), outcome.batches(), seconds));
        }
    }
}
