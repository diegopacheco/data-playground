package bench;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public final class Verify {

    public static final String FIRST_KEY = "key-000000000000";

    public record Digest(String sha256, int rows) {
    }

    private Verify() {
    }

    public static String sha256(byte[] bytes) {
        return HexFormat.of().formatHex(hasher().digest(bytes));
    }

    public static Digest digest(Store store) {
        MessageDigest hasher = hasher();
        String start = FIRST_KEY;
        int rows = 0;
        while (true) {
            List<Store.Entry> page = store.scan(start, Settings.SCAN_PAGE);
            for (Store.Entry entry : page) {
                hasher.update(Store.bytes(entry.line() + "\n"));
            }
            rows += page.size();
            if (page.size() < Settings.SCAN_PAGE) return new Digest(HexFormat.of().formatHex(hasher.digest()), rows);
            start = page.get(page.size() - 1).key() + "\u0000";
        }
    }

    public static int matchingKeys(Store store, Dataset dataset) {
        int matching = 0;
        for (int position : dataset.positions(Settings.SAMPLE_KEYS, 1, 7)) {
            Store.Entry expected = dataset.entry(position);
            if (Arrays.equals(expected.value(), store.get(expected.key()))) matching++;
        }
        return matching;
    }

    public static int matchingRanges(Store store, Dataset dataset) {
        int matching = 0;
        for (int position : dataset.positions(Settings.SAMPLE_RANGES, Settings.RANGE_LENGTH, 11)) {
            if (dataset.lines(position, Settings.RANGE_LENGTH).equals(lines(store.scan(dataset.entry(position).key(), Settings.RANGE_LENGTH)))) matching++;
        }
        return matching;
    }

    public static String lines(List<Store.Entry> entries) {
        StringBuilder text = new StringBuilder();
        for (Store.Entry entry : entries) {
            text.append(entry.line()).append('\n');
        }
        return text.toString();
    }

    private static MessageDigest hasher() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
