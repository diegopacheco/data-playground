package bench;

import java.math.BigDecimal;
import java.math.RoundingMode;

public record Aggregate(String category, long orders, long quantity, BigDecimal priceSum, BigDecimal minPrice, BigDecimal maxPrice) {

    public Aggregate {
        priceSum = priceSum.setScale(2, RoundingMode.UNNECESSARY);
        minPrice = minPrice.setScale(2, RoundingMode.UNNECESSARY);
        maxPrice = maxPrice.setScale(2, RoundingMode.UNNECESSARY);
    }

    public String json() {
        return "{\"category\":\"" + category + "\",\"orders\":" + orders + ",\"quantity\":" + quantity
                + ",\"price_sum\":" + priceSum.toPlainString() + ",\"min_price\":" + minPrice.toPlainString()
                + ",\"max_price\":" + maxPrice.toPlainString() + "}";
    }
}
