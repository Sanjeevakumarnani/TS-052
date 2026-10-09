import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from .config import ATTACHMENTS_DIR, DB_FILE, DATABASE_URL, SEED_FILE, USE_POSTGRES


class _PgRowWrapper:
    """Minimal wrapper to make psycopg2 rows behave like sqlite3.Row (dict-like)."""
    def __init__(self, row, description):
        self._data = {description[i].name: row[i] for i in range(len(description))} if row is not None else {}

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def __iter__(self):
        return iter(self._data)


class _PgCursorWrapper:
    """Wraps psycopg2 cursor to match sqlite3 interface used in codebase."""
    def __init__(self, cursor):
        self._cur = cursor

    @property
    def lastrowid(self):
        self._cur.execute("SELECT lastval()")
        r = self._cur.fetchone()
        return r[0] if r else None

    def execute(self, sql, params=()):
        # Convert SQLite ? placeholders to PostgreSQL %s
        sql = sql.replace("?", "%s")
        # Adapt DDL for PostgreSQL
        sql = _adapt_ddl(sql)

        # Handle SQLite PRAGMA table_info(table_name)
        clean_sql = sql.strip()
        if clean_sql.upper().startswith("PRAGMA TABLE_INFO("):
            tbl = clean_sql[len("PRAGMA TABLE_INFO("):].rstrip(");").strip().strip("\"'").lower()
            self._cur.execute(
                "SELECT column_name AS name FROM information_schema.columns WHERE table_name = %s",
                (tbl,)
            )
            return self
        elif clean_sql.upper().startswith("PRAGMA"):
            # Other pragmas are no-ops on PostgreSQL
            self._cur.execute("SELECT 1 WHERE 1=0")
            return self

        self._cur.execute(sql, params)
        return self

    def fetchone(self):
        if not self._cur.description:
            return None
        row = self._cur.fetchone()
        if row is None:
            return None
        return _PgRowWrapper(row, self._cur.description)

    def fetchall(self):
        if not self._cur.description:
            return []
        rows = self._cur.fetchall()
        if not rows:
            return []
        return [_PgRowWrapper(r, self._cur.description) for r in rows]

    def __iter__(self):
        if not self._cur.description:
            return iter([])
        for row in self._cur:
            yield _PgRowWrapper(row, self._cur.description)


