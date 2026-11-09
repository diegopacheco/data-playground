package microbatch;

import java.util.Optional;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface WatermarkRepository extends CrudRepository<WatermarkRow, String> {

    @Query("SELECT job, last_updated_at, last_id, advanced_at FROM watermarks WHERE job = :job FOR UPDATE")
    Optional<WatermarkRow> lockByJob(String job);
}
