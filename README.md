# LifeOS — Your Personal Life Management System

LifeOS is a multi-user personal management app designed to bring everyday
planning and personal reflection into one place. Instead of keeping tasks,
habits, appointments, goals, notes, finances, and wellness records in separate
tools, LifeOS gives each account a private workspace and connects activity
across those areas.

> **Project status:** LifeOS is an early-stage MVP for local development and
> evaluation. It is not yet ready to host publicly or to store sensitive
> real-world data. See [Production readiness](#production-readiness).

## What you can do

### Organize your day

- **Task manager:** Create, edit, complete, and prioritize tasks; assign a due
  date and category; and organize work in a board or list. Daily and weekly
  recurring tasks are supported.
- **Calendar:** Add appointments and time blocks, and move between day, week,
  and month views. Tasks with deadlines can also be scheduled from the
  calendar.
- **Daily briefing:** See a short, rule-based overview of items that may need
  attention: overdue and upcoming tasks, today's appointments, habit check-ins,
  and goals near their target date or without recent progress. It is a helpful
  prompt, not an AI-generated recommendation.

### Build routines and make progress

- **Habits:** Track daily or weekly check-ins, review streaks, and see recent
  consistency in a calendar-style activity grid.
- **Goals:** Set a target date, break a goal into milestones, and record
  completed steps.
- **Unified activity timeline:** Review completed tasks, habit check-ins,
  journal entries, appointments, completed milestones, wellness check-ins, and
  finance transactions together. Filter by activity type and open the
  corresponding area of the app.

### Keep personal records

- **Notes and journal:** Capture notes, organize them by category, pin
  important items, and search your collection. Journal-category notes appear
  in the activity timeline.
- **Finance:** Record income and expenses, organize transactions by category,
  and keep monthly category budgets.
- **Wellness:** Log mood, sleep, movement, and a short note. The wellness view
  summarizes recent check-ins.
- **Life analytics:** Review summaries and trends based on the information
  recorded in your workspace.

## Project structure

```text
LifeOS/
├── backend/
│   ├── main.py             # FastAPI app, authentication, and workspace API
│   ├── tests/              # Backend API tests
│   ├── .env.example        # Local configuration template
│   ├── requirements.txt    # Backend dependencies
│   └── README.md           # Backend setup and deployment notes
├── frontend/
│   └── index.html          # LifeOS interface and browser-side app logic
└── README.md
```

The frontend is a standalone HTML, CSS, and JavaScript app. The backend is a
Python FastAPI service using SQLAlchemy. SQLite is the local default, and the
backend can be configured to use PostgreSQL. Charts and summaries are generated
from the user's workspace data.

## Run locally

You will need Python installed. Run the API and frontend in separate
PowerShell terminals.

### 1. Set up and start the backend

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `backend/.env` and set `SECRET_KEY` to a new random value. You can generate
one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then start the API from the `backend` directory:

```powershell
uvicorn main:app --reload
```

The API uses `http://localhost:8000` by default. Its health check and
interactive API documentation are available at
[`http://localhost:8000/api/health`](http://localhost:8000/api/health) and
[`http://localhost:8000/docs`](http://localhost:8000/docs).

### 2. Serve the frontend

In a second terminal, from the project root:

```powershell
cd frontend
python -m http.server 5500
```

Open [`http://localhost:5500`](http://localhost:5500), create an account, and
start adding your own data. Use `localhost` for both the frontend and API
addresses so the local refresh cookie works as intended.

The development database is created as `backend/lifeos.db` when the API starts.
It is not necessary to create it manually.

### Other platforms

The commands above use PowerShell and Windows virtual-environment activation.
On macOS or Linux, activate the environment with:

```sh
source .venv/bin/activate
```

Use your platform's equivalent copy command to create `.env` from
`backend/.env.example`.

## Run backend tests

From the project root with the backend virtual environment activated:

```powershell
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests
```

The tests cover authentication, session handling, request-origin checks,
workspace validation, and isolation between accounts.

## Deploy a free demo on Render

The repository includes a Render Blueprint in [`render.yaml`](./render.yaml).
It creates a free Python web service and a new free PostgreSQL database in
Oregon. The web service serves both the frontend and API from one HTTPS
address, so the browser can use same-origin requests for sign-in and workspace
data.

1. Push the project to the `main` branch of the GitHub repository connected to
   Render.
2. Sign in to the [Render Dashboard](https://dashboard.render.com/).
3. Choose **New** → **Blueprint** and select the `timelesslady05/LifeOS`
   repository and `main` branch.
4. Review the resources from `render.yaml` and approve creation of the web
   service and PostgreSQL database.
5. Wait for the database and service to finish deploying. Open the web
   service's `onrender.com` URL to register an account and try the app. Check
   the service's **Logs** if the deploy or health check fails.

The Blueprint generates a production secret and connects the API to the new
database automatically. It does not use or change any other Render database.
If the `lifeos-api` or `lifeos-db` resource names are already taken in your
Render workspace, rename them in `render.yaml` before creating the Blueprint.

**Free-tier limitations:** free web services sleep after 15 minutes without
traffic and can take about a minute to wake up. A free Render Postgres database
expires 30 days after creation. Its data is not suitable for long-term storage;
upgrade to a persistent paid database before relying on the deployed app for
personal records. Free Render services are for demos and testing, not
production use.

## Accounts and data

- Each account has its own workspace. The API scopes workspace reads and writes
  to the authenticated user.
- Passwords are hashed with Argon2; they are not stored as plain text.
- Short-lived access tokens are held in frontend memory. Refresh tokens rotate
  and are sent in an HttpOnly cookie; only their hashes are stored by the API.
- Workspace data is stored by the backend, not in browser local storage.
- The timeline and briefing are currently derived from the data already in the
  workspace; they do not have a separate timeline or AI service.

## Configuration

The backend reads configuration from `backend/.env`. Common settings include:

| Setting | Purpose |
| --- | --- |
| `APP_ENV` | Runtime environment. Use `production` only with production safeguards configured. |
| `SECRET_KEY` | Secret used to sign access tokens. Keep it private and use a unique value. |
| `DATABASE_URL` | Database connection string. Defaults to a local SQLite database. |
| `FRONTEND_ORIGINS` | Comma-separated list of frontend origins permitted to call the API. |
| `COOKIE_SECURE` | Requires HTTPS for the refresh cookie when enabled. |
| `COOKIE_SAMESITE` | Refresh-cookie site policy: `strict`, `lax`, or `none`. |

For PostgreSQL, set `DATABASE_URL` to your PostgreSQL connection URL. Do not
commit `.env`, credentials, or production secrets.

## Current scope and next steps

LifeOS currently provides account registration and login, a private workspace,
the core life-management modules, the unified timeline, and the rule-based
briefing. The briefing is intentionally rule-based for now; AI-generated
summaries are not included.

Before a public launch, the service still needs production-focused work such as
email verification, password recovery, authentication rate limiting, database
migrations, reliable backups, monitoring, and deployment request limits.
Additional setup guidance is in [backend/README.md](./backend/README.md).