class _PgConnWrapper:
    """Wraps psycopg2 connection to match sqlite3.connect() interface."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        return _PgCursorWrapper(cur).execute(sql, params)

    def cursor(self):
        return _PgCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False


def connect():
    if USE_POSTGRES:
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError("psycopg2 not installed. Add psycopg2-binary to requirements.txt")
        raw_url = DATABASE_URL
        # Neon uses postgresql:// but psycopg2 needs postgresql:// (also accepts postgres://)
        conn = psycopg2.connect(raw_url, sslmode="require")
        return _PgConnWrapper(conn)
    else:
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_FILE, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn


def _adapt_ddl(sql: str) -> str:
    """Adapt SQLite DDL and queries to PostgreSQL syntax when needed."""
    if not USE_POSTGRES:
        return sql
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    sql = sql.replace("TEXT DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP")

    # Adapt INSERT OR IGNORE INTO ... and INSERT OR REPLACE INTO ...
    clean_upper = sql.strip().upper()
    if clean_upper.startswith("INSERT OR IGNORE INTO ") or clean_upper.startswith("INSERT OR REPLACE INTO "):
        prefix = "INSERT OR IGNORE INTO " if clean_upper.startswith("INSERT OR IGNORE INTO ") else "INSERT OR REPLACE INTO "
        sql_rest = sql.strip()[len(prefix):]
        # Append ON CONFLICT DO NOTHING if not already present
        if "ON CONFLICT" not in sql_rest.upper():
            sql = f"INSERT INTO {sql_rest} ON CONFLICT DO NOTHING"
        else:
            sql = f"INSERT INTO {sql_rest}"

    return sql


def _upsert(conn, table: str, pk_col: str, pk_val, data: dict):
    """Database-agnostic upsert."""
    if USE_POSTGRES:
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c != pk_col])
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk_col}) DO UPDATE SET {updates}"
        )
        cur = conn._conn.cursor()
        cur.execute(sql, vals)
    else:
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        conn.execute(sql, vals)




def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db():
    if USE_POSTGRES:
        # On Neon PostgreSQL, tables and seed data are already created and managed.
        # Check if initialized, if yes return immediately.
        try:
            with connect() as conn:
                r = conn.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'villages'").fetchone()
                if r:
                    return
        except Exception:
            pass
    with connect() as conn:
        # 1. Existing table: villages
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS villages (
                id TEXT PRIMARY KEY,
                district TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                state_code TEXT,
                district_code TEXT,
                mandal_code TEXT,
                mandal TEXT,
                boundary_geojson TEXT,
                is_demo INTEGER DEFAULT 1,
                data_origin TEXT DEFAULT 'seeded-demo'
            )
            """
        )
        v_cols = {row["name"] for row in conn.execute("PRAGMA table_info(villages)").fetchall()}
        for col, col_def in [
            ("state_code", "TEXT"),
            ("district_code", "TEXT"),
            ("mandal_code", "TEXT"),
            ("mandal", "TEXT"),
            ("boundary_geojson", "TEXT"),
            ("is_demo", "INTEGER DEFAULT 1"),
            ("data_origin", "TEXT DEFAULT 'seeded-demo'"),
        ]:
            if col not in v_cols:
                conn.execute(f"ALTER TABLE villages ADD COLUMN {col} {col_def}")

        # 2. Existing table: field_reports & history
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS field_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                village_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                verification_status TEXT NOT NULL DEFAULT 'unverified',
                reference_code TEXT
            )
            """
        )
        fr_cols = {row["name"] for row in conn.execute("PRAGMA table_info(field_reports)").fetchall()}
        if "reference_code" not in fr_cols:
            conn.execute("ALTER TABLE field_reports ADD COLUMN reference_code TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_field_reports_reference_code ON field_reports(reference_code)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS field_report_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                changed_by TEXT NOT NULL DEFAULT 'system',
                note TEXT
            )
            """
        )

        # 3. Existing CSV import sessions & history
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_sessions (
                token TEXT PRIMARY KEY,
                filename TEXT,
                row_count INTEGER,
                accepted_count INTEGER,
                rejected_json TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                confirmed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                filename TEXT,
                file_sha256 TEXT,
                accepted_count INTEGER,
                rejected_count INTEGER,
                confirmed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewer_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                reviewer_id TEXT NOT NULL,
                action TEXT NOT NULL,
                new_status TEXT NOT NULL,
                note TEXT,
                acted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # 4. Master Prompt Architecture Tables
        # Users
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL, -- 'admin', 'resident', 'public'
                display_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'active'
            )
            """
        )

        # Geography hierarchy
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geography_states (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geography_districts (
                code TEXT PRIMARY KEY,
                state_code TEXT NOT NULL,
                name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geography_mandals (
                code TEXT PRIMARY KEY,
                district_code TEXT NOT NULL,
                name TEXT NOT NULL
            )
            """
        )

        # Village Memberships (location verification records)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS village_memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                village_id TEXT NOT NULL,
                match_status TEXT NOT NULL,
                match_method TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                accuracy_meters REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Development Records & Batches
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                uploader_id TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                schema_version TEXT NOT NULL DEFAULT 'v1',
                status TEXT NOT NULL DEFAULT 'confirmed',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS import_row_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                row_number INTEGER,
                error_reason TEXT NOT NULL,
                raw_data TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS development_records (
                id TEXT PRIMARY KEY,
                village_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                asset_or_project_name TEXT NOT NULL,
                description TEXT,
                reported_status TEXT NOT NULL, -- planned, in_progress, reportedly_completed, operational, non_operational, unknown
                start_date TEXT,
                reported_completion_date TEXT,
                last_observed_date TEXT,
                source_name TEXT,
                source_url TEXT,
                source_reference_id TEXT,
                estimated_cost REAL,
                latitude REAL,
                longitude REAL,
                notes TEXT,
                is_demo INTEGER DEFAULT 0,
                batch_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Evidence Submissions
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL,
                village_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                observed_status TEXT NOT NULL, -- matches_and_appears_functional, exists_but_incomplete, exists_but_damaged_or_not_functional, not_found_at_location, cannot_verify, other_or_conflicting
                notes TEXT,
                capture_latitude REAL,
                capture_longitude REAL,
                capture_accuracy REAL,
                client_capture_time TEXT,
                server_receipt_time TEXT DEFAULT CURRENT_TIMESTAMP,
                user_ai_verdict_notes TEXT,
                review_status TEXT NOT NULL DEFAULT 'unverified', -- unverified, verified, rejected, flagged, pending_info
                reviewer_id TEXT,
                review_note TEXT,
                reviewed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Attachments (Private photo evidence storage)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                storage_key TEXT UNIQUE NOT NULL,
                original_filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                file_sha256 TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # AI Analyses
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                status TEXT NOT NULL, -- complete, failed, not_configured
                provider TEXT NOT NULL,
                model_name TEXT NOT NULL,
                summary TEXT,
                visible_elements_json TEXT,
                relation_to_claim TEXT,
                apparent_condition TEXT,
                observations TEXT,
                uncertainties_and_limitations TEXT,
                possible_privacy_or_safety_issue TEXT,
                recommended_human_review TEXT,
                analyzed_at TEXT,
                error_message TEXT
            )
            """
        )

        # Audit Events & Indicators
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promoted_indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id INTEGER NOT NULL,
                village_id TEXT NOT NULL,
                dimension TEXT NOT NULL,
                indicator_name TEXT NOT NULL,
                promoted_value REAL NOT NULL,
                reason TEXT NOT NULL,
                promoted_by TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Seed initial village records from seed file if empty
        count = conn.execute("SELECT COUNT(*) AS c FROM villages").fetchone()["c"]
        if count == 0 and SEED_FILE.exists():
            data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
            for item in data:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO villages (
                        id, district, payload, state_code, district_code, mandal_code, mandal, is_demo, data_origin
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'seeded-demo')
                    """,
                    (
                        item["id"],
                        item.get("district", "Unknown"),
                        json.dumps(item),
                        "TS",
                        item.get("district", "Karimnagar").upper().replace(" ", "_"),
                        "THIMMAPUR",
                        item.get("block", "Thimmapur"),
                    ),
                )

        # Seed Geography Hierarchy from existing villages
        geo_count = conn.execute("SELECT COUNT(*) AS c FROM geography_states").fetchone()["c"]
        if geo_count == 0:
            conn.execute("INSERT OR REPLACE INTO geography_states (code, name) VALUES ('TS', 'Telangana')")
            conn.execute("INSERT OR REPLACE INTO geography_states (code, name) VALUES ('AP', 'Andhra Pradesh')")
            conn.execute("INSERT OR REPLACE INTO geography_states (code, name) VALUES ('KA', 'Karnataka')")

            # Extract distinct districts and mandals from villages
            v_rows = conn.execute("SELECT id, district, payload FROM villages").fetchall()
            for r in v_rows:
                dist_name = r["district"]
                dist_code = dist_name.upper().replace(" ", "_")
                conn.execute(
                    "INSERT OR REPLACE INTO geography_districts (code, state_code, name) VALUES (?, 'TS', ?)",
                    (dist_code, dist_name),
                )
                try:
                    p = json.loads(r["payload"])
                    mandal_name = p.get("block", "Central")
                except Exception:
                    mandal_name = "Central"
                mandal_code = f"{dist_code}_{mandal_name.upper().replace(' ', '_')}"
                conn.execute(
                    "INSERT OR REPLACE INTO geography_mandals (code, district_code, name) VALUES (?, ?, ?)",
                    (mandal_code, dist_code, mandal_name),
                )
                conn.execute(
                    "UPDATE villages SET state_code = 'TS', district_code = ?, mandal_code = ?, mandal = ? WHERE id = ?",
                    (dist_code, mandal_code, mandal_name, r["id"]),
                )

        # Seed demo development records if empty
        dev_count = conn.execute("SELECT COUNT(*) AS c FROM development_records").fetchone()["c"]
        if dev_count == 0:
            _seed_demo_development_records(conn)


