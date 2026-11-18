package events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class JobArgsTest {

    @Test
    void theTriggerIntervalIsTheOnlyKnobTheSweepTurnsSoItMustReachTheJob() {
        JobArgs args = JobArgs.parse(new String[] {"--table", "lake.db.t", "--checkpoint", "s3a://c/t", "--trigger-seconds", "15"});
        assertEquals(15, args.triggerSeconds());
        assertEquals("lake.db.t", args.table());
        assertEquals("s3a://c/t", args.checkpoint());
        assertEquals("latest", args.startingOffsets());
        assertEquals("events", args.topic());
    }

    @Test
    void aJobWithoutItsOwnCheckpointCannotRecoverSoItRefusesToStart() {
        assertThrows(IllegalArgumentException.class, () -> JobArgs.parse(new String[] {"--table", "lake.db.t"}));
    }

    @Test
    void aZeroTriggerWouldBeAnUnboundedBatchLoopAndIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> JobArgs.parse(new String[] {"--table", "t", "--checkpoint", "c", "--trigger-seconds", "0"}));
    }
}
