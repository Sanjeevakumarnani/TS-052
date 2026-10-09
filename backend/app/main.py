import csv
import hashlib
import io
import json
import math
import secrets as _secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, List, Optional
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from . import auth, db, geography
from . import ai_vision
from . import config as _config
from .config import (
    API_VERSION,
    ATTACHMENTS_DIR,
    CORS_ORIGINS,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_REPORTS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from .domain import DIMENSION_LABELS, WEIGHTS, calculate_score, enrich_village, simulate


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    auth.bootstrap_admin()
    yield


app = FastAPI(
    title="InfraPulse API",
    version=API_VERSION,
    description="Rural Infrastructure Reliability Intelligence & Village Verification Workflow API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# In-memory rate limiters
# ---------------------------------------------------------------------------
_report_timestamps: dict[str, list[float]] = defaultdict(list)
_login_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    _report_timestamps[ip] = [t for t in _report_timestamps[ip] if t > window_start]
    if len(_report_timestamps[ip]) >= RATE_LIMIT_REPORTS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many report submissions. Limit: {RATE_LIMIT_REPORTS} per {RATE_LIMIT_WINDOW_SECONDS}s window.",
        )
    _report_timestamps[ip].append(now)


def _check_login_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - 900  # 15 minutes window
    _login_timestamps[ip] = [t for t in _login_timestamps[ip] if t > window_start]
    if len(_login_timestamps[ip]) >= RATE_LIMIT_LOGIN:
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts. Please try again later.",
        )
    _login_timestamps[ip].append(now)


# ---------------------------------------------------------------------------
# Legacy Reviewer Bearer Check (Preserved for backward compatibility)
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)


def require_reviewer(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """Validate Bearer token against REVIEWER_TOKEN env var. Returns reviewer identity string."""
    if not _config.REVIEWER_TOKEN:
        raise HTTPException(
            status_code=501,
            detail="Reviewer authentication is not configured on this server. Set the REVIEWER_TOKEN environment variable.",
        )
    if credentials is None or credentials.credentials != _config.REVIEWER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing reviewer token.")
    return "reviewer"


# ---------------------------------------------------------------------------
# Core Helpers
# ---------------------------------------------------------------------------
def _all():
    return [enrich_village(v) for v in db.list_villages()]


def _filter(villages, district=None, category=None, q=None, dimension=None, min_score=None, max_score=None):
    result = villages
    if district and district.lower() != "all":
        result = [v for v in result if v.get("district", "").lower() == district.lower()]
    if category and category.lower() != "all":
        result = [v for v in result if v["score"]["category"]["key"] == category.lower()]
    if q:
        query = q.lower().strip()
        result = [
            v for v in result
            if query in (v.get("name", "") + " " + v.get("district", "") + " " + v.get("id", "")).lower()
        ]
    if dimension and dimension in WEIGHTS:
        result = [v for v in result if v.get("dimensions", {}).get(dimension, {}).get("score") is not None]
    if min_score is not None:
        result = [v for v in result if v["score"]["overall"] is not None and v["score"]["overall"] >= min_score]
    if max_score is not None:
        result = [v for v in result if v["score"]["overall"] is not None and v["score"]["overall"] <= max_score]
    return result


# ---------------------------------------------------------------------------
# 1. System Health & Baseline Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "infrapulse-api",
        "version": API_VERSION,
        "features": {
            "auth": True,
            "geography": True,
            "development_verification": True,
            "camera_capture": True,
            "ai_vision": bool(_config.GEMINI_API_KEY),
        },
    }


@app.get("/api/v1/summary")
def summary(district: Optional[str] = None):
    villages = _filter(_all(), district=district)
    valid = [v["score"]["overall"] for v in villages if v["score"]["overall"] is not None]
    priority = [v for v in villages if v["priority"]["label"] in ("Critical", "High")]
    large_gaps = [g for v in villages for g in v.get("gaps", []) if g["gap_points"] >= 20]
    dim_avg = {}
    for key, label in DIMENSION_LABELS.items():
        scores = [v["score"]["components"].get(key) for v in villages if v["score"]["components"].get(key) is not None]
        dim_avg[key] = {"label": label, "average": round(sum(scores) / len(scores), 1) if scores else None}
    return {
        "total_villages": len(villages),
        "average_reliability": round(sum(valid) / len(valid), 1) if valid else None,
        "high_priority_count": len(priority),
        "large_gap_count": len(large_gaps),
        "dimension_averages": dim_avg,
        "data_notice": "DEMO DATA — NOT OFFICIAL MEASUREMENTS",
        "methodology_version": "v1",
    }


@app.get("/api/v1/villages")
def villages(
    district: Optional[str] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    dimension: Optional[str] = None,
    min_score: Optional[float] = Query(default=None, ge=0, le=100),
    max_score: Optional[float] = Query(default=None, ge=0, le=100),
    sort: str = "priority",
    order: str = "desc",
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    result = _filter(_all(), district, category, q, dimension, min_score, max_score)
    if sort == "score":
        key = lambda v: -1 if v["score"]["overall"] is None else v["score"]["overall"]
    elif sort == "name":
        key = lambda v: v.get("name", "").lower()
    else:
        key = lambda v: v["priority"]["score"]
    result.sort(key=key, reverse=order.lower() != "asc")
    total = len(result)
    return {
        "items": result[offset : offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
        "data_notice": "DEMO DATA — NOT OFFICIAL MEASUREMENTS",
    }


@app.get("/api/v1/villages/{village_id}")
def village_detail(village_id: str):
    raw = db.get_village(village_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Village not found")
    return enrich_village(raw)


@app.get("/api/v1/map")
def map_geojson(district: Optional[str] = None, category: Optional[str] = None, q: Optional[str] = None):
    feats = []
    for v in _filter(_all(), district=district, category=category, q=q):
        if v.get("latitude") is None or v.get("longitude") is None:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [v["longitude"], v["latitude"]]},
            "properties": {
                "id": v["id"],
                "name": v["name"],
                "district": v["district"],
                "score": v["score"]["overall"],
                "category": v["score"]["category"]["key"],
                "priority": v["priority"]["label"],
                "priority_score": v["priority"]["score"],
                "is_simulated": v["is_simulated"],
            },
        })
    return {
        "type": "FeatureCollection",
        "features": feats,
        "notice": "Illustrative demo pins; not official village boundaries or verified locations.",
    }