def _seed_demo_development_records(conn: sqlite3.Connection):
    """Seed synthetic development project records linked to demonstration villages."""
    rows = conn.execute("SELECT id, district, payload FROM villages LIMIT 10").fetchall()
    demo_projects = [
        ("roads", "All-Weather BT Road Upgrade", "Upgradation of village main approach road to Bituminous surface under PMGSY Phase-3.", "reportedly_completed", "2024-01-15", "2025-06-20", 4200000.0),
        ("electricity", "Dedicated 25kVA Agriculture Transformer", "Installation of separate distribution transformer for rural household and farm supply reliability.", "operational", "2023-08-10", "2024-02-14", 350000.0),
        ("digital", "BharatNet Gram Panchayat Optical Fiber Point", "Underground optical fiber termination and GP kiosk Wi-Fi access point.", "in_progress", "2024-03-01", None, 180000.0),
        ("public_digital", "Common Service Centre (CSC) Digital Kiosk", "Public digital service point equipped with biometric authentication and certificate issuance terminals.", "reportedly_completed", "2023-11-01", "2024-01-10", 120000.0),
        ("essential_services", "Primary Health Sub-Centre Solar Refrigeration", "Installation of solar-powered vaccine refrigerator and emergency power backup.", "planned", "2025-01-01", None, 250000.0),
    ]
    for r in rows:
        v_id = r["id"]
        v_data = json.loads(r["payload"])
        v_name = v_data.get("name", "Village")
        lat = v_data.get("latitude")
        lon = v_data.get("longitude")
        for idx, (dim, name, desc, status, s_date, c_date, cost) in enumerate(demo_projects):
            rec_id = f"REC-{v_id}-{dim[:3].upper()}-{idx+1:02d}"
            conn.execute(
                """
                INSERT OR REPLACE INTO development_records (
                    id, village_id, dimension, asset_or_project_name, description, reported_status,
                    start_date, reported_completion_date, last_observed_date, source_name, source_url,
                    source_reference_id, estimated_cost, latitude, longitude, notes, is_demo, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'SEED_DEMO_BATCH')
                """,
                (
                    rec_id,
                    v_id,
                    dim,
                    f"{v_name} - {name}",
                    desc,
                    status,
                    s_date,
                    c_date,
                    c_date or s_date,
                    "State Rural Development Department (Demo)",
                    "https://panchayat.gov.in/",
                    f"REF-{v_id}-{idx+1}",
                    cost,
                    lat,
                    lon,
                    "Synthetic demo record for MVP verification testing.",
                ),
            )


# ---------------------------------------------------------------------------
# Existing Village APIs (preserved)
# ---------------------------------------------------------------------------
def list_villages() -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT payload FROM villages ORDER BY id").fetchall()
    return [json.loads(r["payload"]) for r in rows]


def get_village(village_id: str):
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT payload FROM villages WHERE id = ?", (village_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def save_village(item: dict[str, Any]):
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO villages (id, district, payload, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (item["id"], item.get("district", "Unknown"), json.dumps(item)),
        )


