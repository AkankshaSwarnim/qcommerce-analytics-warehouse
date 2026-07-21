{{ config(materialized='table') }}
--
-- dim_date — GST calendar spine.
--
-- WHY A DATE DIMENSION AT ALL, when every database has date functions:
--   1. It makes "no orders on this day" visible. A GROUP BY on a fact table
--      cannot show you a day that is missing; a join to a spine can. Silent
--      gaps are how outages get discovered a quarter late.
--   2. It puts the business calendar (weekend = Sat/Sun in the UAE since 2022,
--      Ramadan, payday) in ONE place instead of in every analyst's WHERE clause.
--
-- UAE-SPECIFIC: the working week changed in January 2022 to Mon-Fri, with the
-- weekend on Saturday and Sunday. Any code written against the old Fri/Sat
-- weekend is wrong for this window. DuckDB's dayofweek: 0=Sunday .. 6=Saturday.
--
with spine as (
    select cast(range as date) as date_gst
    from range(date '2026-01-01', date '2026-04-01', interval 1 day)
)
select
    date_gst,
    extract(year from date_gst)        as year,
    extract(month from date_gst)       as month,
    extract(day from date_gst)         as day_of_month,
    extract(dayofweek from date_gst)   as day_of_week,
    strftime(date_gst, '%A')           as day_name,
    date_trunc('week', date_gst)       as week_start,
    date_trunc('month', date_gst)      as month_start,
    (extract(dayofweek from date_gst) in (0, 6)) as is_weekend,
    -- Payday clustering is real in the UAE and it moves basket size. Flagged
    -- here so nobody rediscovers it in a WHERE clause every quarter.
    (extract(day from date_gst) between 25 and 31 or extract(day from date_gst) <= 2) as is_payday_window
from spine