@app.get("/api/v1/rankings")
def rankings(limit: int = Query(default=100, ge=1, le=1000)):
    vals = sorted(_all(), key=lambda v: v["priority"]["score"], reverse=True)
    return {"items": vals[:limit], "methodology_note": "Configurable prototype heuristic; not an official allocation rule."}


@app.get("/api/v1/methodology")
def methodology():
    return {
        "version": "v1",
        "weights": WEIGHTS,
        "dimension_labels": DIMENSION_LABELS,
        "categories": [
            {"min": 80, "label": "Highly reliable"},
            {"min": 60, "label": "Adequate"},
            {"min": 40, "label": "Vulnerable"},
            {"min": 0, "label": "Critical"},
        ],
        "minimum_weight_coverage_percent": 60,
        "priority_weights": {
            "infrastructure_deficit": 0.35,
            "population_impact": 0.25,
            "service_criticality": 0.25,
            "lack_of_alternatives": 0.15,
        },
        "limitations": [
            "Weights and thresholds are illustrative project settings, not official standards.",
            "Demo records are simulated and do not represent measured conditions in named districts.",
            "Scenario outputs are calculations based on user assumptions, not causal forecasts.",
            "Reliability scores require verified, time-aligned performance data before operational use.",
        ],
    }


@app.get("/api/v1/sources")
def sources():
    return {
        "sources": [
            {
                "name": "Gram Manchitra",
                "url": "https://grammanchitra.gov.in/",
                "use": "Existing Gram Panchayat GIS and planning context; feature availability should be checked before integration.",
                "owner": "Ministry of Panchayati Raj, Government of India",
                "license": "Government open data; verify current terms before use.",
                "geography": "India — village/GP level",
                "last_checked": "2026-10",
            },
            {
                "name": "Mission Antyodaya",
                "url": "https://missionantyodaya.dord.gov.in/",
                "use": "Rural development indicators and gap-analysis context.",
                "owner": "Ministry of Rural Development, Government of India",
                "license": "Government open data; verify current terms before use.",
                "geography": "India — gram panchayat level",
                "last_checked": "2026-10",
            },
            {
                "name": "BharatNet",
                "url": "https://bharatnet.dot.gov.in/",
                "use": "Rural broadband programme context; do not assume village reliability metrics are available via API.",
                "owner": "Department of Telecommunications, Government of India",
                "license": "Government programme data; API terms must be verified.",
                "geography": "India — village/GP level",
                "last_checked": "2026-10",
            },
            {
                "name": "TRAI Apps / MySpeed",
                "url": "https://www.trai.gov.in/portals-apps/trai-apps",
                "use": "Reference for user-measured network quality; data/API terms must be verified.",
                "owner": "Telecom Regulatory Authority of India",
                "license": "Verify current API and data terms before integration.",
                "geography": "India — crowd-sourced device measurements",
                "last_checked": "2026-10",
            },
            {
                "name": "World Bank Rural Access Index",
                "url": "https://datacatalog.worldbank.org/infrastructure-data/search/dataset/0038250/rural-access-index-rai",
                "use": "Road access indicator context; complements rather than duplicates the multi-sector score.",
                "owner": "World Bank",
                "license": "Creative Commons Attribution 4.0 International (CC BY 4.0); check dataset-level terms.",
                "geography": "Global — country/sub-national level",
                "last_checked": "2026-10",
            },
            {
                "name": "OpenStreetMap",
                "url": "https://www.openstreetmap.org/copyright",
                "use": "Optional geographic context under ODbL attribution requirements.",
                "owner": "OpenStreetMap contributors",
                "license": "Open Database License (ODbL) — attribution required.",
                "geography": "Global",
                "last_checked": "2026-10",
            },
        ],
        "note": "These references describe the landscape; verify current access, licences and data granularity before integration.",
    }


# ---------------------------------------------------------------------------
# 2. Scenarios
# ---------------------------------------------------------------------------
class ScenarioRequest(BaseModel):
    village_id: str
    overrides: dict[str, float] = Field(default_factory=dict)
    estimated_cost: float | None = Field(default=None, ge=0)
    assumptions: str = Field(default="", max_length=1000)


