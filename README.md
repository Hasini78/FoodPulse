# FoodPulse — Restaurant Intelligence & Customer Experience Mining Platform

FoodPulse is a data mining and analytics platform that transforms restaurant, customer, order, and review data into actionable insights. It combines data engineering, machine learning, sentiment analysis, recommendation systems, demand forecasting, warehouse publishing, workflow orchestration, and an interactive analytics dashboard.

The platform helps explore customer behavior, restaurant performance, review sentiment, food-item associations, inactivity risk, personalized recommendations, and expected demand.

## Key Features

- **Data engineering:** CSV-based ingestion, data cleaning, validation, and feature engineering using Pandas.
- **Sentiment analysis:** VADER sentiment scoring, lexicon-based aspect sentiment, and an optional transformer-based sentiment backend.
- **Customer segmentation:** Clustering customers using purchasing behavior and review features.
- **Association rule mining:** Apriori-based discovery of frequently co-purchased food items.
- **Customer inactivity analysis:** Rule-based risk scoring using completed-order history and customer feedback.
- **Recommendation system:** Personalized food and restaurant recommendations using customer history, item associations, quality, and popularity.
- **Demand forecasting:** Ridge regression and seasonal-naive forecasts for restaurant orders and food-item quantities.
- **Distributed feature engineering:** A standalone PySpark job for scalable customer and restaurant feature aggregation.
- **Snowflake integration:** Analytical Parquet publishing into Snowflake tables, with dry-run and explicit live-execution modes.
- **Workflow orchestration:** An Airflow DAG that coordinates the existing ETL and data mining modules.
- **Analytics dashboard:** A React application with interactive Plotly visualizations backed by FastAPI.
- **Operational API and database:** FastAPI endpoints, PostgreSQL, SQLAlchemy, and JWT-based authentication infrastructure.

## Technology Stack

| Layer | Technologies |
|---|---|
| Programming | Python, SQL, TypeScript, JavaScript |
| Data engineering | Pandas, NumPy, PyArrow |
| Data mining and ML | scikit-learn, mlxtend, VADER |
| Optional NLP | Transformers, PyTorch |
| Distributed processing | Apache Spark / PySpark |
| Operational database | PostgreSQL |
| Data warehouse | Snowflake |
| Workflow orchestration | Apache Airflow, Docker Compose |
| Backend | FastAPI, SQLAlchemy |
| Frontend | React, Vite, TypeScript, Tailwind CSS, Plotly |
| Testing | pytest, temporary Parquet datasets, mocked warehouse connections |
| Development | Git, GitHub, PowerShell, VS Code / Cursor |

## System Architecture

```text
Raw / Sample CSV Data
        |
        v
Data Cleaning, Validation & Feature Engineering
                 (Pandas)
        |
        v
Processed Parquet Datasets
        |
        +-------------------------------+
        |               |               |
        v               v               v
    Sentiment       Clustering      Association
    Analysis                        Rule Mining
        |               |               |
        +---------------+---------------+
                        |
           +------------+------------+
           |            |            |
           v            v            v
         Churn     Recommendations Forecasting
        Analysis                  Models
           |            |            |
           +------------+------------+
                        |
              +---------+---------+
              |                   |
              v                   v
       Optional PySpark       Snowflake
       Feature Processing     Analytics Load
                                  |
                                  v
                         Analytical Snapshots

Processed Parquet --> FastAPI --> React / Plotly Dashboard

Airflow DAG --> Coordinates the existing processing commands

PostgreSQL --> Operational database and API statistics
```

**Important:** The current mining modules primarily use local processed Parquet files. Snowflake publishing is a separate operation, and the React dashboard reads processed files through FastAPI rather than querying Snowflake directly. PostgreSQL is the operational database, not a substitute for the analytics datasets.

## Project Structure

```text
FoodPulse/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── core/
│   │   ├── db/
│   │   └── main.py
│   └── tests/
├── frontend/
│   └── React + TypeScript + Vite dashboard
├── etl/
│   ├── extract/
│   ├── transform/
│   ├── load/
│   └── pipelines/
├── data/
│   ├── raw/
│   ├── sample/
│   └── processed/
├── mining/
│   ├── sentiment/
│   ├── clustering/
│   ├── association/
│   ├── churn/
│   ├── recommendation/
│   └── forecasting/
├── pyspark/
│   └── jobs/
│       └── feature_aggregations.py
├── warehouse/
│   ├── snowflake/
│   ├── dimensions/
│   ├── facts/
│   └── sql/
├── airflow/
│   ├── dags/
│   │   ├── foodpulse_flow.py
│   │   └── foodpulse_pipeline.py
│   ├── Dockerfile
│   └── requirements.txt
├── tests/
├── docker-compose.yml
├── docker-compose.airflow.yml
├── requirements.txt
├── Makefile
└── README.md
```

