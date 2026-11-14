package etl;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.SequencedMap;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public final class Transform {

    public static final List<String> REGIONS = List.of("AMER", "APAC", "EMEA", "LATAM");
    public static final long MAX_AMOUNT_CENTS = 100_000;

    private Transform() {
    }

    public static long splitmix64(long x) {
        long z = x + 0x9E3779B97F4A7C15L;
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }

    public static Stream<Sale> generate(int rows, long seed) {
        return LongStream.range(0, rows).mapToObj(i -> {
            long z = splitmix64(seed + i);
            String region = REGIONS.get((int) Long.remainderUnsigned(z, REGIONS.size()));
            return new Sale(i, region, Long.remainderUnsigned(z >>> 8, MAX_AMOUNT_CENTS));
        });
    }

    public static Summary summarize(int rows, long seed, int rounds) {
        MessageDigest sha = sha256();
        SequencedMap<String, Long> totals = new LinkedHashMap<>();
        REGIONS.forEach(r -> totals.put(r, 0L));
        byte[] state = new byte[32];
        for (Sale sale : (Iterable<Sale>) generate(rows, seed)::iterator) {
            totals.merge(sale.region(), sale.amountCents(), Long::sum);
            sha.update(state);
            state = sha.digest(sale.line());
            for (int r = 1; r < rounds; r++) {
                state = sha.digest(state);
            }
        }
        return new Summary(rows, totals, HexFormat.of().formatHex(state));
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