@app.post("/api/v1/scenarios")
def run_scenario(req: ScenarioRequest):
    raw = db.get_village(req.village_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Village not found")
    try:
        return simulate(raw, req.overrides, req.estimated_cost, req.assumptions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# 3. Community Reports (Public / Private Ref Workflow)
# ---------------------------------------------------------------------------
class ReportRequest(BaseModel):
    village_id: str
    dimension: str
    description: str = Field(min_length=5, max_length=2000)


@app.post("/api/v1/field-reports")
def create_report(req: ReportRequest, request: Request):
    if req.dimension not in WEIGHTS:
        raise HTTPException(status_code=422, detail="Unknown dimension")
    if db.get_village(req.village_id) is None:
        raise HTTPException(status_code=404, detail="Village not found")
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    _check_rate_limit(client_ip.split(",")[0].strip())
    return db.save_report(req.village_id, req.dimension, req.description)


@app.get("/api/v1/field-reports")
def get_reports(village_id: Optional[str] = None):
    return {
        "items": db.list_reports(village_id),
        "notice": "Report descriptions and private reference codes are not included in public listings.",
    }


@app.get("/api/v1/field-reports/status/{reference_code}")
def get_report_status(reference_code: str):
    if len(reference_code) < 12 or len(reference_code) > 64:
        raise HTTPException(status_code=404, detail="Report not found")
    report = db.get_report_status(reference_code)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report": report,
        "notice": "This status view is private to the holder of the reference code. The report remains unverified unless an authorised review changes its status.",
    }


# ---------------------------------------------------------------------------
# 4. Reviewer Endpoints (Legacy Token Guard)
# ---------------------------------------------------------------------------
class ModerationRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|flag|request_info)$")
    note: str = Field(default="", max_length=1000)


STATUS_MAP = {
    "approve": "verified",
    "reject": "rejected",
    "flag": "flagged",
    "request_info": "pending_info",
}


@app.post("/api/v1/reviewer/reports/{reference_code}/moderate")
def moderate_report(
    reference_code: str,
    req: ModerationRequest,
    reviewer_id: str = Depends(require_reviewer),
):
    if len(reference_code) < 12 or len(reference_code) > 64:
        raise HTTPException(status_code=404, detail="Report not found")
    new_status = STATUS_MAP[req.action]
    result = db.moderate_report(reference_code, reviewer_id, req.action, new_status, req.note or None)
    if result is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report": result,
        "notice": "Moderation action recorded. Status history updated.",
    }


@app.get("/api/v1/reviewer/reports")
def reviewer_list_reports(
    village_id: Optional[str] = None,
    status: Optional[str] = None,
    reviewer_id: str = Depends(require_reviewer),
):
    with db.connect() as conn:
        db.init_db()
        if village_id and status:
            rows = conn.execute(
                "SELECT id, village_id, dimension, description, created_at, verification_status, reference_code FROM field_reports WHERE village_id = ? AND verification_status = ? ORDER BY id DESC",
                (village_id, status),
            ).fetchall()
        elif village_id:
            rows = conn.execute(
                "SELECT id, village_id, dimension, description, created_at, verification_status, reference_code FROM field_reports WHERE village_id = ? ORDER BY id DESC",
                (village_id,),
            ).fetchall()
        elif status:
            rows = conn.execute(
                "SELECT id, village_id, dimension, description, created_at, verification_status, reference_code FROM field_reports WHERE verification_status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, village_id, dimension, description, created_at, verification_status, reference_code FROM field_reports ORDER BY id DESC"
            ).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "notice": "Full report detail is visible only to authenticated reviewers.",
    }


# ---------------------------------------------------------------------------
# 5. CSV Export
# ---------------------------------------------------------------------------
@app.get("/api/v1/export.csv")
def export_csv(district: Optional[str] = None, category: Optional[str] = None, q: Optional[str] = None):
    items = _filter(_all(), district=district, category=category, q=q)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "village_id", "village_name", "district", "population", "overall_score", "category",
        "coverage_percent", "priority_score", "priority_label",
        "digital_score", "electricity_score", "road_score", "public_digital_score", "essential_services_score",
        "digital_availability", "digital_gap_points",
        "evidence_type", "source_name", "source_date", "data_notice",
        "export_scope", "methodology_version",
    ])
    scope = f"district={district or 'all'} category={category or 'all'} q={q or ''}"
    for v in items:
        comp = v["score"]["components"]
        digital_gap = next((g for g in v["gaps"] if g["dimension"] == "digital"), {})
        pop = v.get("population") or {}
        pop_value = pop.get("value") if isinstance(pop, dict) else pop
        writer.writerow([
            v["id"], v["name"], v["district"], pop_value,
            v["score"]["overall"], v["score"]["category"]["label"], v["score"]["coverage_percent"],
            v["priority"]["score"], v["priority"]["label"],
            comp.get("digital"), comp.get("electricity"), comp.get("roads"),
            comp.get("public_digital"), comp.get("essential_services"),
            digital_gap.get("availability"), digital_gap.get("gap_points"),
            v.get("evidence_type"), v.get("source_name"), v.get("source_date"), v.get("data_notice"),
            scope, "v1",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=infrapulse-village-reliability.csv"},
    )


# ---------------------------------------------------------------------------
# 6. Legacy CSV Import (Preview / Confirm / History)
# ---------------------------------------------------------------------------
def _parse_csv_rows(text: str, filename: str) -> tuple[list, list]:
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "id", "name", "district", "latitude", "longitude", "population",
        "digital_score", "electricity_score", "road_score", "public_digital_score", "essential_services_score",
    }
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=422,
            detail={"message": "Missing required columns", "required_columns": sorted(required)},
        )
    accepted: list = []
    rejected: list = []
    for line, row in enumerate(reader, start=2):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            pop = int(float(row["population"]))
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError("coordinates out of range")
            scores = {
                "digital": float(row["digital_score"]),
                "electricity": float(row["electricity_score"]),
                "roads": float(row["road_score"]),
                "public_digital": float(row["public_digital_score"]),
                "essential_services": float(row["essential_services_score"]),
            }
            if any(not 0 <= v <= 100 for v in scores.values()):
                raise ValueError("scores must be between 0 and 100")
            if not row["id"].strip() or not row["name"].strip():
                raise ValueError("id and name are required")
            dims = {}
            for key, score in scores.items():
                dims[key] = {
                    "label": DIMENSION_LABELS[key],
                    "score": score,
                    "evidence_type": "uploaded-unverified",
                    "confidence": "unverified",
                    "indicators": [{"name": "Imported component score", "value": score, "unit": "score / 100", "evidence_type": "uploaded-unverified"}],
                }
            if row.get("digital_availability") not in (None, ""):
                av = float(row["digital_availability"])
                if not 0 <= av <= 100:
                    raise ValueError("digital_availability must be between 0 and 100")
                dims["digital"]["availability_score"] = av
                dims["digital"]["reliability_score"] = scores["digital"]
            item = {
                "id": row["id"].strip(),
                "name": row["name"].strip(),
                "state": row.get("state", "India") or "India",
                "district": row["district"].strip() or "Unknown",
                "block": row.get("block", "Imported") or "Imported",
                "latitude": lat, "longitude": lon,
                "population": {"value": pop, "year": None, "source": "CSV import; not independently verified"},
                "dimensions": dims,
                "criticality": float(row.get("criticality") or 50),
                "alternative_access": float(row.get("alternative_access") or 50),
                "evidence_type": "uploaded-unverified",
                "source_name": filename,
                "source_url": None,
                "source_date": None,
                "data_notice": "UPLOADED DATA — NOT INDEPENDENTLY VERIFIED",
                "notes": "Imported from user-provided CSV.",
                "geometry_note": "Location provided by uploaded file; not independently verified.",
            }
            if not 0 <= item["criticality"] <= 100 or not 0 <= item["alternative_access"] <= 100:
                raise ValueError("criticality and alternative_access must be 0-100")
            accepted.append(item)
        except Exception as exc:
            rejected.append({"row": line, "reason": str(exc)})

    seen: set = set()
    for item in accepted:
        if item["id"] in seen:
            rejected.append({"row": None, "reason": f"duplicate ID in file: {item['id']}"})
        else:
            seen.add(item["id"])
    dup_ids = {x["reason"].split(": ", 1)[1] for x in rejected if x["reason"].startswith("duplicate ID in file: ")}
    final = [x for x in accepted if x["id"] not in dup_ids]
    return final, rejected


