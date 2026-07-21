-- DEFECT: client retry duplicates in the order event log (~1.2% of orders).
--
-- This test asserts the dedup in stg_orders actually worked. It is a singular
-- test rather than a `unique` schema test on the raw source, because the raw
-- source is EXPECTED to have duplicates — that is not a bug in the source, it
-- is a property of it. The bug would be duplicates surviving into the mart.
--
-- Returns rows on failure. Empty = pass.
select order_id, count(*) as n
from {{ ref('fct_orders') }}
group by 1
having count(*) > 1
