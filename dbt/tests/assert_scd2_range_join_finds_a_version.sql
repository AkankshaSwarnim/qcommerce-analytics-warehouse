-- DEFECT CLASS: SCD2 gaps.
--
-- The mirror image of the overlap test. If NO version is valid on the order
-- date, the left join yields NULL and the item silently loses its price and
-- category. Revenue quietly goes missing rather than quietly doubling.
--
-- Overlap and gap are the two failure modes of a range join and you need both
-- tests. Teams usually write neither.
select order_id, product_id
from {{ ref('fct_order_items') }}
where product_key is null
