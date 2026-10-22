# ETL load stage

This directory has two different loaders. Use the Parquet-to-PostgreSQL command for operational data. Do not use `seed.py` to populate the live FoodPulse database.

## Operational PostgreSQL loader

`postgres.py` copies processed operational Parquet files into the existing PostgreSQL tables used by FastAPI.

It loads, in foreign-key order:

1. `locations` (required parent of restaurants)
2. `restaurants`
3. `food_items`
4. `customers`
5. `orders`
6. `order_items`
7. `reviews`

It does not load `users`, `customer_activity`, or `review_sentiment`. Staff `users` are not sample customers. Sentiment and activity stay in processed Parquet for `/analytics`.

An order line is skipped when the food item's `restaurant_id` does not match the order's `restaurant_id`. Food names may repeat; uniqueness is `food_items.id`. Display collapse uses `(name, restaurant_id)` and is not a database unique constraint.

Analytics stay in Parquet. Snowflake snapshot and star-schema loaders are unchanged and do not write to PostgreSQL.

### Required input files

From `data/processed/` (or `--processed-dir`):

- `locations.parquet`
- `restaurants.parquet`
- `food_items.parquet`
- `customers.parquet`
- `orders.parquet`
- `order_items.parquet`
- `reviews.parquet`

Source columns map to the SQLAlchemy fields of the same name. Extra order columns such as `is_total_outlier` and `total_amount_capped` are ignored.

### Dry-run (default)

Validates files, types, required fields, identifiers, unique emails, and parent keys. It does not open PostgreSQL and does not insert, update, or delete rows.

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_postgres_load
.\.venv\Scripts\python.exe -m etl.pipelines.run_postgres_load --dry-run
```

### Live load

Live execution requires `--execute`. Before writing, the command checks that `DATABASE_URL` is PostgreSQL, the database name is `foodpulse`, and the host is `localhost`, `127.0.0.1`, `::1`, or `postgres`. It also checks `current_database()`. It refuses any other target.

```powershell
.\.venv\Scripts\python.exe -m etl.pipelines.run_postgres_load --execute
```

`--execute` upserts by primary key in one transaction. It never deletes or truncates. If a write fails, the transaction is rolled back. Repeated runs update existing ids instead of inserting duplicates.

`--execute` may call SQLAlchemy `create_all` so missing tables from the existing ORM models exist. It never drops tables.

### Validation and row counts

Each table is reported as `prepared`, `inserted`, `updated`, `skipped`, and `rejected`. Dry-run always reports `inserted=0` and `updated=0`.

Typical skip and reject reasons:

- Missing required fields or invalid types
- Duplicate source `id` (skipped)
- Duplicate customer `email` (rejected)
- Rating outside 1–5 (rejected)
- Parent id not present in this load's prepared parent rows (skipped)
- Review `order_id` that is not in prepared orders (cleared to empty; the review can still load)

Parent keys are resolved from prepared source rows in this run, not from rows that already exist in PostgreSQL.

### How to verify loaded records

After a live load that you run yourself:

- `GET /stats/overview`
- `SELECT COUNT(*) FROM locations, restaurants, customers, orders, reviews, food_items, order_items;`
- Spot-check a restaurant, food item, order, and order item by primary key

Do not treat `/analytics/overview` as a PostgreSQL row count. That endpoint reads processed Parquet.

### `seed.py` is not this loader

`python etl/load/seed.py` generates Faker data, can export CSVs, and **drops all ORM tables** before inserting. It is a destructive sample generator, not a repeatable operational load.
