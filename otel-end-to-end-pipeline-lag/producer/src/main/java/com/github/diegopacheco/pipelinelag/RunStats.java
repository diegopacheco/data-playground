package com.github.diegopacheco.pipelinelag;

public record RunStats(String runId, int ratePerSecond, long sent, long acked, long failed, boolean running, String lastError) {
}
