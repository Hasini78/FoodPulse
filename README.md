# FoodPulse — Restaurant Intelligence & Customer Experience Mining Platform

FoodPulse is a data-mining and restaurant analytics platform that transforms restaurant, customer, order, and review data into actionable insights. It combines data engineering, machine learning, sentiment analysis, customer segmentation, recommendation systems, demand forecasting, data warehouse integration, workflow orchestration, and an interactive web application.

FoodPulse has two complementary goals:

- **Food Discovery:** Help users discover relevant food items and restaurants through personalized, explainable recommendations.
- **Restaurant Intelligence:** Help analysts and restaurant owners understand customer behavior, satisfaction, purchasing patterns, restaurant performance, and demand.

The platform connects data mining with practical decisions through interactive food and restaurant cards, recommendation explanations, analytical visualizations, and customer behavior insights.

## Key Features

- **Data Engineering:** CSV ingestion, data validation, cleaning, and feature engineering using Pandas.
- **Sentiment Analysis:** VADER-based sentiment scoring, lexicon-based aspect analysis, and optional transformer-based sentiment inference.
- **Customer Segmentation:** Clustering customers using purchasing behavior and available feedback features.
- **Association Rule Mining:** Apriori-based discovery of frequently co-purchased food items.
- **Customer Churn-Risk Analysis:** Rule-based inactivity and customer risk scoring.
- **Food Recommendations:** Ranked food-item suggestions using available purchase history, item associations, quality, familiarity, and popularity signals.
- **Restaurant Recommendations:** Restaurant rankings based on relevant customer preferences, cuisine, quality, and available analytical features.
- **Explainable Recommendations:** Short reasons that communicate why a food item or restaurant is suggested.
- **Food Discovery Interface:** Dedicated recommendation sections for personalized choices, popular items, similar items, complementary food, restaurants, and new discoveries.
- **Demand Forecasting:** Ridge regression and seasonal-naive forecasts for restaurant orders and food-item quantities.
- **Interactive Analytics Dashboard:** React, TypeScript, and Plotly visualizations for restaurant performance, customer segments, sentiment, churn, recommendations, and forecasts.
- **PostgreSQL Operational API:** FastAPI, SQLAlchemy, database models, authentication infrastructure, and operational statistics endpoints.
- **Snowflake Integration:** Analytical dataset publishing with dry-run and explicit live-execution modes.
- **Airflow Orchestration:** Workflow coordination for existing ETL and mining modules.
- **Optional Distributed Processing:** PySpark-based customer and restaurant feature aggregation.

## Technology Stack

| Layer | Technologies |
|---|---|
| Programming languages | Python, SQL, TypeScript, JavaScript |
| Data engineering | Pandas, NumPy, PyArrow |
| Data mining and machine learning | scikit-learn, MLxtend |
| Sentiment analysis | VADER, optional Transformers and PyTorch |
| Distributed processing | Apache Spark, PySpark |
| Operational database | PostgreSQL |
| Data warehouse | Snowflake |
| Backend | FastAPI, Uvicorn, SQLAlchemy |
| Frontend | React, Vite, TypeScript, Tailwind CSS, Plotly |
| Workflow orchestration | Apache Airflow, Docker Compose |
| Testing | Pytest |
| Development tools | Git, GitHub, VS Code, Cursor |
- **Maps and Location Services:** Google Maps JavaScript API, Google Places functionality, browser Geolocation API
- **Testing:** pytest, frontend test suite, oxlint, TypeScript and Vite production build

## System Architecture

```text
                  Raw / Sample Data
                         |
                         v
               ETL and Data Validation
                         |
                         v
               Processed Parquet Data
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
      Sentiment       Customer       Association
      Analysis       Segmentation    Rule Mining
          |              |              |
          +--------------+--------------+
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
           Churn     Recommendations Forecasting
          Analysis       Engine       Models
             |           |
             +-----------+
                   |
                   v
              FastAPI Backend
                   |
                   v
             React Frontend
                   |
          +--------+---------+
          |                  |
          v                  v
     Food Discovery     Business Insights
     Food and          Interactive Reports
     Restaurant Cards  and Charts

  PostgreSQL --> Operational records and API statistics
  Snowflake  --> Analytical data publishing and warehouse
  Airflow    --> Orchestrates supported pipeline tasks
  PySpark    --> Optional distributed feature aggregation
```

