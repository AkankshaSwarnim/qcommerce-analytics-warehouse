{{ config(materialized='table') }}
--
-- fct_orders — GRAIN: one row per order.
--
-- ============================================================================
--  THIS MODEL IS THE POINT OF THE PROJECT.
-- ============================================================================
-- The ops dashboard reports ITEM fill rate. The customer experiences ORDER
-- fill rate. An order is clean only if EVERY item in it is clean, so:
--
--       P(clean order) = (1 - item_miss_rate) ^ basket_size
--
-- At a ~5.7% item miss rate and a ~7.9-item mean basket, roughly a third of
-- orders are broken while the item metric reads ~94%. Both numbers are correct.
-- They are the same data at two grains, and they support opposite decisions.
--
-- The inversion is the finding: item fill rate is FLAT across basket size (even
-- slightly better for large baskets), while order fill rate collapses. So the
-- ops metric ranks large-basket customers — the highest-value segment — as
-- well-served, at the exact moment they are being served worst.
--
-- Both measures are materialised side by side here, on purpose. Anyone reading
-- this table has to see them together and pick, which is the intended friction.
-- ============================================================================
--
with item_rollup as (
    select
        order_id,
        count(*)                                            as n_items,
        sum(quantity)                                       as n_units,
        sum(line_value_aed)                                 as gross_value_aed,
        sum(case when was_stocked_out then 1 else 0 end)    as n_stocked_out,
        max(case when was_stocked_out then 1 else 0 end)    as had_any_stockout,
        max(case when was_stocked_out and is_high_intent_category then 1 else 0 end)
                                                            as had_high_intent_stockout,
        sum(case when was_substituted then 1 else 0 end)    as n_substituted,
        -- One order can in principle carry several swap types. Take the WORST
        -- (least repairing) as the order's characterisation, because the
        -- customer's memory of the order is set by its worst moment, not its
        -- average. This is a judgement call and it is stated as one.
        min(case substitution_type
                when 'diff_product_same_cat'   then 1
                when 'diff_brand_same_product' then 2
                when 'same_brand_diff_size'    then 3
            end)                                            as worst_sub_rank
    from {{ ref('fct_order_items') }}
    group by 1
),

fulfilment as (
    select * from {{ ref('stg_fulfilment') }}
)

select
    s.order_id,
    s.customer_id,
    d.darkstore_key,
    s.darkstore_id,
    s.order_date_gst,
    s.order_hour_gst,
    s.ordered_at_gst,
    s.is_cancelled,

    -- basket
    r.n_items,
    r.n_units,
    r.gross_value_aed,

    -- ---- the two fill rates, side by side ----
    r.n_stocked_out,
    -- ITEM grain: what ops reports.
    (r.n_items - r.n_stocked_out) * 1.0 / nullif(r.n_items, 0) as item_fill_rate,
    -- ORDER grain: what the customer lives.
    (r.had_any_stockout = 0)                                   as is_clean_order,
    (r.had_any_stockout = 1)                                   as had_stockout,
    (r.had_high_intent_stockout = 1)                           as had_high_intent_stockout,

    -- substitution
    r.n_substituted,
    f.substitute_offered,
    f.substitute_accepted,
    case r.worst_sub_rank
        when 1 then 'diff_product_same_cat'
        when 2 then 'diff_brand_same_product'
        when 3 then 'same_brand_diff_size'
    end                                                        as substitution_type,

    -- data-quality passthrough: lets any consumer see whether this row was
    -- late and decide for itself whether to trust today's number.
    f.ingestion_lag_minutes,
    f.is_late_arriving,

    -- store age at ORDER time — a fact-side calc, see dim_darkstore.
    date_diff('day', d.opened_on, s.order_date_gst)            as store_age_days_at_order

from {{ ref('stg_orders') }} s
inner join item_rollup r using (order_id)
left join fulfilment f using (order_id)
left join {{ ref('dim_darkstore') }} d
    on s.darkstore_id = d.darkstore_id
    and s.order_date_gst >= d.valid_from
    and s.order_date_gst <  d.valid_to