@app.post("/api/v1/imports/csv/preview")
async def preview_csv(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv file")
    raw_bytes = await file.read()
    if len(raw_bytes) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV must be 2 MB or smaller")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")
    accepted, rejected = _parse_csv_rows(text, file.filename or "upload.csv")
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    token = _secrets.token_urlsafe(24)
    db.save_import_session(token, file.filename or "upload.csv", accepted, rejected)
    return {
        "preview_token": token,
        "filename": file.filename,
        "file_sha256": file_sha256,
        "accepted_count": len(accepted),
        "rejected": rejected,
        "preview": [{
            "id": item["id"],
            "name": item["name"],
            "district": item["district"],
            "overall_score": calculate_score(item["dimensions"])["overall"],
        } for item in accepted[:20]],
        "notice": "No data has been written yet. Call POST /api/v1/imports/csv/confirm with the preview_token to commit.",
    }


@app.post("/api/v1/imports/csv/confirm")
def confirm_csv(preview_token: str):
    session = db.get_import_session(preview_token)
    if session is None:
        raise HTTPException(status_code=404, detail="Preview token not found or expired.")
    if session["confirmed"]:
        raise HTTPException(status_code=409, detail="This import has already been confirmed.")
    result = db.confirm_import_session(preview_token)
    if result is None:
        raise HTTPException(status_code=409, detail="Import could not be confirmed.")
    return {
        "token": result["token"],
        "filename": session["filename"],
        "accepted": result["accepted"],
        "rejected_count": result["rejected_count"],
        "notice": "Imported data is unverified; verify sources, dates, units and licensing before operational use.",
    }


@app.get("/api/v1/imports/history")
def import_history(limit: int = Query(default=50, ge=1, le=200)):
    return {
        "items": db.list_import_history(limit),
        "notice": "Only confirmed imports appear here.",
    }


@app.post("/api/v1/imports/csv")
async def import_csv(file: UploadFile = File(...)):
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv file")
    raw_bytes = await file.read()
    if len(raw_bytes) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV must be 2 MB or smaller")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")
    final, rejected = _parse_csv_rows(text, file.filename or "upload.csv")
    for item in final:
        db.save_village(item)
    return {
        "filename": file.filename,
        "accepted": len(final),
        "rejected": rejected,
        "notice": "Imported data is unverified; verify sources, dates, units and licensing before operational use.",
    }


# ===========================================================================
# 7. MASTER PROMPT VERIFICATION WORKFLOW ENDPOINTS
# ===========================================================================

# ---------------------------------------------------------------------------
# 7A. Authentication & User Management
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="resident", pattern="^(resident|admin)$")
    display_name: Optional[str] = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


@app.post("/api/v1/auth/register")
def register_user(req: RegisterRequest):
    clean_username = req.username.lower().strip()
    if not clean_username.replace("_", "").isalnum():
        raise HTTPException(status_code=422, detail="Username must contain alphanumeric characters and underscores only.")
    existing = db.get_user_by_username(clean_username)
    if existing:
        raise HTTPException(status_code=409, detail="A user with this username already exists.")
    pwd_hash = auth.hash_password(req.password)
    user = db.create_user(
        username=clean_username,
        password_hash=pwd_hash,
        role=req.role,
        display_name=req.display_name or req.username,
    )
    token = auth.create_token(user["id"], user["role"], user["username"])
    return {
        "token": token,
        "user": user,
        "notice": f"Account created with {user['role']} role.",
    }


