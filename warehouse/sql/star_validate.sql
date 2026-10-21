-- Star-schema validation. Run after a successful --execute load in a Snowflake worksheet.
-- Local dry-run does not execute these statements. Duplicate, null-key, and orphan checks should return 0.

SELECT 'DIM_DATE' AS table_name, COUNT(*) AS row_count FROM FOODPULSE.ANALYTICS.DIM_DATE;
SELECT 'DIM_DATE' AS table_name, COUNT(*) - COUNT(DISTINCT date_sk) AS duplicate_natural_keys FROM FOODPULSE.ANALYTICS.DIM_DATE;
SELECT 'DIM_DATE' AS table_name, COUNT(*) AS null_natural_keys FROM FOODPULSE.ANALYTICS.DIM_DATE WHERE date_sk IS NULL;

SELECT 'DIM_CUSTOMER' AS table_name, COUNT(*) AS row_count FROM FOODPULSE.ANALYTICS.DIM_CUSTOMER;
SELECT 'DIM_CUSTOMER' AS table_name, COUNT(*) - COUNT(DISTINCT customer_id) AS duplicate_natural_keys FROM FOODPULSE.ANALYTICS.DIM_CUSTOMER;
SELECT 'DIM_CUSTOMER' AS table_name, COUNT(*) AS null_natural_keys FROM FOODPULSE.ANALYTICS.DIM_CUSTOMER WHERE customer_id IS NULL;

SELECT 'DIM_RESTAURANT' AS table_name, COUNT(*) AS row_count FROM FOODPULSE.ANALYTICS.DIM_RESTAURANT;
SELECT 'DIM_RESTAURANT' AS table_name, COUNT(*) - COUNT(DISTINCT restaurant_id) AS duplicate_natural_keys FROM FOODPULSE.ANALYTICS.DIM_RESTAURANT;
SELECT 'DIM_RESTAURANT' AS table_name, COUNT(*) AS null_natural_keys FROM FOODPULSE.ANALYTICS.DIM_RESTAURANT WHERE restaurant_id IS NULL;

SELECT 'DIM_FOOD_ITEM' AS table_name, COUNT(*) AS row_count FROM FOODPULSE.ANALYTICS.DIM_FOOD_ITEM;
SELECT 'DIM_FOOD_ITEM' AS table_name, COUNT(*) - COUNT(DISTINCT food_item_id) AS duplicate_natural_keys FROM FOODPULSE.ANALYTICS.DIM_FOOD_ITEM;
SELECT 'DIM_FOOD_ITEM' AS table_name, COUNT(*) AS null_natural_keys FROM FOODPULSE.ANALYTICS.DIM_FOOD_ITEM WHERE food_item_id IS NULL;

SELECT 'FACT_ORDERS' AS table_name, COUNT(*) AS row_count FROM FOODPULSE.ANALYTICS.FACT_ORDERS;
SELECT 'FACT_ORDERS' AS table_name, COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_natural_keys FROM FOODPULSE.ANALYTICS.FACT_ORDERS;
SELECT 'FACT_ORDERS' AS table_name, COUNT(*) AS null_natural_keys FROM FOODPULSE.ANALYTICS.FACT_ORDERS WHERE order_id IS NULL;

SELECT 'FACT_REVIEWS' AS table_name, COUNT(*) AS row_count FROM FOODPULSE.ANALYTICS.FACT_REVIEWS;
SELECT 'FACT_REVIEWS' AS table_name, COUNT(*) - COUNT(DISTINCT review_id) AS duplicate_natural_keys FROM FOODPULSE.ANALYTICS.FACT_REVIEWS;
SELECT 'FACT_REVIEWS' AS table_name, COUNT(*) AS null_natural_keys FROM FOODPULSE.ANALYTICS.FACT_REVIEWS WHERE review_id IS NULL;

SELECT 'FACT_ORDERS.date_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.FACT_ORDERS fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_DATE dim ON fact.date_sk = dim.date_sk WHERE fact.date_sk IS NOT NULL AND dim.date_sk IS NULL;

