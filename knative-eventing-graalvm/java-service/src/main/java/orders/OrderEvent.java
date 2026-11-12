package orders;

public record OrderEvent(String id, String sku, int quantity, long unitPriceCents) {
}
