# Compliance IQ

Compliance IQ is a production-oriented compliance platform built with **FastAPI** (ASGI), SQLAlchemy, Jinja templates, and static assets.

> **Entrypoint inspection result:** this repository does **not** contain a Flask app object. The correct production entrypoint is `app.main:app` (FastAPI ASGI app).

## Key production features

- Session auth + SSO bridge (`/sso/login`)
- RBAC (`admin`, `compliance_manager`, `auditor`, `reviewer`)
- Compliance assessments and CSV export
- Regulation freshness and sync checks
- Remediation tasks + SLA breach view
- Audit logs, encrypted remediation evidence, backup operation endpoint
- Health endpoint: `GET /health`

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Render deployment (step-by-step)

### 1) Push this repo to GitHub

Commit and push your branch to a GitHub repository.

### 2) Create a new Web Service on Render

- Render Dashboard → **New** → **Web Service**
- Connect your GitHub repo
- Branch: choose your deployment branch

### 3) Configure build/start commands

Use exactly:

- **Build Command**
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**
  ```bash
  gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:$PORT app.main:app
  ```

These are also captured in `render.yaml` and `Procfile`.

### 4) Set required environment variables

From `.env.example`, set at least:

- `SESSION_SECRET` (strong random value)
- `APP_ENCRYPTION_KEY` (base64-url-safe 32-byte key)
- `DATABASE_URL` (Render Postgres recommended)

Optional:

- `BACKUP_SOURCE_FILE`
- `BACKUP_DIR`

### 5) Database recommendation for production

Use **Render Postgres** and set `DATABASE_URL` to the Postgres connection string.
Do not rely on local sqlite file persistence for production web instances.

### 6) Deploy

Click **Create Web Service**. Render will:

1. run build command,
2. run start command,
3. provide a live URL.

### 7) Verify health

Open:

- `https://<your-render-service>.onrender.com/health`

Expected:

```json
{"status":"ok", ...}
```

## Files added for deployment

- `render.yaml`
- `Procfile`
- `.env.example`

## Runtime validation in this environment

- `python -m compileall app tests migrations` ✅
- `pip install -r requirements.txt` ❌ blocked by proxy/network restrictions in this environment
- `pytest -q` ❌ blocked here because dependencies could not be installed
