package microbatch;

import java.time.OffsetDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("watermarks")
public record WatermarkRow(@Id String job, OffsetDateTime lastUpdatedAt, long lastId, OffsetDateTime advancedAt) {

    public Watermark watermark() {
        return new Watermark(lastUpdatedAt, lastId);
    }

    public WatermarkRow advancedTo(Watermark next, OffsetDateTime at) {
        return new WatermarkRow(job, next.updatedAt(), next.id(), at);
    }
}
