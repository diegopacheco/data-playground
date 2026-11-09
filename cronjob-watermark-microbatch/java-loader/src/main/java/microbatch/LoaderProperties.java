package microbatch;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("loader")
public record LoaderProperties(String job, String runner, int pageSize, int lagSeconds, long holdBeforeCommitMs) {

    public LoaderProperties {
        if (job == null || !job.matches("[a-z]+")) {
            throw new IllegalArgumentException("loader.job must be lowercase letters only, got " + job);
        }
        if (pageSize <= 0) {
            throw new IllegalArgumentException("loader.page-size must be positive, got " + pageSize);
        }
        if (lagSeconds < 0 || holdBeforeCommitMs < 0) {
            throw new IllegalArgumentException("loader.lag-seconds and loader.hold-before-commit-ms must not be negative");
        }
    }

    public String targetTable() {
        return "target_" + job;
    }
}
