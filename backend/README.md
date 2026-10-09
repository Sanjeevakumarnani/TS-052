# InfraPulse Backend

FastAPI API for the InfraPulse rural infrastructure reliability prototype.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation and `http://127.0.0.1:8000/health` for the health check.

The SQLite database is created at `backend/data/infrapulse.sqlite3` on first start from the synthetic fixture. Deleting that file resets to seed demo data.

## CSV import schema

Required columns: `id,name,district,latitude,longitude,population,digital_score,electricity_score,road_score,public_digital_score,essential_services_score`.

Optional columns: `state,block,digital_availability,criticality,alternative_access`. All scores must be 0–100. Uploaded records are marked **UPLOADED DATA — NOT INDEPENDENTLY VERIFIED**.

## Tests

From `backend/`: `python -m pytest -q` (install `pytest` first if needed).
