-- THE CENSORING TRAP.
--
-- An order with fewer than 30 days of follow-up cannot have a 30-day outcome.
-- If any order is marked observable but sits inside the censoring window, the
-- retention numbers acquire a fake cliff at the end of the series and every
-- recent cohort looks like it is collapsing.
--
-- This is the single most common way retention charts lie, and it lies in the
-- alarming direction, which is how it survives review: nobody interrogates a
-- number that makes them worried.
with bounds as (select max(order_date_gst) as max_date from {{ ref('fct_orders') }})
select o.order_id, o.order_date_gst, b.max_date
from {{ ref('fct_customer_orders') }} o
cross join bounds b
where o.is_observable_30d
  and o.order_date_gst > b.max_date - interval 30 day
