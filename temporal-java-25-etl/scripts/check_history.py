import json
import sys


def activity(summary, name):
    found = [a for a in summary["activities"] if a["activity"] == name]
    if len(found) != 1:
        sys.exit(f"{name} was scheduled {len(found)} times, expected exactly once")
    return found[0]


def require(condition, message):
    if not condition:
        sys.exit("FAILED: " + message)
    print("ok   " + message)


def check_retry(s):
    extract = activity(s, "ExtractOrders")
    require(extract["attempt"] == 3, f"extractOrders succeeded on attempt {extract['attempt']} after 2 injected failures")
    require("attempt 2" in extract["last_failure"], f"last failure recorded by temporal: {extract['last_failure']}")
    require(s["result"]["transformResumedFrom"] == 0, "transformAggregate ran from the first order")


def check_crash(s):
    extract = activity(s, "ExtractOrders")
    transform = activity(s, "TransformAggregate")
    load = activity(s, "LoadToPostgres")
    first, second = extract["completed_by"], transform["completed_by"]
    require(extract["times_scheduled"] == 1, f"extractOrders scheduled once and completed by {first} before the crash")
    require(transform["attempt"] >= 2, f"transformAggregate finished on attempt {transform['attempt']} after the crash")
    require("heartbeat" in transform["last_failure"].lower(), f"crash detected by heartbeat timeout: {transform['last_failure']}")
    require(first != second, f"transformAggregate completed by the restarted worker {second}")
    require(load["completed_by"] == second, f"loadToPostgres completed by {second}")
    resumed = s["result"]["transformResumedFrom"]
    require(0 < resumed < s["result"]["orders"], f"transformAggregate resumed from heartbeat checkpoint at order {resumed} of {s['result']['orders']}")
    require(len(s["workflow_task_workers"]) >= 2, f"workflow tasks served by {s['workflow_task_workers']}")


summary = json.load(sys.stdin)
require(summary["status"] == "COMPLETED", f"workflow {summary['workflow_id']} completed")
for name in ("ExtractOrders", "TransformAggregate", "LoadToPostgres"):
    require(activity(summary, name)["status"] == "COMPLETED", f"{name} scheduled once and completed")
require(summary["result"]["rowsUpserted"] == 6, "6 category rows upserted")
{"retry": check_retry, "crash": check_crash}[sys.argv[1]](summary)
