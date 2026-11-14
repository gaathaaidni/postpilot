# POSTPILOT GROWTH & INTELLIGENCE — PHASE 1 DATABASE REPORT
**Schema Evolution, Table Count Reconciliation, and Migration Validation**

**Baseline Commit:** `ede77a2`
**Database File:** `D:\postpilot\data\posts.db`
**Migration Version:** `20261114_001_growth_properties`
**Engines Supported:** SQLite (local / Termux) and PostgreSQL (Production VPS)

---

## 1. Table Count Reconciliation

A full forensic inspection was performed across baseline commit `ede77a2` and current Phase 1 state to resolve the discrepancy between 25 inspected tables and 24 active tables:

### 1.1 Baseline Reconciliation (Commit `ede77a2`)
- **SQLite Engine (`sqlite_master`):** Reports **25 total tables**.
  - 24 application domain tables.
  - 1 internal SQLite metadata table: `sqlite_sequence` (automatically created by SQLite when `AUTOINCREMENT` is used).
- **PostgreSQL Engine:** Reports **24 total tables** (PostgreSQL uses independent sequences and does not create a `sqlite_sequence` table).
- **Resolution:** The count difference between 24 and 25 is purely an engine-level artifact: SQLite includes `sqlite_sequence`.

### 1.2 Phase 1 Active Reconciliation
- **Baseline Tables:** 25 in SQLite (24 domain + `sqlite_sequence`).
- **New Tables Added:** 2 tables:
  1. `schema_migrations`
  2. `growth_properties`
- **Total Tables in Phase 1:**
  - **SQLite:** **27 tables** (24 baseline domain + 2 new tables + 1 `sqlite_sequence`).
  - **PostgreSQL:** **26 tables** (24 baseline domain + 2 new tables).

### 1.3 Complete Inventory of Phase 1 SQLite Tables (27 Tables)
1. `users`
2. `organizations`
3. `brands`
4. `campaign_strategies`
5. `brand_marketing_profiles`
6. `brand_personas`
7. `content_templates`
8. `scheduled_posts`
9. `post_approvals`
10. `channels`
11. `system_logs`
12. `media_assets`
13. `worker_leases`
14. `analytics_snapshots`
15. `content_calendar`
16. `publishing_events`
17. `whatsapp_webhook_events`
18. `whatsapp_suppression_list`
19. `whatsapp_templates`
20. `meta_sync_history`
21. `linkedin_sync_history`
22. `oauth_tokens`
23. `audit_log`
24. `user_preferences`
25. `sqlite_sequence` (SQLite internal)
26. `schema_migrations` (NEW — Phase 1)
27. `growth_properties` (NEW — Phase 1)

---

## 2. Scheduled Posts Count Reconciliation

In the Phase 0 audit, two post counts were cited (34 and 41). Full database query reconciliation established:

- **Total records in `scheduled_posts`:** **41 records**.
  - **Active Social Platform Records:** **34 records**
    - Facebook (`fb`): 29 records (17 published, 8 scheduled, 1 publishing, 1 pending_approval, 1 draft, 1 cancelled)
    - Instagram (`ig`): 3 records (2 pending_approval, 1 rejected)
    - LinkedIn (`linkedin`): 2 records (1 published, 1 pending_approval)
  - **Cancelled Legacy Records:** **7 records**
    - Platform `tour` (all set to status `cancelled` during legacy migration).
- **Reconciliation Formula:** `34 active social posts + 7 cancelled legacy posts = 41 total records`.
- **Integrity Status:** All 41 records remain 100% intact with zero modifications or data loss.

---

## 3. Phase 1 Schema DDL & Dual-Engine Compatibility

### 3.1 `schema_migrations` Table
```sql
-- SQLite
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'applied'
);

-- PostgreSQL
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    description TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'applied'
);
```

### 3.2 `growth_properties` Table
```sql
-- SQLite
CREATE TABLE IF NOT EXISTS growth_properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_key VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    primary_type VARCHAR(50) NOT NULL,
    organization_id INTEGER NOT NULL DEFAULT 1,
    brand_id INTEGER,
    canonical_url VARCHAR(255),
    target_countries TEXT,
    primary_language VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'Asia/Kolkata',
    is_active INTEGER NOT NULL DEFAULT 1,
    settings_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL
);

-- PostgreSQL
CREATE TABLE IF NOT EXISTS growth_properties (
    id SERIAL PRIMARY KEY,
    property_key VARCHAR(50) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    primary_type VARCHAR(50) NOT NULL,
    organization_id INTEGER NOT NULL DEFAULT 1,
    brand_id INTEGER,
    canonical_url VARCHAR(255),
    target_countries TEXT,
    primary_language VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'Asia/Kolkata',
    is_active INTEGER NOT NULL DEFAULT 1,
    settings_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
    FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL
);
```

---

## 4. Default Seed Verification

On initialization, `init_growth_properties()` validates whether properties are seeded for Organization 1. All seven canonical properties are seeded with strict brand mapping:

1. `gaatha_corporate` -> Brand 101 (`GAATHA`)
2. `gaatha_terra` -> Brand 4 (`Gaatha Terra`, `target_countries='GLOBAL'`)
3. `gaatha_suite` -> Brand 1 (`Gaatha Suite`)
4. `sentira_ai` -> Brand 3 (`Sentira AI`)
5. `gaatha_pos` -> Brand 2 (`Gaatha POS`)
6. `gaatha_ai` -> Brand 6 (`Gaatha AI`)
7. `phoenix` -> Brand 5 (`Pheonix by Aidni Global`)

---

## 5. Rollback Procedure & Disaster Recovery

The migration is completely additive and reversible without impacting legacy application data.

### 5.1 Reversible Rollback SQL
To roll back the Phase 1 schema changes in SQLite or PostgreSQL:
```sql
DROP TABLE IF EXISTS growth_properties;
DELETE FROM schema_migrations WHERE version = '20261114_001_growth_properties';
```

### 5.2 Rollback Safety Verification
A disposable rollback test was executed as part of `test_growth_properties.py::TestGrowthProperties::test_rollback_safety`:
1. Created an isolated scratch database.
2. Initialized database and applied migration `20261114_001_growth_properties`.
3. Executed rollback statements.
4. Verified that `growth_properties` table was cleanly dropped, migration entry was removed, and baseline tables (e.g., `organizations`, `brands`, `scheduled_posts`) remained 100% intact.
- **Rollback Test Result:** PASSED.
