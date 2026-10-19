from datetime import timedelta
from feast import Entity, FeatureService, FeatureView, Field, FileSource, PushSource
from feast.types import Float64, Int64
from feast.value_type import ValueType

driver = Entity(name="driver", join_keys=["driver_id"], value_type=ValueType.INT64, description="A ride hailing driver")

hourly_source = FileSource(name="driver_hourly_source", path="/data/driver_hourly.parquet", timestamp_field="event_timestamp", created_timestamp_column="created")

hourly_push = PushSource(name="driver_hourly_push", batch_source=hourly_source)

daily_source = FileSource(name="driver_daily_source", path="/data/driver_daily.parquet", timestamp_field="event_timestamp", created_timestamp_column="created")

driver_hourly = FeatureView(
    name="driver_hourly",
    entities=[driver],
    ttl=timedelta(hours=24),
    schema=[Field(name="conv_rate", dtype=Float64), Field(name="acc_rate", dtype=Float64), Field(name="trips_today", dtype=Int64), Field(name="observed_at", dtype=Int64)],
    source=hourly_push,
    online=True,
    description="Hourly driver activity, stale after 24 hours",
)

driver_daily = FeatureView(
    name="driver_daily",
    entities=[driver],
    ttl=timedelta(days=7),
    schema=[Field(name="rating", dtype=Float64), Field(name="lifetime_trips", dtype=Int64), Field(name="observed_at", dtype=Int64)],
    source=daily_source,
    online=True,
    description="Daily driver quality, stale after 7 days",
)

driver_model_v1 = FeatureService(name="driver_model_v1", features=[driver_hourly, driver_daily], description="Features used by the trip acceptance model")
