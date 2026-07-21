{{ config(materialized='view') }}
--
-- stg_orders — one row per ORDER, from an event log that has more than one row
--              per order.
--
-- DEFECT REPAIRED HERE: duplicate order events.
--   The order service retries on network timeout and does not send an
--   idempotency key, so ~1.2% of orders appear twice, a few hundred
--   milliseconds apart, with identical payloads.
--
--   A COUNT(*) on the raw table overstates orders by 1.2%. That is small enough
--   to never look wrong and large enough to move a target.
--
-- WHY QUALIFY AND NOT GROUP BY:
--   GROUP BY order_id would force an aggregate on every other column (MIN, ANY_VALUE),
--   which silently invents rows when the duplicates ever disagree. QUALIFY with
--   ROW_NUMBER keeps the FIRST physical event intact — we take the earliest
--   event as the true one, because the retry is by definition the later row.
--
-- DEFECT REPAIRED HERE: UTC vs GST.
--   Source logs UTC. The business reports GST (UTC+4, no DST). An order placed
--   at 01:30 GST on the 5th is logged 21:30 UTC on the 4th. Reporting on the
--   raw UTC date moves every late-night order — the Late-Night Rescue segment's
--   entire existence — onto the previous day.
--
with deduped as (
    select
        order_id,
        customer_id,
        darkstore_id,
        event_type,
        event_at_utc
    from {{ source('raw', 'raw_order_events') }}
    -- Keep the earliest event per (order, type). The retry is always later.
    qualify row_number() over (
        partition by order_id, event_type
        order by event_at_utc
    ) = 1
),

placed as (
    select order_id, customer_id, darkstore_id, event_at_utc
    from deduped
    where event_type = 'order_placed'
),

cancelled as (
    select distinct order_id
    from deduped
    where event_type = 'order_cancelled'
)

select
    p.order_id,
    p.customer_id,
    p.darkstore_id,
    p.event_at_utc                                            as ordered_at_utc,
    -- The single timezone conversion in the project. Everything downstream
    -- reads _gst and never touches _utc again.
    timezone('{{ var("reporting_tz") }}', p.event_at_utc)     as ordered_at_gst,
    cast(timezone('{{ var("reporting_tz") }}', p.event_at_utc) as date) as order_date_gst,
    extract(hour from timezone('{{ var("reporting_tz") }}', p.event_at_utc)) as order_hour_gst,
    (c.order_id is not null)                                  as is_cancelled
from placed p
left join cancelled c using (order_id)