The dimensions, facts, and general warehouse SQL directories remain placeholders for a future dimensional warehouse implementation. The existing Snowflake loader publishes analytical snapshots; it does not yet implement a complete star-schema warehouse.

## Implemented Data Mining Modules

### 1. ETL and Feature Engineering

**Location:** `etl/transform/`, `etl/pipelines/`

The Pandas pipeline cleans input datasets, validates their structure and relationships, generates a validation report, and creates processed Parquet datasets.

Features include:

- Missing-value and duplicate-key handling.
- Referential integrity and business-rule validation.
- Order outlier detection and capped analytical values.
- Customer purchasing features and restaurant performance features.
- Reference-date-aware features that exclude future events.

The pipeline writes `validation_report.json` and processed entity and feature files. Critical validation failures stop feature generation.

### 2. Sentiment Analysis

**Location:** `mining/sentiment/`

Implemented capabilities:

- Overall sentiment scoring with VADER.
- Positive, negative, neutral, and invalid classifications.
- Aspect sentiment for food, service, ambience, and price using a keyword lexicon.
- Sentiment aggregation by restaurant, city, cuisine, and month.
- Optional transformer-based scoring using `cardiffnlp/twitter-roberta-base-sentiment-latest`.

VADER is the default. Transformer inference is an optional backend selected through `SENTIMENT_MODEL=transformer`.

The transformer was smoke-tested on five hand-written texts. This was not an accuracy evaluation on the project's 3,000 reviews. Aspect labels are lexicon-based rather than predictions from a trained aspect model.

### 3. Customer Segmentation

**Location:** `mining/clustering/`

Customers are grouped using purchasing behavior and feedback features such as recency, order frequency, total spend, average order value, rating, and sentiment.

The module evaluates K-Means, agglomerative clustering, and DBSCAN using clustering-quality metrics. Labels such as `high-value loyal` and `inactive/at-risk` are descriptive interpretations of cluster behavior, not a validated customer taxonomy.

### 4. Association Rule Mining

**Location:** `mining/association/`

The module uses Apriori from `mlxtend` to discover food items that frequently appear together in completed orders.

Metrics include:

- Support and support count.
- Confidence.
- Lift.
- Leverage.
- Conviction.

Both global mining and optional restaurant-specific mining are supported. Food-item IDs distinguish catalog entries that share the same display name. Association indicates co-occurrence, not causation.

### 5. Customer Inactivity and Churn-Risk Analysis

**Location:** `mining/churn/`

The module calculates inactivity from the last completed order and assigns rule-based risk categories.

It also considers order frequency, purchase gaps, changes in recent activity, ratings, and sentiment. The risk score is a capped heuristic, **not a calibrated probability of customer churn**. The categories do not establish that a customer has permanently left.

### 6. Personalized Recommendations

**Location:** `mining/recommendation/`

The recommendation engine generates food-item and restaurant rankings using:

- Customer purchase history.
- Cuisine preference.
- Association-rule strength.
- Restaurant quality.
- Familiarity and popularity.
- A cold-start scoring approach for limited purchase histories.

The module produces ranked recommendations and reason descriptions. Scores represent ranking strength, not purchase probabilities. Holdout evaluation is implemented, although the observed hit rates on the sample dataset were low.

### 7. Demand Forecasting

**Location:** `mining/forecasting/`

The forecasting module predicts completed-order demand at restaurant level and food-item quantity demand.

Supported models:

- Ridge regression.
- Seasonal-naive baseline.

The implementation supports daily and weekly aggregation, chronological holdout evaluation, and forward forecasts. It reports MAE, RMSE, and WAPE.

Forecasts are clipped at zero. The current output does not include prediction intervals, and sparse demand can result in high WAPE values. Results should not be treated as a production-ready staffing or purchasing plan.

## PySpark Feature Engineering

**Location:** `pyspark/jobs/feature_aggregations.py`

A separate Spark job performs customer and restaurant feature aggregation from prepared Parquet datasets.

Features:

- Completed-order filtering.
- Reference-date-aware feature calculations.
- Customer and restaurant feature outputs.
- Restaurant activity summaries.
- Optional restaurant sentiment counts.

The standalone job writes to `data/processed/spark_features/` by default. It does not replace the existing Pandas ETL feature files, modify sample CSVs, or write to PostgreSQL.

**Verification:** The job was run locally on 12 October 2026. It returned 500 customer rows and 50 restaurant rows, and the shared numeric feature columns matched the Pandas outputs for the same reference date.