@app.post("/api/v1/auth/login")
def login_user(req: LoginRequest, request: Request):
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    _check_login_rate_limit(client_ip.split(",")[0].strip())

    clean_username = req.username.lower().strip()
    user = db.get_user_by_username(clean_username)
    if not user or not auth.verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account is disabled.")

    token = auth.create_token(user["id"], user["role"], user["username"])
    user_info = {k: user[k] for k in ("id", "username", "role", "display_name", "created_at")}
    return {
        "token": token,
        "user": user_info,
    }


@app.post("/api/v1/auth/logout")
def logout_user():
    return {"status": "ok", "message": "Logged out successfully."}


@app.get("/api/v1/auth/me")
def get_current_user_profile(user: dict = Depends(auth.get_current_user)):
    return {"user": user}


# ---------------------------------------------------------------------------
# 7B. Cascading Geography & Location Verification
# ---------------------------------------------------------------------------
@app.get("/api/v1/geography/states")
def get_geography_states():
    return {"items": db.list_states()}


@app.get("/api/v1/geography/districts")
def get_geography_districts(state_code: Optional[str] = None):
    return {"items": db.list_districts(state_code)}


@app.get("/api/v1/geography/mandals")
def get_geography_mandals(district_code: Optional[str] = None):
    return {"items": db.list_mandals(district_code)}


@app.get("/api/v1/geography/villages")
def get_geography_villages(mandal_code: Optional[str] = None):
    return {"items": db.list_villages_in_mandal(mandal_code)}


class LocationVerifyRequest(BaseModel):
    village_id: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    accuracy_meters: float = Field(ge=0.0)


@app.post("/api/v1/village-memberships/verify-location")
def verify_village_location(
    req: LocationVerifyRequest,
    user: dict = Depends(auth.get_current_user),
):
    raw_village = db.get_village(req.village_id)
    if not raw_village:
        raise HTTPException(status_code=404, detail="Village not found in canonical registry.")

    match_result = geography.verify_user_location(
        user_lat=req.latitude,
        user_lon=req.longitude,
        accuracy_meters=req.accuracy_meters,
        village=raw_village,
        max_radius_meters=_config.LOCATION_MATCH_RADIUS_METERS,
    )

    membership = db.record_village_membership(
        user_id=user["id"],
        village_id=req.village_id,
        match_status=match_result["status"],
        match_method=match_result["method"],
        latitude=req.latitude,
        longitude=req.longitude,
        accuracy_meters=req.accuracy_meters,
    )

    return {
        "matched": match_result["matched"],
        "result": match_result,
        "membership": membership,
        "notice": "Location verified using device coordinates against village reference centroid. Centroid matching is an approximation.",
    }


@app.get("/api/v1/me/village")
def get_my_active_village(user: dict = Depends(auth.get_current_user)):
    membership = db.get_user_village_membership(user["id"])
    if not membership:
        return {"village": None, "message": "No active village membership verified."}
    return {"village": membership}


# ---------------------------------------------------------------------------
# 7C. Admin Development Data CSV Workflow
# ---------------------------------------------------------------------------
DEVELOPMENT_COLUMNS = [
    "record_id", "state_name", "district_name", "mandal_name", "village_id", "village_name",
    "dimension", "asset_or_project_name", "description", "reported_status",
    "start_date", "reported_completion_date", "last_observed_date",
    "source_name", "source_url", "source_reference_id", "estimated_cost",
    "latitude", "longitude", "notes"
]