def upsert_village_from_csv(
    village_id: str,
    name: str = "",
    district: str = "Unknown",
    state_name: str = "Telangana",
    mandal: str = "Central",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
):
    init_db()
    with connect() as conn:
        state_name = (state_name or "Telangana").strip()
        district = (district or "Unknown").strip()
        mandal = (mandal or "Central").strip()
        name = (name or village_id).strip()

        state_code = "TS" if "telangana" in state_name.lower() else (state_name[:2].upper() if len(state_name) >= 2 else "TS")
        conn.execute("INSERT OR IGNORE INTO geography_states (code, name) VALUES (?, ?)", (state_code, state_name))

        dist_code = district.upper().replace(" ", "_")
        conn.execute("INSERT OR IGNORE INTO geography_districts (code, state_code, name) VALUES (?, ?, ?)", (dist_code, state_code, district))

        mandal_code = f"{dist_code}_{mandal.upper().replace(' ', '_')}"
        conn.execute("INSERT OR IGNORE INTO geography_mandals (code, district_code, name) VALUES (?, ?, ?)", (mandal_code, dist_code, mandal))

        row = conn.execute("SELECT payload FROM villages WHERE id = ?", (village_id,)).fetchone()
        if not row:
            payload = {
                "id": village_id,
                "name": name,
                "state": state_name,
                "district": district,
                "block": mandal,
                "latitude": latitude if latitude is not None else 17.5,
                "longitude": longitude if longitude is not None else 79.2,
                "population": {"value": 3000, "year": 2024, "source": "CSV import auto-registered"},
                "dimensions": {},
                "evidence_type": "uploaded-unverified",
                "data_notice": "IMPORTED FROM DEVELOPMENT DATA CSV",
            }
            conn.execute(
                """
                INSERT OR REPLACE INTO villages (
                    id, district, payload, updated_at, state_code, district_code, mandal_code, mandal, is_demo, data_origin
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, 0, 'imported-csv')
                """,
                (village_id, district, json.dumps(payload), state_code, dist_code, mandal_code, mandal),
            )


# ---------------------------------------------------------------------------
# Existing Field Report & Migration APIs (preserved)
# ---------------------------------------------------------------------------
def save_report(village_id: str, dimension: str, description: str):
    init_db()
    with connect() as conn:
        reference_code = secrets.token_urlsafe(12)
        cur = conn.execute(
            "INSERT INTO field_reports (village_id, dimension, description, verification_status, reference_code) VALUES (?, ?, ?, 'unverified', ?)",
            (village_id, dimension, description, reference_code),
        )
        rid = cur.lastrowid
        conn.execute(
            "INSERT INTO field_report_status_history (report_id, status, changed_by, note) VALUES (?, 'unverified', 'system', 'Submitted by public user')",
            (rid,),
        )
        row = conn.execute(
            "SELECT id, village_id, dimension, created_at, verification_status, reference_code FROM field_reports WHERE id = ?",
            (rid,),
        ).fetchone()
    return dict(row)


def list_reports(village_id: str | None = None):
    init_db()
    with connect() as conn:
        if village_id:
            rows = conn.execute(
                "SELECT id, village_id, dimension, created_at, verification_status FROM field_reports WHERE village_id = ? ORDER BY id DESC",
                (village_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, village_id, dimension, created_at, verification_status FROM field_reports ORDER BY id DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_report_status(reference_code: str):
    init_db()
    with connect() as conn:
        report = conn.execute(
            "SELECT id, village_id, dimension, created_at, verification_status FROM field_reports WHERE reference_code = ?",
            (reference_code,),
        ).fetchone()
        if report is None:
            return None
        history = conn.execute(
            "SELECT status, changed_at, changed_by, note FROM field_report_status_history WHERE report_id = ? ORDER BY id",
            (report["id"],),
        ).fetchall()
    result = dict(report)
    result["history"] = [dict(item) for item in history]
    return result


def moderate_report(reference_code: str, reviewer_id: str, action: str, new_status: str, note: str | None = None):
    init_db()
    with connect() as conn:
        report = conn.execute("SELECT id FROM field_reports WHERE reference_code = ?", (reference_code,)).fetchone()
        if report is None:
            return None
        rid = report["id"]
        conn.execute("UPDATE field_reports SET verification_status = ? WHERE id = ?", (new_status, rid))
        conn.execute(
            "INSERT INTO field_report_status_history (report_id, status, changed_by, note) VALUES (?, ?, ?, ?)",
            (rid, new_status, reviewer_id, note),
        )
        conn.execute(
            "INSERT INTO reviewer_actions (report_id, reviewer_id, action, new_status, note) VALUES (?, ?, ?, ?, ?)",
            (rid, reviewer_id, action, new_status, note),
        )
        updated = conn.execute(
            "SELECT id, village_id, dimension, created_at, verification_status FROM field_reports WHERE id = ?",
            (rid,),
        ).fetchone()
        history = conn.execute(
            "SELECT status, changed_at, changed_by, note FROM field_report_status_history WHERE report_id = ? ORDER BY id",
            (rid,),
        ).fetchall()
    result = dict(updated)
    result["history"] = [dict(h) for h in history]
    return result


def save_import_session(token: str, filename: str, accepted: list, rejected: list):
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO import_sessions (token, filename, row_count, accepted_count, rejected_json, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                token,
                filename,
                len(accepted) + len(rejected),
                len(accepted),
                json.dumps(rejected),
                json.dumps(accepted),
            ),
        )
    return token


def get_import_session(token: str):
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT token, filename, row_count, accepted_count, rejected_json, payload_json, created_at, confirmed FROM import_sessions WHERE token = ?",
            (token,),
        ).fetchone()
    if row is None:
        return None
    s = dict(row)
    s["rejected"] = json.loads(s.pop("rejected_json"))
    s["payload"] = json.loads(s.pop("payload_json"))
    return s


