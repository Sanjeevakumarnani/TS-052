from pathlib import Path
import os

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
SEED_FILE = DATA_DIR / "villages.json"

# In production (Render), use DATABASE_URL for Neon PostgreSQL.
# Locally falls back to SQLite.
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
DB_FILE = DATA_DIR / "infrapulse.sqlite3"  # SQLite fallback for local dev

API_VERSION = "1.0.0"

CORS_ORIGINS = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if origin.strip()]

# Security & Session Authentication
SESSION_SECRET: str = os.getenv("SESSION_SECRET", "infrapulse-default-insecure-secret-key-change-in-prod")
ADMIN_BOOTSTRAP_USERNAME: str = os.getenv("ADMIN_BOOTSTRAP_USERNAME", "")
ADMIN_BOOTSTRAP_PASSWORD: str = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "")
REVIEWER_TOKEN: str = os.getenv("REVIEWER_TOKEN", "")

# Geolocation verification parameters
LOCATION_MATCH_RADIUS_METERS: float = float(os.getenv("LOCATION_MATCH_RADIUS_METERS", "5000.0"))

# AI Vision Configuration
VISION_AI_PROVIDER: str = os.getenv("VISION_AI_PROVIDER", "gemini")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
VISION_AI_MODEL: str = os.getenv("VISION_AI_MODEL", "gemini-1.5-flash")
VISION_AI_TIMEOUT: float = float(os.getenv("VISION_AI_TIMEOUT", "25.0"))

# Rate Limiting
RATE_LIMIT_REPORTS: int = int(os.getenv("RATE_LIMIT_REPORTS", "10"))
RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "3600"))
RATE_LIMIT_LOGIN: int = int(os.getenv("RATE_LIMIT_LOGIN", "20"))

# Derived flag: use PostgreSQL if DATABASE_URL is set
USE_POSTGRES: bool = bool(DATABASE_URL and DATABASE_URL.startswith(("postgresql", "postgres")))
