-- DEFECT: ~47 internal QA accounts, flagged nowhere, ordering ~22x a human.
--
-- This test does not assert they are gone — it asserts they are IDENTIFIED.
-- Deleting them from the warehouse would be wrong: finance still needs the raw
-- counts to reconcile against the payment processor. The contract is that they
-- are flagged, and every analysis filters on the flag.
--
-- Fails if the behavioural detector found nobody, which would mean the MAD rule
-- silently stopped working — a much more likely failure than the bots vanishing.
select 'no test accounts detected — is int_test_accounts still working?' as failure
from {{ ref('dim_customer') }}
having sum(case when is_test_account then 1 else 0 end) = 0
