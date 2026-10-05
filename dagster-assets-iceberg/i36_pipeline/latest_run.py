import warnings

from dagster import DagsterInstance

warnings.filterwarnings("ignore")


def main():
    instance = DagsterInstance.get()
    run = instance.get_runs(limit=1)[0]
    print(f"run {run.run_id} {run.status.value}")
    for record in instance.all_logs(run.run_id):
        event = record.dagster_event
        if event and event.event_type_value == "ASSET_MATERIALIZATION":
            print(f"materialized {event.asset_key.to_user_string()}")
        if event and event.event_type_value == "ASSET_CHECK_EVALUATION":
            data = event.event_specific_data
            print(f"check {data.asset_check_key.name} {'PASSED' if data.passed else 'FAILED'}")


if __name__ == "__main__":
    main()
