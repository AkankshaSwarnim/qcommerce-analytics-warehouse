{{ config(materialized='view') }}
--
-- int_customer_order_sequence — put every order in its customer's timeline.
--
-- This is the model that makes the causal question answerable. Everything the
-- analysis needs about "what happened next" is a window function away once each
-- order knows its position in a sequence.
--
-- WHY THIS IS INTERMEDIATE AND NOT A MART: it is a building block two marts
-- need (fct_orders and the retention analysis). Duplicating the window logic in
-- both is how two dashboards start disagreeing about retention six months later.
--
with base as (
    select
        o.order_id,
        o.customer_id,
        o.darkstore_id,
        o.ordered_at_gst,
        o.order_date_gst,
        o.order_hour_gst,
        o.is_cancelled
    from {{ ref('stg_orders') }} o
    -- Cancelled orders are excluded from the SEQUENCE because a cancelled order
    -- is not an experience of the service — nothing was picked, nothing was
    -- missing. They remain in fct_orders for finance. This is a metric
    -- definition decision and it is documented in docs/05_metrics.md, not
    -- buried here.
    where not o.is_cancelled
)

select
    b.*,
    row_number() over (partition by b.customer_id order by b.ordered_at_gst)     as order_seq,
    row_number() over (partition by b.customer_id order by b.ordered_at_gst) - 1 as prior_order_count,
    lead(b.ordered_at_gst) over (partition by b.customer_id order by b.ordered_at_gst) as next_ordered_at_gst,
    lag(b.ordered_at_gst)  over (partition by b.customer_id order by b.ordered_at_gst) as prev_ordered_at_gst,
    date_diff('day', b.ordered_at_gst,
        lead(b.ordered_at_gst) over (partition by b.customer_id order by b.ordered_at_gst)
    ) as days_to_next_order,
    count(*) over (partition by b.customer_id) as customer_lifetime_orders
from base b
