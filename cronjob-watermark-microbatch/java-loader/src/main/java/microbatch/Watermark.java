package microbatch;

import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;

public record Watermark(OffsetDateTime updatedAt, long id) {

    private static final Comparator<Watermark> ORDER = Comparator
            .comparing(Watermark::updatedAt, OffsetDateTime.timeLineOrder())
            .thenComparingLong(Watermark::id);

    public static Watermark of(Event event) {
        return new Watermark(event.updatedAt(), event.id());
    }

    public Watermark advance(List<Event> page) {
        return page.stream()
                .map(Watermark::of)
                .reduce(this, (a, b) -> ORDER.compare(a, b) >= 0 ? a : b);
    }
}
