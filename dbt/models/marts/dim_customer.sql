{{ config(materialized='table') }}
--
-- dim_customer — one row per customer. SCD Type 1 (current state only).
--
-- WHY TYPE 1 HERE AND TYPE 2 ELSEWHERE: segment and home store are assigned at
-- acquisition and do not change in this window, so there is no history to lose.
-- Choosing Type 2 anyway would double the row count and buy nothing. SCD2 is a
-- cost, not a virtue — pay it where history actually changes (price, catchment).
--
select
    c.customer_id                                    as customer_key,
    c.customer_id,
    c.segment,
    c.acquired_on,
    c.home_darkstore_id,
    c.is_test_account_source_flag,
    -- The flag the CRM never set, recovered behaviourally. Kept as a separate
    -- column from the source flag so the disagreement stays auditable.
    coalesce(t.is_test_account, false)               as is_test_account,
    coalesce(t.order_count, 0)                       as lifetime_orders
from {{ ref('stg_customers') }} c
left join {{ ref('int_test_accounts') }} t using (customer_id)
