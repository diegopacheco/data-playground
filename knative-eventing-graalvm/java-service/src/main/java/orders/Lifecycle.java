package orders;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class Lifecycle {

    private final long startedAtMs = ProcessStats.processStartedAtMs();
    private volatile long readyAtMs = -1;

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        readyAtMs = System.currentTimeMillis();
    }

    public long startedAtMs() {
        return startedAtMs;
    }

    public long readyAtMs() {
        return readyAtMs;
    }
}
