package com.github.diegopacheco.cdciceberg;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;

public record OrderRow(int orderId, String customer, String product, String category, int quantity, BigDecimal price, LocalDateTime ts) {

    public String fingerprint() {
        return orderId + "|" + customer + "|" + product + "|" + category + "|" + quantity + "|"
                + price.setScale(2, RoundingMode.HALF_UP).toPlainString() + "|" + ts;
    }
}
