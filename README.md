# Compliance IQ

Compliance IQ is a production-oriented manufacturing compliance platform with:

- Enterprise-ready authentication patterns (session auth + SSO bridge)
- Role-based access control (admin, compliance_manager, auditor, reviewer)
- Verified regulatory intelligence with freshness gating
- Compliance assessments, findings, and report export
- Remediation task workflow with SLA breach tracking
- Audit logging, encrypted evidence storage, and backup operations

## Completed production-readiness steps

### 1) Enterprise SSO + RBAC

- SSO bridge endpoint: `GET /sso/login` (for IdP/reverse-proxy header integration)
- Role control endpoint: `PATCH /admin/users/{user_id}/role`
- Role checks enforced on sensitive endpoints (facilities, regulations, assessments, ops)

### 2) Migrations + managed DB readiness

- `DATABASE_URL` environment variable support for managed databases (e.g., PostgreSQL)
- Migration bootstrap folder: `migrations/001_initial_schema.sql`

### 3) Audit, encryption, and backup controls

- Immutable-style audit events stored in `audit_logs`
- Remediation evidence encrypted/decrypted using Fernet helpers (`app/security.py`)
- Operational backup endpoint `POST /ops/backup` with checksums and records

### 4) Regulation update automation

- Source metadata sync endpoint: `POST /regulations/sync/check`
- Per-regulation sync history in `regulation_sync_logs`

### 5) Remediation SLA workflows

- Create remediation tasks: `POST /remediations`
- Close tasks: `POST /remediations/{id}/complete`
- SLA breach visibility: `GET /remediations/sla/breaches`

## UI pages

- `/` home
- `/signup` sign-up
- `/signin` sign-in
- `/dashboard` KPI dashboard
- `/tool` full workspace details

## Core API summary

- Facilities: `POST /facilities`
- Regulations: `GET /regulations`, `POST /regulations`, `POST /regulations/{id}/reviews`, `GET /regulations/stale`, `POST /regulations/sync/check`
- Assessments: `POST /assessments/run`, `GET /reports/assessment/{id}/csv`
- Remediation: `POST /remediations`, `GET /remediations`, `POST /remediations/{id}/complete`, `GET /remediations/sla/breaches`
- Ops: `POST /ops/backup`, `GET /ops/audit-logs`

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SESSION_SECRET='replace-me'
# Fernet key for encryption (base64-url-safe 32-byte key)
export APP_ENCRYPTION_KEY='MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY='
uvicorn app.main:app --reload
```

## Environment variables

- `DATABASE_URL` (default: `sqlite:///./compliance_iq.db`)
- `SESSION_SECRET`
- `APP_ENCRYPTION_KEY`
- `BACKUP_SOURCE_FILE` (default: `./compliance_iq.db`)
- `BACKUP_DIR` (default: `./backups`)

## Runtime validation in this environment

- `python -m compileall app tests` ✅
- `pip install -r requirements.txt` ❌ blocked by proxy/network restrictions in this environment
- `pytest -q` ❌ blocked here because dependencies could not be installed
