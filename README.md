# FoodPulse

**FoodPulse — Restaurant Intelligence & Customer Experience Mining Platform.**

FoodPulse turns restaurant customer, order, and review data into insights: sentiment, segments, co-purchase rules, inactivity risk, offline recommendations, and demand forecasts.

## What is implemented

| Area | Status |
|------|--------|
| Pandas cleaning, validation, and feature engineering (`etl/transform/`, `etl.pipelines.run_transform`) | Implemented |
| VADER overall sentiment and lexicon aspect labels (`mining/sentiment/`) | Implemented |
| Customer clustering (`mining/clustering/`) | Implemented |
| Apriori association rules (`mining/association/`, mlxtend) | Implemented |
| Rule-based inactivity / churn-risk score (`mining/churn/`) | Implemented |
| Offline food and restaurant recommendations (`mining/recommendation/`) | Implemented |
| Demand forecasting (`mining/forecasting/`) | Implemented |
| FastAPI list and stats endpoints | Implemented |
| Snowflake analytical load (`warehouse/snowflake/`) | Implemented. A previous live account test completed the analytical load |
| Airflow orchestration | Not implemented |
| PySpark feature job (`pyspark/jobs/feature_aggregations.py`) | Implemented. Verified locally on 12 October 2026 with Java 25 and PySpark 4.2.0. It writes a separate directory and does not replace the Pandas ETL files |
| Optional transformer sentiment (`SENTIMENT_MODEL=transformer`) | Present as optional code; not downloaded or verified |
| React dashboard wired to mining outputs, and Power BI | Not implemented |

```
Raw data → ETL (Pandas/PySpark, Airflow) → PostgreSQL (operational)
  → Snowflake (star-schema warehouse)
  → Data mining / ML / NLP
  → FastAPI → React dashboard + Power BI
```

The mining modules above read and write local Parquet. They do not open a Snowflake connection. `warehouse/snowflake/` can publish approved analytical Parquet files, and only when `python -m warehouse.snowflake.run_load --execute` is used. The default command is a local dry-run. The FastAPI routes are the Module 1 list and stats endpoints, not a dashboard over the mining files. PostgreSQL remains the operational database.

## Project structure

```
FoodPulse/
├── backend/app/
│   ├── api/ models/ schemas/ services/
│   ├── core/          # config.py, security.py (JWT + bcrypt)
│   ├── db/session.py  # SQLAlchemy engine/session
│   └── main.py
├── frontend/          # Vite + React + TS + Tailwind + Recharts
├── etl/{extract,transform,load,pipelines}
├── data/{raw,processed,sample}
├── mining/{sentiment,clustering,association,churn,recommendation,forecasting}
├── warehouse/snowflake/   # config, connection, DDL, load, CLI
├── warehouse/{dimensions,facts,sql}
├── airflow/dags  pyspark/jobs  powerbi/reports  docker  docs
├── docker-compose.yml
├── Makefile / scripts/
├── requirements.txt
└── .env.example
```

`warehouse/snowflake/` is implemented. `warehouse/dimensions/`, `warehouse/facts/`, and `warehouse/sql/` remain placeholders. `airflow/` and `powerbi/` are not implemented. `pyspark/jobs/feature_aggregations.py` is the Spark feature job; the directory `pyspark/` is not the PySpark library. `mining/forecasting/` is implemented.

## Make / scripts

| Target | Action |
|--------|--------|
| `make setup` / `scripts/setup.ps1` | venv + backend deps + frontend npm install |
| `make run-backend` / `scripts/run-backend.ps1` | `uvicorn app.main:app --reload` |
| `make run-frontend` / `scripts/run-frontend.ps1` | `npm run dev` |
| `make run-etl` / `scripts/run-etl.ps1` | Seed CSVs. This is not the transform pipeline |
| `make test` / `scripts/test.ps1` | pytest from `backend/` only |

`scripts/run-etl.ps1` runs `python etl\load\seed.py --csv-only`. That regenerates and overwrites `data/sample`. The transform pipeline is a different command, `python -m etl.pipelines.run_transform`, which only reads the existing sample CSVs.

