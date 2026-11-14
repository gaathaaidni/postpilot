# POSTPILOT CURRENT STATE AUDIT
**Phase 0 — Baseline Architecture Discovery & Validation**  
**Date:** November 14, 2026  
**Environment:** Local Workstation (`D:\postpilot`)  
**Git Branch:** `main` | **Current Commit:** `ede77a2`  
**Repository:** `https://github.com/gaathaaidni/postpilot`  
**Working Tree Status:** Clean (no uncommitted modifications)

---

## 1. Executive Summary

PostPilot is an enterprise-grade multi-tenant content orchestration, campaign generation, and social publishing system engineered with a fail-closed architecture. It was designed to run ubiquitously across three distinct environments:
- **Environment A:** Linux Web Server (Cloud VPS / Gunicorn / PostgreSQL / Nginx reverse proxy)
- **Environment B:** Android Mobile Phone (Termux / SQLite WAL / Python 3.12 / Loopback binding)
- **Environment C:** Local Development Workstation (Windows 10/11 / SQLite WAL)

This audit establishes the definitive baseline of the existing codebase prior to its expansion into a **Growth & Intelligence Command Center**.

---

## 2. Source Code & Git State Validation

- **Repository Origin:** `https://github.com/gaathaaidni/postpilot`
- **Active Branch:** `main` (synchronized with `origin/main`)
- **Current HEAD Commit:** `ede77a2` (*"Implement LinkedIn personal profile publishing, company page preparation, and duplicate dispatch protection"*)
- **Recent Commit History:**
  - `ede77a2`: Implement LinkedIn personal profile publishing, company page preparation, and duplicate dispatch protection
  - `aed8aae`: Configure verified Meta portfolio Pages, Instagram mappings, and WhatsApp preferred sender
  - `e5dd9d8`: Normalize UTF-8 middle-dot and dash glyphs in WhatsApp status and UI
  - `ac8fc80`: Align WhatsApp preferred sender (+91 98257 28291), preserve secondary, and distinguish confirmed/unknown/cached/restricted states
  - `634af0e`: Represent both WhatsApp Business accounts independently with sender selector and readiness checks

---

## 3. Architecture Inventory

### 3.1 Backend Application Framework
- **Framework:** Python Flask (Flask 3.x), WSGI compliant.
- **Entry Points:**
  - `app.py`: Web API, authentication, routing, and single-page dashboard rendering (107 defined routes).
  - `worker.py`: Background synchronization worker and scheduled post dispatch engine.
  - `channel_runner.py`: Thread-based execution loops for legacy channel publishing.
  - `backup.py`: CLI and programmatic portable backup utility.
- **Configuration Engine (`config.py`):**
  - Universal runtime environment detection (`production`, `termux`, `development`).
  - Dynamic host/port binding (strictly enforces `127.0.0.1` inside Termux; configurable in dev/prod).
  - Explicit session cookie security (`HttpOnly=True`, `SameSite=Lax`, `Secure` in production).
  - Centralized, fail-closed publishing switchboard.

### 3.2 Frontend Architecture
- **Rendering Engine:** Server-rendered Jinja2 templates serving an integrated Single-Page Interface (SPA).
- **Templates (`templates/`):**
  - `index.html` (80.2 KB): Core application dashboard incorporating:
    - Multi-brand switcher and brand profile inspector
    - Post composer with live multi-platform previews (Facebook, Instagram, LinkedIn, WhatsApp)
    - Editorial calendar grid with drag-and-drop / reschedule workflows
    - Marketing Studio with AI campaign generators and draft revision inspectors
    - Scheduled posts queue and two-man rule approval desk
    - Social account connectivity manager and WhatsApp readiness viewer
    - AI usage telemetry and token cost metrics
  - `login.html`: Secure authentication interface with CSRF token injection
  - `about.html`, `privacy.html`, `terms.html`, `user-agreement.html`: Formal legal documentation pages
- **Static Assets (`static/`):**
  - Modern, responsive Dark & Light theme CSS utilizing CSS custom properties.
  - Vanilla JavaScript architecture with no heavy external SPA frameworks (zero React/Vue/Angular build step overhead), ensuring ultra-fast load times and seamless Android Termux compatibility.

