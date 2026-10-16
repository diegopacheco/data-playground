package bench;

import java.nio.charset.StandardCharsets;
import java.util.List;

public interface Store extends AutoCloseable {

    record Entry(String key, byte[] value) {

        String line() {
            return key + "," + new String(value, StandardCharsets.ISO_8859_1);
        }
    }

    String name();

    String api();

    String version();

    void reset();

    void load(List<Entry> batch);

    byte[] get(String key);

    List<Entry> scan(String start, int limit);

    @Override
    void close();

    static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.ISO_8859_1);
    }

    static String text(byte[] bytes) {
        return new String(bytes, StandardCharsets.ISO_8859_1);
    }

    static List<Store> openAll() {
        return List.of(new TikvStore(), new ScyllaStore(), new FdbStore());
    }
}
