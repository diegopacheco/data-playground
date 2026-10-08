from pathlib import Path

from prefect import flow, get_run_logger, task
from prefect.cache_policies import INPUTS
from prefect.runtime import flow_run, task_run

from revenue import aggregate, clean, read_orders
from store import save

ROOT = Path(__file__).resolve().parent.parent
MARKERS = ROOT / ".run" / "markers"


@task(retries=2, retry_delay_seconds=2)
def extract(file_name):
    logger = get_run_logger()
    MARKERS.mkdir(parents=True, exist_ok=True)
    marker = MARKERS / f"{flow_run.get_id()}.extract"
    if not marker.exists():
        marker.touch()
        logger.warning("attempt %s: marker %s missing, failing on purpose", task_run.run_count, marker.name)
        raise RuntimeError("transient failure on first attempt")
    rows = read_orders(ROOT / "data" / file_name)
    logger.info("attempt %s: extracted %d rows", task_run.run_count, len(rows))
    return rows


@task(cache_policy=INPUTS, persist_result=True)
def transform(rows):
    logger = get_run_logger()
    cleaned = clean(rows)
    result = aggregate(cleaned)
    logger.info("transform computed: %d raw rows, %d clean rows, %d categories", len(rows), len(cleaned), len(result))
    return result


@task
def load(rows):
    count = save(rows)
    get_run_logger().info("loaded %d rows into revenue_by_category", count)
    return count


@flow(name="revenue-etl")
def revenue_etl(file_name: str = "orders.csv"):
    rows = extract(file_name)
    result = transform(rows)
    return load(result)


if __name__ == "__main__":
    revenue_etl()