def confirm_import_session(token: str, file_sha256: str | None = None) -> dict | None:
    init_db()
    session = get_import_session(token)
    if session is None or session["confirmed"]:
        return None
    with connect() as conn:
        for item in session["payload"]:
            conn.execute(
                "INSERT OR REPLACE INTO villages (id, district, payload, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (item["id"], item.get("district", "Unknown"), json.dumps(item)),
            )
        conn.execute("UPDATE import_sessions SET confirmed = 1 WHERE token = ?", (token,))
        conn.execute(
            "INSERT INTO import_history (token, filename, file_sha256, accepted_count, rejected_count) VALUES (?, ?, ?, ?, ?)",
            (token, session["filename"], file_sha256, session["accepted_count"], len(session["rejected"])),
        )
    return {"token": token, "accepted": session["accepted_count"], "rejected_count": len(session["rejected"])}


def list_import_history(limit: int = 50):
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, token, filename, file_sha256, accepted_count, rejected_count, confirmed_at FROM import_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# User Authentication & Role Management
# ---------------------------------------------------------------------------
def create_user(username: str, password_hash: str, role: str, display_name: Optional[str] = None) -> dict:
    init_db()
    user_id = f"usr_{secrets.token_hex(8)}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, role, display_name) VALUES (?, ?, ?, ?, ?)",
            (user_id, username.lower().strip(), password_hash, role, display_name or username),
        )
        row = conn.execute("SELECT id, username, role, display_name, created_at, status FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


def get_user_by_id(user_id: str) -> Optional[dict]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT id, username, password_hash, role, display_name, created_at, status FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[dict]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT id, username, password_hash, role, display_name, created_at, status FROM users WHERE username = ?", (username.lower().strip(),)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Cascading Geography APIs
# ---------------------------------------------------------------------------
def list_states() -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT code, name FROM geography_states ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def list_districts(state_code: Optional[str] = None) -> list[dict]:
    init_db()
    with connect() as conn:
        if state_code:
            rows = conn.execute("SELECT code, state_code, name FROM geography_districts WHERE state_code = ? ORDER BY name", (state_code,)).fetchall()
        else:
            rows = conn.execute("SELECT code, state_code, name FROM geography_districts ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def list_mandals(district_code: Optional[str] = None) -> list[dict]:
    init_db()
    with connect() as conn:
        if district_code:
            rows = conn.execute("SELECT code, district_code, name FROM geography_mandals WHERE district_code = ? ORDER BY name", (district_code,)).fetchall()
        else:
            rows = conn.execute("SELECT code, district_code, name FROM geography_mandals ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def list_villages_in_mandal(mandal_code: Optional[str] = None) -> list[dict]:
    init_db()
    with connect() as conn:
        if mandal_code:
            rows = conn.execute(
                "SELECT id, district, state_code, district_code, mandal_code, mandal, payload, is_demo FROM villages WHERE mandal_code = ? ORDER BY id",
                (mandal_code,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT id, district, state_code, district_code, mandal_code, mandal, payload, is_demo FROM villages ORDER BY id").fetchall()
    results = []
    for r in rows:
        p = json.loads(r["payload"])
        results.append({
            "id": r["id"],
            "name": p.get("name", r["id"]),
            "district": r["district"],
            "state_code": r["state_code"],
            "district_code": r["district_code"],
            "mandal_code": r["mandal_code"],
            "mandal": r["mandal"],
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "is_demo": bool(r["is_demo"]),
        })
    return results


# ---------------------------------------------------------------------------
# Village Membership & Location Verification
# ---------------------------------------------------------------------------
def record_village_membership(
    user_id: str,
    village_id: str,
    match_status: str,
    match_method: str,
    latitude: Optional[float],
    longitude: Optional[float],
    accuracy_meters: Optional[float],
) -> dict:
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO village_memberships (user_id, village_id, match_status, match_method, latitude, longitude, accuracy_meters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, village_id, match_status, match_method, latitude, longitude, accuracy_meters),
        )
        mid = cur.lastrowid
        row = conn.execute("SELECT * FROM village_memberships WHERE id = ?", (mid,)).fetchone()
    return dict(row)


def get_user_village_membership(user_id: str) -> Optional[dict]:
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT m.*, v.district, v.payload
            FROM village_memberships m
            JOIN villages v ON m.village_id = v.id
            WHERE m.user_id = ? AND m.match_status IN ('boundary_match', 'centroid_match', 'accepted', 'accepted_no_centroid', 'verified')
            ORDER BY m.id DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return None
    res = dict(row)
    v_data = json.loads(res.pop("payload", "{}"))
    res["village_name"] = v_data.get("name", res["village_id"])
    return res


# ---------------------------------------------------------------------------
# Admin Development Data & CSV Imports
# ---------------------------------------------------------------------------
def create_import_batch(
    batch_id: str,
    filename: str,
    file_hash: str,
    uploader_id: str,
    row_count: int,
    accepted_count: int,
    rejected_count: int,
    records: list[dict],
    errors: list[dict],
    notes: str = "",
) -> dict:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO import_batches (id, filename, file_hash, uploader_id, row_count, accepted_count, rejected_count, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, filename, file_hash, uploader_id, row_count, accepted_count, rejected_count, notes),
        )
        for err in errors:
            conn.execute(
                "INSERT INTO import_row_errors (batch_id, row_number, error_reason, raw_data) VALUES (?, ?, ?, ?)",
                (batch_id, err.get("row"), err.get("reason", "Unknown error"), json.dumps(err.get("data", {}))),
            )
        for r in records:
            v_id = r.get("village_id")
            if v_id:
                v_row = conn.execute("SELECT id FROM villages WHERE id = ?", (v_id,)).fetchone()
                if not v_row:
                    st_name = (r.get("state_name") or "Telangana").strip()
                    dist_name = (r.get("district_name") or "Unknown").strip()
                    m_name = (r.get("mandal_name") or "Central").strip()
                    v_name = (r.get("village_name") or v_id).strip()
                    st_code = "TS" if "telangana" in st_name.lower() else (st_name[:2].upper() if len(st_name) >= 2 else "TS")
                    conn.execute("INSERT OR IGNORE INTO geography_states (code, name) VALUES (?, ?)", (st_code, st_name))
                    d_code = dist_name.upper().replace(" ", "_")
                    conn.execute("INSERT OR IGNORE INTO geography_districts (code, state_code, name) VALUES (?, ?, ?)", (d_code, st_code, dist_name))
                    man_code = f"{d_code}_{m_name.upper().replace(' ', '_')}"
                    conn.execute("INSERT OR IGNORE INTO geography_mandals (code, district_code, name) VALUES (?, ?, ?)", (man_code, d_code, m_name))
                    p_load = {
                        "id": v_id,
                        "name": v_name,
                        "state": st_name,
                        "district": dist_name,
                        "block": m_name,
                        "latitude": r.get("latitude") if r.get("latitude") is not None else 17.5,
                        "longitude": r.get("longitude") if r.get("longitude") is not None else 79.2,
                        "population": {"value": 3000, "year": 2024, "source": "CSV import auto-registered"},
                        "dimensions": {},
                        "evidence_type": "uploaded-unverified",
                        "data_notice": "IMPORTED FROM DEVELOPMENT DATA CSV",
                    }
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO villages (
                            id, district, payload, updated_at, state_code, district_code, mandal_code, mandal, is_demo, data_origin
                        ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, 0, 'imported-csv')
                        """,
                        (v_id, dist_name, json.dumps(p_load), st_code, d_code, man_code, m_name),
                    )
            conn.execute(
                """
                INSERT OR REPLACE INTO development_records (
                    id, village_id, dimension, asset_or_project_name, description, reported_status,
                    start_date, reported_completion_date, last_observed_date, source_name, source_url,
                    source_reference_id, estimated_cost, latitude, longitude, notes, is_demo, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["id"],
                    r["village_id"],
                    r["dimension"],
                    r["asset_or_project_name"],
                    r.get("description", ""),
                    r["reported_status"],
                    r.get("start_date"),
                    r.get("reported_completion_date"),
                    r.get("last_observed_date"),
                    r.get("source_name", filename),
                    r.get("source_url"),
                    r.get("source_reference_id"),
                    r.get("estimated_cost"),
                    r.get("latitude"),
                    r.get("longitude"),
                    r.get("notes"),
                    r.get("is_demo", 0),
                    batch_id,
                ),
            )
        batch = conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
    return dict(batch)


def list_import_batches(limit: int = 50) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM import_batches ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_import_batch_detail(batch_id: str) -> Optional[dict]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM import_batches WHERE id = ?", (batch_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        errors = conn.execute("SELECT row_number, error_reason, raw_data FROM import_row_errors WHERE batch_id = ?", (batch_id,)).fetchall()
        res["errors"] = [dict(e) for e in errors]
    return res


def list_development_records(
    village_id: Optional[str] = None,
    dimension: Optional[str] = None,
    reported_status: Optional[str] = None,
) -> list[dict]:
    init_db()
    with connect() as conn:
        query = "SELECT * FROM development_records WHERE 1=1"
        params: list[Any] = []
        if village_id:
            query += " AND village_id = ?"
            params.append(village_id)
        if dimension:
            query += " AND dimension = ?"
            params.append(dimension)
        if reported_status:
            query += " AND reported_status = ?"
            params.append(reported_status)
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_development_record(record_id: str) -> Optional[dict]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM development_records WHERE id = ?", (record_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Evidence Submissions, Attachments, and AI Analyses
# ---------------------------------------------------------------------------
def create_evidence_submission(
    record_id: str,
    village_id: str,
    user_id: str,
    observed_status: str,
    notes: Optional[str],
    capture_latitude: Optional[float],
    capture_longitude: Optional[float],
    capture_accuracy: Optional[float],
    client_capture_time: Optional[str],
    user_ai_verdict_notes: Optional[str] = None,
) -> int:
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO evidence_submissions (
                record_id, village_id, user_id, observed_status, notes,
                capture_latitude, capture_longitude, capture_accuracy,
                client_capture_time, user_ai_verdict_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                village_id,
                user_id,
                observed_status,
                notes,
                capture_latitude,
                capture_longitude,
                capture_accuracy,
                client_capture_time,
                user_ai_verdict_notes,
            ),
        )
        return cur.lastrowid


def save_attachment(
    submission_id: int,
    storage_key: str,
    original_filename: str,
    content_type: str,
    file_size_bytes: int,
    file_sha256: str,
) -> dict:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO attachments (submission_id, storage_key, original_filename, content_type, file_size_bytes, file_sha256)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (submission_id, storage_key, original_filename, content_type, file_size_bytes, file_sha256),
        )
        row = conn.execute("SELECT * FROM attachments WHERE storage_key = ?", (storage_key,)).fetchone()
    return dict(row)