SELECT 'FACT_ORDERS.customer_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.FACT_ORDERS fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_CUSTOMER dim ON fact.customer_sk = dim.customer_sk WHERE fact.customer_sk IS NOT NULL AND dim.customer_sk IS NULL;

SELECT 'FACT_ORDERS.restaurant_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.FACT_ORDERS fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_RESTAURANT dim ON fact.restaurant_sk = dim.restaurant_sk WHERE fact.restaurant_sk IS NOT NULL AND dim.restaurant_sk IS NULL;

SELECT 'FACT_REVIEWS.date_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.FACT_REVIEWS fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_DATE dim ON fact.date_sk = dim.date_sk WHERE fact.date_sk IS NOT NULL AND dim.date_sk IS NULL;

SELECT 'FACT_REVIEWS.customer_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.FACT_REVIEWS fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_CUSTOMER dim ON fact.customer_sk = dim.customer_sk WHERE fact.customer_sk IS NOT NULL AND dim.customer_sk IS NULL;

SELECT 'FACT_REVIEWS.restaurant_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.FACT_REVIEWS fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_RESTAURANT dim ON fact.restaurant_sk = dim.restaurant_sk WHERE fact.restaurant_sk IS NOT NULL AND dim.restaurant_sk IS NULL;

SELECT 'DIM_FOOD_ITEM.restaurant_sk' AS relationship, COUNT(*) AS orphan_rows FROM FOODPULSE.ANALYTICS.DIM_FOOD_ITEM fact LEFT JOIN FOODPULSE.ANALYTICS.DIM_RESTAURANT dim ON fact.restaurant_sk = dim.restaurant_sk WHERE fact.restaurant_sk IS NOT NULL AND dim.restaurant_sk IS NULL;

SELECT COUNT(*) AS reviews_with_unknown_order FROM FOODPULSE.ANALYTICS.FACT_REVIEWS WHERE order_sk IS NOT NULL AND order_sk NOT IN (SELECT order_sk FROM FOODPULSE.ANALYTICS.FACT_ORDERS);
SELECT COUNT(*) AS orders_missing_required_keys FROM FOODPULSE.ANALYTICS.FACT_ORDERS WHERE date_sk IS NULL OR customer_sk IS NULL OR restaurant_sk IS NULL;
SELECT COUNT(*) AS reviews_missing_required_keys FROM FOODPULSE.ANALYTICS.FACT_REVIEWS WHERE date_sk IS NULL OR customer_sk IS NULL OR restaurant_sk IS NULL;
SELECT COUNT(*) AS food_items_missing_restaurant FROM FOODPULSE.ANALYTICS.DIM_FOOD_ITEM WHERE restaurant_sk IS NULL;

SELECT COUNT(*) AS unexpected_customer_contact_columns FROM FOODPULSE.INFORMATION_SCHEMA.COLUMNS WHERE table_schema = 'ANALYTICS' AND table_name = 'DIM_CUSTOMER' AND column_name IN ('EMAIL', 'PHONE', 'FIRST_NAME', 'LAST_NAME', 'DATE_OF_BIRTH');
SELECT COUNT(*) AS unexpected_restaurant_contact_columns FROM FOODPULSE.INFORMATION_SCHEMA.COLUMNS WHERE table_schema = 'ANALYTICS' AND table_name = 'DIM_RESTAURANT' AND column_name IN ('EMAIL', 'PHONE');
SELECT COUNT(*) AS unexpected_review_body_columns FROM FOODPULSE.INFORMATION_SCHEMA.COLUMNS WHERE table_schema = 'ANALYTICS' AND table_name = 'FACT_REVIEWS' AND column_name IN ('REVIEW_TEXT');
SELECT COUNT(*) AS unexpected_order_line_columns FROM FOODPULSE.INFORMATION_SCHEMA.COLUMNS WHERE table_schema = 'ANALYTICS' AND table_name = 'FACT_ORDERS' AND column_name IN ('FOOD_ITEM_ID');
