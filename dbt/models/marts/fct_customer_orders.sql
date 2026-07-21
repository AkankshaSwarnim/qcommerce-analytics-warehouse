{{ config(materialized='table') }}
--
-- fct_customer_orders — GRAIN: one row per order, positioned in the customer's
--                       timeline, with the retention outcome attached.
--
-- This is the analysis table. It is a mart rather than something an analyst
-- rebuilds each time, because "did they come back within 30 days" has about
-- five defensible definitions and the only way two dashboards agree is if they
-- read the same one. The definition here is documented in docs/05_metrics.md.
--
-- CENSORING — the part that is easy to get wrong:
--   An order placed 5 days before the data ends CANNOT have a 30-day outcome.
--   Counting it as "did not repeat" is not conservative, it is wrong: it
--   mislabels every recent order as a failure and manufactures a retention
--   cliff at the end of every chart. is_observable_30d marks the orders that
--   actually have 30 clear days behind them; everything else must be excluded
--   from retention analysis, not defaulted to false.
--
with seq as (
    select * from {{ ref('int_customer_order_sequence') }}
),
bounds as (
    select max(order_date_gst) as max_date from {{ ref('stg_orders') }}
),
orders as (
    select * from {{ ref('fct_orders') }}
)

select
    q.order_id,
    q.customer_id,
    c.segment,
    c.is_test_account,
    q.darkstore_id,
    q.order_date_gst,
    q.order_hour_gst,
    q.order_seq,
    q.prior_order_count,

    -- Tenure. The moderator that carries the decision: a stock-out on order #1
    -- is evidence the service does not work; on order #30 it is a Tuesday.
    case when q.prior_order_count <= {{ var('tenure_new_max_prior_orders') }}
         then 'new' else 'established' end                    as tenure,

    o.n_items,
    o.gross_value_aed,
    o.item_fill_rate,
    o.is_clean_order,
    o.had_stockout,
    o.had_high_intent_stockout,
    o.substitute_offered,
    o.substitute_accepted,
    o.substitution_type,
    o.store_age_days_at_order,

    q.days_to_next_order,

    -- ---- the outcome ----
    (q.days_to_next_order <= {{ var('retention_window_days') }}) as repeat_within_30d,
    -- ...and whether we are entitled to look at it.
    (q.order_date_gst <= b.max_date - interval ({{ var('retention_window_days') }}) day)
                                                                as is_observable_30d

from seq q
inner join orders o using (order_id)
left join {{ ref('dim_customer') }} c on q.customer_id = c.customer_id
cross join bounds b
