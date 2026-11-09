package microbatch;

import org.springframework.data.repository.CrudRepository;

public interface BatchRunRepository extends CrudRepository<BatchRun, Long> {
}
