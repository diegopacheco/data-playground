package producer;

public record Event(String eventId, String batchId, String userId, String category, long amountCents, long ts) {

    public String toJson() {
        return "{\"event_id\":\"" + eventId + "\",\"batch_id\":\"" + batchId + "\",\"user_id\":\"" + userId
                + "\",\"category\":\"" + category + "\",\"amount_cents\":" + amountCents + ",\"ts\":" + ts + "}";
    }
}
