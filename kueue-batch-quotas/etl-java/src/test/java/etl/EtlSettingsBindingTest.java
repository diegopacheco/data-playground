package etl;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {"etl.run=false", "JOB_NAME=etl-7", "POD_NAME=etl-7-abc", "TEAM=reports",
        "ETL_ROWS=42", "ETL_SEED=9", "ETL_ROUNDS=5", "RESULTS_DIR=/tmp/r"})
class EtlSettingsBindingTest {

    @Autowired
    EtlSettings settings;

    @Test
    void jobEnvironmentFromTheKueueJobTemplateBindsToSettings() {
        assertEquals(new EtlSettings("etl-7", "etl-7-abc", "reports", 42, 9, 5, Path.of("/tmp/r")), settings);
    }
}