def get_attachment_by_key(storage_key: str) -> Optional[dict]:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE storage_key = ?", (storage_key,)).fetchone()
    return dict(row) if row else None


def save_ai_analysis(submission_id: int, analysis: dict) -> dict:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO ai_analyses (
                submission_id, status, provider, model_name, summary, visible_elements_json,
                relation_to_claim, apparent_condition, observations, uncertainties_and_limitations,
                possible_privacy_or_safety_issue, recommended_human_review, analyzed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                analysis.get("status", "complete"),
                analysis.get("provider", "gemini"),
                analysis.get("model_name", "gemini-1.5-flash"),
                analysis.get("summary", ""),
                json.dumps(analysis.get("visible_elements", [])),
                analysis.get("relation_to_claim", "inconclusive"),
                analysis.get("apparent_condition", "not_assessable"),
                analysis.get("observations", ""),
                analysis.get("uncertainties_and_limitations", ""),
                analysis.get("possible_privacy_or_safety_issue", "none_detected"),
                analysis.get("recommended_human_review", "standard"),
                analysis.get("analyzed_at", _now_iso()),
                analysis.get("error_message"),
            ),
        )
        row = conn.execute("SELECT * FROM ai_analyses WHERE submission_id = ?", (submission_id,)).fetchone()
    return dict(row)


