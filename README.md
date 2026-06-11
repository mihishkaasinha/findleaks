# FINDLEAKS — Exam Integrity Platform

Detect exam paper leaks across Twitter/X, Telegram, and manual photo uploads using OCR + semantic similarity.

---

## Quick Start (Docker Compose)

```bash
cp .env.example .env          # fill in all values
docker compose up --build
```

- Frontend: http://localhost
- Backend API: http://localhost:8000/api
- Health: http://localhost:8000/api/health

---

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

cp ../.env.example .env         # fill in values
uvicorn app:create_app --factory --reload --port 8000
```

#### Run tests

```bash
cd backend
pytest tests/ -q
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # Vite dev server on :5173 (proxies /api → :8000)
```

#### Run tests

```bash
cd frontend
npm test -- --run
```

---

## Deployment

### Railway (backend)

1. Connect repo to Railway
2. Set root directory to `backend/`
3. Set all env vars from `.env.example` in Railway dashboard
4. Railway auto-detects the `Procfile` and deploys

### Supabase (database)

1. Create a Supabase project
2. Copy **Connection String (Transaction mode)** from Settings → Database
3. Set `DATABASE_URL=postgresql+asyncpg://...` in Railway env vars

### Netlify / Vercel (frontend)

```bash
cd frontend
npm run build
# upload dist/ to Netlify / set VITE build command in Netlify UI
```

Set `VITE_API_BASE=/api` or configure the Vite proxy for your domain.

---

## Environment Variables

See `.env.example` for the full list. Required variables:

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret (min 32 chars) |
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `TWITTER_BEARER_TOKEN` | Twitter/X API v2 Bearer Token |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_USER` | SMTP username / sender address |
| `SMTP_PASS` | SMTP password |

---

## Architecture

```
frontend/          React + Vite + Tailwind
backend/
  app.py           FastAPI application factory
  findleaks/
    config.py      Pydantic settings
    database.py    SQLAlchemy async engine
    models.py      ORM models (Exam, Question, Leak, Alert, ScannerStatus, User)
    schemas.py     Pydantic v2 request/response models
    auth.py        JWT + bcrypt utilities
    ingestion.py   PDF/image → questions → FAISS index
    detector.py    OpenCV → OCR → FAISS search → confidence
    alerts.py      Email (aiosmtplib) + webhook + SMS
    scanners/
      base.py      BaseScanner ABC
      twitter.py   tweepy v2 polling scanner
      telegram.py  python-telegram-bot async scanner
    routers/
      auth.py      POST /auth/login, /logout, GET /auth/me
      exams.py     CRUD + upload + SSE progress + scan
      leaks.py     GET/PATCH leaks
      alerts.py    GET alert log
      scanners.py  GET/start/stop/patch scanners
      health.py    GET /health (public)
```

---

## Test Coverage

| Suite | Tests | Status |
|---|---|---|
| Backend unit | 98 | ✅ |
| Backend integration | 48 | ✅ |
| Frontend unit | 11 | ✅ |
| Security validation | 13 | ✅ |
| **Total** | **170** | **✅** |
