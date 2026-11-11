package backfill;

import java.time.LocalDate;
import java.util.Map;

public record Settings(
        String worker,
        String runId,
        String pod,
        int index,
        int attempt,
        LocalDate startDay,
        int subRanges,
        int failIndex,
        int fatalIndex) {

    public static Settings fromEnv(Map<String, String> env) {
        return new Settings(
                env.get("WORKER"),
                env.get("RUN_ID"),
                env.get("POD_NAME"),
                Integer.parseInt(env.get("JOB_COMPLETION_INDEX")),
                intOr(env, "INDEX_FAILURES", 0),
                LocalDate.parse(env.get("START_DAY")),
                intOr(env, "SUBRANGES", 4),
                intOr(env, "FAIL_INDEX", -1),
                intOr(env, "FATAL_INDEX", -1));
    }

    private static int intOr(Map<String, String> env, String key, int fallback) {
        String value = env.get(key);
        return value == null || value.isBlank() ? fallback : Integer.parseInt(value);
    }

    public boolean mustFailTransiently() {
        return index == failIndex && attempt == 0;
    }

    public boolean mustFailFatally() {
        return index == fatalIndex;
    }
}
