-- THE PROJECT'S CENTRAL INVARIANT, enforced as a test.
--
-- An order is clean only if every item is. So for any grouping, order-level
-- fill rate can never exceed item-level fill rate. If it ever does, the rollup
-- has a bug — most likely a join fanning out, or is_clean_order computed off a
-- different item set than item_fill_rate.
--
-- Encoding the finding as an invariant means the pipeline defends the claim
-- rather than the README asserting it.
with by_day as (
    select
        order_date_gst,
        avg(item_fill_rate)                                          as item_fill,
        sum(case when is_clean_order then 1 else 0 end) * 1.0 / count(*) as order_fill
    from {{ ref('fct_orders') }}
    group by 1
)
select * from by_day
where order_fill > item_fill + 1e-9
