package orders;

import java.util.Locale;

public final class Transform {

    private Transform() {
    }

    public static ProcessedOrder apply(OrderEvent event) {
        if (event.id() == null || event.id().isBlank()) {
            throw new IllegalArgumentException("order id is required");
        }
        if (event.quantity() <= 0 || event.unitPriceCents() < 0) {
            throw new IllegalArgumentException("order " + event.id() + " has an invalid quantity or price");
        }
        String sku = event.sku().strip().toUpperCase(Locale.ROOT);
        return new ProcessedOrder(event.id(), sku, Math.multiplyExact(event.quantity(), event.unitPriceCents()));
    }
}
