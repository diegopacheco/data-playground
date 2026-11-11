package backfill;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class SettingsTest {

    private static Settings with(Map<String, String> overrides) {
        Map<String, String> env = new HashMap<>(Map.of(
                "WORKER", "java",
                "RUN_ID", "backfill-java-1",
                "POD_NAME", "backfill-java-1-3-abcde",
                "JOB_COMPLETION_INDEX", "3",
                "START_DAY", "2026-10-01",
                "SUBRANGES", "4",
                "FAIL_INDEX", "3",
                "FATAL_INDEX", "-1"));
        env.putAll(overrides);
        return Settings.fromEnv(env);
    }

    @Test
    void missingFailureCountAnnotationMeansFirstAttempt() {
        assertEquals(0, with(Map.of("INDEX_FAILURES", "")).attempt());
    }

    @Test
    void forcedTransientFailureHitsOnlyTheFirstAttemptOfItsIndexSoTheRetryCanSucceed() {
        assertTrue(with(Map.of("INDEX_FAILURES", "0")).mustFailTransiently());
        assertFalse(with(Map.of("INDEX_FAILURES", "1")).mustFailTransiently());
        assertFalse(with(Map.of("JOB_COMPLETION_INDEX", "4", "INDEX_FAILURES", "0")).mustFailTransiently());
    }

    @Test
    void fatalFailureAppliesOnEveryAttemptBecauseRetryingCannotFixIt() {
        assertTrue(with(Map.of("FAIL_INDEX", "-1", "FATAL_INDEX", "3", "INDEX_FAILURES", "0")).mustFailFatally());
        assertTrue(with(Map.of("FAIL_INDEX", "-1", "FATAL_INDEX", "3", "INDEX_FAILURES", "2")).mustFailFatally());
        assertFalse(with(Map.of("FATAL_INDEX", "3", "JOB_COMPLETION_INDEX", "4")).mustFailFatally());
    }
}
