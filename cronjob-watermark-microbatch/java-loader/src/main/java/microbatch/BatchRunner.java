package microbatch;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class BatchRunner implements CommandLineRunner {

    private final PageLoader loader;
    private final EventStore events;
    private final BatchRunRepository runs;
    private final LoaderProperties properties;

    public BatchRunner(PageLoader loader, EventStore events, BatchRunRepository runs, LoaderProperties properties) {
        this.loader = loader;
        this.events = events;
        this.runs = runs;
        this.properties = properties;
    }

    @Override
    public void run(String... args) throws InterruptedException {
        OffsetDateTime started = OffsetDateTime.now(ZoneOffset.UTC);
        long start = System.nanoTime();
        OffsetDateTime cutoff = events.cutoff(properties.lagSeconds());
        long rows = 0;
        int pages = 0;
        PageLoader.PageResult page = loader.load(cutoff);
        while (page.rows() > 0) {
            rows += page.rows();
            pages++;
            page = loader.load(cutoff);
        }
        long durationMs = Duration.ofNanos(System.nanoTime() - start).toMillis();
        Watermark last = page.watermark();
        runs.save(new BatchRun(null, properties.job(), properties.runner(), started, durationMs, rows, pages,
                last.updatedAt(), last.id()));
        System.out.printf("job=%s runner=%s rows=%d pages=%d duration_ms=%d watermark=%s/%d%n",
                properties.job(), properties.runner(), rows, pages, durationMs, last.updatedAt(), last.id());
    }
}
