-- Star schema for FOODPULSE.ANALYTICS.
-- Companion to warehouse/snowflake/sql/analytics_tables.sql. Star tables only.
-- CREATE IF NOT EXISTS only. This file does not drop snapshot tables or create a warehouse.
-- DDL commits on its own. A multi-table load is not one atomic snapshot.
-- Grain is documented per table in warehouse/README.md.
-- Live execution uses python -m warehouse.snowflake.run_star --execute, not a local dry-run.

USE WAREHOUSE FOODPULSE_WH;

CREATE DATABASE IF NOT EXISTS FOODPULSE;

CREATE SCHEMA IF NOT EXISTS FOODPULSE.ANALYTICS;

USE DATABASE FOODPULSE;

USE SCHEMA ANALYTICS;

-- DIM_DATE grain: One row per UTC calendar date that appears on an order or a review.
CREATE TABLE IF NOT EXISTS FOODPULSE.ANALYTICS.DIM_DATE (DATE_SK NUMBER, DATE_DAY DATE, YEAR NUMBER, QUARTER NUMBER, MONTH NUMBER, MONTH_NAME VARCHAR, DAY NUMBER, DAY_OF_WEEK NUMBER, DAY_NAME VARCHAR, IS_WEEKEND BOOLEAN, LOADED_AT TIMESTAMP_TZ);

-- DIM_CUSTOMER grain: One row per customer_id from customers.parquet. Given names, contact details, and date of birth are not loaded.
CREATE TABLE IF NOT EXISTS FOODPULSE.ANALYTICS.DIM_CUSTOMER (CUSTOMER_SK NUMBER, CUSTOMER_ID VARCHAR, CITY VARCHAR, GENDER VARCHAR, CREATED_AT TIMESTAMP_TZ, LOADED_AT TIMESTAMP_TZ);

-- DIM_RESTAURANT grain: One row per restaurant_id. City, state, and country come from locations.parquet when location_id matches.
CREATE TABLE IF NOT EXISTS FOODPULSE.ANALYTICS.DIM_RESTAURANT (RESTAURANT_SK NUMBER, RESTAURANT_ID VARCHAR, NAME VARCHAR, CUISINE_TYPE VARCHAR, IS_ACTIVE BOOLEAN, CITY VARCHAR, STATE VARCHAR, COUNTRY VARCHAR, CREATED_AT TIMESTAMP_TZ, LOADED_AT TIMESTAMP_TZ);

-- DIM_FOOD_ITEM grain: One row per food item. restaurant_sk points at DIM_RESTAURANT. There is no fact at this grain.
CREATE TABLE IF NOT EXISTS FOODPULSE.ANALYTICS.DIM_FOOD_ITEM (FOOD_ITEM_SK NUMBER, FOOD_ITEM_ID VARCHAR, RESTAURANT_SK NUMBER, RESTAURANT_ID VARCHAR, NAME VARCHAR, CATEGORY VARCHAR, PRICE FLOAT, IS_AVAILABLE BOOLEAN, CREATED_AT TIMESTAMP_TZ, LOADED_AT TIMESTAMP_TZ);

-- FACT_ORDERS grain: One row per order. Food-item quantity is not at this grain; order_items.parquet is not loaded as a fact.
CREATE TABLE IF NOT EXISTS FOODPULSE.ANALYTICS.FACT_ORDERS (ORDER_SK NUMBER, ORDER_ID VARCHAR, DATE_SK NUMBER, CUSTOMER_SK NUMBER, RESTAURANT_SK NUMBER, STATUS VARCHAR, TOTAL_AMOUNT FLOAT, DISCOUNT_USED FLOAT, TOTAL_AMOUNT_CAPPED FLOAT, IS_TOTAL_OUTLIER BOOLEAN, ORDER_TS TIMESTAMP_TZ, LOADED_AT TIMESTAMP_TZ);

-- FACT_REVIEWS grain: One row per review. Review body text is not loaded. order_sk is null when the review has no matching order.
CREATE TABLE IF NOT EXISTS FOODPULSE.ANALYTICS.FACT_REVIEWS (REVIEW_SK NUMBER, REVIEW_ID VARCHAR, DATE_SK NUMBER, CUSTOMER_SK NUMBER, RESTAURANT_SK NUMBER, ORDER_SK NUMBER, RATING NUMBER, REVIEW_TS TIMESTAMP_TZ, LOADED_AT TIMESTAMP_TZ);

-- Dropped tables
-- DIM_LOCATION: Not requested. City, state, and country are copied onto DIM_RESTAURANT from locations.parquet.
-- DIM_USER: users.parquet holds hashed passwords and is already excluded from the snapshot loader.
-- FACT_ORDER_ITEMS: Not requested. Attaching food_item_id to FACT_ORDERS would repeat order totals.
