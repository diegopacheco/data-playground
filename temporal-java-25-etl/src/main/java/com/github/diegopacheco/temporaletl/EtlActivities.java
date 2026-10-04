package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.CategoryTotal;
import com.github.diegopacheco.temporaletl.Model.ExtractResult;
import com.github.diegopacheco.temporaletl.Model.Order;
import com.github.diegopacheco.temporaletl.Model.TransformResult;
import io.temporal.activity.ActivityInterface;

import java.util.List;

@ActivityInterface
public interface EtlActivities {

    ExtractResult extractOrders(String csvPath, int failAttempts);

    TransformResult transformAggregate(List<Order> orders, int millisPerOrder);

    int loadToPostgres(String workflowId, List<CategoryTotal> totals);
}