`scripts/test.ps1` changes into `backend/` and runs `pytest -q`. It does not collect the root `tests/` modules (`test_transform.py`, `test_sentiment.py`, `test_clustering.py`, `test_association.py`, `test_churn.py`, `test_recommendation.py`, `test_forecasting.py`, `test_snowflake_load.py`, `test_spark_features.py`). There are no test modules under `backend/`. The `tests/` command and the count from this documentation check are in [Tests](#tests).

## Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local seed / API outside Docker)
- PostgreSQL reachable at the URL in `.env` (provided by Compose)

## Quick start

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` if needed. Defaults work with the Compose Postgres service when the API runs on the host:

```
DATABASE_URL=postgresql+psycopg2://foodpulse:foodpulse@localhost:5432/foodpulse
SECRET_KEY=change-me-to-a-long-random-secret
```

### 2. Start Postgres + API with Docker Compose

```bash
docker compose up --build -d
# or: cd docker && docker compose up --build -d
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Postgres: `localhost:5432` (user/password/db: `foodpulse`)

### 3. Install Python deps (host) and seed data

From the project root:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r backend/requirements.txt
python etl/load/seed.py
```

This generates about 50 restaurants, 500 customers, 5,000 orders, and 3,000 reviews, writes CSVs under `data/sample/`, and loads them into PostgreSQL. `python etl/load/seed.py --csv-only` writes the CSVs and does not load the database. Both forms overwrite `data/sample`.

### 4. Run the API locally (optional)

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ensure Postgres is running (`docker compose up -d postgres` from `docker/`).

## API endpoints (Module 1)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness / app info |
| `GET` | `/restaurants` | List restaurants (`skip`, `limit`) |
| `GET` | `/restaurants/{id}` | Restaurant detail |
| `GET` | `/customers` | List customers (`skip`, `limit`) |
| `GET` | `/stats/overview` | Totals + average rating |

```bash
curl http://localhost:8000/health
curl http://localhost:8000/stats/overview
```

## Database entities

`users`, `restaurants`, `customers`, `food_items`, `orders`, `order_items`, `reviews`, `locations`, `customer_activity`

Reviews include `rating`, `review_text`, and `created_at`. Orders include `customer_id`, `restaurant_id`, `total_amount`, `discount_used`, and `order_date`.

`review_sentiment` (`review_id` primary key, plus overall and aspect columns) is created with the other SQLAlchemy models. It stays empty unless sentiment analysis is run with `--persist`. After the initial sentiment run it had **zero** rows.

## Data cleaning, validation, and features

Pandas pipeline in `etl/transform/`, entry point `etl/pipelines/run_transform.py`. It reads `data/sample/*.csv`, cleans each table, writes a JSON validation report, and stops when that report contains critical errors. Warnings do not stop it. Source CSVs are only read.

`pyarrow` is required to write Parquet. It is in the root `requirements.txt`, not `backend/requirements.txt`. If the virtualenv was installed from the backend file only:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyarrow>=15.0"
```

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_transform --reference-date 2026-10-11
```

`--reference-date` is a UTC calendar date (`YYYY-MM-DD`). If omitted, the pipeline uses `FEATURE_REFERENCE_DATE` when set, otherwise the current UTC date. Optional flags: `--sample-dir`, `--output-dir` (default `data/processed`).

`USE_SPARK=1` loads `pyspark/jobs/feature_aggregations.py` by file path and uses it only for the feature tables inside the ETL run. The default path does not import PySpark. The standalone job below is the verified way to run Spark without replacing those ETL files.

### PySpark feature job

`pyspark/jobs/feature_aggregations.py` reads prepared Parquet from `--input-dir` (default `data/processed`) and writes a new directory. It does not modify `data/sample`, PostgreSQL, or the original ETL Parquet files. Required inputs are `customers.parquet`, `restaurants.parquet`, `orders.parquet`, and `reviews.parquet`. `review_sentiment.parquet` is optional.

Shared feature columns match `etl/transform/feature_engineering.py`. Completed orders are `status` lowercased to `completed`, events after the reference date are excluded, and `sentiment_label` and `sentiment_score` stay null. Spark also writes `restaurant_activity.parquet` (restaurant spend, average order value, and distinct customer count), which the Pandas feature file does not contain. When review sentiment is present, it writes `restaurant_sentiment_counts.parquet` with positive, negative, neutral, and invalid counts and proportions. Those counts are not copied into `restaurant_features.parquet`.

Prerequisites: Java and `pyspark` from the root `requirements.txt` (`pyspark>=3.5`). On 12 October 2026 this machine used Java 25.0.3 and PySpark 4.2.0. Spark warned that `winutils.exe` was missing and still finished. Install PySpark into the project virtualenv if it is not already there:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyspark>=3.5"
```

Run the job from the repository root. The default output is `data/processed/spark_features`, which is not the ETL feature files:

```powershell
.\.venv\Scripts\python.exe pyspark\jobs\feature_aggregations.py --input-dir data\processed --output-dir data\processed\spark_features --reference-date 2026-10-11
```

Outputs in that directory: `customer_features.parquet`, `restaurant_features.parquet`, `restaurant_activity.parquet`, and, when the sentiment file exists, `restaurant_sentiment_counts.parquet`.

Tests use temporary Parquet files and do not read `data/processed`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_spark_features.py -q
```

On 12 October 2026 that command reported **4 passed**. The same day, the job above was run with `--output-dir` set to a temporary directory. Spark returned 500 customer rows and 50 restaurant rows. The shared numeric feature columns matched the existing Pandas `customer_features.parquet` and `restaurant_features.parquet` for reference date 2026-10-11. The original ETL files were not replaced. `restaurant_sentiment_counts.parquet` contained 3,000 scored reviews. Airflow does not call this job.

### Observed on the 2026-10-11 sample run

These figures are from that run of `--reference-date 2026-10-11`. They are not guaranteed for another date or another sample extract. `validation_report.json` had `"status": "warning"`, `"reference_date": "2026-10-11"`, and no critical errors.

| Dataset | Rows checked | Report status |
|---------|----------------|---------------|
| `locations` | 20 | passed |
| `users` | 5 | passed |
| `restaurants` | 50 | passed |
| `food_items` | 587 | passed |
| `customers` | 500 | warning |
| `orders` | 5,000 | warning |
| `order_items` | 14,995 | passed |
| `reviews` | 3,000 | passed |
| `customer_activity` | 1,241 | passed |

- `customers`: optional `gender` missing on **138** rows. The value is left missing. Identifiers are not invented.
- `orders`: **25** `total_amount` values fall outside Tukey 1.5-IQR fences. `total_amount` is unchanged. `total_amount_capped` is clipped to the fences. The lower fence is held at 0. That run recorded `outlier_lower_fence` 0, `outlier_upper_fence` 3188.86, and `outlier_method` `tukey_iqr_1.5_lower_fence_at_least_zero`. `is_total_outlier` marks the 25 rows.

### Cleaning and validation

Cleaning returns a new DataFrame. Duplicate primary keys (`id`) keep the first row. Distinct ids are kept even when other fields match. A missing `id` stays missing.

Empty optional text becomes missing. The only numeric fill is `orders.discount_used`: a missing discount becomes 0, matching the ORM default. Review text is HTML-stripped, trimmed, and lowercased. Negations, contrast words, and punctuation stay. Timestamps use Pandas `format="mixed"`. Eleven review `created_at` values in this sample include microseconds.

Critical checks raise `CriticalValidationError` after the JSON report is written, and feature files are not written. They cover required columns, missing or duplicate primary keys, required values, foreign keys (`orders` to `customers` and `restaurants`, and the other model relationships, with nullable `reviews.order_id`), integer ratings 1–5, negative prices or totals, non-positive `order_items.quantity`, and dates outside the accepted range (events from 1990-01-01 through 2100-01-01; dates of birth from 1900-01-01). Dates after the reference date are warnings.

### Feature definitions

`customer_features.parquet` uses completed orders whose `order_date` is on or before the end of the reference date. Cancelled and pending orders are excluded. Recency is calendar days from the last completed order to `feature_reference_date`, null when there is no such order. Spend, order frequency, average order value, and discount usage rate use that same set. Spend is the sum of `orders.total_amount` and is not joined to `order_items`. Average rating and review frequency use reviews on or before the cutoff. Discount usage rate and average order value are null when the completed-order count is zero.

| `restaurant_features.parquet` column | Definition |
|--------|------------|
| `avg_rating` | Mean rating of reviews on or before the reference date |
| `rolling_avg_rating` | Mean rating in the 90 days ending at the reference date; null when that window has no reviews |
| `review_volume` | Count of reviews on or before the reference date |
| `order_volume` | Count of completed orders on or before the reference date |
| `complaint_count` | Reviews in that set with `rating <= 2`. A rating heuristic, not model sentiment |
| `sentiment_label`, `sentiment_score` | Left null. Scored sentiment is in `review_sentiment.parquet` |

Both feature tables include `feature_reference_date`. Feature values change if `--reference-date` changes.

### Generated files

`data/processed/` is gitignored. The pipeline writes:

- `locations.parquet`, `users.parquet`, `restaurants.parquet`, `food_items.parquet`, `customers.parquet`, `orders.parquet`, `order_items.parquet`, `reviews.parquet`, `customer_activity.parquet`
- `customer_features.parquet`, `restaurant_features.parquet`
- `validation_report.json`

Order tables also carry `is_total_outlier`, `total_amount_capped`, `outlier_lower_fence`, `outlier_upper_fence`, and `outlier_method`.

## Sentiment analysis

`mining/sentiment/` scores processed reviews. The default command reads `data/processed/reviews.parquet`, `restaurants.parquet`, and `locations.parquet`. It does not modify `data/sample` or those cleaned entity files. `vaderSentiment` and `matplotlib` are in the root `requirements.txt`, not `backend/requirements.txt`.

```powershell
.\.venv\Scripts\python.exe -m pip install "vaderSentiment>=3.3" "matplotlib>=3.8"
.\.venv\Scripts\python.exe -m mining.sentiment.run_analysis
```

| Flag | Default | Role |
|------|---------|------|
| `--processed-dir` | `data/processed` | Input Parquet and sentiment Parquet output |
| `--artifacts-dir` | `mining/sentiment/artifacts` | Evaluation JSON and confusion-matrix image |
| `--persist` | off | Upsert into PostgreSQL `review_sentiment` |

There is no model-selection flag. The default scorer is VADER. `SENTIMENT_MODEL=transformer` (default model name `cardiffnlp/twitter-roberta-base-sentiment-latest`) was not downloaded or run. The default command does not import `transformers`. The initial run did not pass `--persist`.

Compound score `>= 0.05` is positive, `<= -0.05` is negative, and values strictly between those thresholds are neutral. Empty or non-text review text is `invalid` with a null score, not neutral. The sample run had no invalid rows.

Aspects are food, service, ambience, and price (`food_sent`, `service_sent`, `ambience_sent`, `price_sent`). A keyword lexicon finds mentions. Clauses split on `.`, `!`, `;`, `?`, and contrast words (`but`, `however`, `although`, `though`, `yet`, `while`). Polarity is counted in the clauses that mention the aspect, with a three-token negation window (`not`, `never`, `no`, and similar). `not mentioned` means the aspect was not found. `neutral` means it was mentioned and the lexicon score was balanced. Example: “The biryani was amazing, but the service was extremely slow.” is food positive, service negative, ambience and price `not mentioned`. VADER’s overall label for that sentence is positive. VADER alone scores “extremely slow” as neutral, which is why aspect polarity uses the lexicon.

Text is HTML-stripped, whitespace-collapsed, and lowercased. Tokens keep punctuation. Lemmatization uses spaCy `en_core_web_sm` or NLTK WordNet when that data is already installed. Neither was available for the initial run, so the offline lemmatizer was used. No external API is called.

`evaluate()` compares VADER labels with rating proxies: ratings 1–2 negative, 3 neutral, 4–5 positive. These are weak proxy labels, not human annotation. Missing or out-of-range ratings are skipped. Classes with no support use zero precision and recall. The confusion matrix is `mining/sentiment/artifacts/confusion_matrix.png` (rows: rating proxy; columns: predicted label; order negative, neutral, positive).

Trends use `reviews.id`, `reviews.restaurant_id`, `reviews.created_at`, `restaurants.cuisine_type`, `restaurants.location_id`, and `locations.city`. Restaurant and location rows are deduped on `id` before the join. Each group reports `review_count`, positive, negative, neutral, and invalid counts, and `mean_score`.

### Observed on the 2026-10-11 sample run

All **3,000** processed reviews were scored: **positive 2,301**, **negative 514**, **neutral 185**. Aggregations wrote 50 restaurant groups, 17 city groups, 10 cuisine groups, and 13 month groups (`YYYY-MM`).

| Aspect | positive | negative | neutral | not mentioned |
|--------|----------|----------|---------|----------------|
| food | 1,374 | 139 | 147 | 1,340 |
| service | 877 | 406 | 410 | 1,307 |
| price | 1,182 | 644 | 196 | 978 |
| ambience | 0 | 0 | 0 | 3,000 |

The sample review text has no recognized ambience mentions. Proxy metrics in `evaluation.json`, rounded to three decimals: accuracy **0.765**, macro precision **0.665**, macro recall **0.610**, macro F1 **0.610**. All 3,000 rows were evaluated. The neutral proxy is the weak class (support 595, recall about 0.104). Every positive proxy row was predicted positive (recall 1.0).

### Output files

- `data/processed/review_sentiment.parquet` — `review_id`, `overall_sentiment`, `overall_score`, `food_sent`, `service_sent`, `ambience_sent`, `price_sent`, `analyzed_at`
- `data/processed/sentiment_by_restaurant.parquet`, `sentiment_by_city.parquet`, `sentiment_by_cuisine.parquet`, `sentiment_by_month.parquet`
- `mining/sentiment/artifacts/evaluation.json`, `confusion_matrix.png`

`--persist` upserts by `review_id` and creates `review_sentiment` only if it is missing. It does not drop or truncate other tables. The initial run did not use it. Tests check the upsert on temporary SQLite, not the project PostgreSQL database.

Aspect labels are a lexicon, not a trained aspect model. `restaurant_features.parquet` still leaves `sentiment_label` and `sentiment_score` null.

## Customer segmentation

`mining/clustering/` groups customers by purchasing behavior. It reads processed Parquet and writes new files. It does not modify sample CSVs, existing Parquet inputs, or PostgreSQL.

```powershell
.\.venv\Scripts\python.exe -m mining.clustering.run_segmentation --seed 42
```

Other flags: `--customers`, `--orders`, `--reviews`, `--sentiment`, `--output-dir`, `--artifacts-dir`. Defaults are the processed Parquet paths, `data/processed`, and `mining/clustering/artifacts`.

The seven model features are scaled with a fitted `StandardScaler` after each column is clipped to its 1st and 99th percentiles. Identifiers, names, emails, and phone numbers are not features. Cancelled and pending orders are excluded. Order totals are not joined to line items.

| Feature | Role |
|---------|------|
| `recency_days` | Days since the last completed order |
| `order_frequency` | Count of completed orders |
| `total_spend` | Sum of completed order totals |
| `avg_order_value` | Mean completed order total |
| `avg_discount` | Mean `discount_used` on completed orders on or before `2026-10-11`, from `orders.parquet`. `discount_usage_rate` is a share, not an amount |
| `avg_rating` | Customer-level mean star rating |
| `avg_sentiment_score` | Mean VADER `overall_score`, joined from `review_id` to `reviews.customer_id` and aggregated before any other join |

### Observed on the 2026-10-11 sample run

One customer had no rating and no sentiment score. Those two values were median-imputed in the model matrix only (`avg_rating` 3.6667, `avg_sentiment_score` 0.5596). That fill is not written back to the source files. 499 of 500 customers had a real sentiment score.

K from 2 through 8 was evaluated. K-Means uses `n_init=10` and `random_state=42`. Agglomerative clustering uses Ward linkage. DBSCAN uses a median 5-neighbor distance and `min_samples=5`.

- **Silhouette** (higher is better): fit versus the nearest other cluster.
- **Davies–Bouldin** (lower is better): compactness relative to separation.
- **Calinski–Harabasz** (higher is better): between-cluster scatter versus within-cluster scatter.

The selection rule is the highest silhouette. K-Means is preferred only when its silhouette is within 0.01 of the leader. Fewer than two usable clusters makes a result ineligible and does not stop the run.

| Model | Configuration | Silhouette | Davies–Bouldin | Calinski–Harabasz |
|---|---|---:|---:|---:|
| Agglomerative (selected) | K=2, Ward linkage | 0.226 | 2.016 | 95.98 |
| K-Means | K=2 | 0.189 | 1.897 | 123.70 |
| DBSCAN | eps=1.25, min_samples=5 | 0.176 | 1.021 | 8.80 |

Agglomerative clustering was selected because the K-Means silhouette was not within 0.01 of 0.226. K-Means had a higher Calinski–Harabasz score at K=2. Separation is weak, and silhouette fell as K increased.

Labels compare each cluster’s medians with the population. They are descriptive, not a validated taxonomy.

| Segment | Customers | Share | Median recency | Median orders | Median spend |
|---|---:|---:|---:|---:|---:|
| High-value loyal | 368 | 73.6% | 27 days | 10 | 11,008.12 |
| Inactive/at-risk | 132 | 26.4% | 86 days | 6 | 5,650.89 |

Stored labels: `high-value loyal`, `inactive/at-risk`.

### Artifacts

- `data/processed/customer_segments.parquet` — `customer_id`, `cluster_id`, `segment_label`
- `data/processed/customer_segment_summary.parquet`
- `data/processed/customer_segmentation_metrics.json`
- `mining/clustering/artifacts/customer_segments_pca.png`

PCA is only for that plot. It is not a clustering feature. The table rounds the JSON metrics.

## Association rule mining

`mining/association/` finds food items that appear together in completed orders. A rule is an association, not a cause.

Inputs: `orders.parquet`, `order_items.parquet`, `food_items.parquet`.

- One basket per completed order. Status is compared after trimming and lowercasing, so `cancelled` and `pending` are excluded.
- Basket key: `(restaurant_id, order_id)`. In this extract, order ids are unique across restaurants. The composite key still separates restaurants if an id were reused.
- A line is kept only when the food item belongs to the same restaurant as the order.
- The mining item is `food_item_id`. Names are labels. This catalog has 587 items and 68 distinct names.
- Quantity is not support. Repeated lines for the same item in one order count once.
- Customer ids, emails, and phone numbers are not mining inputs.

Apriori (`mlxtend`) finds itemsets of every size that meets the support threshold. FP-Growth is not used. Support is the share of transactions in the scope that contain every item. Confidence of A → C is support(A ∪ C) / support(A). Lift is confidence(A → C) / support(C). Leverage is support(A ∪ C) − support(A) × support(C). Conviction is (1 − support(C)) / (1 − confidence); it is null when confidence is 1. Support is also stored as a count. For 4,405 global transactions and support 0.003, the minimum count is 14.

```powershell
.\.venv\Scripts\python.exe -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3
```

| Argument | Default | Meaning |
|---|---|---|
| `--min-support` | 0.003 | Fraction of transactions in the scope. Greater than 0 and at most 1 |
| `--min-confidence` | 0.3 | Minimum confidence. Same bounds |
| `--min-lift` | omitted | Optional. When set, a finite number of at least 0 |
| `--restaurant-specific` | off | Mine each restaurant on its own baskets |
| `--min-restaurant-transactions` | 30 | Skip a restaurant below this many valid transactions |
| `--orders`, `--order-items`, `--food-items`, `--output-dir` | `data/processed` | Input and output locations |

The default support is 0.003 because the most frequent pair in the written rules occurs in 20 of 4,405 completed orders (support 0.004540). Support 0.01 would keep only single items. Invalid thresholds stop the command.

### Observed on the 2026-10-11 sample run

Global scope `all`, from `association_mining_metrics.json` and `association_rules.parquet`:

| Measurement | Result |
|---|---:|
| Source orders | 5,000 |
| Eligible completed orders | 4,405 |
| Valid transactions | 4,405 |
| Distinct food items | 587 |
| Orders not completed | 595 |
| Item rows on non-completed orders | 1,808 |
| Frequent itemsets | 622 (554 size 1, 68 size 2, none larger) |
| Association rules | 136 |

No order id, restaurant id, food id, or quantity was invalid in this extract, and no completed order lacked an item. The strongest pair by lift is item 426 (Miso Soup) → item 430 (Tempura): support count 14, support 0.003178, confidence 0.608696, lift 89.38, leverage 0.003143, conviction 2.538. The reverse rule has the same support and lift, confidence 0.466667, and conviction 1.865. Other high-lift pairs are Pho Bo (570) with Spring Rolls (572), and Bun Cha (281) with Spring Rolls (279). Lift is high because each item is rare in the 4,405-order denominator. Every global rule in this run has confidence below 1.

Restaurant-specific mining writes a separate directory and does not replace the global files:

```powershell
.\.venv\Scripts\python.exe -m mining.association.run_mining --restaurant-specific --min-support 0.05 --min-confidence 0.4 --min-restaurant-transactions 30 --output-dir data/processed/association_restaurant_run
```

All 50 restaurants had 71–105 valid transactions, so none were skipped. That run found 2,802 itemsets (587 size 1, 1,849 size 2, 359 size 3, 7 size 4) and 1,365 rules. At restaurant 31 (94 transactions), Chocolate Shake (354) and Cheeseburger (359) → Brownie (352): support count 5, support 0.053191, confidence 0.833333, lift 4.352, leverage 0.040969, conviction 4.851. Some rules have confidence 1; their conviction is null.

### Artifacts

- `data/processed/association_frequent_itemsets.parquet` — item ids and names, size, support count, support, restaurant scope
- `data/processed/association_rules.parquet` — antecedent and consequent ids and names, support count, support, confidence, lift, leverage, conviction, restaurant scope
- `data/processed/association_mining_metrics.json`
- `data/processed/association_restaurant_run/` — the same three files for the restaurant-specific command

An empty threshold still writes the column schema with zero rows. The JSON explains why.

Menu items belong to one restaurant, so a global rule is not a cross-restaurant combination. Global support uses all 4,405 transactions, which dilutes pairs that exist at only one restaurant. Identical dish names stay distinct when their ids differ.

## Customer churn analysis

`mining/churn/` flags customers whose last completed order is old relative to a reference date. The label is an inactivity rule. It is not a prediction that the customer is permanently lost, and there is no verified churn label to score it against.

Reference date for the documented run: `2026-10-11`. Only completed orders count. Cancelled and pending orders do not reset the clock. Customers with no completed order on or before the reference date are excluded from `customer_churn_risk.parquet`.

Inactivity is calendar days from the last completed order to the reference date. The category comes from that rule, not from the score.

| Category | Rule |
|---|---|
| `active` | Fewer than 45 days |
| `at_risk` | At least 45 days and fewer than 90 |
| `churned_under_definition` | At least 90 days. Inactive under this rule, not permanently lost |
| `insufficient_history` | First completed order is less than 90 days before the reference date. Not flagged. `risk_score` is null |

Behavior is recomputed from completed orders, reviews, and VADER `overall_score` in `review_sentiment.parquet`. It does not use the null sentiment placeholders on `restaurant_features.parquet`. Spend is the sum of completed order totals and is not joined to line items. Names, emails, and phone numbers are not used.

`risk_score` is a capped heuristic, not a probability. This run does not report accuracy, precision, recall, or ROC-AUC. Points are added only after a customer has enough history. The total is capped at 100.

| Points | When they are added |
|---|---|
| Up to 60 | `min(60, 60 * inactivity_days / 90)` |
| 15 | Completed-order count is 4 or fewer (`--low-frequency-max`, default 4) |
| 15 | At least one closed gap exists, and inactivity is more than 1.5 times the mean gap between consecutive completed orders. One order has no closed gap |
| 10 | Observed for at least 90 days, the previous 45-day window has at least one completed order, and the latest 45-day window has strictly fewer than half as many (`recent * 2 < prior`). Half does not count |
| 10 | Mean rating is present and at or below 2.5 |
| 10 | Mean VADER score is present and at or below -0.05 |

A missing rating or sentiment score adds nothing. It is not treated as neutral. The category is not chosen by score thresholds.

```powershell
.\.venv\Scripts\python.exe -m mining.churn.run_analysis --reference-date 2026-10-11 --inactivity-days 90 --at-risk-days 45
```

Other flags: `--customers`, `--orders`, `--reviews`, `--sentiment`, `--output-dir`, `--artifacts-dir`, `--low-frequency-max`.

### Observed on the 2026-10-11 sample run

`customer_churn_metrics.json`: 500 eligible customers, 0 without a completed order, 0 `insufficient_history`, 4,405 completed orders used, 595 cancelled or pending orders ignored. Shares are of those 500 rows.

| Category | Customers | Share | Median inactivity | Median orders | Median spend |
|---|---:|---:|---:|---:|---:|
| active | 292 | 58.4% | 19 days | 9 | 10,761.275 |
| at_risk | 139 | 27.8% | 62 days | 9 | 9,828.33 |
| churned_under_definition | 69 | 13.8% | 126 days | 6 | 6,285.94 |

### Artifacts

- `data/processed/customer_churn_risk.parquet` — behavior fields, inactivity days, `risk_score`, `risk_category`, `reason_codes`
- `data/processed/customer_churn_summary.parquet`
- `data/processed/customer_churn_metrics.json`
- `mining/churn/artifacts/customer_churn_categories.png` — category counts only

The module does not modify sample CSVs, existing Parquet inputs, or PostgreSQL. A long gap can be a pause. The score is not calibrated. Short histories are not flagged.

## Personalized recommendations

`mining/recommendation/` ranks food items and restaurants. The stored number is a ranking score, not a purchase probability. Association rules are read from `data/processed/association_rules.parquet` and are not mined again per customer. If that file is missing, the command continues without the association signal and the metrics JSON says to generate it with `python -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3`.

Only completed orders on or before the reference date count. A food item is recommended only when it is available, the restaurant is active, and the catalog restaurant matches. An item bought once is left out. An item bought on two or more completed orders can be recommended as a reorder. Names, emails, and phone numbers are not output fields. Restaurants the customer already used are recommended only when that customer's mean rating there is at least 4.

Each signal is scaled to 0–1. Cuisine fit is the share of completed orders in that cuisine. Association strength is `0.5 * min(confidence, 1) + 0.5 * min(lift, 5) / 5` for a rule whose antecedent the customer bought and whose consequent is the candidate. Rules with lift below 1, a missing item, more than one item on a side, or items from two restaurants are dropped. Quality is the mean of `rating / 5` and `(sentiment + 1) / 2` when those restaurant values exist; if both are missing, quality is 0.5. Familiarity is `0.5 *` order share at the restaurant `+ 0.5 * 1 / (1 + days / 30)`. Popularity is the count divided by the maximum.

For completed-order count `n` and `limited_history_orders = 2`, `alpha = 0` when `n = 0`, otherwise `alpha = min(1, n / 3)`. `score = alpha * history_score + (1 - alpha) * cold_score`.

Food history: `0.25 * cuisine_fit + 0.25 * association + 0.20 * quality + 0.20 * familiarity + 0.10 * popularity`. Cold-start score for food and restaurants: `0.75 * quality + 0.25 * popularity`. Restaurant history: `0.40 * cuisine_fit + 0.40 * quality + 0.10 * familiarity + 0.10 * popularity`.

Ties prefer the higher association strength for food, or higher quality for restaurants, then the lower numeric id. The reason is the strongest positive contribution, including `associated with a previously purchased item`, `frequently purchased cuisine`, `highly rated in preferred cuisine`, `previously reordered item`, `previously highly rated restaurant`, `highly rated restaurant`, and `general pick for limited history`. A reorder contributes to the reason text only; it is not added to the score. A customer with no completed orders gets `general pick for limited history`. One or two completed orders use the alpha blend. This extract has no zero-order customers, so that reason does not appear in the written files.

```powershell
.\.venv\Scripts\python.exe -m mining.recommendation.run_recommendations --reference-date 2026-10-11
```

`--food-k` defaults to 5 and `--restaurant-k` defaults to 3.

### Observed on the 2026-10-11 sample run

The run wrote 2,500 food rows and 1,500 restaurant rows for 500 customers, using 136 association rules. No duplicate customer-item or customer-restaurant pair was written, and no food row pointed at a different restaurant than the catalog.

Holdout leaves out each customer's last completed order and builds preferences only from earlier completed orders. Reviews after that cutoff are excluded. Stored association rules are off (`association_in_holdout: false`) because they were mined on the full history. Eligible food customers: last order contains a catalog item not bought earlier (492). Eligible restaurant customers: last order is at a restaurant not used earlier (438).

| Metric | Food @5 | Restaurant @3 |
|---|---:|---:|
| Hit rate | 0.0244 | 0.0639 |
| Precision | 0.0053 | 0.0213 |
| Recall | 0.0163 | 0.0639 |

Unrounded values are in `recommendation_metrics.json` (food hit rate 0.024390243902439025, restaurant hit rate 0.0639269406392694). These checks compare ranks with a later order. They are not a claim about satisfaction or sales. A low hit rate is expected when five items are chosen from 587 catalog items. Popularity does not decide the written reason when another signal is present.

### Artifacts

- `data/processed/food_recommendations.parquet` — `customer_id`, `food_item_id`, `restaurant_id`, `recommendation_score`, `rank`, `reason`
- `data/processed/restaurant_recommendations.parquet` — `customer_id`, `restaurant_id`, `recommendation_score`, `rank`, `reason`
- `data/processed/recommendation_metrics.json`
- `mining/recommendation/artifacts/recommendation_reasons.png`

## Demand forecasting

`mining/forecasting/` forecasts completed-order demand for each restaurant and each food item. It reads `orders.parquet`, `order_items.parquet`, and `food_items.parquet`. It does not modify those files, the sample CSVs, or PostgreSQL. `scikit-learn` and `matplotlib` come from the root `requirements.txt`.

Only status `completed`, compared after trimming and lowercasing, counts. Cancelled and pending orders are excluded. Orders after the reference date are excluded.

| Level | Demand |
|---|---|
| Restaurant | Count of completed orders in the period. Order totals are not joined to line items |
| Food item | Sum of `quantity` on those orders. The restaurant id is the order's restaurant. A line whose food item belongs to another restaurant is excluded |

A missing day or week is zero only after that series' first observed period, through the reference date. Earlier dates are not filled. The first order is not a known menu-launch date.

The baseline is seasonal naive: season length 7 for daily data and 4 for weekly data. A series shorter than one season uses the previous period. The other model is ridge regression (`alpha=1.0`, `random_state` from `--seed`) on `lag_1`, `lag_season`, the mean of the last season, and day of week (daily) or ISO week (weekly). Both forecasts are recursive. Each later step appends that step's prediction and does not read a future actual. Predictions are clipped at zero. Ridge is fit only when at least four training rows exist; otherwise that series keeps the seasonal naive forecast. The default minimum training length is 28 daily periods or 8 weekly periods, and the holdout is extra. Shorter series are skipped. If none qualify, the command stops.

Evaluation is a chronological holdout: the last `horizon` periods through the reference date. That score is fit only on earlier periods. A second fit on the full history writes the forward forecast after the reference date. There is no random split.

| Metric | Definition |
|---|---|
| MAE | Mean absolute error. Each holdout point counts equally |
| RMSE | Root mean squared error. Large misses count more than in MAE |
| WAPE | Total absolute error divided by total actual demand. Null when that total is zero |

```powershell
.\.venv\Scripts\python.exe -m mining.forecasting.run_forecast --reference-date 2026-10-11 --horizon 7
```

| Flag | Default | Role |
|---|---|---|
| `--reference-date` | `2026-10-11` | UTC date. Later orders are ignored |
| `--horizon` | 7 | Holdout length and forward forecast length |
| `--aggregation` | `daily` | `daily` or `weekly` |
| `--model` | `ridge` | `ridge` or `seasonal_naive`. The baseline is always scored |
| `--seed` | 42 | Ridge `random_state` |
| `--min-history` | 28 daily, 8 weekly | Minimum training periods before the holdout |
| `--orders`, `--order-items`, `--food-items` | `data/processed` | Input Parquet |
| `--output-dir` | `data/processed` | Forecast, history, and metrics |
| `--artifacts-dir` | `mining/forecasting/artifacts` | Holdout chart |

Module test, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_forecasting.py -q
```

`tests/test_forecasting.py` has 7 tests. The combined root-suite command is in [Tests](#tests).

### Observed on the 2026-10-11 daily sample run

These figures are from `demand_forecast_metrics.json` for that daily, horizon-7 run. They are not a guaranteed error rate, and they are not the weekly aggregation. Weekly aggregation is implemented and covered by tests. Completed orders used: 4,405. Non-completed orders excluded: 595. Item lines used: 13,187. Invalid quantities: 0. Unknown or cross-restaurant lines: 0. Restaurants scored: 50, skipped: 0. Food items scored: 587, skipped: 0. Ridge fallback: 0. In the written forecast file, forward dates run from 2026-10-12 through 2026-10-18, and the smallest predicted demand is 0.

Holdout actuals were 26 completed orders over 350 restaurant-days and 170 quantity units over 4,109 item-days. A WAPE above 1 means total absolute error exceeded total holdout demand.

| Level | Model | MAE | RMSE | WAPE |
|---|---|---:|---:|---:|
| Restaurant | Seasonal naive | 0.317 | 0.630 | 4.269 |
| Restaurant | Ridge | 0.283 | 0.334 | 3.806 |
| Food item | Seasonal naive | 0.155 | 0.614 | 3.747 |
| Food item | Ridge | 0.157 | 0.331 | 3.790 |

On this run, pooled restaurant WAPE was lower for ridge (3.806 versus 4.269). Pooled food-item WAPE was lower for the seasonal naive forecast (3.747 versus 3.790). Ridge had the lower RMSE at both levels. This is not evidence that the forecast is ready for staffing or purchasing.

### Artifacts

- `data/processed/demand_forecasts.parquet` — `level`, `restaurant_id`, `food_item_id`, `forecast_date`, `horizon_step`, `horizon`, `aggregation`, `model_name`, `predicted_demand`, `forecast_role` (`holdout` or `forward`), `evaluation_mae`, `evaluation_rmse`, `evaluation_wape`
- `data/processed/demand_forecast_history.parquet` — `level`, ids, `period_start`, `actual_demand`, `aggregation`
- `data/processed/demand_forecast_metrics.json`
- `mining/forecasting/artifacts/demand_forecast_holdout.png` — one restaurant's history, holdout actuals, seasonal naive forecast, and ridge forecast

### Limitations

- The numbers are holdout error on this extract. They are not revenue, satisfaction, or a staffing plan.
- Daily series are sparse, so a small MAE can still accompany a WAPE above 1.
- Zero-fill starts at the first completed order, not at a known menu-launch date.
- A weekly bucket that contains the reference date can be a partial week when that date is not a Sunday. The documented sample run is daily, and 2026-10-11 is a Sunday.
- Ridge uses four lag and calendar features with a fixed penalty. It is not a causal demand model.
- Series that never reach the minimum history are omitted rather than imputed from other series. None were omitted in the daily sample run.

## Snowflake analytical load

`warehouse/snowflake/` publishes approved Parquet files into a Snowflake database named `FOODPULSE` and a schema named `ANALYTICS`. It does not read or write PostgreSQL, and it does not change the Parquet files. The connector dependency stays in the root `requirements.txt` (`snowflake-connector-python[pandas]`). It is not a backend API dependency.

The default command validates local files and prints planned table names and row counts. It does not connect and does not need Snowflake credentials:

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_load --dry-run
```

`--dry-run` is also the default when neither flag is passed. Add `--tables REVIEW_SENTIMENT CUSTOMER_CHURN_RISK` to limit the plan to approved table names. A live load is a separate opt-in:

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_load --execute
```

To check the login without creating objects or loading data:

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_load --test-connection
```

That command reads the same `.env` settings, connects without selecting a database or schema, runs `SELECT CURRENT_VERSION(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()`, prints those four values, and closes the connection. `connect` does not change autocommit; the load path still disables and verifies it before any setup or write. A previous run against the live Snowflake account completed the analytical load. This documentation edit did not open a new connection or repeat that load.

### Environment

Put these in the gitignored `.env`. Do not commit them.

| Variable | Purpose |
|----------|---------|
| `SNOWFLAKE_ACCOUNT` | Account locator. It is not written to logs. |
| `SNOWFLAKE_USER` | Login name |
| `SNOWFLAKE_PASSWORD` | Password. A missing value raises `SNOWFLAKE_PASSWORD is not set` and the value is never echoed. |
| `SNOWFLAKE_WAREHOUSE` | Defaults to `FOODPULSE_WH` |
| `SNOWFLAKE_DATABASE` | Defaults to `FOODPULSE` |
| `SNOWFLAKE_SCHEMA` | Defaults to `ANALYTICS` |
| `SNOWFLAKE_ROLE` | Optional |

Warehouse, database, schema, and role must be simple identifiers. The loader does not print the account URL, the user, the password, or row values. `SnowflakeConfig` does not include those secrets in its text form. Connector logging is left at warning level. Exceptions are redacted before they are logged.

### Account setup

Do not assume the warehouse, database, schema, or role already exist.

1. In the Snowflake UI, create a virtual warehouse named `FOODPULSE_WH` (an X-Small warehouse with auto-suspend is enough for this trial). Grant `USAGE` on that warehouse to the role you will use. The loader does not run `CREATE WAREHOUSE`, because that spends credits and is an account-level object.
2. Set the environment variables above.
3. Run the dry-run and confirm the 16 planned tables.
4. Only then run `--execute`. The login does not require `FOODPULSE` or `ANALYTICS` to exist. The loader checks that `FOODPULSE_WH` is active, runs `CREATE DATABASE IF NOT EXISTS` and `CREATE SCHEMA IF NOT EXISTS`, selects that database and schema, and creates only the selected tables with `CREATE TABLE IF NOT EXISTS`. `--tables` does not create the other analytical tables. It does not drop the database, and it does not delete published rows before the replacement snapshot has been counted in a temporary staging table. If autocommit cannot be turned off, the command stops before any of that setup.
5. After a successful load, suspend the warehouse in the UI if auto-suspend is not already set.

The configured role needs `USAGE` on the warehouse, `CREATE DATABASE` on the account when the database is missing, `USAGE` and `CREATE SCHEMA` on the database, `USAGE` and `CREATE TABLE` on the schema, and `SELECT`, `INSERT`, and `DELETE` on each published table. `INSERT OVERWRITE` needs `DELETE` as well as `INSERT`. The role that creates a table receives `OWNERSHIP`, which covers those table privileges. A missing grant raises a redacted privilege error and does not continue the load.

Reviewed statements are in `warehouse/snowflake/sql/analytics_tables.sql`. They use `USE` and `IF NOT EXISTS` only. There is no `DROP`, `TRUNCATE`, or `CREATE OR REPLACE` of a published table in that file. The loader does not run `CREATE WAREHOUSE`.

### What is loaded

The default plan reads these files from `data/processed/`:

`review_sentiment.parquet`, `sentiment_by_restaurant.parquet`, `sentiment_by_city.parquet`, `sentiment_by_cuisine.parquet`, `sentiment_by_month.parquet`, `customer_segments.parquet`, `customer_segment_summary.parquet`, `association_frequent_itemsets.parquet`, `association_rules.parquet`, `customer_churn_risk.parquet`, `customer_churn_summary.parquet`, `food_recommendations.parquet`, `restaurant_recommendations.parquet`, `demand_forecasts.parquet`, `customer_features.parquet`, `restaurant_features.parquet`.

Identifier columns (`review_id`, `customer_id`, `restaurant_id`, `food_item_id`) are loaded as `VARCHAR` so integer feature ids and string recommendation ids land in one type. Each table gains a `loaded_at` timestamp that is not in the Parquet file. Nullable Pandas and NumPy values become SQL NULL.

These files stay out of the default plan: `users.parquet` (password hashes), `customers.parquet` (names, emails, phone numbers), raw `reviews.parquet` (review text), and `demand_forecast_history.parquet`. Restaurant-specific association files under `association_restaurant_run/` are not merged into the global association tables, because they use the same columns with a different scope and the files are left unchanged.

### Publish behavior

Every selected file is validated before a connection is opened. The load sends those validated rows with bound parameters. If a file changes after validation, the command stops before the next write and does not rewrite the Parquet file. Each table is inserted into a session temporary staging table. `INSERT OVERWRITE` is valid for these permanent tables and stays in the same transaction as the staging inserts. It is committed only after the published count matches. A failed staging insert rolls back that table. If the rollback itself fails, the original sanitized error is kept and the rollback error is logged without secrets. A later successful load overwrites the snapshot rather than appending a second copy.

Snowflake commits DDL on its own. `CREATE TABLE IF NOT EXISTS` can therefore leave an empty published table if the first load fails after setup and before a successful overwrite. A later failed load leaves that table's previous successful snapshot in place when the overwrite has not committed. Tables that already committed in the same run stay on the new snapshot, and tables not yet reached stay on the old one. The full 16-table load is not atomic. Disabling autocommit is checked before any setup statement; if that check fails, nothing is created and nothing is written.

### Checks after a manual load

Confirm the session without printing secrets:

```sql
SELECT CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA();
```

Then compare counts with the dry-run report:

```sql
SELECT COUNT(*) FROM FOODPULSE.ANALYTICS.REVIEW_SENTIMENT;
SELECT COUNT(*) FROM FOODPULSE.ANALYTICS.FOOD_RECOMMENDATIONS;
SELECT COUNT(*) FROM FOODPULSE.ANALYTICS.DEMAND_FORECASTS;
```

Repeat `COUNT(*)` for the other planned tables. A second `--execute` should leave those counts unchanged.

### Limitations

- A previous live account test completed the analytical load. The automated tests below do not connect to Snowflake, and this documentation edit did not repeat the load.
- The virtual warehouse must be created manually. A running warehouse consumes trial credits while it is resumed, including for a failed query. Suspend it when you are done.
- Published tables are not primary-key enforced. Idempotency comes from snapshot replacement, not from a merge key.
- The first failed publish can leave an empty table because DDL commits independently of the data transaction. It does not leave a partial row set from a failed batch. A failure partway through the 16 tables leaves a mix of new snapshots, the previous snapshot, and empty tables. It is not one atomic publish.
- `warehouse/dimensions/`, `warehouse/facts/`, and `warehouse/sql/` are still placeholders. This load is a set of analytical snapshots, not a dimensional star schema.
- Association output files are not rewritten, and restaurant-scoped itemsets are not combined with the global ones.

## Run the implemented modules

From the repository root. Transform reads `data/sample` and writes processed Parquet. The mining commands read that Parquet. None of these commands modify the sample CSVs or PostgreSQL. Do not use `scripts/run-etl.ps1` for this sequence; that script overwrites `data/sample`.

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_transform --reference-date 2026-10-11
.\.venv\Scripts\python.exe -m mining.sentiment.run_analysis
.\.venv\Scripts\python.exe -m mining.clustering.run_segmentation --seed 42
.\.venv\Scripts\python.exe -m mining.association.run_mining --min-support 0.003 --min-confidence 0.3
.\.venv\Scripts\python.exe -m mining.churn.run_analysis --reference-date 2026-10-11 --inactivity-days 90 --at-risk-days 45
.\.venv\Scripts\python.exe -m mining.recommendation.run_recommendations --reference-date 2026-10-11
.\.venv\Scripts\python.exe -m mining.forecasting.run_forecast --reference-date 2026-10-11 --horizon 7
```

## Tests

`scripts/test.ps1` and `make test` run pytest from `backend/` and do not collect these files. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transform.py tests\test_sentiment.py tests\test_clustering.py tests\test_association.py tests\test_churn.py tests\test_recommendation.py tests\test_forecasting.py -q
```

On 11 October 2026 that command reported **67 passed**: 14 transform, 12 sentiment, 8 clustering, 8 association, 9 churn, 9 recommendation, and 7 forecasting tests. That is the mining and transform suite from that run, not a historical partial count and not the result of `scripts/test.ps1`. It does not include the Snowflake loader tests. Those stay local and do not need credentials:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_snowflake_load.py -q
```

On 11 October 2026 that command reported **21 passed**. These are automated tests using temporary Parquet files and mocked connections. They are not live Snowflake tests.

## Not implemented

- Airflow orchestration
- A verified transformer sentiment backend
- Dashboard integration (React views of the mining outputs, and Power BI)
