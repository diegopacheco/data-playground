package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.EtlRequest;
import com.github.diegopacheco.temporaletl.Model.EtlResult;
import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

@WorkflowInterface
public interface EtlWorkflow {

    @WorkflowMethod
    EtlResult run(EtlRequest request);
}
