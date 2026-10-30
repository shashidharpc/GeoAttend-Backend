import os
from datetime import timedelta
from dotenv import load_dotenv

# Ensure backend/.env is loaded even if run from parent directory
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path, override=True)
else:
    load_dotenv()


class Config:
    """Production & Development Configuration for GeoAttend Backend"""

    # ─── Flask Application & Security ───────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "geoattend_super_secret_jwt_key_2024")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 5000))

    # ─── Environment & Mode Detection ───────────────────────────
    is_production = (
        os.getenv("FLASK_ENV") == "production"
        or os.getenv("RENDER") is not None
        or (os.getenv("PORT") is not None and os.getenv("PORT") != "5000")
    )

    # ─── CORS Allowed Origins ───────────────────────────────────
    _raw_cors = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    ).split(",")
    CORS_ORIGINS = [
        origin.strip()
        for origin in _raw_cors
        if origin.strip()
    ]
    # Automatically permit all Vercel deployments and Render domains
    for _pat in [r"https://.*\.vercel\.app", r"https://.*\.onrender\.com"]:
        if _pat not in CORS_ORIGINS:
            CORS_ORIGINS.append(_pat)

    # ─── MongoDB Database Configuration ─────────────────────────
    MONGO_URI = os.getenv(
        "MONGO_URI",
        "mongodb+srv://shashidharpc_db_user:<db_password>@cluster0.lanadsm.mongodb.net/?retryWrites=true&w=majority"
    )
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "qr_attendance_db")

    # ─── Flask-Login & Session Security ─────────────────────────
    SESSION_LIFETIME_DAYS = int(os.getenv("SESSION_LIFETIME_DAYS", 7))
    REMEMBER_COOKIE_DURATION = timedelta(days=SESSION_LIFETIME_DAYS)
    PERMANENT_SESSION_LIFETIME = timedelta(days=SESSION_LIFETIME_DAYS)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE",
        "true" if is_production else "false"
    ).lower() in ("true", "1", "t")
    SESSION_COOKIE_SAMESITE = os.getenv(
        "SESSION_COOKIE_SAMESITE",
        "None" if is_production else "Lax"
    )

    # ─── Administrator Default Credentials ──────────────────────
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@edu.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")

    # ─── Geofencing & Security Policy ───────────────────────────
    # Strict boundary in meters for physical attendance validation
    ALLOWED_RADIUS_METERS = float(os.getenv("ALLOWED_RADIUS_METERS", 30))
    # Time in minutes before QR code token self-expires
    QR_EXPIRY_MINUTES = int(os.getenv("QR_EXPIRY_MINUTES", 2))

    # ─── Flask-Mail (SMTP Notification Service) ─────────────────
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "t")
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "t")

    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip()
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").replace(" ", "").strip()

    MAIL_SENDER_NAME = os.getenv("MAIL_SENDER_NAME", "GeoAttend Security")
    MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME or "no-reply@geoattend.local")

    MAIL_DEFAULT_SENDER = (
        MAIL_SENDER_NAME,
        MAIL_FROM
    )

    # ─── Geocoding & Maps APIs (Optional Integrations) ──────────
    GEOCODING_API_URL = os.getenv("GEOCODING_API_URL", "https://nominatim.openstreetmap.org")
    MAPS_API_KEY = os.getenv("MAPS_API_KEY", "")
