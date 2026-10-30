# GeoAttend Backend API

RESTful API backend for **GeoAttend** — Smart Geofenced Classroom Attendance System built with Flask, MongoDB, and GPS verification.

---

## Features

- **Role-Based Access Control (RBAC):** Admin and Student roles with persistent session authentication via Flask-Login.
- **Geofence Boundary Enforcement:** Real-time Haversine distance verification enforcing strict 30-meter classroom perimeters.
- **Dynamic QR Generation & Auto-Expiry:** Generates cryptographic attendance tokens with automatic expiry (default: 2 minutes).
- **Automated Anti-Proxy Auditing:** Flags and logs unauthorized attendance attempts, GPS spoofing, and perimeter breaches with exact coordinates and distances.
- **Automated Email Credentials:** Automatically generates and delivers secure student login credentials via Google SMTP (Flask-Mail).
- **Comprehensive Audit Reports:** Detailed attendance reports per session with CSV export and turnout percentage metrics.

---

## Tech Stack

- **Runtime:** Python 3.10+
- **Framework:** Flask 3.0+
- **Database:** MongoDB (PyMongo)
- **Authentication:** Flask-Login, Bcrypt
- **Email Delivery:** Flask-Mail
- **QR Code Generation:** qrcode, Pillow
- **Data Export & Reporting:** Pandas, OpenPyXL
- **CORS:** Flask-CORS

---

## Quickstart

### 1. Clone & Navigate
```bash
git clone https://github.com/shashidharpc/GeoAttend-Backend.git
cd GeoAttend-Backend
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your settings:
```bash
cp .env.example .env
```

Ensure your MongoDB instance is running locally on port 27017 or provide your MongoDB Atlas connection string.

### 5. Start the Server
```bash
python app.py
```
The server will boot on `http://127.0.0.1:5000` with the default administrator account created automatically (`admin@edu.com` / `admin1234`).

---

## Environment Configuration

See [`.env.example`](.env.example) for all available options:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `SECRET_KEY` | Cryptographic key for session signing | Required in production |
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017/` |
| `MONGO_DB_NAME` | Primary application database | `qr_attendance_db` |
| `ADMIN_EMAIL` | Initial administrator email | `admin@edu.com` |
| `ADMIN_PASSWORD` | Initial administrator password | `admin1234` |
| `ALLOWED_RADIUS_METERS` | Classroom geofence radius limit | `30` |
| `QR_EXPIRY_MINUTES` | QR token auto-expiry lifetime | `2` |
| `MAIL_USERNAME` | SMTP sender email | Optional for email delivery |
| `MAIL_PASSWORD` | Google App Password | Optional for email delivery |

---

## License

MIT License. Designed and maintained for GeoAttend.
