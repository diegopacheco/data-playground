package com.github.diegopacheco.temporaletl;

import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowClientOptions;
import io.temporal.serviceclient.WorkflowServiceStubs;
import io.temporal.serviceclient.WorkflowServiceStubsOptions;

public final class Temporal {

    private Temporal() {
    }

    public static WorkflowClient client(String identity) {
        var stubs = WorkflowServiceStubs.newServiceStubs(WorkflowServiceStubsOptions.newBuilder()
                .setTarget(Config.temporalAddress())
                .build());
        return WorkflowClient.newInstance(stubs, WorkflowClientOptions.newBuilder()
                .setNamespace("default")
                .setIdentity(identity)
                .build());
    }
}
