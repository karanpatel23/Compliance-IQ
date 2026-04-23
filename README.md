# Compliance IQ

Compliance IQ is a production-oriented compliance platform built with **FastAPI** (ASGI), SQLAlchemy, Jinja templates, and static assets.

> **Entrypoint inspection result:** there is no Flask app in this repo. The correct deploy entrypoint is `app.main:app`.

## Why Render dependency install failed (root cause)

Your failure (`maturin`, `cargo`, read-only `/usr/local/cargo`) is caused when pip cannot find a compatible wheel and falls back to building Rust-backed dependencies from source.

In this repo, the main Rust-triggering risk was:

- `passlib[bcrypt]` → pulls `bcrypt` (Rust-backed build path via `maturin` when no wheel is available for the runtime).

To make Render installs reliable, this repo now:

1. Removes `passlib[bcrypt]` extra and uses `passlib` with `pbkdf2_sha256` only.
2. Pins Python to **3.11.11** (`render.yaml` + `runtime.txt`) for broad wheel compatibility.
3. Keeps `app.main:app` with Gunicorn+Uvicorn worker for ASGI production startup.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Render deployment (step-by-step)

### 1) Push to GitHub

Push this branch to your GitHub repo.

### 2) Create Render Web Service

- Render Dashboard → **New** → **Web Service**
- Connect repo + branch

### 3) Use these commands

- **Build Command**
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command**
  ```bash
  gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:$PORT app.main:app
  ```

(Also present in `render.yaml` and `Procfile`.)

### 4) Set environment variables

Required:

- `SESSION_SECRET`
- `APP_ENCRYPTION_KEY`
- `DATABASE_URL` (Render Postgres recommended)

Optional:

- `BACKUP_SOURCE_FILE`
- `BACKUP_DIR`

### 5) Deploy and verify

- Deploy in Render
- Open: `https://<your-service>.onrender.com/health`
- Expected JSON contains `"status": "ok"`

## Production files

- `render.yaml`
- `Procfile`
- `.env.example`
- `runtime.txt`

## Runtime validation in this environment

- `python -m compileall app tests migrations` ✅
- `pip install -r requirements.txt` ❌ blocked by proxy/network restrictions in this environment
- `pytest -q` ❌ blocked here because dependencies could not be installed
