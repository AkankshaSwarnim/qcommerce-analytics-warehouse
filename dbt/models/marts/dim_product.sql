{{ config(materialized='table') }}
--
-- dim_product — SCD Type 2 on price.
--
-- THE SURROGATE KEY IS THE POINT. product_id is NOT unique here — a repriced
-- SKU has two rows. Joining a fact to product_id would fan out and duplicate
-- revenue. Facts must join on product_key, which is unique per version, and the
-- range condition (order date between valid_from and valid_to) picks the
-- version that was live when the order happened.
--
-- Get this wrong and January's GMV silently restates itself every time
-- someone changes a price. That bug is invisible: no error, no null, just
-- numbers that quietly stop matching last month's deck.
--
select
    md5(concat(product_id, '|', cast(valid_from as varchar))) as product_key,
    product_id,
    category,
    is_category_unmapped,
    base_price_aed,
    valid_from,
    valid_to,
    is_current
from {{ ref('stg_products') }}