**Data-flow note:** The mining modules primarily consume local processed Parquet files. The dashboard accesses analytical results through FastAPI. PostgreSQL operational statistics are separate from processed-data analytics. Snowflake publishing is a separate workflow and is not automatically triggered when a dashboard page loads.

## Implemented Data Mining Modules

### 1. ETL and Feature Engineering

**Location:** `etl/transform/`, `etl/pipelines/`

The Pandas-based ETL pipeline validates source data, cleans records, checks relationships, generates data-quality reports, and produces processed Parquet datasets.

Features include:

- Missing-value and duplicate-key handling.
- Referential-integrity and business-rule validation.
- Order outlier detection and capped analytical values.
- Customer purchasing and restaurant performance features.
- Reference-date-aware calculations that exclude future events.
- Validation reports and processed entity and feature datasets.

The pipeline generates `validation_report.json` and processed Parquet outputs. Critical validation failures stop feature generation.

### 2. Sentiment Analysis

**Location:** `mining/sentiment/`

Implemented capabilities include:

- Overall review sentiment scoring using VADER.
- Positive, negative, neutral, and invalid classifications.
- Lexicon-based aspect sentiment for food, service, ambience, and price.
- Sentiment aggregation by restaurant, city, cuisine, and month.
- Optional transformer-based sentiment inference using `cardiffnlp/twitter-roberta-base-sentiment-latest`.

VADER is the default backend. Transformer inference can be selected using `SENTIMENT_MODEL=transformer`.

The transformer smoke test is not a full accuracy evaluation against a labeled dataset. Aspect labels are lexicon-based rather than outputs from a trained aspect model.

### 3. Customer Segmentation

**Location:** `mining/clustering/`

The clustering module groups customers using purchasing and feedback features, including:

- Recency and order frequency.
- Total spend and average order value.
- Ratings and sentiment, when available.

The module evaluates K-Means, agglomerative clustering, and DBSCAN using clustering-quality metrics.

Cluster labels are descriptive interpretations of customer behavior, not a validated customer taxonomy.

### 4. Association Rule Mining

**Location:** `mining/association/`

The module uses Apriori from MLxtend to discover food items that frequently occur together in completed orders.

Metrics include:

- Support and support count.
- Confidence.
- Lift.
- Leverage.
- Conviction.

Global mining and optional restaurant-specific mining are supported. Food-item identifiers distinguish catalog entries that share the same display name.

Association indicates co-occurrence, not causation. These patterns can support complementary-item recommendations.

### 5. Customer Inactivity and Churn-Risk Analysis

**Location:** `mining/churn/`

The module calculates customer inactivity from completed-order history and assigns rule-based risk categories.

It considers features such as order frequency, purchase gaps, recent activity changes, ratings, and sentiment where available.

The risk score is a heuristic, not a calibrated probability that a customer will churn.

### 6. Food and Restaurant Recommendation System

**Location:** `mining/recommendation/`, `backend/app/services/`, `backend/app/api/analytics.py`

FoodPulse includes a recommendation engine and a user-facing discovery interface that present mining results through food-item and restaurant cards.

The recommendation foundation uses available signals such as:

- Customer purchase history.
- Cuisine preferences.
- Association-rule strength.
- Restaurant quality and ratings.
- Familiarity and popularity.
- Cold-start scoring for limited purchase histories.

The recommendation API exposes ranked recommendations and supporting explanations. The interface separates food discovery from detailed business analytics.

#### Food Discovery Sections

The discovery interface organizes recommendations into six sections.

**1. Picked for You**

Ranks food items using available individual customer history and relevant preference signals. When purchase history is insufficient, the system should provide an appropriate fallback rather than imply strong personalization.

**2. Popular Choices**

Surfaces popular food items and restaurants based on available data. Popularity-based suggestions are distinguished from individualized recommendations.

**3. Similar to What You Like**

Suggests similar food items using available item attributes and purchasing patterns. Similarity depends on the attributes and history available in the processed datasets.

**4. Frequently Bought Together**

Uses association-rule mining to identify complementary items that frequently appear together in completed orders. The section translates association-rule results into understandable food suggestions.

