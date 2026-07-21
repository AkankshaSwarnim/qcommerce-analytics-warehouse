-- A rate outside [0,1] means the rollup divided by the wrong denominator —
-- usually a fanned join inflating the numerator. Cheap test, catches a whole
-- class of join bugs the moment they appear.
select order_id, item_fill_rate
from {{ ref('fct_orders') }}
where item_fill_rate < 0 or item_fill_rate > 1
