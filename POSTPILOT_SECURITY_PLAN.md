# POSTPILOT SECURITY, PRIVACY & COMPLIANCE PLAN
**Phase 0 — Security Architecture & Hardening Standards**  
**Jurisdictions in Scope:** Republic of Albania (NIPT: `M62118505B`) & India (DPDP Act)  
**Security Standard:** Zero-Trust, Least Privilege, Fail-Closed

---

## 1. Security Mandate & Guiding Policies

The transformation of PostPilot into a Growth & Intelligence Command Center introduces external data ingestion pipelines, technical website crawling, and lead management. To protect system integrity and client privacy, the following zero-compromise security controls are strictly enforced across all components.

---

## 2. Core Security Pillars

### 2.1 Principle of Least Privilege & Read-Only Access
- **Google Analytics 4:** Only the read-only scope `https://www.googleapis.com/auth/analytics.readonly` is permitted. PostPilot will never request or accept edit, admin, or user management permissions.
- **Google Search Console:** Only the read-only scope `https://www.googleapis.com/auth/webmasters.readonly` is permitted. PostPilot will never request site ownership verification or sitemap submission write rights.
- **Bing Webmaster Tools:** Read-only rank and traffic queries only.
- **First-Party Analytics (Umami):** Read-only viewing tokens.

### 2.2 Cryptographic Credential Protection at Rest & in Transit
- **No Secrets in Source Control:** `.env`, `.env.backup`, JSON service account credentials, private keys, and token files are strictly barred from Git via `.gitignore`.
- **Database Encryption at Rest:** OAuth refresh tokens, API keys, and third-party secrets stored in `social_accounts` or `growth_properties` are symmetrically encrypted using AES-128-CBC / Fernet encryption (`cryptography.fernet`) with a master encryption key derived from `SECRET_KEY`.
- **In-Transit Encryption:** All communications with third-party APIs (Google, Bing, Meta, LinkedIn, Groq) use TLS 1.3 with strict certificate validation.

### 2.3 Zero-Leakage Telemetry & Logging
- **Sanitized Exception Logging:** In accordance with established PostPilot security standards (enforced by `test_channel_runner.py`), exception handlers must filter out authorization headers, bearer tokens, API keys, query string secrets, and password hashes before logging to disk or sending to error loggers.
- **Sanitized API Responses:** Endpoint responses must never serialize raw tokens, hashed passwords, or private service account credentials. Sensitive columns are excluded at the SQL query projection level.

### 2.4 Multi-Tenant Boundary Enforcement
- **Dual-Key Scoping:** Every database query in the Growth modules must enforce both `organization_id = session['organization_id']` and `property_id = ...`.
- **Cross-Tenant Prohibition:** It is cryptographically impossible for an administrator of Organization A to view, query, or crawl properties, leads, keywords, or analytics belonging to Organization B.

### 2.5 Server-Side Request Forgery (SSRF) & Crawler Guardrails
- **Restricted Crawl Targets:** The Technical SEO Crawler (`seo_crawler.py`) will only crawl domains explicitly registered in `growth_properties` that match approved Gaatha domain patterns (`*.gaatha.tech`, `*.aidni.global`).
- **Loopback & Private Network Banning:** The crawler strictly rejects and drops requests attempting to target:
  - `127.0.0.1` / `localhost` / `::1`
  - Private RFC-1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
  - Cloud metadata services (`169.254.169.254`)
  - Internal Docker container names (`gaathaai-backend`, `phoenix-app`, etc.)
- **Polite Crawling Concurrency:** Fixed at 1 concurrent request per target domain with a mandatory 500ms sleep between GET requests.

### 2.6 Inbound Webhook Defense & HMAC Verification
- **WhatsApp Webhook:** Enforces HMAC-SHA256 signature verification in the `X-Hub-Signature-256` header using `WHATSAPP_APP_SECRET`.
- **Lead Webhook (`/api/webhooks/leads`):** Enforces HMAC-SHA256 signature verification in the `X-PostPilot-Signature` header using `LEAD_WEBHOOK_SECRET`.
- **Timing Attack Mitigation:** Constant-time comparison (`hmac.compare_digest`) is strictly utilized on all signature checks.

### 2.7 Fail-Closed Publishing Safeguards
- **Master Publishing Lock:** `POSTPILOT_PUBLISHING_ENABLED=0` remains strictly active.
- **WhatsApp Publishing Lock:** `WHATSAPP_PUBLISHING_ENABLED=0` remains strictly active.
- **Worker Isolation:** The background worker will continue to refuse to claim or dispatch any live post while these switches remain 0.

---

## 3. Regulatory Compliance & Data Governance

### 3.1 EU & Albanian Data Protection Compliance (GAATHA Ventures Sh.P.K.)
- **Entity:** GAATHA Ventures Sh.P.K., Durana Tech Park, Tirana, Albania (NIPT: `M62118505B`).
- **GDPR Alignment:**
  - Cookieless analytics paradigm via Umami (no personal tracking cookies placed on visitors' machines).
  - Data minimization: Only aggregated, anonymized metrics (page counts, country-level aggregates) are retained in PostPilot.
  - Right to be Forgotten: CRM Lead desk supports one-click cryptographic erasure of individual lead records upon formal DPO request.

### 3.2 Indian Digital Personal Data Protection (DPDP) Act Compliance (Aidni Global LLP)
- **Entity:** Aidni Global LLP (India).
- **Lead Information Governance:**
  - Contact information collected through Phoenix partner desks or website forms is stored exclusively on authorized multi-tenant storage with audit logs tracking which user viewed or exported lead contact details.
  - Opt-out enforcement: WhatsApp suppression lists automatically bar outbound messaging to any user requesting opt-out.

