package microbatch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class LoaderPropertiesTest {

    @Test
    void targetTableIsDerivedFromJobSoEachLoaderOwnsItsTable() {
        assertEquals("target_java", new LoaderProperties("java", "pod", 500, 2, 0).targetTable());
    }

    @Test
    void jobNameIsRejectedWhenItCouldInjectSqlIntoTheTableName() {
        assertThrows(IllegalArgumentException.class,
                () -> new LoaderProperties("java; DROP TABLE source_events", "pod", 500, 2, 0));
    }

    @Test
    void zeroPageSizeIsRejectedBecauseTheLoadLoopWouldNeverAdvance() {
        assertThrows(IllegalArgumentException.class, () -> new LoaderProperties("java", "pod", 0, 2, 0));
    }
}
