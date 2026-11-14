package etl;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "etl")
public record EtlSettings(String jobName, String podName, String team, int rows, long seed, int rounds, Path resultsDir) {

    public EtlSettings {
        if (rows < 1 || rounds < 1 || seed < 0) {
            throw new IllegalArgumentException("ETL_ROWS and ETL_ROUNDS must be >= 1 and ETL_SEED >= 0");
        }
    }
}
