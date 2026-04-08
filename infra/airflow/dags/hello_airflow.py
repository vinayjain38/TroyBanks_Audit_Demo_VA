from __future__ import annotations

from airflow.decorators import dag, task
from pendulum import datetime

@dag(
    dag_id="hello_airflow",
    schedule=None,
    start_date=datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    tags=["debug"],
)
def hello_airflow():
    @task
    def say_hello():
        print("Hello from Airflow! ✅")

    say_hello()

hello_airflow()
