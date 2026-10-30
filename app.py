from flask import Flask, send_from_directory, jsonify
from flask_login import LoginManager
from flask_mail import Mail
from flask_cors import CORS
from config import Config
from models import Database, User, Classroom
import os
from bson.objectid import ObjectId

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Enable CORS with credentials support for frontend API integration
CORS(
    app,
    resources={r"/api/*": {"origins": app.config.get('CORS_ORIGINS', ['http://localhost:5173', 'http://127.0.0.1:5173'])}},
    supports_credentials=True
)

app.config['SESSION_COOKIE_SAMESITE'] = app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['SESSION_COOKIE_SECURE'] = app.config.get('SESSION_COOKIE_SECURE', False)
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Initialize database
db = Database(app.config['MONGO_URI'], app.config['MONGO_DB_NAME']).db
# Attach db to app to avoid circular imports from route modules
app.db = db

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.unauthorized_handler
def unauthorized_callback():
    return jsonify({
        'success': False,
        'authenticated': False,
        'error': 'Unauthorized',
        'message': 'Authentication required. Please log in.'
    }), 401

# Initialize Flask-Mail
mail = Mail(app)
app.mail = mail

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(db, user_id)

# Register API Blueprint (REST endpoints for React frontend)
from routes.api import api_bp
app.register_blueprint(api_bp)

REACT_DIST = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')

# Serve React SPA for all frontend routes
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    if os.path.exists(REACT_DIST):
        file_path = os.path.join(REACT_DIST, path)
        if path != "" and os.path.exists(file_path):
            return send_from_directory(REACT_DIST, path)
        else:
            return send_from_directory(REACT_DIST, 'index.html')
    return "React frontend build not found. Run 'npm run build' in the frontend folder.", 500

# Ensure the initial administrator account exists
def init_admin():
    admin = User.get_by_email(db, Config.ADMIN_EMAIL)
    if not admin:
        admin = User.create_user(
            db,
            Config.ADMIN_EMAIL,
            'Administrator',
            Config.ADMIN_PASSWORD,
            role='admin'
        )
        print("Default administrator created successfully!")

if __name__ == '__main__':
    with app.app_context():
        init_admin()
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT)
