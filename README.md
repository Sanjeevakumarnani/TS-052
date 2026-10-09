# InfraPulse — Rural Infrastructure Reliability Intelligence

A runnable MVP for SDG 9. InfraPulse aims to show the difference between infrastructure availability and reliable service, identify villages needing review, explain ranking factors and compare hypothetical interventions.

## What is included

- React/Vite frontend with dashboard, Leaflet map explorer, village profile drawer, priority ranking, scenario simulator, methodology and source pages.
- FastAPI backend with versioned REST endpoints.
- SQLite persistence seeded with clearly labelled synthetic demonstration records.
- Weighted reliability score with data-coverage handling.
- Availability–reliability gap calculation where comparable values exist.
- Explainable priority heuristic and non-destructive what-if scenarios.
- CSV export and CSV import with field validation; imported data is marked unverified.
- Optional field-observation report endpoint and UI.
- Backend unit tests and original PRD/architecture/tasks PDFs under `docs/`.

## Important data notice

**The included village scores, population figures, and map pins are synthetic demo data. They do not represent measured conditions or verified village locations.** District names are used only as illustrative regional context. Do not present these values as official data. Scenario results are calculations from user-supplied assumptions, not causal forecasts or confirmed investment recommendations.

## Run locally

Requirements: Python 3.10+ and Node.js 20+.

### 1. Start the backend

Linux/macOS:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Windows PowerShell:
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: `http://127.0.0.1:8000/docs`  
Health check: `http://127.0.0.1:8000/health`

### 2. Start the frontend in a second terminal

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

### 3. Verification Workflow Configuration & Roles

#### First Admin User Setup
You can bootstrap an administrator either via environment variables or registration:
- **Auto-bootstrap**: Define `ADMIN_BOOTSTRAP_USERNAME` and `ADMIN_BOOTSTRAP_PASSWORD` in `backend/.env`. On startup, this admin account is automatically created.
- **Manual Registration**: Navigate to `/auth` on the frontend or send `POST /api/v1/auth/register` with `"role": "admin"`.

#### Camera & Geolocation (HTTPS / Localhost Requirements)
- Browser APIs (`navigator.mediaDevices.getUserMedia` and `navigator.geolocation`) require a **Secure Context** (`https://` or `http://localhost`).
- When accessing the app locally via `http://localhost:5173` or `http://127.0.0.1:5173`, modern browsers grant camera and GPS permissions seamlessly.
- For mobile testing across local networks (e.g. testing phone camera on a LAN IP), enable HTTPS or test via desktop browser emulation.

#### AI Vision Setup (Google Gemini)
- InfraPulse incorporates server-side vision AI for citizen photo submissions.
- Set `GEMINI_API_KEY` in `backend/.env` with your Google AI Studio key.
- If unconfigured, the system returns an honest `not_configured` fallback without failing submissions or inventing fake results.
- Model defaults to `gemini-1.5-flash` with a 25-second timeout (`VISION_AI_MODEL` and `VISION_AI_TIMEOUT`).

### One-command helper (Linux/macOS)

From the project root, run `bash scripts/run-dev.sh`. This installs nothing automatically; backend and frontend dependencies must already be installed as shown above. It starts both processes in one terminal session.

## Run tests

```bash
cd backend
pip install pytest httpx
python -m pytest -q
```

## Use the app

1. **Overview:** inspect sample metrics and highest-priority demo villages.
2. **Map explorer:** search/filter villages and open any village profile.
3. **Village profile:** inspect dimensions and availability–reliability gaps; submit a non-personal field observation.
4. **Priority ranking:** compare the transparent heuristic and its factor drivers.
5. **Scenario lab:** choose a village, choose a dimension, set a hypothetical post-intervention score, and calculate score change. The baseline is not modified.
6. **Methodology & data:** review dimension weights, thresholds, source references and limitations.
7. **Export CSV:** export filtered rows with score and provenance fields.
8. **Import CSV:** follow the schema below. Uploaded rows are unverified.

Community reports are unverified by default and do not change village scores. A submission returns an opaque status reference; keep it private and use it with the status endpoint or the in-app "Report status" page. Public report listings intentionally omit report descriptions and private reference codes. Reviewers can authenticate via `REVIEWER_TOKEN` to triage and moderate submitted reports. See [docs/COMPLETION_AUDIT.md](docs/COMPLETION_AUDIT.md) for verification status and audit details.

