{{ config(materialized='view') }}
--
-- stg_sessions — app analytics.
--
-- The grain that matters for the experiment: a session is where ASSIGNMENT
-- happens. An order is where EXPOSURE happens. Those are not the same event and
-- conflating them is what breaks the experiment. See marts/fct_sessions.sql.
--
select
    session_id,
    customer_id,
    started_at_utc,
    timezone('{{ var("reporting_tz") }}', started_at_utc)  as started_at_gst,
    cast(timezone('{{ var("reporting_tz") }}', started_at_utc) as date) as session_date_gst,
    converted,
    order_id
from {{ source('raw', 'raw_sessions') }}
