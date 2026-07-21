{{ config(materialized='table') }}
--
-- fct_order_items — GRAIN: one row per order-item. The atomic fact.
--
-- This is where item-level fill rate is computed, and it is deliberately the
-- FINEST grain available. Kimball's rule holds: model at the lowest grain the
-- business can observe, because you can always aggregate up and you can never
-- disaggregate down. Had this been built at order grain to "save space", the
-- entire finding of this project would be unrecoverable.
--
-- THE SCD2 RANGE JOIN: note the join to dim_product is on product_id AND a
-- date-range predicate, not on product_id alone. That predicate is what selects
-- the price version that was live when the order was placed. Drop it and every
-- repriced SKU fans out to two rows, doubling those items' revenue.
--
with items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select * from {{ ref('stg_orders') }}
)

select
    i.order_id,
    i.product_id,
    p.product_key,
    o.customer_id,
    o.darkstore_id,
    o.order_date_gst,
    i.quantity,
    p.category,
    p.is_category_unmapped,
    p.base_price_aed,
    i.quantity * p.base_price_aed          as line_value_aed,
    i.was_stocked_out,
    i.was_substituted,
    i.substitution_type,
    -- High-intent categories: the reason the customer opened the app at 11pm.
    -- A missing bag of crisps is an annoyance; missing infant formula is why
    -- they came. Flagged at the fact grain so the asymmetry is queryable
    -- rather than being re-derived (differently) by every analyst.
    (p.category in ('Dairy & Eggs', 'Fresh Produce', 'Baby', 'Meat & Poultry')) as is_high_intent_category
from items i
inner join orders o
    on i.order_id = o.order_id
left join {{ ref('dim_product') }} p
    on i.product_id = p.product_id
    -- The range predicate. This line is the difference between correct history
    -- and quietly-restated history.
    and o.order_date_gst >= p.valid_from
    and o.order_date_gst <  p.valid_to
