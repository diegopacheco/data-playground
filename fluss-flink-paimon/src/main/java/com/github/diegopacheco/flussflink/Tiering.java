package com.github.diegopacheco.flussflink;

import org.apache.flink.api.common.JobStatus;
import org.apache.flink.configuration.RestOptions;
import org.apache.flink.core.execution.JobClient;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.fluss.config.Configuration;
import org.apache.fluss.flink.tiering.LakeTieringJobBuilder;

import java.io.IOException;
import java.net.ServerSocket;
import java.util.Map;

public final class Tiering {

    private JobClient job;

    public synchronized void start() throws Exception {
        if (running()) {
            return;
        }
        org.apache.flink.configuration.Configuration flink = Settings.localCluster();
        flink.set(RestOptions.BIND_ADDRESS, "0.0.0.0");
        flink.set(RestOptions.BIND_PORT, String.valueOf(Settings.FLINK_PORT));
        flink.setString("restart-strategy.type", "exponential-delay");
        flink.setString("pipeline.name", "Fluss Lake Tiering Service - paimon");
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment(flink);
        Configuration fluss = Configuration.fromMap(Map.of("bootstrap.servers", Settings.BOOTSTRAP));
        Configuration paimon = Configuration.fromMap(Map.of("metastore", "filesystem", "warehouse", Settings.WAREHOUSE));
        job = LakeTieringJobBuilder.newBuilder(env, fluss, paimon, new Configuration(), "paimon").build();
    }

    public synchronized void stop() throws Exception {
        if (job != null) {
            if (running()) {
                job.cancel().get();
            }
            job = null;
            awaitRestPortFree();
        }
    }

    private static void awaitRestPortFree() throws InterruptedException {
        for (int i = 0; i < 60; i++) {
            try (ServerSocket socket = new ServerSocket(Settings.FLINK_PORT)) {
                return;
            } catch (IOException e) {
                Thread.sleep(500);
            }
        }
        throw new IllegalStateException("flink rest port " + Settings.FLINK_PORT + " still in use after the tiering job was cancelled");
    }

    public synchronized boolean running() {
        return job != null && !status().isGloballyTerminalState();
    }

    public synchronized JobStatus status() {
        if (job == null) {
            return JobStatus.CANCELED;
        }
        try {
            return job.getJobStatus().get();
        } catch (Exception e) {
            return JobStatus.FAILED;
        }
    }

    public synchronized String jobId() {
        return job == null ? null : job.getJobID().toHexString();
    }
}
