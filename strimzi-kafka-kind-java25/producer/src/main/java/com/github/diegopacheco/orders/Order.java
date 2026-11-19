package com.github.diegopacheco.orders;

public record Order(String runId, long seq, String sku, int qty, long priceCents) {

    private static final int SKU_COUNT = 50;

    public static Order of(String runId, long seq) {
        return new Order(runId, seq, "sku-" + (seq % SKU_COUNT), (int) (seq % 5) + 1, 100 + (seq * 37) % 9900);
    }

    public String key() {
        return runId + "-" + seq;
    }

    public String toJson() {
        return "{\"runId\":\"" + runId + "\",\"seq\":" + seq + ",\"sku\":\"" + sku
                + "\",\"qty\":" + qty + ",\"priceCents\":" + priceCents + "}";
    }
}
