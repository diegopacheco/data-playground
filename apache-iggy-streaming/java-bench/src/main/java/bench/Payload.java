package bench;

import java.nio.ByteBuffer;
import java.time.Instant;

public final class Payload {

    public static final int HEADER_SIZE = Long.BYTES * 2;

    public record Stamp(long seq, long sentAtUs) {
    }

    private Payload() {
    }

    public static long nowUs() {
        Instant now = Instant.now();
        return now.getEpochSecond() * 1_000_000L + now.getNano() / 1_000;
    }

    public static byte[] encode(long seq, long sentAtUs, int size) {
        if (size < HEADER_SIZE) {
            throw new IllegalArgumentException("message size " + size + " is below the " + HEADER_SIZE + " byte header");
        }
        return ByteBuffer.allocate(size).putLong(seq).putLong(sentAtUs).array();
    }

    public static Stamp decode(byte[] data) {
        ByteBuffer buffer = ByteBuffer.wrap(data);
        return new Stamp(buffer.getLong(), buffer.getLong());
    }
}
