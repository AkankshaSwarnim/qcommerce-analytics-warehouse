{{ config(materialized='view') }}
--
-- stg_fulfilment — picker outcome per order.
--
-- DEFECT SURFACED (not repaired) HERE: late-arriving data.
--   fulfilled_at_utc is when it HAPPENED. ingested_at_utc is when the warehouse
--   SAW it. ~8% of rows trail by up to 6 hours.
--
--   This cannot be "fixed" in SQL — the data genuinely was not there. What SQL
--   can do is make the latency VISIBLE so downstream models stop pretending
--   today's fill rate is final. Any dashboard reading the current day is
--   reading an incomplete number that will move overnight, and the fix is to
--   mark the day provisional, not to argue with physics.
--
--   ingestion_lag_minutes is exposed for exactly that purpose.
--
select
    order_id,
    fulfilled_at_utc,
    ingested_at_utc,
    timezone('{{ var("reporting_tz") }}', fulfilled_at_utc) as fulfilled_at_gst,
    date_diff('minute', fulfilled_at_utc, ingested_at_utc)  as ingestion_lag_minutes,
    (date_diff('minute', fulfilled_at_utc, ingested_at_utc) > 60) as is_late_arriving,
    had_stockout,
    substitute_offered,
    substitute_accepted,
    substitution_type
from {{ source('raw', 'raw_fulfilment_events') }}