**5. Restaurants for You**

Ranks restaurants using relevant available preferences and attributes, such as cuisine, quality, popularity, and customer history.

**6. Explore Something New**

Provides relevant alternatives and less repetitive suggestions. Recommendations are de-duplicated across applicable sections to reduce unnecessary repetition.

#### Recommendation Cards and Interactions

The frontend presents discovery results through card-based layouts rather than requiring users to interpret mining tables directly.

The discovery experience includes:

- Separate food-item and restaurant recommendations.
- Search and useful filters.
- Short explanations for recommendation choices.
- Data-backed popularity and similarity signals.
- Complementary-item suggestions.
- Alternative discovery options.
- Responsive layouts and loading or empty states.

Food names and item identifiers must remain distinct because different catalog entries may share the same display name.

Images, prices, ingredients, ratings, and availability must come from verified data sources. Missing attributes should not be invented or presented as verified facts.

#### Recommendation Limitations

- Recommendation scores represent ranking strength, not purchase probabilities.
- Personalized suggestions depend on the available customer history.
- General popularity results are not equivalent to personalized recommendations.
- Sparse interaction history can reduce recommendation quality.
- Association rules show co-occurrence, not causation.
- Recommendation quality requires continued evaluation using suitable holdout data.

A previous holdout evaluation reported the following results:

| Evaluation | Precision | Recall | Hit Rate |
|---|---:|---:|---:|
| Food items at 5 | 0.0053 | 0.0163 | 0.0244 |
| Restaurants at 3 | 0.0213 | 0.0639 | 0.0639 |

These are previously recorded results, not a guarantee of current performance. They indicate that recommendation quality remains an area for improvement. Association rules were excluded from that holdout evaluation to avoid using full-history mining results that could leak future information.

### Nearby Restaurants — Google Maps Integration

- Added a Nearby Restaurants page at `/app/nearby`.
- Users can search for real-world restaurants by destination, such as a city, address, college, landmark, or tourist destination.
- Supports browser geolocation after the user grants permission.
- Displays Google Maps markers and a corresponding restaurant list.
- Shows restaurant names and available ratings, review counts, addresses, and price information when returned by Google Places.
- Provides Google Maps directions links.
- Handles loading, empty results, missing API key, location permission denial, and API errors.
- Loads Google Maps only when needed on the Nearby page.
- Uses a Google Maps Demo Key; supported features and quotas apply.

**Data separation:** Google Places listings are real-world results and are not treated as FoodPulse sample restaurants.

### Nearby-to-Recommendations Integration

- Users can select a sample FoodPulse customer from the existing recommendation customer list.
- The Nearby page links to that customer's stored recommendations.
- Supported Google `primaryType` values can map to FoodPulse cuisine filters when the mapping is unambiguous.
- Generic or ambiguous restaurant types do not trigger guessed cuisine filters.
- Recommendation cards remain labelled as sample-data rankings, not dishes from the selected Google restaurant.
- No matching is performed using Google Place IDs, restaurant names, addresses, or coordinates.

### Discovery and Analytics Improvements

- Improved discovery filters, recommendation cards, loading states, empty states, and error messages.
- Added explanations for metrics, data sources, and score interpretation.
- Clarified association-rule support, confidence, lift, and basket scope.
- Distinguished historical demand from forward forecasts.
- Clarified that review sentiment and restaurant ratings come from sample data rather than live public reviews.
- Improved responsive layouts and data-provenance messaging across analytics pages.

### 7. Demand Forecasting

**Location:** `mining/forecasting/`

The forecasting module predicts completed-order demand at restaurant level and food-item quantity demand.

Supported models:

- Ridge regression.
- Seasonal-naive baseline.

Features include daily and weekly aggregation, chronological holdout evaluation, forward forecasts, and MAE, RMSE, and WAPE metrics.

Forecasts are clipped at zero. Prediction intervals are not currently included, and sparse demand may produce high WAPE values. Forecasts should not be treated as guaranteed production demand.

## PySpark Feature Engineering

**Location:** `pyspark/jobs/feature_aggregations.py`

A standalone Spark job performs customer and restaurant feature aggregation from prepared Parquet datasets.

