package com.github.diegopacheco.temporaletl;

import com.github.diegopacheco.temporaletl.Model.EtlResult;
import io.temporal.api.history.v1.HistoryEvent;
import io.temporal.client.WorkflowClient;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public final class HistorySummary {

    private HistorySummary() {
    }

    public static List<Map<String, Object>> recent(WorkflowClient client, int limit) {
        return client.listExecutions("WorkflowType = 'EtlWorkflow'")
                .sorted(Comparator.comparing(m -> m.getStartTime(), Comparator.reverseOrder()))
                .limit(limit)
                .map(m -> summarize(client, m.getExecution().getWorkflowId()))
                .toList();
    }

    public static Map<String, Object> summarize(WorkflowClient client, String workflowId) {
        var events = client.fetchHistory(workflowId).getEvents();
        var activities = new LinkedHashMap<Long, Map<String, Object>>();
        var scheduledCount = new LinkedHashMap<String, Integer>();
        var workflowTaskWorkers = new LinkedHashSet<String>();
        var summary = new LinkedHashMap<String, Object>();
        summary.put("workflow_id", workflowId);
        summary.put("status", "RUNNING");
        summary.put("event_count", events.size());
        for (var e : events) {
            switch (e.getEventType()) {
                case EVENT_TYPE_WORKFLOW_EXECUTION_STARTED -> summary.put("started_at", time(e));
                case EVENT_TYPE_WORKFLOW_TASK_STARTED -> workflowTaskWorkers.add(e.getWorkflowTaskStartedEventAttributes().getIdentity());
                case EVENT_TYPE_ACTIVITY_TASK_SCHEDULED -> {
                    String name = e.getActivityTaskScheduledEventAttributes().getActivityType().getName();
                    scheduledCount.merge(name, 1, Integer::sum);
                    var a = new LinkedHashMap<String, Object>();
                    a.put("activity", name);
                    a.put("status", "SCHEDULED");
                    a.put("scheduled_at", time(e));
                    activities.put(e.getEventId(), a);
                }
                case EVENT_TYPE_ACTIVITY_TASK_STARTED -> {
                    var attrs = e.getActivityTaskStartedEventAttributes();
                    var a = activities.get(attrs.getScheduledEventId());
                    a.put("status", "STARTED");
                    a.put("attempt", attrs.getAttempt());
                    a.put("worker", attrs.getIdentity());
                    a.put("last_failure", attrs.hasLastFailure() ? attrs.getLastFailure().getMessage() : "");
                }
                case EVENT_TYPE_ACTIVITY_TASK_COMPLETED -> {
                    var attrs = e.getActivityTaskCompletedEventAttributes();
                    var a = activities.get(attrs.getScheduledEventId());
                    a.put("status", "COMPLETED");
                    a.put("completed_by", attrs.getIdentity());
                    a.put("completed_at", time(e));
                }
                case EVENT_TYPE_ACTIVITY_TASK_FAILED -> activities.get(e.getActivityTaskFailedEventAttributes().getScheduledEventId()).put("status", "FAILED");
                case EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT -> activities.get(e.getActivityTaskTimedOutEventAttributes().getScheduledEventId()).put("status", "TIMED_OUT");
                case EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED -> {
                    summary.put("status", "COMPLETED");
                    summary.put("closed_at", time(e));
                    summary.put("result", result(client, e));
                }
                case EVENT_TYPE_WORKFLOW_EXECUTION_FAILED -> summary.put("status", "FAILED");
                case EVENT_TYPE_WORKFLOW_EXECUTION_TIMED_OUT -> summary.put("status", "TIMED_OUT");
                case EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED -> summary.put("status", "TERMINATED");
                default -> {
                }
            }
        }
        for (var a : activities.values()) {
            a.put("times_scheduled", scheduledCount.get((String) a.get("activity")));
        }
        summary.put("activities", new ArrayList<>(activities.values()));
        summary.put("workflow_task_workers", new ArrayList<>(workflowTaskWorkers));
        return summary;
    }

    private static EtlResult result(WorkflowClient client, HistoryEvent e) {
        var payloads = e.getWorkflowExecutionCompletedEventAttributes().getResult();
        return client.getOptions().getDataConverter().fromPayloads(0, Optional.of(payloads), EtlResult.class, EtlResult.class);
    }

    private static String time(HistoryEvent e) {
        return Instant.ofEpochSecond(e.getEventTime().getSeconds(), e.getEventTime().getNanos()).toString();
    }
}
