import os

# Gunicorn configuration file for Render / Production
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"

# Number of worker processes
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
threads = int(os.environ.get("PYTHON_GET_MAX_THREADS", 2))

# Application entry point
wsgi_app = "app:app"

# Timeout
timeout = 120
keepalive = 5
