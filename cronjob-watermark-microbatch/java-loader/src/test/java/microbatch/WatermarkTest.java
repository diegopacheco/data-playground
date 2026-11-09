package microbatch;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class WatermarkTest {

    private static final OffsetDateTime T = OffsetDateTime.of(2026, 11, 7, 12, 0, 0, 0, ZoneOffset.UTC);

    private static Event event(long id, OffsetDateTime at) {
        return new Event(id, "acc", 100, at);
    }

    @Test
    void emptyPageKeepsWatermarkSoNoRowIsSkipped() {
        Watermark current = new Watermark(T, 7);
        assertEquals(current, current.advance(List.of()));
    }

    @Test
    void equalTimestampsAdvanceByIdSoTheRestOfTheTieIsStillPending() {
        Watermark next = new Watermark(T, 1).advance(List.of(event(2, T), event(3, T)));
        assertEquals(new Watermark(T, 3), next);
    }

    @Test
    void laterTimestampWinsEvenWithSmallerIdBecauseUpdatesKeepTheirOldId() {
        Watermark next = new Watermark(T, 50).advance(List.of(event(51, T), event(4, T.plusSeconds(1))));
        assertEquals(new Watermark(T.plusSeconds(1), 4), next);
    }

    @Test
    void neverMovesBackwardsSoAReplayedOldPageCannotReopenAGap() {
        Watermark current = new Watermark(T.plusSeconds(10), 9);
        assertEquals(current, current.advance(List.of(event(1, T), event(2, T.plusSeconds(5)))));
    }

    @Test
    void sameInstantInDifferentOffsetsIsTheSameTimestamp() {
        OffsetDateTime sameInstant = T.withOffsetSameInstant(ZoneOffset.ofHours(-3));
        Watermark next = new Watermark(T, 5).advance(List.of(event(6, sameInstant)));
        assertEquals(6, next.id());
    }
}
