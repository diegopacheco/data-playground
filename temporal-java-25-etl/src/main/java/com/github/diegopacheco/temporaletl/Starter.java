package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.EtlRequest;
import com.github.diegopacheco.temporaletl.Model.EtlResult;
import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowOptions;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class Starter {

    public static void main(String[] args) {
        if (args.length < 2) {
            System.err.println("usage: start|run <workflowId> <csvPath> <failExtractAttempts> <millisPerOrder> | wait <workflowId>");
            System.exit(2);
        }
        var client = Temporal.client("etl-starter");
        String command = args[0];
        String workflowId = args[1];
        switch (command) {
            case "start" -> {
                start(client, workflowId, request(args));
                System.out.println("started workflow=" + workflowId);
            }
            case "run" -> {
                start(client, workflowId, request(args));
                print(await(client, workflowId));
            }
            case "wait" -> print(await(client, workflowId));
            default -> {
                System.err.println("unknown command " + command);
                System.exit(2);
            }
        }
        System.exit(0);
    }

    private static EtlRequest request(String[] args) {
        return new EtlRequest(args[2], Integer.parseInt(args[3]), Integer.parseInt(args[4]));
    }

    private static void start(WorkflowClient client, String workflowId, EtlRequest request) {
        var stub = client.newWorkflowStub(EtlWorkflow.class, WorkflowOptions.newBuilder()
                .setWorkflowId(workflowId)
                .setTaskQueue(Config.TASK_QUEUE)
                .setWorkflowExecutionTimeout(Duration.ofMinutes(10))
                .build());
        WorkflowClient.start(stub::run, request);
    }

    private static EtlResult await(WorkflowClient client, String workflowId) {
        try {
            return client.newUntypedWorkflowStub(workflowId).getResult(60, TimeUnit.SECONDS, EtlResult.class);
        } catch (TimeoutException e) {
            System.err.println("workflow " + workflowId + " did not finish within 60 seconds");
            System.exit(1);
            return null;
        }
    }

    private static void print(EtlResult r) {
        System.out.printf("workflow=%s orders=%d categories=%d rowsUpserted=%d extractAttempt=%d transformAttempt=%d transformResumedFrom=%d%n",
                r.workflowId(), r.orders(), r.categories(), r.rowsUpserted(), r.extractAttempt(), r.transformAttempt(), r.transformResumedFrom());
    }
}
