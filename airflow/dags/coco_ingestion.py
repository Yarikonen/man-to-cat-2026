from airflow.models.dag import DAG
from datetime import datetime

with DAG(
    dag_id="coco_ingestion",
    start_date=datetime(2023, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["coco", "ingestion"],
) as dag:
    pass
