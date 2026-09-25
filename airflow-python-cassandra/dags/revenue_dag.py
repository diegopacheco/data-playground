import os

from airflow.sdk import dag, task

import revenue

ORDERS_CSV = os.environ.get("ORDERS_CSV", "/opt/airflow/data/orders.csv")


@dag(dag_id="revenue_pipeline", schedule=None, catchup=False, tags=["sales"])
def revenue_pipeline():
    @task
    def extract():
        return revenue.read_orders(ORDERS_CSV)

    @task
    def transform(orders):
        return revenue.aggregate(orders)

    @task
    def load(rows):
        revenue.save(rows)
        return len(rows)

    load(transform(extract()))


revenue_pipeline()
