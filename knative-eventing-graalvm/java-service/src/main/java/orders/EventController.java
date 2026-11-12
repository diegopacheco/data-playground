package orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EventController {

    private final Lifecycle lifecycle;
    private final LabClient lab;
    private final String variant;
    private final String pod;

    public EventController(
            Lifecycle lifecycle,
            LabClient lab,
            @Value("${variant}") String variant,
            @Value("${HOSTNAME:local}") String pod) {
        this.lifecycle = lifecycle;
        this.lab = lab;
        this.variant = variant;
        this.pod = pod;
    }

    @PostMapping("/")
    public ProcessedOrder handle(@RequestBody OrderEvent event) {
        ProcessedOrder order = Transform.apply(event);
        lab.report(new HandledRecord(
                variant,
                order.id(),
                order.sku(),
                order.totalCents(),
                pod,
                lifecycle.startedAtMs(),
                lifecycle.readyAtMs(),
                System.currentTimeMillis(),
                ProcessStats.currentRssKb(),
                ProcessStats.cgroupMemoryBytes()));
        return order;
    }
}
