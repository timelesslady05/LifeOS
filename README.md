# LifeOS

LifeOS is a personal life-management app with a standalone frontend and an
account-aware FastAPI backend. Each account has a private workspace that is
stored by the API, rather than in browser local storage.

The dashboard includes a rule-based daily briefing for deadlines, today's
calendar, habit check-ins, and goals that need attention. The activity timeline
brings completed tasks, habit check-ins, journal entries, appointments,
milestones, wellness logs, and finance transactions together, with filters and
links back to their modules.

## Run locally

1. Follow [backend setup](./backend/README.md) to create the Python environment,
   configure a secret, and start the API.
2. In another terminal, serve `frontend/`:

   ```powershell
   cd frontend
   python -m http.server 5500
   ```

3. Open `http://localhost:5500`, create an account, and add your own data.

For backend tests, install `backend/requirements-dev.txt` and run
`python -m pytest backend/tests` from the project root.

This is an early multi-user MVP, not yet ready for public production. See the
backend README for required production safeguards.
