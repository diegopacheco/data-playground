package bench;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public record Dataset(List<Store.Entry> entries) {

    public static Dataset read() {
        try {
            List<Store.Entry> entries = new ArrayList<>();
            for (String line : Files.readAllLines(Settings.DATASET, StandardCharsets.ISO_8859_1)) {
                int comma = line.indexOf(',');
                entries.add(new Store.Entry(line.substring(0, comma), Store.bytes(line.substring(comma + 1))));
            }
            return new Dataset(entries);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public int size() {
        return entries.size();
    }

    public Store.Entry entry(int index) {
        return entries.get(index);
    }

    public List<List<Store.Entry>> batches() {
        List<List<Store.Entry>> batches = new ArrayList<>();
        for (int from = 0; from < size(); from += Settings.LOAD_BATCH) {
            batches.add(entries.subList(from, Math.min(size(), from + Settings.LOAD_BATCH)));
        }
        return batches;
    }

    public int[] positions(int count, int span, long seed) {
        Random random = new Random(seed);
        int[] positions = new int[count];
        for (int i = 0; i < count; i++) {
            positions[i] = random.nextInt(size() - span + 1);
        }
        return positions;
    }

    public String lines(int from, int count) {
        StringBuilder text = new StringBuilder();
        for (Store.Entry entry : entries.subList(from, from + count)) {
            text.append(entry.line()).append('\n');
        }
        return text.toString();
    }
}