## Snowflake Analytics Integration

**Location:** `warehouse/snowflake/`

The Snowflake loader publishes approved processed Parquet datasets into the `FOODPULSE.ANALYTICS` schema.

Implemented capabilities:

- Configuration through environment variables.
- Local file and schema validation before connecting.
- Dry-run planning and table row counts.
- Optional connection verification.
- Parameterized row loading.
- Temporary staging tables and snapshot replacement.
- Row-count verification and transaction rollback for failed table loads.
- Sanitized error reporting.

The default mode is a dry run. A live load requires explicit use of `--execute` and valid Snowflake credentials and permissions.

A previous live account test completed the analytical load. Automated tests use mocked connections and do not require Snowflake credentials.

**Current limitation:** The existing loader publishes analytical snapshots, not a fully implemented dimensional star schema. The `warehouse/dimensions/`, `warehouse/facts/`, and `warehouse/sql/` directories still need their planned implementation.

## Airflow Workflow Orchestration

**Location:** `airflow/dags/`, `docker-compose.airflow.yml`

The `foodpulse_pipeline` DAG coordinates the existing processing commands rather than reimplementing the ETL and mining logic.

### Workflow

1. **Input validation:** Checks the required sample CSV files and resolves the reference date.
2. **ETL and feature engineering:** Runs the Pandas transform pipeline.
3. **Parallel processing:** Runs sentiment analysis, association rule mining, and demand forecasting.
4. **Customer analysis:** Runs clustering and inactivity-risk analysis after sentiment processing.
5. **Recommendations:** Uses association rules and sentiment outputs to generate recommendations.
6. **Optional Spark processing:** Runs only when `FOODPULSE_SPARK=1`.
7. **Optional Snowflake publishing:** Runs only when `FOODPULSE_SNOWFLAKE_LOAD=1`.
8. **Output validation:** Checks expected output files after the upstream tasks finish.

The Snowflake task defaults to a dry run. A live warehouse load additionally requires `FOODPULSE_SNOWFLAKE_EXECUTE=1`.

### Airflow Runtime

The optional Docker Compose setup includes:

- Airflow webserver.
- Airflow scheduler.
- PostgreSQL metadata database.
- LocalExecutor configuration.
- A mounted DAG directory and FoodPulse project directory.

