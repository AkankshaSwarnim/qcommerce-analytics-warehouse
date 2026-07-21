{{ config(materialized='table') }}
--
-- dim_darkstore — SCD Type 2 on catchment radius.
--
-- Same surrogate-key discipline as dim_product. Two stores widened catchment
-- mid-window, so darkstore_id is not unique and a fact joined on it would fan.
--
-- store_age_days is NOT stored here — it depends on the ORDER date, not the
-- dimension row, so it is a fact-side calculation. Putting a date-relative
-- measure in a dimension is a classic way to build a column that is only
-- correct on the day you built it.
--
select
    md5(concat(darkstore_id, '|', cast(valid_from as varchar))) as darkstore_key,
    darkstore_id,
    darkstore_name,
    area,
    affluence_index,
    opened_on,
    catchment_radius_km,
    valid_from,
    valid_to,
    is_current
from {{ ref('stg_darkstores') }}