Features include completed-order filtering, reference-date-aware calculations, customer and restaurant outputs, restaurant activity summaries, and optional sentiment counts.

The standalone job writes to `data/processed/spark_features/` by default. It does not replace the Pandas ETL outputs or write to PostgreSQL.

The job was locally verified on 12 October 2026, producing 500 customer rows and 50 restaurant rows, with shared numeric features matching Pandas outputs for the same reference date.

Spark remains optional in the Airflow workflow.

## Snowflake Analytics Integration

**Location:** `warehouse/snowflake/`

The Snowflake loader publishes approved processed Parquet datasets into the `FOODPULSE.ANALYTICS` schema.

Implemented capabilities include:

- Environment-based configuration.
- Local file and schema validation.
- Dry-run planning and table row counts.
- Optional connection verification.
- Parameterized row loading.
- Temporary staging tables and snapshot replacement.
- Row-count verification and rollback for failed table loads.
- Sanitized error reporting.

The default mode is a dry run. Live loading requires explicit execution and valid Snowflake credentials and permissions.

A previous live account test completed an analytical load. Automated loader tests use mocked connections and do not require a live Snowflake account.

The dimensional star schema is implemented beside the snapshots. It does not replace them.

- Dimensions: `DIM_DATE`, `DIM_CUSTOMER`, `DIM_RESTAURANT`, `DIM_FOOD_ITEM`.
- Facts: `FACT_ORDERS` (one row per order), `FACT_REVIEWS` (one row per review).
- Surrogate keys are deterministic source integer ids. Foreign keys are validated in tests and in `warehouse/snowflake/sql/star_validate.sql`.
- Contact details, hashed passwords, and review body text are not loaded.
- `DIM_LOCATION`, `DIM_USER`, and `FACT_ORDER_ITEMS` are omitted because the requested model and source files do not support them without inventing grain or PII.

Dry-run the star transform without connecting:

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_star --dry-run
```

Details: `warehouse/README.md`, `warehouse/snowflake/sql/star_schema.sql`, `warehouse/snowflake/sql/star_load.sql`, `warehouse/snowflake/sql/star_validate.sql`.

A live star load still requires a Snowflake warehouse, `SNOWFLAKE_*` settings, and an explicit `--execute`. This repository does not run those statements.

## Airflow Workflow Orchestration

**Location:** `airflow/dags/`, `docker-compose.airflow.yml`

The `foodpulse_pipeline` DAG coordinates existing processing commands rather than reimplementing the mining algorithms.

### Workflow

1. Validate input files and resolve the reference date.
2. Run ETL and feature engineering.
3. Run sentiment analysis, association-rule mining, and demand forecasting.
4. Run customer segmentation and churn-risk analysis.
5. Generate recommendations.
6. Optionally run Spark feature processing.
7. Optionally run the Snowflake publishing task.
8. Validate the expected output files.

The Airflow environment includes a webserver, scheduler, PostgreSQL metadata database, LocalExecutor configuration, and mounted DAG and project directories.

The Airflow UI is available at `http://localhost:8080` when services are running and initialized.

### Verification Status

The workflow was manually executed on 19 October 2026.

- Input validation, ETL, sentiment, forecasting, clustering, churn analysis, association mining, recommendations, Snowflake dry-run, and output validation completed successfully.
- The Spark task was skipped because optional Spark processing was disabled.
- Association mining completed after enabling Apriori's `low_memory=True` option.
- The Snowflake task completed in dry-run mode. It did not write data to Snowflake during that run.

A successful dry run verifies the configured planning workflow, not a live warehouse load.

**Execution safety:** ETL tasks regenerate files in `data/processed/` and can replace existing outputs. Preserve important outputs before intentionally running a full pipeline. Keep `FOODPULSE_SNOWFLAKE_EXECUTE` unset unless a live load is specifically intended.

## Redesigned React Analytics Dashboard

**Location:** `frontend/`, `backend/app/`

The redesigned frontend integrates the recommendation experience and analytical reporting into the existing FoodPulse application.

The stack uses React, TypeScript, Vite, Tailwind CSS, and Plotly, with FastAPI providing backend analytics.

The production frontend build completed successfully in a previous verification. The Plotly bundle produces a chunk-size warning that can be optimized later.

