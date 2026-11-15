package com.github.diegopacheco.pipelinelag;

public record Order(String runId, long seq, String sku, int qty, long priceCents, long eventTimeMs) {

    private static final int SKU_COUNT = 50;

    public static Order of(String runId, long seq, long eventTimeMs) {
        return new Order(runId, seq, "sku-" + (seq % SKU_COUNT), (int) (seq % 5) + 1, 100 + (seq * 37) % 9900, eventTimeMs);
    }

    public String id() {
        return runId + "-" + seq;
    }

    public String toJson() {
        return "{\"id\":\"" + id() + "\",\"runId\":\"" + runId + "\",\"seq\":" + seq + ",\"sku\":\"" + sku
                + "\",\"qty\":" + qty + ",\"priceCents\":" + priceCents + ",\"eventTimeMs\":" + eventTimeMs + "}";
    }
}
