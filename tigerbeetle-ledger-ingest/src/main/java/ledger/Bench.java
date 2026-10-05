package ledger;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class Bench {

    private static final int IN_FLIGHT = 4;
    private static final int INDEX_BITS = 20;

    private Bench() {
    }

    public static void main(String[] args) throws Exception {
        int count = Settings.BENCH_TRANSFERS;
        int accountCount = Settings.BENCH_ACCOUNTS;
        if (count > 1 << INDEX_BITS) {
            throw new IllegalArgumentException("BENCH_TRANSFERS must be at most " + (1 << INDEX_BITS));
        }
        List<Long> accountIds = Chart.benchIds(accountCount);
        List<Ledger.NewTransfer> transfers = generate(count, accountIds, System.currentTimeMillis() << INDEX_BITS);
        long amountTotal = transfers.stream().mapToLong(Ledger.NewTransfer::amount).sum();
        try (Ledger ledger = Ledger.connect()) {
            ledger.createAccounts(accountIds.stream()
                    .map(id -> new Ledger.NewAccount(id, Settings.BENCH_LEDGER, Settings.BENCH_CODE)).toList());
            long before = creditsTotal(ledger.lookup(accountIds));
            long start = System.nanoTime();
            Ledger.Outcome outcome = ledger.createTransfers(transfers, IN_FLIGHT);
            double seconds = (System.nanoTime() - start) / 1e9;
            long delta = creditsTotal(ledger.lookup(accountIds)) - before;
            boolean verified = outcome.created() == count && delta == amountTotal;
            double tps = count / seconds;
            System.out.printf(Locale.ROOT, "bench: %d transfers, %d batches of %d, %d in flight, %.3fs, %.0f transfers/sec%n",
                    count, outcome.batches(), Settings.BATCH_SIZE, IN_FLIGHT, seconds, tps);
            System.out.printf("bench: amount total %d, credits delta %d, verified %s%n", amountTotal, delta, verified);
            Files.createDirectories(Settings.RUN_DIR);
            Files.writeString(Settings.RUN_DIR.resolve("bench.json"), String.format(Locale.ROOT,
                    "{\"transfers\":%d,\"accounts\":%d,\"batch_size\":%d,\"batches\":%d,\"in_flight\":%d,"
                            + "\"seconds\":%.6f,\"tps\":%.0f,\"amount_total\":%d,\"credits_delta\":%d,\"verified\":%s}",
                    count, accountCount, Settings.BATCH_SIZE, outcome.batches(), IN_FLIGHT,
                    seconds, tps, amountTotal, delta, verified));
            if (!verified) {
                throw new IllegalStateException("bench balances do not match the generated amounts");
            }
        }
    }

    private static List<Ledger.NewTransfer> generate(int count, List<Long> accountIds, long idBase) {
        int n = accountIds.size();
        List<Ledger.NewTransfer> transfers = new ArrayList<>(count);
        for (int i = 0; i < count; i++) {
            int debit = i % n;
            int credit = (int) ((i * 31L + 7) % n);
            if (credit == debit) {
                credit = (credit + 1) % n;
            }
            long amount = 1 + (i * 7919L) % 10_000;
            transfers.add(new Ledger.NewTransfer(idBase | i, accountIds.get(debit), accountIds.get(credit),
                    amount, Settings.BENCH_LEDGER, Settings.BENCH_TRANSFER_CODE));
        }
        return transfers;
    }

    private static long creditsTotal(Map<Long, Ledger.Balance> balances) {
        return balances.values().stream().mapToLong(Ledger.Balance::creditsPosted).sum();
    }
}