@app.get("/api/v1/admin/imports/template.csv")
def download_development_csv_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(DEVELOPMENT_COLUMNS)
    writer.writerow([
        "REC-VIL-ROA-01", "Telangana", "Karimnagar", "Thimmapur", "DEMO-01", "Demo Village 01",
        "roads", "Village Approach All-Weather Road Upgrade", "Bituminous upgrade connecting main highway", "reportedly_completed",
        "2024-01-10", "2024-11-20", "2024-11-25",
        "Panchayati Raj Engineering Dept", "https://panchayat.gov.in/", "PR-2024-884", "3500000",
        "18.4386", "79.1288", "Illustrative template sample"
    ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=infrapulse-development-records-template.csv"},
    )


DEV_STATUS_NORMALIZATION = {
    "completed & finalled": "reportedly_completed",
    "completed and finalled": "reportedly_completed",
    "completed": "reportedly_completed",
    "complete": "reportedly_completed",
    "finalled": "reportedly_completed",
    "reportedly_completed": "reportedly_completed",
    "reportedly completed": "reportedly_completed",
    "in_progress": "in_progress",
    "in progress": "in_progress",
    "in-progress": "in_progress",
    "ongoing": "in_progress",
    "work in progress": "in_progress",
    "wip": "in_progress",
    "under construction": "in_progress",
    "under_construction": "in_progress",
    "planned": "planned",
    "sanctioned": "planned",
    "approved": "planned",
    "proposed": "planned",
    "operational": "operational",
    "functional": "operational",
    "non_operational": "non_operational",
    "non operational": "non_operational",
    "non-operational": "non_operational",
    "damaged": "non_operational",
    "defunct": "non_operational",
    "unknown": "unknown",
}

DEV_DIMENSION_NORMALIZATION = {
    "road": "roads",
    "roads": "roads",
    "digital": "digital",
    "connectivity": "digital",
    "telecom": "digital",
    "internet": "digital",
    "electricity": "electricity",
    "power": "electricity",
    "energy": "electricity",
    "public_digital": "public_digital",
    "public digital": "public_digital",
    "public-digital": "public_digital",
    "csc": "public_digital",
    "essential_services": "essential_services",
    "essential services": "essential_services",
    "essential-services": "essential_services",
    "water": "essential_services",
    "health": "essential_services",
    "sanitation": "essential_services",
}


@app.post("/api/v1/admin/imports/validate")
async def validate_development_csv(
    file: UploadFile = File(...),
    admin: dict = Depends(auth.require_admin),
):
    name = (file.filename or "").lower()
    if not (name.endswith(".csv") or name.endswith(".tsv") or name.endswith(".txt")):
        raise HTTPException(status_code=415, detail="File must be a .csv or .tsv file.")
    raw_bytes = await file.read()
    if len(raw_bytes) > 10_000_000:
        raise HTTPException(status_code=413, detail="CSV file must be 10 MB or smaller.")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="CSV must be UTF-8 or text encoded.")

    first_few_lines = "\n".join([line for line in text.splitlines()[:5] if line.strip()])
    delimiter = ","
    if "\t" in first_few_lines and first_few_lines.count("\t") > first_few_lines.count(","):
        delimiter = "\t"
    elif ";" in first_few_lines and first_few_lines.count(";") > first_few_lines.count(","):
        delimiter = ";"

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fieldnames = [f.strip() for f in reader.fieldnames] if reader.fieldnames else []
    required_cols = {"village_id", "dimension", "asset_or_project_name", "reported_status"}
    if not fieldnames or not required_cols.issubset(set(fieldnames)):
        raise HTTPException(
            status_code=422,
            detail={"message": "Missing required columns in CSV.", "required": sorted(required_cols)},
        )

    allowed_dimensions = set(WEIGHTS.keys())
    allowed_statuses = {"planned", "in_progress", "reportedly_completed", "operational", "non_operational", "unknown"}

    accepted = []
    rejected = []
    seen_ids = set()

    for line_idx, raw_row in enumerate(reader, start=2):
        row = {k.strip(): v for k, v in raw_row.items() if k is not None}
        try:
            v_id = (row.get("village_id") or "").strip()
            dim_raw = (row.get("dimension") or "").strip().lower()
            dim = DEV_DIMENSION_NORMALIZATION.get(dim_raw, dim_raw)
            asset_name = (row.get("asset_or_project_name") or "").strip()
            rep_status_raw = (row.get("reported_status") or "").strip().lower()
            rep_status = DEV_STATUS_NORMALIZATION.get(rep_status_raw, rep_status_raw)

            if not v_id or not asset_name:
                raise ValueError("village_id and asset_or_project_name are required.")

            if dim not in allowed_dimensions:
                raise ValueError(f"dimension '{dim}' invalid. Must be one of: {sorted(allowed_dimensions)}")

            # Fuzzy status normalization fallback instead of throwing error
            if rep_status not in allowed_statuses:
                if "complet" in rep_status_raw or "finall" in rep_status_raw:
                    rep_status = "reportedly_completed"
                elif "progress" in rep_status_raw or "ongoing" in rep_status_raw or "construct" in rep_status_raw:
                    rep_status = "in_progress"
                elif "plan" in rep_status_raw or "sanction" in rep_status_raw:
                    rep_status = "planned"
                elif "operat" in rep_status_raw or "function" in rep_status_raw:
                    rep_status = "operational"
                else:
                    rep_status = "unknown"

            # Parse coordinates & cost safely
            lat_str = (row.get("latitude") or "").strip()
            lon_str = (row.get("longitude") or "").strip()
            try:
                lat = float(lat_str) if lat_str else None
            except Exception:
                lat = None
            try:
                lon = float(lon_str) if lon_str else None
            except Exception:
                lon = None

            cost_str = (row.get("estimated_cost") or "").strip().replace(",", "").replace("INR", "").replace("₹", "").strip()
            try:
                cost = float(cost_str) if cost_str else None
            except Exception:
                cost = None

            v_name = (row.get("village_name") or v_id).strip()
            dist_name = (row.get("district_name") or "Unknown").strip()
            st_name = (row.get("state_name") or "Telangana").strip()
            m_name = (row.get("mandal_name") or "Central").strip()

            # If village does not exist in registry, auto-register it
            if db.get_village(v_id) is None:
                db.upsert_village_from_csv(
                    village_id=v_id,
                    name=v_name,
                    district=dist_name,
                    state_name=st_name,
                    mandal=m_name,
                    latitude=lat,
                    longitude=lon,
                )

            rec_id = (row.get("record_id") or "").strip() or f"REC-{v_id[:12]}-{dim[:3].upper()}-{secrets.token_hex(4).upper()}"
            if rec_id in seen_ids:
                raise ValueError(f"Duplicate record_id '{rec_id}' in file.")
            seen_ids.add(rec_id)

            accepted.append({
                "id": rec_id,
                "village_id": v_id,
                "village_name": v_name,
                "district_name": dist_name,
                "mandal_name": m_name,
                "state_name": st_name,
                "dimension": dim,
                "asset_or_project_name": asset_name,
                "description": (row.get("description") or "").strip(),
                "reported_status": rep_status,
                "start_date": (row.get("start_date") or "").strip() or None,
                "reported_completion_date": (row.get("reported_completion_date") or "").strip() or None,
                "last_observed_date": (row.get("last_observed_date") or "").strip() or None,
                "source_name": (row.get("source_name") or file.filename or "").strip(),
                "source_url": (row.get("source_url") or "").strip() or None,
                "source_reference_id": (row.get("source_reference_id") or "").strip() or None,
                "estimated_cost": cost,
                "latitude": lat,
                "longitude": lon,
                "notes": (row.get("notes") or "").strip() or None,
            })
        except Exception as exc:
            rejected.append({"row": line_idx, "reason": str(exc), "data": row})

    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    batch_id = f"batch_{_secrets.token_hex(8)}"

    return {
        "batch_id": batch_id,
        "filename": file.filename,
        "file_hash": file_hash,
        "total_rows": len(accepted) + len(rejected),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected_errors": rejected[:50],
        "preview_records": accepted[:25],
        "notice": "Validation complete. Call POST /api/v1/admin/imports/confirm to commit transaction.",
    }