### User-Facing Food Discovery

The discovery interface focuses on practical food and restaurant recommendations through:

- Food-item and restaurant cards.
- Search and useful filters.
- Personalized recommendations when customer history is available.
- Popular choices and similar-item discovery.
- Frequently bought together suggestions.
- Restaurant recommendations.
- Clear explanations for recommendations.
- Data-backed ratings, prices, cuisine, images, and availability when available.
- Responsive layouts, loading states, and useful empty states.

The six recommendation sections are designed to distinguish personalized recommendations from general popularity results and complementary-item suggestions.

### Business Intelligence Reports

FoodPulse uses its React and Plotly stack for interactive reporting instead of requiring a separate Power BI implementation.

Reporting areas include:

- Restaurant performance and customer ratings.
- Review sentiment and satisfaction trends.
- Customer segments and churn-risk summaries.
- Food-item purchasing patterns and association rules.
- Historical and forecast demand.
- Recommendation insights and evaluation results.

Charts should communicate the meaning of the data using clear labels, summaries, and explanations.

The food discovery experience and business insights remain separate areas so users can browse recommendations while analysts explore detailed reports.

## PostgreSQL and FastAPI

The operational backend uses FastAPI, SQLAlchemy, and PostgreSQL. It includes database models, authentication infrastructure, and endpoints for operational entities and statistics.

Representative endpoints include:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Application health |
| GET | `/restaurants` | List restaurants |
| GET | `/restaurants/{id}` | Restaurant details |
| GET | `/customers` | List customers |
| GET | `/stats/overview` | Operational database statistics |
| GET | `/analytics/overview` | Processed analytics summary |
| GET | `/analytics/restaurants` | Restaurant analytics |
| GET | `/analytics/sentiment` | Sentiment analysis |
| GET | `/analytics/segments` | Customer segments |
| GET | `/analytics/churn` | Customer inactivity-risk summaries |
| GET | `/analytics/association` | Association rules |
| GET | `/analytics/forecast` | Demand forecasts |

Other analytics endpoints cover recommendations, itemsets, discovery sections, and restaurant-specific forecast details. Check the running application's `/docs` page for the exact available endpoints.

### Operational Database Status

The PostgreSQL database is configured as `foodpulse`. During the latest local verification, the `restaurants`, `customers`, `orders`, and `reviews` tables contained zero rows.

Consequently, `/stats/overview` returned zero counts and null average values. This is consistent with the empty operational tables observed during that check.

The processed Parquet analytics source remains populated independently. The successful `/analytics/overview` response reported:

- 50 restaurants.
- 500 customers.
- 5,000 orders.
- 3,000 reviews.
- 4,405 completed orders.
- Completed-order revenue of approximately 5,054,698.08 in the dataset's currency units.

These values describe the processed analytics data, not PostgreSQL table counts.

The operational loader is `python -m etl.pipelines.run_postgres_load`. It copies processed Parquet into the existing `locations`, `restaurants`, `customers`, `orders`, and `reviews` tables. Locations are loaded first because restaurants require `location_id`. The default is a dry-run that validates files and does not write. `--execute` upserts by primary key in one transaction after confirming the target is the local `foodpulse` database. It never deletes rows. It does not load users, food items, order items, or customer activity. See `etl/load/README.md`.

`etl/load/seed.py` generates Faker sample data and drops all ORM tables. Do not use it to populate the operational database.

The current empty PostgreSQL tables do not imply that the Parquet-backed analytics are empty. These sources must remain clearly distinguished in the application and documentation.

## Project Structure

