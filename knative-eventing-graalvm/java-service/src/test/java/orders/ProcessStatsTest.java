package orders;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ProcessStatsTest {

    private static final String STAT =
            "42 (java (main) x) S 1 42 42 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 20 0 12345 1000000 2000 0";

    @Test
    void processStartIsDerivedFromBootUptimeSoItDoesNotInheritWholeSecondBtimeError() {
        long now = 1_700_000_000_000L;
        long started = ProcessStats.startedAtMs(STAT, "130.45 900.00\n", now);
        assertEquals(now - (130_450 - 123_450), started);
    }

    @Test
    void commWithSpacesAndParenthesesDoesNotShiftTheStartTimeField() {
        long started = ProcessStats.startedAtMs(STAT, "123.45 1.00", 10_000);
        assertEquals(10_000, started);
    }

    @Test
    void rssIsReadFromVmRssInKilobytes() {
        String status = "Name:\tjava\nVmPeak:\t  999 kB\nVmRSS:\t   51234 kB\nThreads:\t9\n";
        assertEquals(51234, ProcessStats.rssKb(status));
    }

    @Test
    void missingRssIsReportedAsUnknown() {
        assertEquals(-1, ProcessStats.rssKb("Name:\tx\n"));
    }
}