class ImportConfirmRequest(BaseModel):
    batch_id: str
    filename: str
    file_hash: str
    records: List[dict]
    errors: List[dict] = Field(default_factory=list)
    notes: str = Field(default="")


@app.post("/api/v1/admin/imports/confirm")
def confirm_development_import(
    req: ImportConfirmRequest,
    admin: dict = Depends(auth.require_admin),
):
    if not req.records:
        raise HTTPException(status_code=400, detail="Cannot confirm an empty batch.")
    batch = db.create_import_batch(
        batch_id=req.batch_id,
        filename=req.filename,
        file_hash=req.file_hash,
        uploader_id=admin["id"],
        row_count=len(req.records) + len(req.errors),
        accepted_count=len(req.records),
        rejected_count=len(req.errors),
        records=req.records,
        errors=req.errors,
        notes=req.notes,
    )
    db.create_audit_event(
        actor_id=admin["id"],
        actor_role="admin",
        action="import_development_records",
        target_type="import_batch",
        target_id=req.batch_id,
        details={"accepted": len(req.records), "rejected": len(req.errors), "filename": req.filename},
    )
    return {
        "batch": batch,
        "message": f"Successfully committed {len(req.records)} development records.",
    }


@app.get("/api/v1/admin/imports")
def list_development_import_batches(admin: dict = Depends(auth.require_admin)):
    return {"items": db.list_import_batches()}


@app.get("/api/v1/admin/imports/{batch_id}")
def get_development_import_batch(batch_id: str, admin: dict = Depends(auth.require_admin)):
    batch = db.get_import_batch_detail(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return {"batch": batch}


@app.get("/api/v1/admin/villages/{village_id}/development-records")
def get_village_development_records_admin(village_id: str, admin: dict = Depends(auth.require_admin)):
    records = db.list_development_records(village_id=village_id)
    return {"village_id": village_id, "items": records}


# ---------------------------------------------------------------------------
# 7D. Resident Verification & Observation Workflow
# ---------------------------------------------------------------------------
@app.get("/api/v1/me/development-records")
def get_resident_development_records(user: dict = Depends(auth.require_resident)):
    membership = db.get_user_village_membership(user["id"])
    if not membership:
        raise HTTPException(
            status_code=400,
            detail="You must verify location for a village before accessing development records.",
        )
    v_id = membership["village_id"]
    records = db.list_development_records(village_id=v_id)
    if not records:
        records = db.list_development_records(village_id="TS-DEMO-001")
    return {
        "village_id": v_id,
        "village_name": membership.get("village_name", v_id),
        "items": records,
    }


@app.get("/api/v1/development-records/{record_id}")
def get_development_record_detail(record_id: str):
    rec = db.get_development_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Development record not found.")
    return {"record": rec}


ALLOWED_OBSERVED_STATUSES = {
    # Canonical server keys
    "matches_and_appears_functional",
    "exists_but_incomplete",
    "exists_but_damaged_or_not_functional",
    "not_found_at_location",
    "cannot_verify",
    "other_or_conflicting",
    # Frontend observation form keys
    "exists_and_functional",
    "under_construction",
    "reportedly_completed",
    "not_found",
    "could_not_observe",
    "operational",
}


@app.post("/api/v1/development-records/{record_id}/submissions")
async def submit_evidence_observation(
    record_id: str,
    observed_status: str = Form(...),
    notes: Optional[str] = Form(None),
    capture_latitude: Optional[float] = Form(None),
    capture_longitude: Optional[float] = Form(None),
    capture_accuracy: Optional[float] = Form(None),
    client_capture_time: Optional[str] = Form(None),
    user_ai_verdict_notes: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(auth.require_resident),
):
    rec = db.get_development_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Development record not found.")
    if observed_status not in ALLOWED_OBSERVED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid observed_status '{observed_status}'. Allowed: {sorted(ALLOWED_OBSERVED_STATUSES)}",
        )

    # 1. Create Evidence Submission Row
    sub_id = db.create_evidence_submission(
        record_id=record_id,
        village_id=rec["village_id"],
        user_id=user["id"],
        observed_status=observed_status,
        notes=notes,
        capture_latitude=capture_latitude,
        capture_longitude=capture_longitude,
        capture_accuracy=capture_accuracy,
        client_capture_time=client_capture_time,
        user_ai_verdict_notes=user_ai_verdict_notes,
    )

    image_bytes = None
    ai_result = None

    # 2. Process Image Attachment if captured
    if file and file.filename:
        raw_bytes = await file.read()
        if len(raw_bytes) > 15_000_000:
            raise HTTPException(status_code=413, detail="Photo file must be 15 MB or smaller.")

        # Validate image magic bytes
        mime_type = file.content_type or "image/jpeg"
        is_jpeg = raw_bytes.startswith(b"\xff\xd8\xff")
        is_png = raw_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        is_webp = len(raw_bytes) > 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP"

        if not (is_jpeg or is_png or is_webp):
            raise HTTPException(status_code=415, detail="Unsupported image format. Upload JPEG, PNG, or WebP.")

        storage_key = f"att_{sub_id}_{_secrets.token_hex(16)}"
        file_path = ATTACHMENTS_DIR / storage_key
        file_path.write_bytes(raw_bytes)

        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        db.save_attachment(
            submission_id=sub_id,
            storage_key=storage_key,
            original_filename=file.filename,
            content_type=mime_type,
            file_size_bytes=len(raw_bytes),
            file_sha256=file_hash,
        )
        image_bytes = raw_bytes

    # 3. Server-Side AI Vision Analysis
    if image_bytes:
        ai_result = ai_vision.analyze_evidence_image_sync(
            image_bytes=image_bytes,
            claim_details=rec,
            user_observation={"observed_status": observed_status, "notes": notes},
            mime_type=file.content_type or "image/jpeg",
        )
        db.save_ai_analysis(sub_id, ai_result)

    submission = db.get_evidence_submission(sub_id)
    return {
        "submission": submission,
        "message": "Observation submitted. Stored securely for reviewer triage.",
    }


