package microbatch;

import java.time.OffsetDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("batch_runs")
public record BatchRun(
        @Id Long id,
        String job,
        String runner,
        OffsetDateTime startedAt,
        long durationMs,
        long rowsLoaded,
        int pages,
        OffsetDateTime lastUpdatedAt,
        long lastId) {
}