```text
FoodPulse/
├── airflow/
│   ├── dags/
│   ├── Dockerfile
│   └── requirements.txt
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
├── data/
│   ├── raw/
│   ├── sample/
│   └── processed/
├── etl/
│   ├── extract/
│   ├── transform/
│   ├── load/
│   └── pipelines/
├── frontend/
│   ├── public/
│   └── src/
│   ├── components/
│   │   ├── NearbyMap.tsx
│   │   └── ...
│   ├── lib/
│   │   ├── googleMaps.ts
│   │   ├── nearbyPlaces.ts
│   │   ├── nearbyRecommendations.ts
│   │   └── ...
│   ├── pages/
│   │   ├── NearbyPage.tsx
│   │   └── ...
│   ├── vite-env.d.ts
│   ├── .env.example
│   └── tests/
│       ├── nearbyPlaces.test.ts
│       ├── nearbyRecommendations.test.ts
│       └── ...
├── mining/
│   ├── sentiment/
│   ├── clustering/
│   ├── association/
│   ├── churn/
│   ├── recommendation/
│   └── forecasting/
├── pyspark/
│   └── jobs/
├── tests/
├── warehouse/
│   ├── snowflake/
│   ├── dimensions/
│   ├── facts/
│   └── sql/
├── docker-compose.yml
├── docker-compose.airflow.yml
├── requirements.txt
└── README.md
```

## Local Setup and Execution

### Prerequisites

- Python and a virtual environment.
- Node.js and npm.
- PostgreSQL for operational database functionality.
- Docker Desktop and Docker Compose for Airflow and containerized services.
- Java and PySpark for standalone Spark processing.
- Snowflake credentials only when a live warehouse connection is required.

### 1. Configure Environment Variables

From the project root, create your local `.env` using the repository's environment template if one exists:

```powershell
Copy-Item .env.example .env
```

If the template does not exist, inspect the configuration code and create the required variables manually.

Configure the database connection, application secrets, and optional integrations according to the current configuration.

Never commit `.env` files, database passwords, API keys, or other credentials.

### Google Maps Demo Key

The Nearby Restaurants feature reads the following Vite environment variable from `frontend/.env`:

```dotenv
VITE_GOOGLE_MAPS_API_KEY=YOUR_DEMO_KEY
```

Replace the placeholder with your own Demo Key. Keep the actual key out of GitHub. The variable name and an empty placeholder belong in `frontend/.env.example`.

Vite variables prefixed with `VITE_` are exposed to browser code. Do not store backend passwords or other private server credentials in these variables.

The Demo Key has supported-feature and quota limits. The current implementation does not automatically switch to a billable API when a feature is unavailable or a quota is reached.

### 2. Install Python Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Install additional dependency files only if they exist in the current checkout and have not already been installed.

### 3. Start the Backend

From the repository root, use the existing startup script:

```powershell
.\scripts\run-backend.ps1
```

The expected backend address is:

`http://localhost:8000`

Open `http://localhost:8000/docs` to inspect the available API endpoints.

If the startup script is unavailable, inspect the current backend entry point before selecting the appropriate Uvicorn command.

### 4. Start the Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local development URL printed by Vite, usually `http://localhost:5173`.

### 5. Build the Frontend

From the `frontend` directory:

```powershell
npm run build
```

A successful build verifies TypeScript compilation and production bundling. It does not independently verify that every backend endpoint or page works correctly.

### 6. Run Tests

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

A previous full-suite verification reported **123 passed, 1 skipped**. Rerun the tests after subsequent changes to establish the current result.

### 7. Run Individual Mining Modules

Run commands from the repository root after the required processed inputs are available.

**Transform and feature engineering**

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_transform --reference-date 2026-10-11
```

**Sentiment analysis**

```powershell
.\.venv\Scripts\python.exe -m mining.sentiment.run_analysis
```

**Customer segmentation**

```powershell
.\.venv\Scripts\python.exe -m mining.clustering.run_segmentation --seed 42
```

**Association rule mining**

```powershell
.\.venv\Scripts\python.exe -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3
```

**Churn-risk analysis**

```powershell
.\.venv\Scripts\python.exe -m mining.churn.run_analysis --reference-date 2026-10-11 --inactivity-days 90 --at-risk-days 45
```

**Recommendations**

```powershell
.\.venv\Scripts\python.exe -m mining.recommendation.run_recommendations --reference-date 2026-10-11
```

**Demand forecasting**

```powershell
.\.venv\Scripts\python.exe -m mining.forecasting.run_forecast --reference-date 2026-10-11 --horizon 7
```

**Snowflake dry run**

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_load --dry-run
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_star --dry-run
```

**PostgreSQL operational load (dry-run default)**

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_postgres_load
.\.venv\Scripts\python.exe -m etl.pipelines.run_postgres_load --dry-run
```

Live PostgreSQL writes require an explicit flag and a verified local `foodpulse` database:

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_postgres_load --execute
```

