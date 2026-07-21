{{ config(materialized='view') }}
--
-- int_test_accounts — find the QA bots nobody flagged.
--
-- ============================================================================
--  THE PROBLEM
-- ============================================================================
-- ~47 internal accounts order roughly 22x more than a human and never lapse.
-- They sit in the CRM with is_test_account = false, because the flag was built
-- and never populated. They inflate order counts, drag average retention up,
-- and distort every segment aggregate they touch.
--
-- You cannot look them up. You have to find them by shape.
--
-- ============================================================================
--  WHAT I TRIED FIRST, AND WHY IT WAS WRONG
-- ============================================================================
-- First attempt: median + 8 * 1.4826 * MAD on order_count. The reasoning was
-- that MAD resists the masking problem — the bots are inside the sample used to
-- set the threshold, so a mean/sd rule lets them inflate the bar until it can
-- no longer see them.
--
-- The masking reasoning was right. The threshold was garbage.
--
-- Human order_count is heavy-tailed: median 2, MAD 1. So k=8 in MAD units is an
-- ABSOLUTE threshold of ~14 orders — and 1,205 real customers order more than
-- 14 times in 90 days. Result: precision 0.038, recall 1.000. It flagged 1,252
-- accounts to catch 47.
--
-- "k=8 is conservative" was an assumption about the units, not a fact about the
-- data. On a distribution with a tiny MAD, a small k is a LOW bar, not a high
-- one. Kept in the comments rather than quietly corrected, because the mistake
-- is more instructive than the fix.
--
-- ============================================================================
--  WHAT THE DATA ACTUALLY SAYS
-- ============================================================================
--   order_count            humans: median 2,   p99 18,  max 31
--                          bots:   median 116, min 29,  max 165
--   orders_per_active_day  humans: median 1.0, p99 2.0, max 4.0
--                          bots:   median 1.8, min 1.5, max 2.24
--
-- THE CLASSES OVERLAP. Human max is 31 orders; bot min is 29. A heavy human
-- power-user and a light QA bot are genuinely indistinguishable on volume
-- alone, so NO threshold on this feature can be perfect. That is a property of
-- the world, not a tuning failure, and it caps recall at 0.979 no matter what.
--
-- k sweep on order_count:
--
--     k    threshold   flagged   precision   recall
--     8          13     1,144       0.041    1.000   <- the original mistake
--    20          31        46       1.000    0.979   <- chosen
--    40          61        42       1.000    0.894
--    60          90        30       1.000    0.638
--   100         150         5       1.000    0.106
--
-- ============================================================================
--  THE CHOICE, AND WHY
-- ============================================================================
-- k = 20 (threshold: 31 orders). Precision 1.000, recall 0.979 — 46 of 47 bots
-- caught, zero real customers wrongly excluded. The one miss is the bot sitting
-- at 29 orders, inside the human range; it is unreachable by construction.
--
-- Raising k buys nothing. Precision is already 1.000 at k=20, so k=40 trades
-- 9 points of recall for no gain. Lowering k is catastrophic: k=8 flags 1,144
-- accounts to catch 47.
--
-- The asymmetry that sets the direction of the error, if one has to be made:
-- the central finding of this project concerns large-basket, high-frequency
-- customers. They are exactly who a low threshold discards. Wrongly excluding
-- real power users would bias the very population the analysis is about, which
-- is worse than leaving one bot in 145,000 orders (~0.08% of volume).
--
-- The threshold is chosen against the ANALYSIS, not a generic accuracy metric.
-- A different question would justify a different k. That is not inconsistency,
-- it is what fitness for purpose means.
--
-- ============================================================================
--  THE HONEST CAVEAT
-- ============================================================================
-- Those precision/recall numbers exist only because this data is synthetic and
-- there IS a ground-truth file to score against. In production there is not.
-- You would never know your recall.
--
-- What you would do instead is triangulate on signals unrelated to volume:
-- internal IP ranges, @company email domains, device fingerprints shared across
-- accounts, creation timestamps clustered in one afternoon, payment instruments
-- repeated across "customers". Volume alone is the weakest available signal and
-- it is the only one this dataset carries.
--
-- Reported in reports/results.json as a sensitivity, never asserted as a fact.
-- ============================================================================
--
with per_customer as (
    select
        customer_id,
        count(*)                                        as order_count,
        count(distinct order_date_gst)                  as active_days,
        count(*) * 1.0 / nullif(count(distinct order_date_gst), 0) as orders_per_active_day
    from {{ ref('stg_orders') }}
    where not is_cancelled
    group by 1
),

robust_stats as (
    select
        median(order_count) as med_orders,
        median(abs(order_count - (select median(order_count) from per_customer))) as mad_orders
    from per_customer
)

select
    p.customer_id,
    p.order_count,
    p.active_days,
    p.orders_per_active_day,
    s.med_orders,
    s.mad_orders,
    -- 1.4826 rescales MAD into sigma-equivalent units under normality.
    s.med_orders + 20 * 1.4826 * nullif(s.mad_orders, 0)                as threshold,
    (p.order_count > s.med_orders + 20 * 1.4826 * nullif(s.mad_orders, 0)) as is_test_account
from per_customer p
cross join robust_stats s
