package microbatch;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class PageLoader {

    public record PageResult(int rows, Watermark watermark) {
    }

    private final WatermarkRepository watermarks;
    private final EventStore events;
    private final LoaderProperties properties;

    public PageLoader(WatermarkRepository watermarks, EventStore events, LoaderProperties properties) {
        this.watermarks = watermarks;
        this.events = events;
        this.properties = properties;
    }

    @Transactional
    public PageResult load(OffsetDateTime cutoff) throws InterruptedException {
        WatermarkRow row = watermarks.lockByJob(properties.job())
                .orElseThrow(() -> new IllegalStateException("no watermark row for job " + properties.job()));
        Watermark current = row.watermark();
        List<Event> page = events.pageAfter(current, cutoff, properties.pageSize());
        if (page.isEmpty()) {
            return new PageResult(0, current);
        }
        events.upsert(properties.targetTable(), page);
        Thread.sleep(properties.holdBeforeCommitMs());
        Watermark next = current.advance(page);
        watermarks.save(row.advancedTo(next, OffsetDateTime.now(ZoneOffset.UTC)));
        return new PageResult(page.size(), next);
    }
}
