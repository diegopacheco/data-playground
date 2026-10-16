package bench;

import org.tikv.common.TiConfiguration;
import org.tikv.common.TiSession;
import org.tikv.raw.RawKVClient;
import org.tikv.shade.com.google.protobuf.ByteString;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class TikvStore implements Store {

    private static final Pattern VERSION = Pattern.compile("\"version\":\\s*\"([^\"]+)\"");

    private final TiSession session;
    private final RawKVClient client;

    public TikvStore() {
        session = TiSession.create(TiConfiguration.createRawDefault(Settings.PD_ADDRESS));
        client = session.createRawClient();
    }

    @Override
    public String name() {
        return "tikv";
    }

    @Override
    public String api() {
        return "raw KV API (RawKVClient get, scan, batchPut), PD for region routing";
    }

    @Override
    public String version() {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create("http://" + Settings.PD_ADDRESS + "/pd/api/v1/stores")).build();
            String body = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString()).body();
            Matcher matcher = VERSION.matcher(body);
            if (matcher.find()) return matcher.group(1);
            throw new IllegalStateException("no tikv version in pd stores answer");
        } catch (java.io.IOException | InterruptedException e) {
            throw new IllegalStateException("pd stores api failed", e);
        }
    }

    @Override
    public void reset() {
        client.deleteRange(ByteString.copyFromUtf8("key-"), ByteString.copyFromUtf8("key."));
    }

    @Override
    public void load(List<Entry> batch) {
        Map<ByteString, ByteString> pairs = new HashMap<>();
        for (Entry entry : batch) {
            pairs.put(ByteString.copyFromUtf8(entry.key()), ByteString.copyFrom(entry.value()));
        }
        client.batchPut(pairs);
    }

    @Override
    public byte[] get(String key) {
        return client.get(ByteString.copyFromUtf8(key)).map(ByteString::toByteArray).orElse(null);
    }

    @Override
    public List<Entry> scan(String start, int limit) {
        return client.scan(ByteString.copyFromUtf8(start), limit).stream()
                .map(pair -> new Entry(pair.getKey().toStringUtf8(), pair.getValue().toByteArray()))
                .toList();
    }

    @Override
    public void close() {
        try {
            client.close();
            session.close();
        } catch (Exception e) {
            throw new IllegalStateException("tikv close failed", e);
        }
    }
}
