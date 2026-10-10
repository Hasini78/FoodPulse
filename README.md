# FoodPulse

Restaurant Intelligence & Customer Experience Mining Platform.

FoodPulse turns restaurant customer, order, and review data into actionable insights: what customers like or dislike, which restaurants are improving or declining, churn risk, market basket patterns, and demand forecasts.

> **Scaffold + foundation:** monorepo layout, FastAPI core/db/security, sample seed, and a Vite React shell. Mining, Snowflake, Airflow, and dashboard wiring come in later modules.

## Planned pipeline

```
Raw data → ETL (Pandas/PySpark, Airflow) → PostgreSQL (operational)
  → Snowflake (star-schema warehouse)
  → Data mining / ML / NLP
  → FastAPI → React dashboard + Power BI
```

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
├── warehouse/{dimensions,facts,sql}
├── airflow/dags  pyspark/jobs  powerbi/reports  docker  docs
├── docker-compose.yml
├── Makefile / scripts/
├── requirements.txt
└── .env.example
```

## Make / scripts

| Target | Action |
|--------|--------|
| `make setup` / `scripts/setup.ps1` | venv + backend deps + frontend npm install |
| `make run-backend` / `scripts/run-backend.ps1` | `uvicorn app.main:app --reload` |
| `make run-frontend` / `scripts/run-frontend.ps1` | `npm run dev` |
| `make run-etl` / `scripts/run-etl.ps1` | seed CSVs |
| `make test` / `scripts/test.ps1` | pytest |

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

This generates ~50 restaurants, 500 customers, 5,000 orders, and 3,000 reviews, writes CSVs under `data/sample/`, and loads them into PostgreSQL.

To export CSVs without loading the database:

```bash
python etl/load/seed.py --csv-only
```

### 4. Run the API locally (optional)

If you prefer uvicorn on the host instead of the Compose `backend` service:

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

Example:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/stats/overview
```

## Database entities

`users`, `restaurants`, `customers`, `food_items`, `orders`, `order_items`, `reviews`, `locations`, `customer_activity`

Reviews include `rating`, `review_text`, and `created_at`. Orders include `customer_id`, `restaurant_id`, `total_amount`, `discount_used`, and `order_date`.

## Next modules (not implemented yet)

- ETL with Pandas/PySpark + Airflow
- Snowflake star-schema warehouse
- Sentiment analysis, K-Means segmentation, Apriori, churn, recommendations, forecasting
- React dashboard + Power BI
