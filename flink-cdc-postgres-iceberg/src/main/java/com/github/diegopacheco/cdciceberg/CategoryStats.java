package com.github.diegopacheco.cdciceberg;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public record CategoryStats(String category, long orders, long quantity, BigDecimal revenue) {

    public String toJson() {
        return String.format(Locale.ROOT, "{\"category\":\"%s\",\"orders\":%d,\"quantity\":%d,\"revenue\":%s}",
                category, orders, quantity, revenue.setScale(2, RoundingMode.HALF_UP).toPlainString());
    }
}
