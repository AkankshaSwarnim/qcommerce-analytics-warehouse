{{ config(materialized='table') }}
--
-- fct_sessions — GRAIN: one row per session. The EXPERIMENT ANALYSIS TABLE.
--
-- ============================================================================
--  WHY THE GRAIN IS SESSION AND NOT ORDER
-- ============================================================================
-- Assignment happens at session start. Exposure happens at checkout. The
-- treatment (pre-approved substitutions) adds a step to checkout, and some
-- treatment users abandon on that step.
--
-- So: assignment is a clean 50/50. The population that reaches CHECKOUT is not.
--
-- An analyst who builds the experiment table from ORDERS is analysing a
-- population that the treatment itself selected. The randomisation is gone and
-- nothing downstream — no CUPED, no stratification, no bigger sample — can
-- bring it back. The result will be clean, significant, and wrong.
--
-- Building from the ASSIGNMENT table is what makes the sample-ratio mismatch
-- detectable at all. This is the single most consequential grain decision in
-- the warehouse, which is why the model exists rather than being a subquery.
-- ============================================================================
--
select
    s.session_id,
    s.customer_id,
    c.segment,
    c.is_test_account,
    s.session_date_gst,
    s.started_at_gst,
    a.variant,
    (a.variant is not null)      as is_in_experiment,
    s.converted,
    s.order_id,
    o.had_stockout,
    o.substitute_offered,
    o.substitute_accepted,
    o.substitution_type,
    o.gross_value_aed
from {{ ref('stg_sessions') }} s
-- LEFT join from sessions: every assigned session must survive, including the
-- ones that never converted. Those are precisely the rows the SRM lives in.
left join {{ ref('stg_experiment_assignments') }} a using (session_id)
left join {{ ref('fct_orders') }} o on s.order_id = o.order_id
left join {{ ref('dim_customer') }} c on s.customer_id = c.customer_id
