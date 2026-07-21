{{ config(materialized='view') }}
--
-- stg_order_items — one row per order-item. The FINEST grain in the warehouse,
--                   and the reason the whole project exists.
--
-- Fill rate can be computed at this grain (item fill) or collapsed to the order
-- grain (order fill). They are different numbers and they support different
-- decisions. Neither is wrong. Reporting only the first one is.
-- See docs/05_metrics.md and marts/fct_orders.sql.
--
select
    order_id,
    product_id,
    cast(quantity as integer)          as quantity,
    was_stocked_out,
    was_substituted,
    -- The picker's swap category. Logged. Whether the swap was any GOOD is not
    -- logged anywhere — see docs/08_ambiguity.md.
    substitution_type
from {{ source('raw', 'raw_order_items') }}
