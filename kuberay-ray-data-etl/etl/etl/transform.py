import pyarrow as pa
import pyarrow.compute as pc
from ray.data.aggregate import AggregateFn, Count, Max, Sum

COLUMNS = ["event_id", "batch_id", "user_id", "category", "amount_cents", "ts"]
GROUP_KEYS = ["batch_id", "category"]


def clean_events(batch: pa.Table) -> pa.Table:
    valid = batch.select(COLUMNS).filter(pc.call_function("greater", [batch["amount_cents"], 0]))
    category = pc.call_function("utf8_lower", [pc.call_function("utf8_trim_whitespace", [valid["category"]])])
    return valid.set_column(COLUMNS.index("category"), "category", category)


def aggregations() -> list[AggregateFn]:
    return [
        Count(alias_name="events"),
        Sum("amount_cents", alias_name="amount_cents"),
        Max("amount_cents", alias_name="max_amount_cents"),
    ]