## CSV import schema

Required columns:
`id,name,district,latitude,longitude,population,digital_score,electricity_score,road_score,public_digital_score,essential_services_score`

Optional columns:
`state,block,digital_availability,criticality,alternative_access`

Scores must be 0–100. Latitude must be -90 to 90 and longitude -180 to 180. Example CSV is `backend/data/import_template.csv`. Imports support a two-step preview-before-confirm workflow with permanent import history logging.

## API overview

- `GET /health`
- `GET /api/v1/summary`
- `GET /api/v1/villages`
- `GET /api/v1/villages/{village_id}`
- `GET /api/v1/map`
- `GET /api/v1/rankings`
- `GET /api/v1/methodology`
- `GET /api/v1/sources`
- `POST /api/v1/scenarios`
- `POST /api/v1/field-reports`
- `GET /api/v1/field-reports`
- `GET /api/v1/field-reports/status/{reference_code}`
- `GET /api/v1/reviewer/reports` *(requires Bearer token)*
- `POST /api/v1/reviewer/reports/{reference_code}/moderate` *(requires Bearer token)*
- `GET /api/v1/export.csv`
- `POST /api/v1/imports/csv/preview`
- `POST /api/v1/imports/csv/confirm`
- `GET /api/v1/imports/history`
- `POST /api/v1/imports/csv` *(legacy single-step)*

## Scoring model

Dimension weights: digital connectivity 25%, electricity 20%, roads 20%, public digital infrastructure 15%, essential-service access 20%. These are configurable prototype assumptions, not official standards. The overall score is the weighted mean of valid dimensions, provided at least 60% of total weight has valid input. Missing values do not silently become zero.

Availability–reliability gap = availability score − reliability score, only where the two indicators are provided on a comparable 0–100 scale. Priority heuristic uses 35% infrastructure deficit, 25% population factor, 25% service criticality, and 15% lack of alternatives. These weights are illustrative and should be reviewed and validated with stakeholders before operational use.

## Research positioning

Existing platforms such as Gram Manchitra and Mission Antyodaya already provide rural GIS, infrastructure indicators and gap-analysis context; BharatNet addresses rural broadband infrastructure; TRAI MySpeed offers network quality measurements; and the World Bank Rural Access Index addresses rural access to all-season roads. InfraPulse must not claim these domains are entirely new. The prototype contribution is the integrated, provenance-aware workflow joining multi-sector service reliability, explicit availability-performance gaps, explainable prioritization, and scenario comparisons.

## Reset demo database

Stop the backend, delete `backend/data/infrapulse.sqlite3`, and restart the API. It will re-seed from `backend/data/villages.json`.

## Deployment notes

The frontend and API can be deployed separately. Set `VITE_API_BASE_URL` to the deployed API URL and configure FastAPI CORS for the exact deployed frontend origin before launch. Use a managed persistent database for production; the default SQLite file is intended for local demo use. Verify all public datasets, licensing, API availability, and data granularity before connecting them.

## Configuration and deployment

- Backend CORS is controlled by `CORS_ORIGINS`, a comma-separated list. Local defaults are `http://localhost:5173,http://127.0.0.1:5173`. Add the exact deployed frontend origin in the hosting provider's environment settings.
- Frontend API origin is controlled by `VITE_API_BASE_URL` in `frontend/.env` (for example `http://127.0.0.1:8000`). Vite embeds this value at build time.
- A Render Blueprint starting point is provided in `render.yaml`. Review the service settings and set `CORS_ORIGINS` after deploying the frontend. The default SQLite database is suitable for demonstration only; use a persistent managed database and backups for production.
- OpenStreetMap map tiles and the optional Google Fonts import require a network connection. If map tiles are unavailable, use the village table and profiles; the map pins themselves are illustrative, synthetic points.

## Frontend build validation note

The frontend source uses the package versions listed in `frontend/package.json`. In the creation environment, npm dependency installation could not reach `registry.npmjs.org` because DNS lookup failed. The backend and API tests were executed locally; the frontend production build must be run after dependencies can be installed with `npm install`.