### 3.3 Database Engine, Schema & Migrations
- **Engine Support:**
  - **Local Dev / Termux:** SQLite 3 in `PRAGMA journal_mode=wal` (Write-Ahead Logging) with `PRAGMA busy_timeout=5000` and `PRAGMA synchronous=NORMAL`.
  - **Production:** PostgreSQL 15/16 via standard SQL abstractions in `database.py`.
- **Database File:** `D:\postpilot\data\posts.db` (356 KB).
- **Database Schema (25 Tables):**
  1. `organizations`: Tenant accounts, subscription tiers, timezones, active states.
  2. `brands`: Sub-entities / products mapped to organizations (e.g. GAATHA Suite, Sentira AI, POS, Terra, Phoenix, AI).
  3. `brand_marketing_profiles`: In-depth positioning, audiences, voice, guidelines, and prohibited claims.
  4. `users`: Multi-tenant user credentials, bcrypt password hashes, and RBAC roles.
  5. `posts`: Content templates and historical baseline post records.
  6. `scheduled_posts`: Queue of scheduled posts with status lifecycle, idempotency keys, and approval locks.
  7. `post_audit_logs`: Immutable audit trail tracking every post status transition and user action.
  8. `campaigns`: Marketing initiatives with objectives, target audiences, and budget allocations.
  9. `campaign_strategies`: Structured AI-generated campaign blueprints and channel allocations.
  10. `content_plans`: High-level multi-week editorial calendar schedules.
  11. `content_plan_entries`: Individual planned content slots linked to campaigns.
  12. `content_drafts`: Platform-specific post drafts generated by AI or written manually.
  13. `content_draft_revisions`: Full revision history with optimistic locking and rollback support.
  14. `media_assets`: Image and video asset metadata linked to brands and campaigns.
  15. `social_accounts`: Connected social accounts across Facebook, Instagram, LinkedIn, and WhatsApp.
  16. `whatsapp_webhook_events`: Inbound webhook events, delivery receipts, and status updates.
  17. `whatsapp_suppression_list`: Phone number opt-out registry enforcing compliance.
  18. `whatsapp_templates`: Synced Meta WhatsApp Cloud API pre-approved templates.
  19. `ai_usage_logs`: Token consumption, latency, cost estimation, and provider logging.
  20. `subscription_plans`: SaaS plan definitions and quota limits.
  21. `organization_subscriptions`: Active organization billing cycles and plan status.
  22. `worker_leases`: Distributed mutual exclusion locks preventing concurrent worker execution.
  23. `task_state`: Interval and execution state tracking for background worker loops.
  24. `synced_posts`: Deduping table preventing cross-platform duplicate posting.
  25. `sqlite_sequence`: Internal SQLite sequence tracking.

### 3.4 Authentication & Authorization
- **Session Security:** Server-side sessions backed by `SECRET_KEY`, secured with `HttpOnly` and `SameSite=Lax`.
- **CSRF Defense:** Cryptographic CSRF tokens generated in user session and validated on all state-mutating requests (`POST`, `PUT`, `DELETE`).
- **Localhost Developer Mode (`LOCAL_MODE`):** Automatic bypass active *strictly* for loopback requests (`127.0.0.1` / `::1`) in development and Termux environments. Strictly disabled in production.
- **Tenant Isolation:** Every data access query in `database.py` enforces `organization_id` scoping to prevent cross-tenant data leakage.
- **Role-Based Access Control (RBAC):** Supports `admin`, `editor`, `viewer`, and `approver` roles.

