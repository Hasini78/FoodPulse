"""Manual FoodPulse pipeline.

Schedule is None. Trigger a run from the Airflow UI or CLI. Do not start a
scheduler and assume this DAG is running continuously.

The DAG file imports Airflow and ``foodpulse_flow`` only. Task functions do
not connect to Snowflake or PostgreSQL while the DAG is parsed.
"""

from __future__ import annotations

from datetime import timedelta

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

import foodpulse_flow as flow

def _run(action):
    try:
        return action()
    except flow.SkipStep as exc:
        raise AirflowSkipException(str(exc)) from exc


def check_inputs_task():
    return flow.check_inputs()


def etl_features_task():
    flow.run_etl()


def sentiment_task():
    flow.run_sentiment()


def association_task():
    flow.run_association()


def forecasting_task():
    flow.run_forecasting()


def clustering_task():
    flow.run_clustering()


def churn_task():
    flow.run_churn()


def recommendations_task():
    flow.run_recommendations()


def spark_features_task():
    _run(flow.run_spark)


def snowflake_load_task():
    _run(flow.run_snowflake)


def validate_outputs_task():
    return flow.validate_outputs()


with DAG(
    dag_id="foodpulse_pipeline",
    description="ETL, mining modules, optional Spark, and an opt-in Snowflake dry-run.",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "foodpulse",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=60),
    },
    tags=["foodpulse"],
) as dag:
    check_inputs = PythonOperator(
        task_id="check_inputs",
        python_callable=check_inputs_task,
        retries=0,
        execution_timeout=timedelta(minutes=5),
        doc="Confirm the nine sample CSVs exist and the reference date is YYYY-MM-DD.",
    )
    etl_features = PythonOperator(
        task_id="etl_features",
        python_callable=etl_features_task,
        doc="Run etl.pipelines.run_transform. Replaces processed Parquet. Does not set USE_SPARK.",
    )
    sentiment = PythonOperator(
        task_id="sentiment",
        python_callable=sentiment_task,
        doc="Run mining.sentiment.run_analysis without --persist.",
    )
    association = PythonOperator(
        task_id="association",
        python_callable=association_task,
        doc="Run mining.association.run_mining on completed-order baskets.",
    )
    forecasting = PythonOperator(
        task_id="forecasting",
        python_callable=forecasting_task,
        doc="Run mining.forecasting.run_forecast for a daily horizon of 7.",
    )
    clustering = PythonOperator(
        task_id="clustering",
        python_callable=clustering_task,
        doc="Run mining.clustering.run_segmentation after sentiment exists.",
    )
    churn = PythonOperator(
        task_id="churn",
        python_callable=churn_task,
        doc="Run mining.churn.run_analysis. The score is not a probability.",
    )
    recommendations = PythonOperator(
        task_id="recommendations",
        python_callable=recommendations_task,
        doc="Run mining.recommendation.run_recommendations after association rules exist.",
    )
    spark_features = PythonOperator(
        task_id="spark_features",
        python_callable=spark_features_task,
        doc="Run the Spark feature job only when FOODPULSE_SPARK=1. Otherwise skip.",
    )
    snowflake_load = PythonOperator(
        task_id="snowflake_load",
        python_callable=snowflake_load_task,
        doc="Skip unless FOODPULSE_SNOWFLAKE_LOAD=1. Enabled runs are dry-run unless FOODPULSE_SNOWFLAKE_EXECUTE=1.",
    )
    validate_outputs = PythonOperator(
        task_id="validate_outputs",
        python_callable=validate_outputs_task,
        retries=0,
        execution_timeout=timedelta(minutes=5),
        trigger_rule=TriggerRule.ALL_DONE,
        doc="Fail if an expected processed file is missing. Spark files are required only when Spark is enabled.",
    )

    check_inputs >> etl_features
    etl_features >> [sentiment, association, forecasting]
    sentiment >> [clustering, churn, spark_features]
    association >> recommendations
    sentiment >> recommendations
    [clustering, churn, recommendations, forecasting] >> snowflake_load
    [clustering, churn, recommendations, forecasting, spark_features, snowflake_load] >> validate_outputs