@app.get("/api/v1/me/submissions")
def get_my_submissions(user: dict = Depends(auth.require_resident)):
    items = db.list_submissions(user_id=user["id"])
    return {"items": items}


@app.get("/api/v1/me/submissions/{submission_id}")
def get_my_submission_detail(submission_id: int, user: dict = Depends(auth.require_resident)):
    sub = db.get_evidence_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    if sub["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Access denied.")
    return {"submission": sub}


class UserReviewRequest(BaseModel):
    user_notes: str = Field(max_length=2000)


@app.post("/api/v1/submissions/{submission_id}/user-review")
def update_submission_user_review(
    submission_id: int,
    req: UserReviewRequest,
    user: dict = Depends(auth.require_resident),
):
    sub = db.get_evidence_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    if sub["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied.")
    success = db.update_submission_user_review(submission_id, user["id"], req.user_notes)
    return {"status": "ok", "updated": success}


# ---------------------------------------------------------------------------
# 7E. Protected Attachments Endpoint
# ---------------------------------------------------------------------------
@app.get("/api/v1/attachments/{storage_key}")
def download_protected_attachment(
    storage_key: str,
    user: dict = Depends(auth.get_current_user),
):
    att = db.get_attachment_by_key(storage_key)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    sub = db.get_evidence_submission(att["submission_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="Associated submission not found.")

    # Access control: user must be the author or an admin
    if user["role"] != "admin" and sub["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You cannot access this private evidence file.")

    file_path = ATTACHMENTS_DIR / storage_key
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing from secure storage.")

    return FileResponse(
        path=str(file_path),
        media_type=att["content_type"],
        filename=att["original_filename"],
    )


# ---------------------------------------------------------------------------
# 7F. Admin Review Console & Verification Metrics
# ---------------------------------------------------------------------------
@app.get("/api/v1/admin/submissions")
def list_admin_submissions(
    village_id: Optional[str] = None,
    record_id: Optional[str] = None,
    review_status: Optional[str] = None,
    discrepancy_only: bool = False,
    admin: dict = Depends(auth.require_admin),
):
    items = db.list_submissions(
        village_id=village_id,
        record_id=record_id,
        review_status=review_status,
        discrepancy_only=discrepancy_only,
    )
    return {"items": items}


@app.get("/api/v1/admin/submissions/{submission_id}")
def get_admin_submission_detail(submission_id: int, admin: dict = Depends(auth.require_admin)):
    sub = db.get_evidence_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return {"submission": sub}


class AdminSubmissionReviewRequest(BaseModel):
    review_status: str = Field(..., pattern="^(verified|rejected|flagged|pending_info)$")
    review_note: Optional[str] = Field(default="", max_length=2000)


@app.post("/api/v1/admin/submissions/{submission_id}/review")
def review_resident_submission(
    submission_id: int,
    req: AdminSubmissionReviewRequest,
    admin: dict = Depends(auth.require_admin),
):
    sub = db.get_evidence_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    updated = db.review_submission(
        submission_id=submission_id,
        reviewer_id=admin["id"],
        review_status=req.review_status,
        review_note=req.review_note,
    )
    return {"submission": updated, "message": f"Submission status updated to '{req.review_status}'."}


class PromoteIndicatorRequest(BaseModel):
    dimension: str = Field(..., pattern="^(digital|electricity|roads|public_digital|essential_services)$")
    indicator_name: str = Field(min_length=3, max_length=100)
    promoted_value: float = Field(ge=0.0, le=100.0)
    reason: str = Field(min_length=5, max_length=1000)


@app.post("/api/v1/admin/submissions/{submission_id}/promote-indicator")
def promote_submission_to_indicator(
    submission_id: int,
    req: PromoteIndicatorRequest,
    admin: dict = Depends(auth.require_admin),
):
    sub = db.get_evidence_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found.")
    if sub.get("review_status") != "verified":
        raise HTTPException(status_code=400, detail="Only 'verified' submissions may be promoted to trusted indicators.")

    promoted = db.promote_indicator(
        submission_id=submission_id,
        village_id=sub["village_id"],
        dimension=req.dimension,
        indicator_name=req.indicator_name,
        promoted_value=req.promoted_value,
        reason=req.reason,
        promoted_by=admin["id"],
    )
    return {
        "promoted_indicator": promoted,
        "message": f"Promoted verified observation to {req.dimension} indicator value {req.promoted_value}.",
    }


@app.get("/api/v1/admin/villages/{village_id}/verification-summary")
def get_village_verification_summary(
    village_id: str,
    user: dict = Depends(auth.get_current_user),
):
    # Allowed to admin, or resident if matched with this village
    if user["role"] != "admin":
        active_v = db.get_user_village_membership(user["id"])
        if not active_v or active_v["village_id"] != village_id:
            raise HTTPException(status_code=403, detail="Forbidden: You can only view summaries for your verified village.")

    summary_data = db.get_village_verification_summary(village_id)
    return {"summary": summary_data}


@app.get("/api/v1/admin/audit-events")
def list_system_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    admin: dict = Depends(auth.require_admin),
):
    events = db.list_audit_events(limit=limit)
    return {"items": events}
