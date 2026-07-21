-- DEFECT CLASS: overlapping SCD2 validity ranges.
--
-- If two versions of the same product are valid on the same date, the range
-- join in fct_order_items fans out and silently doubles that SKU's revenue.
-- There is no error message for this. The only symptom is that the numbers are
-- wrong, which nobody notices until a month-end review.
--
-- This is the test that would have caught the classic SCD2 off-by-one, where
-- valid_to on version 1 equals valid_from on version 2 and both match a
-- BETWEEN predicate. (We use >= / < half-open ranges precisely to avoid it.)
select
    a.product_id,
    a.valid_from as a_from, a.valid_to as a_to,
    b.valid_from as b_from, b.valid_to as b_to
from {{ ref('dim_product') }} a
join {{ ref('dim_product') }} b
    on a.product_id = b.product_id
    and a.product_key <> b.product_key
    and a.valid_from < b.valid_to
    and b.valid_from < a.valid_to
