package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.EtlRequest;
import com.github.diegopacheco.temporaletl.Model.EtlResult;
import io.temporal.activity.ActivityOptions;
import io.temporal.common.RetryOptions;
import io.temporal.workflow.Workflow;

import java.time.Duration;

public class EtlWorkflowImpl implements EtlWorkflow {

    private static final RetryOptions RETRY = RetryOptions.newBuilder()
            .setInitialInterval(Duration.ofSeconds(1))
            .setBackoffCoefficient(2.0)
            .setMaximumInterval(Duration.ofSeconds(4))
            .setMaximumAttempts(5)
            .build();

    private final EtlActivities extract = Workflow.newActivityStub(EtlActivities.class, ActivityOptions.newBuilder()
            .setStartToCloseTimeout(Duration.ofSeconds(30))
            .setRetryOptions(RETRY)
            .build());

    private final EtlActivities transform = Workflow.newActivityStub(EtlActivities.class, ActivityOptions.newBuilder()
            .setStartToCloseTimeout(Duration.ofMinutes(5))
            .setHeartbeatTimeout(Duration.ofSeconds(3))
            .setRetryOptions(RETRY)
            .build());

    private final EtlActivities load = Workflow.newActivityStub(EtlActivities.class, ActivityOptions.newBuilder()
            .setStartToCloseTimeout(Duration.ofSeconds(30))
            .setRetryOptions(RETRY)
            .build());

    @Override
    public EtlResult run(EtlRequest request) {
        String workflowId = Workflow.getInfo().getWorkflowId();
        var extracted = extract.extractOrders(request.csvPath(), request.failExtractAttempts());
        var transformed = transform.transformAggregate(extracted.orders(), request.millisPerOrder());
        int rows = load.loadToPostgres(workflowId, transformed.totals());
        return new EtlResult(workflowId, extracted.orders().size(), transformed.totals().size(), rows,
                extracted.attempt(), transformed.attempt(), transformed.resumedFrom());
    }
}
