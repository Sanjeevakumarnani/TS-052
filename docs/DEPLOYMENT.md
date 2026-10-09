# InfraPulse Deployment Guide

## Local run (recommended first)

### Backend

```bash
cd backend
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend docs: `http://127.0.0.1:8000/docs`; health: `http://127.0.0.1:8000/health`.

### Frontend

Open another terminal:

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`. The web app needs access to the backend and an internet connection for OpenStreetMap tiles and remote fonts; the data table remains the fallback if map tiles fail.

Windows setup helpers: run `scripts\setup-windows.bat`, then `scripts\start-infrapulse-windows.bat`. Node and Python must be installed first.

## Deploy API to Render

1. Push the project folder to a Git repository.
2. Create a Render Blueprint or Web Service from the repo. `render.yaml` is included as a starting point; review the service settings before creating it.
3. The service root should be `backend`; build command `pip install -r requirements.txt`; start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. Set `CORS_ORIGINS` to the exact frontend origin after the frontend is deployed, for example `https://your-app.vercel.app`. Include local origins only if still needed.
5. Check `https://YOUR-API/health` and `https://YOUR-API/docs`.

## Deploy frontend to Vercel

1. Import the same repository into Vercel.
2. Set Root Directory to `frontend`.
3. Build command `npm run build`; output directory `dist` (the included `vercel.json` is a project-level starter and may need to be placed/adjusted for the selected root-directory setting).
4. Add environment variable `VITE_API_BASE_URL=https://YOUR-API.onrender.com` before building.
5. Redeploy, then add the final Vercel origin to the API's `CORS_ORIGINS` variable and redeploy the API.
6. Test dashboard, map, detail, ranking, scenario, CSV import/export and field report in the deployed browser.

## Important persistence warning

The current backend uses SQLite at `backend/data/infrapulse.sqlite3` and seeds synthetic records from `backend/data/villages.json`. This is appropriate for local demonstration. A typical ephemeral app filesystem may lose SQLite writes on redeploy/restart. For a sustained public deployment, migrate to a managed PostgreSQL database, add backups and authentication for imports/admin tools, and review user-submitted report privacy.

## Data warning

All seeded metrics and coordinates are simulated. Do not present them as official measurement or verified village locations. Imported CSV rows are marked as unverified. Before real-world use, confirm the source, licence, spatial resolution, timestamp, indicator definition and measurement method for each field.
