# LifeOS API

The API gives each account its own workspace. Passwords are hashed with
Argon2; short-lived access tokens stay in frontend memory, and rotating refresh
tokens are stored as hashes and sent in an HttpOnly, SameSite=Strict cookie.
Workspace reads and writes are scoped to the authenticated user.

## Run locally

From the project root, in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Replace `SECRET_KEY` in `.env` with a fresh value from:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then start the API and (in a second terminal) serve the frontend:

```powershell
uvicorn main:app --reload
```

```powershell
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500` (use `localhost` for both services so the local
HttpOnly refresh cookie remains same-site). The API health check and
interactive docs are at `http://localhost:8000/api/health` and
`http://localhost:8000/docs`.

The local default database is SQLite (`backend/lifeos.db`). To use PostgreSQL,
set `DATABASE_URL` to a PostgreSQL connection URL, for example
`postgresql+psycopg://lifeos:password@localhost:5432/lifeos`.

## Before production

Use PostgreSQL, HTTPS, a unique secret held in a secrets manager, and set
`APP_ENV=production` and `COOKIE_SECURE=true`. Set `FRONTEND_ORIGINS` to only
the deployed frontend origins. Add database migrations, email verification,
account recovery, authentication rate limiting, backups, monitoring, and
deployment-level request limits before accepting real users or sensitive data.
Prefer deploying the frontend and API on the same site (for example
`app.example.com` and `api.example.com`). For different sites (for example
separate Vercel and Render domains), set `COOKIE_SAMESITE=none`; the API
requires `COOKIE_SECURE=true` for this setting, and the frontend must send
credentialed requests over HTTPS. Some browsers restrict third-party cookies,
so a custom same-site domain or reverse proxy is preferable.
The current API creates its initial tables at startup and is a development MVP,
not a production-hardened service.
