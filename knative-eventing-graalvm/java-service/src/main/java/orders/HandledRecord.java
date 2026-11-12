package orders;

public record HandledRecord(
        String variant,
        String id,
        String sku,
        long totalCents,
        String pod,
        long startedAtMs,
        long readyAtMs,
        long handledAtMs,
        long rssKb,
        long cgroupBytes) {
}
