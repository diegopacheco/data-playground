package producer;

import java.time.Clock;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "producer.run", havingValue = "true", matchIfMissing = true)
public class ProducerRunner implements ApplicationRunner {

    private final ProducerSettings settings;

    public ProducerRunner(ProducerSettings settings) {
        this.settings = settings;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        ObjectStore store = new S3ObjectStore(settings);
        store.createBucket();
        BatchWriter writer = new BatchWriter(store, settings.filesPerBatch(), settings.eventsPerFile(), Clock.systemUTC());
        System.out.println("producer mode=" + settings.mode() + " run=" + settings.runId());
        long next = System.currentTimeMillis();
        for (int seq = 1; settings.mode() == ProducerSettings.Mode.STEADY || seq <= settings.batches(); seq++) {
            String batchId = BatchWriter.batchId(settings.runId(), seq);
            writer.write(batchId);
            System.out.println("READY " + batchId);
            if (settings.mode() == ProducerSettings.Mode.STEADY) {
                next += settings.interval().toMillis();
                Thread.sleep(Math.max(0, next - System.currentTimeMillis()));
            }
        }
        System.out.println("producer done run=" + settings.runId());
    }
}