### 3.5 AI Integration (`ai_service.py`)
- **Architecture:** Provider-agnostic factory pattern (`BaseAIProvider`).
- **Supported Providers:**
  - `MockAIProvider`: Fully offline simulation generating realistic multi-platform copy without API keys or internet access.
  - `GroqProvider`: Production-grade high-speed inference utilizing Groq Cloud API (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`).
  - `OpenAIProvider` & `OpenAICompatibleProvider`: Integration with OpenAI (`gpt-4o-mini`) or self-hosted local LLMs.
- **Cost & Generation Controls:**
  - Maximum platform count per request (default: 5)
  - Maximum input prompt character limits (8,000 chars)
  - Maximum output token budgets (1,500 tokens)
  - Hourly organization generation ceilings and 15-second deduplication windows.

### 3.6 Social Integrations & Publishing Engine
- **Platform Adapters (`platform_adapters/`):**
  - `facebook.py`: Meta Graph API integration supporting multi-page publishing across verified business portfolio pages.
  - `instagram.py`: Three-stage containerized publishing flow (create container -> poll container status -> publish container).
  - `linkedin.py`: Dual-mode publishing supporting personal profile shares (`w_member_social`) and Company Page organizational shares (`w_organization_social`).
  - `whatsapp.py`: Meta WhatsApp Cloud API integration with WABA sender selector (+91 98257 28291 preferred), template variable interpolation, and suppression list checks.
- **Publishing Safeguards:**
  - Global master kill switch: `POSTPILOT_PUBLISHING_ENABLED=0` (hard failure if zero or unset).
  - Platform-level kill switches: `WHATSAPP_PUBLISHING_ENABLED=0`, `POSTPILOT_LINKEDIN_PERSONAL_PUBLISHING_ENABLED=0`.
  - Allowed platforms whitelist: `POSTPILOT_ALLOWED_PLATFORMS`.
  - Two-man rule: Posts cannot be dispatched without explicit approval by an authorized approver.
  - Idempotency keys preventing accidental double-posting on worker crashes.

### 3.7 Background Workers & Task Scheduling
- **Engine (`worker.py`):**
  - Standalone process executing continuous sync loops.
  - Distributed mutual exclusion via `worker_leases` table.
  - Automatic dispatch of due scheduled posts matching `status='approved'` and `scheduled_for <= utcnow()`.
  - Signal-safe termination handling (`SIGINT`, `SIGTERM`).

### 3.8 Test Suite & Quality Assurance
- **Framework:** `pytest` with `pytest-subtests`.
- **Test Inventory:** 305 collected test cases covering unit, integration, security, and end-to-end flows.
- **Test Categories:**
  - `test_ai_service.py`: Provider factory, token budgets, JSON parsers, error classifications.
  - `test_campaign_api.py`: Multi-tenant isolation, campaign lifecycle, draft versioning, CSRF.
  - `test_channel_runner.py`: Error classifications, retry strategies, credential sanitization.
  - `test_linkedin_personal_and_company.py`: Dual app credentialing, duplicate post suppression.
  - `test_whatsapp_readiness.py`: Sandbox simulation, HMAC-SHA256 signature verification, opt-outs.
  - `test_termux_compatibility.py`: Loopback binding, dependency portability, WAL mode.

---

## 4. Platform Preservation Checklist

| Component | Current State | Preservation Mandate |
|---|---|---|
| **Facebook Publishing** | Ready (Meta Portfolio: 560075574375818) | **PRESERVE** — Adapter code, page ID mappings, and safety switches untouched. |
| **Instagram Graph API** | Ready (Verified IG Accounts mapped) | **PRESERVE** — Container publishing and hashtag parsing logic untouched. |
| **WhatsApp Cloud API** | Verified WABA & Phone (+91 98257 28291) | **PRESERVE** — Zero outbound requests, suppression lists, and webhooks intact. |
| **LinkedIn Integration** | Dual-app architecture (Personal & Company)| **PRESERVE** — Token refresh flows and duplicate protection untouched. |
| **Scheduled Posts** | 39 queued/approved posts in database | **PRESERVE** — Zero records deleted, modified, or prematurely dispatched. |
| **Groq AI Integration** | Configured for `llama-3.3-70b-versatile` | **PRESERVE** — Prompts, deduplication, and budget caps preserved. |
| **Brand Management** | 9 brands across 2 organizations | **PRESERVE** — Multi-tenant boundary and brand identities preserved. |
| **Media Storage** | `D:\postpilot\data\images` | **PRESERVE** — Zero files deleted, path traversal protections enforced. |
| **Worker Safeguards** | `POSTPILOT_PUBLISHING_ENABLED=0` | **ENFORCE** — Master publishing switch remains strictly disabled. |

