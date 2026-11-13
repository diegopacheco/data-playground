package producer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {"producer.run=false", "S3_ENDPOINT=http://m:9000", "PRODUCER_MODE=burst",
        "RUN_ID=b42", "PRODUCER_BATCHES=12", "FILES_PER_BATCH=8", "EVENTS_PER_FILE=1000"})
class ProducerSettingsBindingTest {

    @Autowired
    ProducerSettings settings;

    @Test
    void burstJobEnvironmentBindsToSettings() {
        assertEquals(new ProducerSettings("http://m:9000", "minioadmin", "minioadmin", "events",
                ProducerSettings.Mode.BURST, "b42", Duration.ofSeconds(5), 12, 8, 1000), settings);
    }

    @Test
    void blankRunIdGetsAFreshOneSoARestartedProducerNeverOverwritesProcessedBatches() {
        ProducerSettings steady = new ProducerSettings("e", "a", "s", "b", ProducerSettings.Mode.STEADY, "",
                Duration.ofSeconds(1), 0, 1, 1);
        assertTrue(steady.runId().matches("s\\d+"), steady.runId());
    }

    @Test
    void runIdWithCharactersThatBreakBatchKeysIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> new ProducerSettings("e", "a", "s", "b",
                ProducerSettings.Mode.STEADY, "S-1/x", Duration.ofSeconds(1), 0, 1, 1));
    }
}