The Airflow UI is available at [http://localhost:8080](http://localhost:8080) when the services are running and initialization succeeds.

### Verification Status

The FoodPulse Airflow workflow was manually executed and verified on 19 October 2026.

- The `foodpulse_pipeline` DAG was visible in the Airflow UI, and the scheduler and webserver were running.
- The manual run completed successfully for input validation, ETL and feature engineering, sentiment analysis, demand forecasting, customer clustering, churn-risk analysis, association rule mining, personalized recommendations, the Snowflake dry-run task, and final output validation.
- The `spark_features` task was skipped because optional Spark processing was disabled. This is expected behavior when `FOODPULSE_SPARK` is not enabled.
- The association rule mining task completed successfully after reducing Apriori's memory usage with `low_memory=True`.
- The Snowflake task completed in **dry-run mode**. It validated and planned the analytical publishing operation; this successful task does **not** mean that data was written to Snowflake.
- Final output validation succeeded.

The successful DAG run verifies orchestration of the configured workflow. It does not establish that this particular DAG run performed a live Snowflake load.

### Important Execution Warning

The DAG runs the ETL pipeline into `data/processed/`. That operation regenerates processed Parquet outputs and can replace existing files. Preserve important outputs or use an isolated copy of the data before triggering a full run.

Spark and Snowflake publishing are controlled by environment variables:

- Set `FOODPULSE_SPARK=1` only when intentionally running the optional Spark task.
- Set `FOODPULSE_SNOWFLAKE_LOAD=1` to enable the Snowflake publishing task.
- Keep `FOODPULSE_SNOWFLAKE_EXECUTE` unset unless an intentional live Snowflake load is planned.

The Snowflake task defaults to dry-run mode. Do not enable live execution unintentionally.

## React Analytics Dashboard

**Location:** `frontend/`, `backend/app/`

The dashboard presents stored analytics through a React and TypeScript interface, interactive Plotly charts, and FastAPI endpoints.

### Dashboard Pages

- **Overview:** Dataset counts, completed-order revenue, average order value, ratings, sentiment mix, segment distributions, churn categories, and forecast summaries.
- **Restaurants:** Performance rankings, cuisine filters, rating-versus-volume comparisons, and restaurant details.
- **Sentiment:** Overall sentiment distribution, monthly trends, aspect sentiment, and restaurant comparisons.
- **Segments:** Customer segment counts and behavioral summaries.
- **Churn:** Inactivity, risk categories, and stored heuristic scores.
- **Recommendations and association:** Stored food and restaurant recommendations, frequent itemsets, and association rules.
- **Forecast:** Historical demand and forward predictions for the selected restaurant and model.
- **Customers and Insights:** Existing routes that still have placeholder or link-hub behavior.

### Dashboard Design

The dashboard reads existing processed Parquet data through FastAPI. It does not retrain mining models, rescore reviews, rewrite Parquet files, or open a Snowflake connection during page loads.

PostgreSQL operational counts are reported separately from processed-dataset analytics. Empty operational tables must not be interpreted as proof that the processed analytics datasets are empty.

### Verification

On 19 October 2026:

- Dashboard API tests: **12 passed** across the checked analytics test files.
- The frontend TypeScript check and Vite production build succeeded.
- Browser checks covered the main analytics pages and a narrow mobile viewport.
- The Plotly bundle remains relatively large, producing a Vite chunk-size warning.

The dashboard is implemented and locally verified. Power BI reports are not implemented.

## PostgreSQL and FastAPI

The operational backend uses FastAPI, SQLAlchemy, and PostgreSQL. It includes database models, authentication infrastructure, and API endpoints for operational entities and statistics.

Representative endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Application health |
| GET | `/restaurants` | List restaurants |
| GET | `/restaurants/{id}` | Restaurant details |
| GET | `/customers` | List customers |
| GET | `/stats/overview` | Operational database statistics |
| GET | `/analytics/overview` | Processed analytics summary |
| GET | `/analytics/restaurants` | Restaurant analytics |
| GET | `/analytics/sentiment` | Stored sentiment analysis |
| GET | `/analytics/segments` | Customer segment summaries |
| GET | `/analytics/churn` | Customer inactivity-risk summaries |
| GET | `/analytics/association` | Stored association rules |
| GET | `/analytics/forecast` | Stored demand forecasts |

The remaining analytics endpoints cover recommendations, itemsets, and restaurant-specific forecast details. See the FastAPI interactive documentation at `/docs` when the backend is running.

## Setup and Local Execution

### Prerequisites

- Python 3.11 or later for the local application components.
- Node.js and npm for the React frontend.
- PostgreSQL for operational database functionality.
- Docker Desktop and Docker Compose for containerized services and the optional Airflow runtime.
- Java and PySpark for standalone Spark processing.
- A configured Snowflake account only when a live warehouse connection is required.

### 1. Configure the Environment

From the repository root, create the local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` to configure the database connection, secret key, and any optional Snowflake settings. Never commit `.env` or credentials.

### 2. Install Python Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r backend/requirements.txt
```

The root requirements file contains the data processing and mining dependencies. The backend requirements file contains the API dependencies.

### 3. Start PostgreSQL and the Backend

Use the repository's existing Docker Compose configuration for the operational database and services:

```powershell
docker compose up --build -d
```

Check the current Compose configuration if you want to start only a particular service. Ensure the database URL in `.env` matches the database's actual host port.

To start the backend locally from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to inspect the API.

### 4. Generate Processed Analytics

The sample CSV files are already part of the project's data workflow. The transform command reads the existing files and writes processed outputs:

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_transform --reference-date 2026-10-11
```

This command writes into `data/processed/` by default and can replace existing processed outputs.

**Do not run `scripts/run-etl.ps1` when your goal is merely to regenerate processed Parquet.** That script runs the CSV seeding workflow and can overwrite `data/sample/`.

### 5. Run the React Dashboard

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

The dashboard requires the backend and the appropriate processed Parquet outputs to be available.

## Running Individual Modules

Run commands from the repository root.

```powershell
# VADER sentiment analysis
.\.venv\Scripts\python.exe -m mining.sentiment.run_analysis

# Customer segmentation
.\.venv\Scripts\python.exe -m mining.clustering.run_segmentation --seed 42

# Association rule mining
.\.venv\Scripts\python.exe -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3

# Inactivity / churn-risk analysis
.\.venv\Scripts\python.exe -m mining.churn.run_analysis --reference-date 2026-10-11 --inactivity-days 90 --at-risk-days 45

# Personalized recommendations
.\.venv\Scripts\python.exe -m mining.recommendation.run_recommendations --reference-date 2026-10-11

# Demand forecasting
.\.venv\Scripts\python.exe -m mining.forecasting.run_forecast --reference-date 2026-10-11 --horizon 7

# Snowflake dry run
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_load --dry-run
```

The mining modules use processed Parquet inputs and write their analytical outputs to the processed-data directory unless configured otherwise.

### Optional Transformer Sentiment

Set `SENTIMENT_MODEL=transformer` in the environment to use the transformer backend. Leave it unset or set it to `vader` for the default VADER backend.

Transformer inference is optional and can require additional dependencies and model downloads. The dashboard does not run transformer inference automatically.

### Optional PySpark Job

The standalone Spark job writes to a separate output directory:

```powershell
.\.venv\Scripts\python.exe pyspark\jobs\feature_aggregations.py --input-dir data\processed --output-dir data\processed\spark_features --reference-date 2026-10-11
```

This preserves the original Pandas ETL files.

## Testing and Verification

The following commands cover the main implemented modules.

### Data Mining and ETL

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transform.py tests\test_sentiment.py tests\test_clustering.py tests\test_association.py tests\test_churn.py tests\test_recommendation.py tests\test_forecasting.py -q
```

The documented run reported **67 passed** on 11 October 2026.

### Snowflake Loader

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_snowflake_load.py -q
```

The documented run reported **21 passed**. These tests use mocked connections and temporary data, not a live Snowflake account.

### PySpark

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_spark_features.py -q
```

The documented run reported **4 passed**.

### Airflow DAG

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_airflow_dag.py -q
```

The documented local result was **8 passed, 1 skipped**. The skip was due to Airflow not being installed in the host project's Python interpreter. Docker-based runtime checks are separate from this test result.

### Dashboard

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_dashboard_metrics.py backend\tests\test_analytics.py -q
```

The documented run reported **12 passed**.

For the frontend production build:

```powershell
cd frontend
npm run build
```

The documented build completed successfully. Test counts above describe specific recorded runs; they are not a guarantee that every test will pass after subsequent changes.

A later full-project test run reported **123 passed, 1 skipped**. Test results may change as the project evolves.

## Data Safety and Configuration

- Keep `.env` and all database credentials out of version control.
- Do not commit passwords, access tokens, or sensitive customer data.
- `data/processed/` is generated data and is gitignored.
- The ETL pipeline can replace processed files. Preserve or copy important outputs before a full rerun.
- The Airflow DAG invokes existing processing commands and is not a separate implementation of each algorithm.
- Keep `FOODPULSE_SPARK` disabled unless the optional Spark task is deliberately being tested.
- `FOODPULSE_SNOWFLAKE_LOAD` controls whether the Snowflake publishing task runs in Airflow.
- Keep `FOODPULSE_SNOWFLAKE_EXECUTE` unset unless an intentional live Snowflake load is planned.
- Snowflake DDL and individual table transactions are not one atomic transaction across the entire 16-table load.
- The local dashboard uses processed Parquet data; PostgreSQL statistics are displayed separately.

## Current Project Status

| Component | Status |
|---|---|
| Pandas ETL and feature engineering | Implemented and tested |
| VADER sentiment and aspect labels | Implemented and tested |
| Optional transformer sentiment | Smoke-tested; full accuracy evaluation pending |
| Customer clustering | Implemented and tested |
| Apriori association rules | Implemented and tested |
| Rule-based inactivity / churn-risk analysis | Implemented and tested |
| Personalized recommendations | Implemented and tested |
| Demand forecasting | Implemented and tested |
| PySpark feature aggregation | Implemented and locally verified; optional in Airflow |
| Snowflake analytical loader | Implemented; prior live load completed |
| FastAPI operational endpoints | Implemented |
| React / Plotly analytics dashboard | Implemented and locally verified |
| Airflow DAG and Docker runtime | Manually executed successfully; Snowflake task verified in dry-run mode |
| Dimensional Snowflake star schema | Pending |
| Power BI reports | Pending |

## Future Enhancements

1. Implement warehouse dimensions, fact tables, and the corresponding dimensional SQL model.
2. Improve and evaluate transformer sentiment using a representative labeled dataset.
3. Evaluate recommendation quality on more suitable holdout data and investigate the low observed hit rates.
4. Improve forecast evaluation for sparse restaurant and food-item demand, and consider calibrated uncertainty estimates.
5. Add Power BI reports if required by the project scope.
6. Improve dashboard bundle performance and expand automated integration testing.
7. Perform a controlled live Snowflake load when required, with valid credentials, explicit execution settings, and post-load verification.

## Project Goal

FoodPulse demonstrates an end-to-end restaurant analytics workflow that connects data preparation, data mining, machine learning, workflow orchestration, analytical warehouse publishing, API development, and interactive visualization. It is designed as an extensible academic data mining project with a practical, resume-oriented engineering structure.
