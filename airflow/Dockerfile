# Optional Airflow image. It is not built by the application setup.
# Build only when you intend to run the scheduler:
#   docker compose -f docker-compose.airflow.yml build
FROM apache/airflow:2.10.5-python3.12

USER airflow
COPY --chown=airflow:root requirements.txt /tmp/foodpulse-requirements.txt
RUN pip install --no-cache-dir -r /tmp/foodpulse-requirements.txt
