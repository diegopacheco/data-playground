package producer;

import java.time.Duration;
import java.time.Instant;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "producer")
public record ProducerSettings(
        String endpoint,
        String accessKey,
        String secretKey,
        String bucket,
        Mode mode,
        String runId,
        Duration interval,
        int batches,
        int filesPerBatch,
        int eventsPerFile) {

    public enum Mode { STEADY, BURST }

    public ProducerSettings {
        if (filesPerBatch < 1 || eventsPerFile < 1) {
            throw new IllegalArgumentException("files-per-batch and events-per-file must be >= 1");
        }
        if (mode == Mode.BURST && batches < 1) {
            throw new IllegalArgumentException("burst mode needs batches >= 1");
        }
        if (runId == null || runId.isBlank()) {
            runId = (mode == Mode.BURST ? "b" : "s") + Instant.now().getEpochSecond();
        }
        if (!runId.matches("[a-z0-9]+")) {
            throw new IllegalArgumentException("run-id must be lowercase letters and digits");
        }
    }
}
