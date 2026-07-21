{{ config(materialized='view') }}
--
-- stg_customers — CRM export, 1:1 with source.
--
-- NOTE ON is_test_account: the column exists. It is False for every row,
-- including the ~47 internal QA accounts that hammer the platform. The flag was
-- built and never populated, which is the most common state for any flag column
-- in any CRM anywhere.
--
-- Detecting them is a BEHAVIOURAL problem, not a staging one, so it lives in
-- int_test_accounts.sql. Staging stays 1:1 with the source on principle: if
-- staging starts making judgements, nobody can tell what the source actually
-- said.
--
select
    customer_id,
    segment,
    cast(acquired_on as date)   as acquired_on,
    home_darkstore_id,
    is_test_account             as is_test_account_source_flag
from {{ source('raw', 'raw_customers') }}