Do not run `--execute` until you have reviewed the dry-run summary. The command never deletes existing rows. After a live load, compare `GET /stats/overview` with the loader summary; `/analytics/overview` still reads Parquet.

These commands can generate or replace processed outputs. Review the output paths and preserve important files before rerunning a pipeline.

### Optional Transformer Sentiment

Set `SENTIMENT_MODEL=transformer` to select transformer inference. Leave it unset or set it to `vader` to use the default VADER backend.

Transformer inference may require additional dependencies and model downloads. The dashboard does not run transformer inference automatically.

### Optional Spark Processing

The standalone Spark job writes to `data/processed/spark_features/` by default and preserves the Pandas ETL outputs.

Enable the Airflow Spark task only when deliberately testing it in a configured Spark environment.

## Testing and Verification

Previously recorded verification results include:

| Area | Recorded result |
|---|---|
| ETL and data-mining modules | 67 passed |
| Snowflake loader tests | 21 passed |
| Spark feature tests | 4 passed |
| Airflow DAG tests | 8 passed, 1 skipped |
| Dashboard API tests | 12 passed |
| Full test suite | 123 passed, 1 skipped |
| Frontend production build | Successful |
| Discovery and analytics tests | Previously passed targeted test runs |
| Discovery-related frontend build | Previously successful |

These are historical results, not a guarantee that all tests still pass after later changes. Rerun the relevant tests when modifying a module.

## Data Safety and Security

- Keep `.env`, credentials, database passwords, and access tokens out of version control.
- Do not commit generated datasets, temporary validation outputs, or local virtual environments.
- Review ETL and Airflow tasks before rerunning them because processed files may be replaced.
- Keep Spark and live Snowflake execution disabled unless explicitly required.
- Use Snowflake dry-run mode to inspect planned operations before a live load.
- Do not modify production data or run destructive database operations as part of ordinary testing.
- Verify the intended local `foodpulse` database with a PostgreSQL dry-run before `--execute`. The loader refuses unexpected hosts and database names and never deletes rows.
- Keep operational database statistics separate from processed Parquet analytics.

## Application Routes

The React frontend provides dedicated pages for food discovery, restaurant discovery, personalized recommendations, and business analytics.

| Route | Purpose |
|---|---|
| `/` | FoodPulse application landing page |
| `/app/nearby` | Discover nearby restaurants using Google Maps Places and a user-selected location |
| `/app/recommendations` | Explore food-item and restaurant recommendations using available sample customer data |
| `/app/restaurants` | Browse restaurant information and discovery features |
| `/app/sentiment` | Explore review sentiment and satisfaction insights |
| `/app/segments` | View customer segmentation results |
| `/app/churn` | Explore customer inactivity and churn-risk analysis |
| `/app/association` | Inspect food-item association rules and complementary-item patterns |
| `/app/forecast` | View historical demand and demand forecasts |
| `/app` | Access the main application and its analytics navigation |

**Route note:** The application may use additional nested routes or query parameters. Check the current frontend router for the exact route configuration. The recommendations page can accept a customer identifier through the `customer` query parameter when navigating from Nearby Restaurants.

## Limitations and Known Issues

### Nearby Restaurant Discovery

- Nearby restaurant search uses Google Maps JavaScript API and Places functionality, subject to the configured API key, available fields, and usage quotas.
- Browser geolocation requires user permission. Users can alternatively search using a destination such as a city, address, college, or landmark.
- The Google Maps Demo Key is intended for prototyping. Live search behavior and quota-related states still require end-to-end verification.
- Restaurant photos and reviews are not guaranteed to be available through the current integration.
- Google Places restaurants are not automatically matched to FoodPulse's sample restaurant records. Google Place IDs, names, addresses, and coordinates are not used to establish a verified relationship with the sample recommendation datasets.
- Recommendations reached from Nearby Restaurants use a selected sample FoodPulse customer and, where the cuisine mapping is unambiguous, a cuisine preference. They are not verified dish-level recommendations from the selected Google restaurant.
- The Google Maps API key must remain in the local `frontend/.env` file and must never be committed to version control. Values prefixed with `VITE_` are exposed to the browser, so the key must not contain server-side secrets.