def get_evidence_submission(submission_id: int) -> Optional[dict]:
    init_db()
    with connect() as conn:
        sub = conn.execute("SELECT * FROM evidence_submissions WHERE id = ?", (submission_id,)).fetchone()
        if not sub:
            return None
        res = dict(sub)
        att = conn.execute("SELECT storage_key, original_filename, content_type, file_size_bytes, created_at FROM attachments WHERE submission_id = ?", (submission_id,)).fetchone()
        res["attachment"] = dict(att) if att else None
        ai = conn.execute("SELECT * FROM ai_analyses WHERE submission_id = ?", (submission_id,)).fetchone()
        if ai:
            ai_dict = dict(ai)
            ai_dict["visible_elements"] = json.loads(ai_dict.pop("visible_elements_json", "[]"))
            res["ai_analysis"] = ai_dict
        else:
            res["ai_analysis"] = None
        rec = conn.execute("SELECT * FROM development_records WHERE id = ?", (res["record_id"],)).fetchone()
        res["record"] = dict(rec) if rec else None
    return res


def list_submissions(
    village_id: Optional[str] = None,
    record_id: Optional[str] = None,
    user_id: Optional[str] = None,
    review_status: Optional[str] = None,
    discrepancy_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    init_db()
    with connect() as conn:
        query = """
            SELECT s.*, r.asset_or_project_name, r.dimension, r.reported_status as claimed_status,
                   u.username as submitter_username, a.storage_key
            FROM evidence_submissions s
            JOIN development_records r ON s.record_id = r.id
            JOIN users u ON s.user_id = u.id
            LEFT JOIN attachments a ON s.id = a.submission_id
            WHERE 1=1
        """
        params: list[Any] = []
        if village_id:
            query += " AND s.village_id = ?"
            params.append(village_id)
        if record_id:
            query += " AND s.record_id = ?"
            params.append(record_id)
        if user_id:
            query += " AND s.user_id = ?"
            params.append(user_id)
        if review_status and review_status != "all":
            query += " AND s.review_status = ?"
            params.append(review_status)
        query += " ORDER BY s.id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

    results = []
    for r in rows:
        item = dict(r)
        # Check if discrepancy exists
        claimed = item.get("claimed_status", "").lower()
        observed = item.get("observed_status", "").lower()
        is_discrepant = (
            claimed in ("reportedly_completed", "operational")
            and observed in ("exists_but_incomplete", "exists_but_damaged_or_not_functional", "not_found_at_location")
        )
        item["is_discrepancy"] = is_discrepant
        if discrepancy_only and not is_discrepant:
            continue
        results.append(item)
    return results


def update_submission_user_review(submission_id: int, user_id: str, user_ai_verdict_notes: str) -> bool:
    init_db()
    with connect() as conn:
        cur = conn.execute(
            "UPDATE evidence_submissions SET user_ai_verdict_notes = ? WHERE id = ? AND user_id = ?",
            (user_ai_verdict_notes, submission_id, user_id),
        )
        return cur.rowcount > 0


def review_submission(submission_id: int, reviewer_id: str, review_status: str, review_note: Optional[str]) -> Optional[dict]:
    init_db()
    with connect() as conn:
        now = _now_iso()
        conn.execute(
            """
            UPDATE evidence_submissions
            SET review_status = ?, reviewer_id = ?, review_note = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (review_status, reviewer_id, review_note, now, submission_id),
        )
        create_audit_event(
            actor_id=reviewer_id,
            actor_role="admin",
            action="review_submission",
            target_type="evidence_submission",
            target_id=str(submission_id),
            details={"review_status": review_status, "review_note": review_note},
            conn=conn,
        )
    return get_evidence_submission(submission_id)


# ---------------------------------------------------------------------------
# Indicator Promotion & Verification Summaries
# ---------------------------------------------------------------------------
def promote_indicator(
    submission_id: int,
    village_id: str,
    dimension: str,
    indicator_name: str,
    promoted_value: float,
    reason: str,
    promoted_by: str,
) -> dict:
    init_db()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO promoted_indicators (submission_id, village_id, dimension, indicator_name, promoted_value, reason, promoted_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (submission_id, village_id, dimension, indicator_name, promoted_value, reason, promoted_by),
        )
        pid = cur.lastrowid
        create_audit_event(
            actor_id=promoted_by,
            actor_role="admin",
            action="promote_indicator",
            target_type="promoted_indicator",
            target_id=str(pid),
            details={
                "submission_id": submission_id,
                "village_id": village_id,
                "dimension": dimension,
                "indicator_name": indicator_name,
                "promoted_value": promoted_value,
                "reason": reason,
            },
            conn=conn,
        )
        row = conn.execute("SELECT * FROM promoted_indicators WHERE id = ?", (pid,)).fetchone()
    return dict(row)


def list_promoted_indicators(village_id: Optional[str] = None) -> list[dict]:
    init_db()
    with connect() as conn:
        if village_id:
            rows = conn.execute("SELECT * FROM promoted_indicators WHERE village_id = ? ORDER BY id DESC", (village_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM promoted_indicators ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def create_audit_event(
    actor_id: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    details: Optional[dict] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    if conn:
        conn.execute(
            """
            INSERT INTO audit_events (actor_id, actor_role, action, target_type, target_id, details_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor_id, actor_role, action, target_type, target_id, json.dumps(details or {})),
        )
    else:
        init_db()
        with connect() as c:
            c.execute(
                """
                INSERT INTO audit_events (actor_id, actor_role, action, target_type, target_id, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (actor_id, actor_role, action, target_type, target_id, json.dumps(details or {})),
            )


def list_audit_events(limit: int = 100) -> list[dict]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    results = []
    for r in rows:
        item = dict(r)
        item["details"] = json.loads(item.pop("details_json", "{}"))
        results.append(item)
    return results


def get_village_verification_summary(village_id: str) -> dict:
    init_db()
    with connect() as conn:
        # Total records
        tot_records = conn.execute("SELECT COUNT(*) as c FROM development_records WHERE village_id = ?", (village_id,)).fetchone()["c"]

        # Distinct records with at least one submission
        covered = conn.execute("SELECT COUNT(DISTINCT record_id) as c FROM evidence_submissions WHERE village_id = ?", (village_id,)).fetchone()["c"]

        # Submissions counts
        all_subs = conn.execute(
            """
            SELECT s.observed_status, s.review_status, r.reported_status as claimed_status
            FROM evidence_submissions s
            JOIN development_records r ON s.record_id = r.id
            WHERE s.village_id = ?
            """,
            (village_id,),
        ).fetchall()

    total_subs = len(all_subs)
    awaiting_review = sum(1 for s in all_subs if s["review_status"] == "unverified")
    reviewed_count = sum(1 for s in all_subs if s["review_status"] == "verified")

    # Discrepancies
    discrepancy_count = 0
    agreement_count = 0
    for s in all_subs:
        claimed = (s["claimed_status"] or "").lower()
        observed = (s["observed_status"] or "").lower()
        if claimed in ("reportedly_completed", "operational"):
            if observed in ("exists_but_incomplete", "exists_but_damaged_or_not_functional", "not_found_at_location"):
                discrepancy_count += 1
            elif observed == "matches_and_appears_functional":
                agreement_count += 1

    coverage_pct = round((covered / tot_records * 100.0), 1) if tot_records > 0 else 0.0
    discrepancy_rate = round((discrepancy_count / total_subs * 100.0), 1) if total_subs > 0 else 0.0
    agreement_rate = round((agreement_count / total_subs * 100.0), 1) if total_subs > 0 else 0.0

    return {
        "village_id": village_id,
        "total_development_records": tot_records,
        "covered_development_records": covered,
        "response_coverage_percent": coverage_pct,
        "total_submissions": total_subs,
        "awaiting_review_count": awaiting_review,
        "verified_submissions_count": reviewed_count,
        "discrepancy_count": discrepancy_count,
        "discrepancy_rate_percent": discrepancy_rate,
        "agreement_count": agreement_count,
        "agreement_rate_percent": agreement_rate,
        "data_notice": "Verification summary reflects community-submitted and reviewed evidence. It does not replace baseline official census data without explicit promotion.",
    }
