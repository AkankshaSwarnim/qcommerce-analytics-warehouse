{{ config(materialized='view') }}
--
-- stg_products — SCD Type 2 catalogue.
--
-- DEFECT REPAIRED HERE: ~3% NULL category.
--   The tempting fix is `where category is not null`, which silently deletes 3%
--   of revenue from every category report and makes the totals stop tying out.
--   The honest fix is an explicit 'Unmapped' bucket: the number stays visible,
--   the totals still tie, and it embarrasses someone into fixing the catalogue.
--   A quiet filter is how a data team loses trust exactly once.
--
-- SCD2 NOTE: valid_to is NULL for the current version. Downstream range joins
-- must coalesce it to a far-future date or they will drop every live row —
-- see dim_product.
--
select
    product_id,
    coalesce(category, 'Unmapped')          as category,
    (category is null)                      as is_category_unmapped,
    cast(base_price_aed as double)          as base_price_aed,
    cast(valid_from as date)                as valid_from,
    cast(coalesce(valid_to, '2999-12-31') as date) as valid_to,
    is_current
from {{ source('raw', 'raw_products') }}
