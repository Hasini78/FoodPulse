# Optional Airflow image. It is not built by the application setup.
# Build only when you intend to run the scheduler:
#   docker compose -f docker-compose.airflow.yml build
#
# airflow/requirements.txt is the task environment. The root requirements.txt
# includes PySpark, whose source distribution timed out during image build.
# Spark stays opt-in and is not installed in this image.
FROM apache/airflow:2.10.5-python3.12

USER airflow
COPY --chown=airflow:root airflow/requirements.txt /tmp/foodpulse-airflow-requirements.txt
RUN pip install --no-cache-dir -r /tmp/foodpulse-airflow-requirements.txt
