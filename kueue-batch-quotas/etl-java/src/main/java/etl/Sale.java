package etl;

import java.nio.charset.StandardCharsets;

public record Sale(long rowId, String region, long amountCents) {

    public byte[] line() {
        return (rowId + "," + region + "," + amountCents).getBytes(StandardCharsets.UTF_8);
    }
}