### Recommendation and Analytics Data

- Recommendation scores are ranking signals, not probabilities that a customer will purchase an item.
- Personalization depends on the customer history available in the processed datasets. Sample customers should not be treated as authenticated real users.
- Restaurant-level review aggregates do not represent verified ratings for individual food items.
- Missing images or food attributes should use an appropriate fallback rather than display invented information.
- Association rules describe co-occurrence and do not establish causation.
- Forecasts are estimates and may be less reliable for sparse or irregular demand.
- The PostgreSQL operational database and processed Parquet analytics are separate data sources. Empty PostgreSQL tables do not imply that the processed analytics datasets are empty.

### Remaining Validation and UI Work

- Complete live end-to-end testing of destination search, geolocation, Google Places search, map markers, list selection, and directions links.
- Verify the missing-API-key, no-results, loading, and quota-error states without exposing credentials.
- The Customers page remains a directory placeholder rather than a fully implemented customer analytics experience.
- The forecast page may briefly display an empty-state message while data is loading.
- The Nearby page's permission-denied message may appear in more than one panel.
- The frontend production build reports an existing Plotly bundle-size warning that can be optimized separately.

### Verification Status

The latest recorded automated checks completed successfully:

| Check | Result |
|---|---|
| Frontend lint | Passed |
| Frontend tests | 48 passed |
| Frontend production build | Passed, with an existing Plotly bundle-size warning |
| Backend tests | 164 passed, 1 skipped |
| Skipped test | Airflow DAG test; Apache Airflow was not installed in the project virtual environment |
| Nearby live Google Maps requests | Not performed during the recorded verification |

These results describe the recorded verification run and should be refreshed after further code changes. A successful automated test run does not replace live end-to-end testing of Google Maps and Places functionality.

## Current Project Status

| Component | Status |
|---|---|
| Pandas ETL and feature engineering | Implemented and tested |
| VADER sentiment and aspect labels | Implemented and tested |
| Optional transformer sentiment | Smoke-tested; full accuracy evaluation pending |
| Customer clustering | Implemented and tested |
| Apriori association rules | Implemented and tested |
| Rule-based churn-risk analysis | Implemented and tested |
| Recommendation foundation | Implemented; recommendation quality can be improved |
| Food and restaurant discovery cards | Integrated; verify the latest end-to-end behavior |
| Recommendation explanations and discovery sections | Implemented; continue validating with available data |
| Demand forecasting | Implemented and tested |
| PySpark feature aggregation | Implemented and locally verified; optional in Airflow |
| Snowflake analytical loader | Implemented; dry-run workflow verified and a prior live account test completed |
| Snowflake dimensional star schema | Implemented; unit-tested dry-run transform; live `--execute` still required |
| FastAPI backend | Implemented |
| React analytics frontend | Integrated; production build previously successful |
| Interactive Plotly dashboard | Implemented; further reporting improvements possible |
| Airflow orchestration | Manually executed successfully; live execution must be verified separately where required |
| PostgreSQL operational tables | Currently empty in the latest local verification; populate only with `--execute` after review |
| PostgreSQL data-loading workflow | Implemented; dry-run default; unit-tested without writing to PostgreSQL |
| Final end-to-end regression validation | Required |

## Next Development Priorities

1. Continue improving and validating food-item and restaurant recommendations.
2. Run a live Snowflake star-schema load with `--execute` and `warehouse/snowflake/sql/star_validate.sql` when an account is available.
3. Verify all frontend pages, API integrations, filters, and empty states.
4. Review the PostgreSQL dry-run summary, then run `python -m etl.pipelines.run_postgres_load --execute` when operational population is scheduled.
5. Evaluate recommendation quality using appropriate holdout data and meaningful metrics.
6. Rerun the full test suite and validate the Airflow workflow after changes.
7. Document the final architecture, data flow, supported functionality, and limitations.

## Project Goal

FoodPulse connects data mining with practical decisions. It combines restaurant analytics, customer behavior analysis, machine learning, warehouse integration, workflow orchestration, and an accessible web interface.

The goal is to build a platform that does not merely display data, but helps users discover relevant food and restaurants while enabling analysts to understand customer behavior, restaurant performance, and demand.
