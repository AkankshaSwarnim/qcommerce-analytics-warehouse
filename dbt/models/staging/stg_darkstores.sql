{{ config(materialized='view') }}
--
-- stg_darkstores — SCD Type 2 ops master data.
--
-- WHY TYPE 2 AND NOT TYPE 1: catchment radius changes as rider supply changes.
-- Overwriting it (Type 1) makes every historical order inherit today's
-- catchment, which restates delivery-time history and produces confident,
-- wrong trend lines. Two stores widened catchment inside the window.
--
select
    darkstore_id,
    darkstore_name,
    area,
    cast(affluence_index as double)         as affluence_index,
    cast(opened_on as date)                 as opened_on,
    cast(catchment_radius_km as double)     as catchment_radius_km,
    cast(valid_from as date)                as valid_from,
    cast(coalesce(valid_to, '2999-12-31') as date) as valid_to,
    is_current
from {{ source('raw', 'raw_darkstores') }}
