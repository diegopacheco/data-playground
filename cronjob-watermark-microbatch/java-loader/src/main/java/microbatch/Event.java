package microbatch;

import java.time.OffsetDateTime;

public record Event(long id, String account, long amountCents, OffsetDateTime updatedAt) {
}
