package bench;

import com.apple.foundationdb.Database;
import com.apple.foundationdb.FDB;
import com.apple.foundationdb.KeySelector;
import com.apple.foundationdb.Range;

import java.io.IOException;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class FdbStore implements Store {

    private static final Pattern VERSION = Pattern.compile("\"version\"\\s*:\\s*\"([0-9.]+)\"");
    private static final byte[] FIRST = Store.bytes("key-");
    private static final byte[] LAST = Store.bytes("key.");

    private final Database db;

    public FdbStore() {
        try {
            Path cluster = Files.createTempFile("fdb", ".cluster");
            Files.writeString(cluster, "docker:docker@" + InetAddress.getByName(Settings.FDB_HOST).getHostAddress() + ":4500\n");
            db = FDB.selectAPIVersion(740).open(cluster.toString());
        } catch (IOException e) {
            throw new IllegalStateException("fdb cluster file failed", e);
        }
    }

    @Override
    public String name() {
        return "foundationdb";
    }

    @Override
    public String api() {
        return "transactional key-value API, one read transaction per operation (get, getRange)";
    }

    @Override
    public String version() {
        byte[] status = db.read(tr -> tr.get(Store.bytes("ÿÿ/status/json")).join());
        Matcher matcher = VERSION.matcher(Store.text(status));
        if (matcher.find()) return matcher.group(1);
        throw new IllegalStateException("no fdb version in status json");
    }

    @Override
    public void reset() {
        db.run(tr -> {
            tr.clear(new Range(FIRST, LAST));
            return null;
        });
    }

    @Override
    public void load(List<Entry> batch) {
        db.run(tr -> {
            for (Entry entry : batch) {
                tr.set(Store.bytes(entry.key()), entry.value());
            }
            return null;
        });
    }

    @Override
    public byte[] get(String key) {
        return db.read(tr -> tr.get(Store.bytes(key)).join());
    }

    @Override
    public List<Entry> scan(String start, int limit) {
        return db.read(tr -> tr.getRange(KeySelector.firstGreaterOrEqual(Store.bytes(start)), KeySelector.firstGreaterOrEqual(LAST), limit).asList().join())
                .stream()
                .map(pair -> new Entry(Store.text(pair.getKey()), pair.getValue()))
                .toList();
    }

    @Override
    public void close() {
        db.close();
    }
}
