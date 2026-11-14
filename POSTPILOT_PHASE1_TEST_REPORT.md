# POSTPILOT GROWTH & INTELLIGENCE — PHASE 1 TEST REPORT
**Regression Verification, Test Arithmetic Reconciliation, and Baseline Attribution**

**Baseline Commit:** `ede77a2`
**Phase 1 Dedicated Test Suite:** `test_growth_properties.py`
**Date:** 2026-11-14

---

## 1. Test Arithmetic Reconciliation

The full pytest execution summary across the active repository is as follows:

| Metric | Count | Reconciliation Check |
|---|---|---|
| **Total Tests Collected** | **322** | 305 baseline + 17 Phase 1 tests |
| **Passed Tests** | **311** | 294 baseline + 17 Phase 1 tests |
| **Failed Tests** | **11** | 11 pre-existing baseline failures |
| **Skipped Tests** | **0** | |
| **Errors** | **0** | |
| **Total Accounted For** | **322** | **311 Passed + 11 Failed = 322 Total** |
| **Execution Duration** | **55.43s** | |
| **Pytest Exit Code** | 1 | (due to 11 pre-existing failures) |

*Note: Exactly 311 tests passed and 11 tests failed, accounting for 100% of the 322 collected test nodes.*

---

## 2. Phase 1 Dedicated Test Suite Results (`test_growth_properties.py`)

All 17 dedicated Phase 1 tests passed cleanly (100% pass rate in 3.24 seconds):

```
test_growth_properties.py::TestGrowthProperties::test_default_growth_properties_seeded PASSED
test_growth_properties.py::TestGrowthProperties::test_property_terra_target_countries_is_global PASSED
test_growth_properties.py::TestGrowthProperties::test_brand_mappings_accurate PASSED
test_growth_properties.py::TestGrowthProperties::test_schema_migration_recorded PASSED
test_growth_properties.py::TestGrowthProperties::test_crud_create_property PASSED
test_growth_properties.py::TestGrowthProperties::test_crud_update_property PASSED
test_growth_properties.py::TestGrowthProperties::test_crud_toggle_status PASSED
test_growth_properties.py::TestGrowthProperties::test_api_list_properties PASSED
test_growth_properties.py::TestGrowthProperties::test_api_get_property_by_id PASSED
test_growth_properties.py::TestGrowthProperties::test_api_create_property_success PASSED
test_growth_properties.py::TestGrowthProperties::test_api_create_property_duplicate_key_rejected PASSED
test_growth_properties.py::TestGrowthProperties::test_api_create_property_invalid_payload_rejected PASSED
test_growth_properties.py::TestGrowthProperties::test_api_update_property PASSED
test_growth_properties.py::TestGrowthProperties::test_api_toggle_status_patch_csrf_protected PASSED
test_growth_properties.py::TestGrowthProperties::test_api_viewer_role_cannot_modify PASSED
test_growth_properties.py::TestGrowthProperties::test_tenant_isolation_enforced PASSED
test_growth_properties.py::TestGrowthProperties::test_rollback_safety PASSED

============================= 17 passed in 3.24s =============================
```

---

## 3. Pre-existing Baseline Failure Attribution (The 11 Failures)

To provide forensic certainty that Phase 1 introduced zero regressions, an isolated git worktree was checked out directly from clean commit `ede77a2` (before any Phase 1 modifications). Running the tests against `ede77a2` confirmed that all 11 failures are 100% pre-existing:

### 3.1 Failure Attribution Matrix

| Test Node ID | Failure Reason | Root Cause in Baseline `ede77a2` | Regressed in Phase 1? |
|---|---|---|:---:|
| `test_campaign_api.py::TestCampaignAPI::test_brand_marketing_profiles_table_exists` | Missing table in test DB | Test creates temporary SQLite database without running brand migration scripts | **NO** (Pre-existing) |
| `test_campaign_api.py::TestCampaignAPI::test_campaign_strategies_table_exists` | Missing table in test DB | Test creates temporary SQLite database without running strategy migration scripts | **NO** (Pre-existing) |
| `test_channel_runner.py::TestChannelRunner::test_gaatha_interval_config` | Assertion mismatch | `GAATHA_INTERVAL` was changed to 1800s in config while test expects legacy 7200s | **NO** (Pre-existing) |
| `test_channel_runner.py::TestChannelRunner::test_insta_interval_config` | Assertion mismatch | `INSTA_INTERVAL` was changed to 180s in config while test expects legacy 300s | **NO** (Pre-existing) |
| `test_channel_runner.py::TestChannelRunner::test_legacy_channel_execution_raises_guard_error` | Missing exception | Guard error string expects 'legacy' but channel returns general deactivated error | **NO** (Pre-existing) |
| `test_channel_runner.py::TestChannelRunner::test_nz_interval_config` | Key error | New Zealand channel was decommissioned in baseline commit `ede77a2` | **NO** (Pre-existing) |
| `test_channel_runner.py::TestChannelRunner::test_tour_interval_config` | Assertion mismatch | Tour channel interval was deprecated when Tour was replaced with Suite | **NO** (Pre-existing) |
| `test_cross_platform_restore.py::test_termux_simulated_restore` | Path separator mismatch | Test fixture uses Unix `/` path separator on Windows environment | **NO** (Pre-existing) |
| `test_publishing_approval_workflow.py::TestPublishingApprovalWorkflow::test_approval_history_audit_log_recorded` | Missing audit log record | Test runs against mock session without database audit logger hook | **NO** (Pre-existing) |
| `test_publishing_approval_workflow.py::TestPublishingApprovalWorkflow::test_pending_approval_filter_returns_only_submitted` | Filter assertion mismatch | Query fixture includes unsubmitted draft posts in local fixture | **NO** (Pre-existing) |
| `test_publishing_approval_workflow.py::TestPublishingApprovalWorkflow::test_two_man_rule_creator_cannot_approve` | Status code mismatch | Returns 403 instead of test-asserted 400 for self-approval block | **NO** (Pre-existing) |

### 3.2 Net Regression Conclusion
- **Total Failures in Baseline `ede77a2`:** 11
- **Total Failures in Phase 1:** 11
- **Net New Regressions Introduced:** **0 (ZERO)**

---

## 4. Security & Isolation Test Summary

1. **CSRF Enforcement on PATCH:** Verified by `test_api_toggle_status_patch_csrf_protected`. Requests without valid CSRF token return 400.
2. **Tenant Isolation:** Verified by `test_tenant_isolation_enforced`. Users in Organization 1 cannot read, list, update, or toggle properties belonging to Organization 2.
3. **Role Restrictions:** Verified by `test_api_viewer_role_cannot_modify`. Accounts with `role='viewer'` receive 403 Forbidden on create, update, or status toggle requests.
4. **Publishing Safeguards:** `POSTPILOT_PUBLISHING_ENABLED=0` and `WHATSAPP_PUBLISHING_ENABLED=0` validated and remain fail-closed.
