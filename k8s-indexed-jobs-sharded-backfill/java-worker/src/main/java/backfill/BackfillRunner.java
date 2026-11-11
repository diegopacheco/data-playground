package backfill;

import java.time.Instant;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class BackfillRunner {

    public static final int EXIT_TRANSIENT = 42;
    public static final int EXIT_FATAL = 3;

    private final Settings settings;
    private final EventSource source;
    private final AggregateWriter writer;

    public BackfillRunner(Settings settings, EventSource source, AggregateWriter writer) {
        this.settings = settings;
        this.source = source;
        this.writer = writer;
    }

    public int run() throws InterruptedException {
        Partition partition = Partition.of(settings.startDay(), settings.index());
        Attempt attempt = new Attempt(settings, partition, Instant.now());
        if (settings.mustFailFatally()) {
            writer.recordFailure(attempt, "fatal");
            System.out.printf("index=%d day=%s fatal%n", settings.index(), partition.day());
            return EXIT_FATAL;
        }
        long began = System.nanoTime();
        Map<String, Stats> aggregates = ConcurrentAggregator.aggregate(partition.window().split(settings.subRanges()), source);
        long rows = Stats.rowCount(aggregates);
        try {
            writer.writePartition(attempt, aggregates, rows);
        } catch (TransientFailure failure) {
            writer.recordFailure(attempt, "transient");
            System.out.printf("index=%d day=%s %s%n", settings.index(), partition.day(), failure.getMessage());
            return EXIT_TRANSIENT;
        }
        double seconds = (System.nanoTime() - began) / 1e9;
        System.out.printf("index=%d day=%s rows=%d categories=%d seconds=%.3f%n",
                settings.index(), partition.day(), rows, aggregates.size(), seconds);
        return 0;
    }
}
