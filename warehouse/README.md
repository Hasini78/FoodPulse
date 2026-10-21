# FoodPulse warehouse

PostgreSQL remains the operational database. Snowflake holds analytical snapshots and the dimensional star schema. Neither loader writes to PostgreSQL or modifies `data/processed`.

## Snapshot tables

Approved mining outputs are published by `python -m warehouse.snowflake.run_load`. DDL lives in `warehouse/snowflake/sql/analytics_tables.sql`. `customers.parquet`, `reviews.parquet`, `users.parquet`, and `demand_forecast_history.parquet` stay excluded from that catalog.

## Star schema

Built from processed Parquet by `python -m warehouse.snowflake.run_star`. Tables are created in `FOODPULSE.ANALYTICS` beside the snapshots. They do not replace them.

| Table | Grain | Natural key | Measures / attributes from source |
|---|---|---|---|
| `DIM_DATE` | One UTC calendar date that appears on an order or a review | `date_sk` (`YYYYMMDD`) | year, quarter, month, day, weekday, weekend flag |
| `DIM_CUSTOMER` | One customer | `customer_id` | city, gender, created_at |
| `DIM_RESTAURANT` | One restaurant | `restaurant_id` | name, cuisine_type, is_active, city, state, country, created_at |
| `DIM_FOOD_ITEM` | One menu item | `food_item_id` | restaurant_sk, name, category, price, is_available |
| `FACT_ORDERS` | One order | `order_id` | status, total_amount, discount_used, total_amount_capped, is_total_outlier, order_ts |
| `FACT_REVIEWS` | One review | `review_id` | rating, review_ts; order_sk when the order exists |

Surrogate keys are NUMBER values equal to the source integer id so a full refresh is deterministic. Identifiers stay VARCHAR so they join snapshot tables.

Foreign keys: `FACT_ORDERS` and `FACT_REVIEWS` → `DIM_DATE`, `DIM_CUSTOMER`, `DIM_RESTAURANT`. `DIM_FOOD_ITEM.restaurant_sk` → `DIM_RESTAURANT`. `FACT_REVIEWS.order_sk` → `FACT_ORDERS.order_sk` when not null.

### Dropped tables

- `DIM_LOCATION` — not requested; city/state/country are copied onto `DIM_RESTAURANT`.
- `DIM_USER` — `users.parquet` includes hashed passwords.
- `FACT_ORDER_ITEMS` — not requested. Food quantity lives on `order_items.parquet`; attaching it to `FACT_ORDERS` would repeat order totals.

`DIM_CUSTOMER` omits given names, email, phone, and date of birth. `DIM_RESTAURANT` omits phone and email. `FACT_REVIEWS` omits review body text.

## Load flow

1. Read `customers`, `restaurants`, `locations` (optional), `food_items`, `orders`, and `reviews` from the processed directory.
2. Build dimensions, then facts. Rows missing a required key are skipped, not invented.
3. Dry-run (default) prints planned row counts and does not connect.
4. `--execute` reuses the snapshot publisher: `CREATE TABLE IF NOT EXISTS`, bind rows into a temporary staging table, `COUNT(*)`, then `INSERT OVERWRITE`.
5. After a live load, run the queries in `warehouse/snowflake/sql/star_validate.sql` in a Snowflake worksheet. A local dry-run does not run them.

SQL (canonical files live beside the snapshot DDL; identical reviewed copies are in `warehouse/sql/`):

- `warehouse/snowflake/sql/analytics_tables.sql` — snapshot mining tables only. Unchanged by the star loader.
- `warehouse/snowflake/sql/star_schema.sql` — create database, schema, and the six star tables. `CREATE IF NOT EXISTS` only.
- `warehouse/snowflake/sql/star_load.sql` — reviewed overwrite pattern used by `--execute`. Not a COPY FROM Parquet script; star rows are prepared locally because `customers.parquet` and `reviews.parquet` are excluded from snapshots.
- `warehouse/snowflake/sql/star_validate.sql` — counts, duplicate keys, null keys, orphan foreign keys, and unexpected contact/line-item columns.

Execution order:

1. Optional snapshot publish: `python -m warehouse.snowflake.run_load` (dry-run default). Does not create star tables.
2. Star dry-run (default): `python -m warehouse.snowflake.run_star` or `--dry-run`. Validates local Parquet and prints planned counts. No Snowflake connection.
3. Live star load: `python -m warehouse.snowflake.run_star --execute`. Requires `SNOWFLAKE_*` settings and warehouse `FOODPULSE_WH`. Applies `star_schema.sql` then the `star_load.sql` pattern.
4. After a successful live load, run `star_validate.sql` in the account. This repository does not run those statements.

## Commands

Dry-run (no Snowflake connection):

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_star --dry-run
```

Connection check (existing snapshot CLI; creates no star objects):

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_load --test-connection
```

Tests (mocked; no credentials):

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_snowflake_star.py tests\test_snowflake_load.py -q
```

Live load still needed: create warehouse `FOODPULSE_WH` in the Snowflake UI, grant the documented privileges, set `SNOWFLAKE_*` in `.env`, then:

```powershell
.\.venv\Scripts\python.exe -m warehouse.snowflake.run_star --execute
```

Then run `warehouse/snowflake/sql/star_validate.sql` in that account. This repository does not run those live statements. Local `--dry-run` is not a substitute for that worksheet.
