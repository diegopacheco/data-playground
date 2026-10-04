package com.github.diegopacheco.temporaletl;

import java.util.List;

public final class Model {

    private Model() {
    }

    public record Order(long orderId, String customer, String product, String category, int quantity, long priceCents) {
    }

    public record CategoryTotal(String category, long orders, long quantity, long revenueCents) {
        public CategoryTotal add(Order order) {
            return new CategoryTotal(category, orders + 1, quantity + order.quantity(), revenueCents + order.quantity() * order.priceCents());
        }
    }

    public record EtlRequest(String csvPath, int failExtractAttempts, int millisPerOrder) {
    }

    public record ExtractResult(List<Order> orders, int attempt) {
    }

    public record Checkpoint(int next, List<CategoryTotal> totals) {
    }

    public record TransformResult(List<CategoryTotal> totals, int resumedFrom, int attempt) {
    }

    public record EtlResult(String workflowId, int orders, int categories, int rowsUpserted, int extractAttempt, int transformAttempt, int transformResumedFrom) {
    }
}
