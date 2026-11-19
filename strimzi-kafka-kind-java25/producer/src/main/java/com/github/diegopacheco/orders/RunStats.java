package com.github.diegopacheco.orders;

public record RunStats(String runId, int ratePerSecond, long sent, long acked, long failed, boolean running, String lastError) {
}
