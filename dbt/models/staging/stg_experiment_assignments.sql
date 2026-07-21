{{ config(materialized='view') }}
--
-- stg_experiment_assignments — one row per assigned session.
--
-- Assignment is written at session START. Read that twice. The analysis
-- population must be defined from THIS table, not from the orders that
-- happened to result, or the SRM is invisible by construction.
--
select
    session_id,
    customer_id,
    variant,
    assigned_at_utc,
    timezone('{{ var("reporting_tz") }}', assigned_at_utc) as assigned_at_gst
from {{ source('raw', 'raw_experiment_assignments') }}
