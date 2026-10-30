from pymongo import MongoClient
from datetime import datetime, timedelta
from flask_login import UserMixin
import bcrypt
import uuid

class Database:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        
        # Collections
        self.users = self.db.users
        self.classrooms = self.db.classrooms
        self.sessions = self.db.sessions
        self.attendance = self.db.attendance
        self.proxy_attempts = self.db.proxy_attempts
        
        # Create indexes
        self._create_indexes()
    
    def _create_indexes(self):
        self.users.create_index('email', unique=True)
        self.users.create_index('role')
        self.classrooms.create_index('name')
        self.sessions.create_index('session_id', unique=True)
        self.sessions.create_index('expires_at')
        self.sessions.create_index('class_id')
        self.attendance.create_index([('student_id', 1), ('session_id', 1)], unique=True)
        self.attendance.create_index('session_id')
        self.attendance.create_index('student_id')
        self.proxy_attempts.create_index('timestamp')

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.name = user_data['name']
        self.role = user_data['role']
        self.class_id = user_data.get('class_id')
        self.created_at = user_data.get('created_at')
    
    @staticmethod
    def hash_password(password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    @staticmethod
    def verify_password(password, hashed):
        if not password or not hashed:
            return False
        try:
            if isinstance(hashed, str):
                hashed = hashed.encode('utf-8')
            return bcrypt.checkpw(password.encode('utf-8'), bytes(hashed))
        except Exception:
            return False
    
    @staticmethod
    def create_user(db, email, name, password, role='student', class_id=None):
        user_data = {
            'email': email,
            'name': name,
            'password': User.hash_password(password),
            'role': role,
            'class_id': class_id,
            'created_at': datetime.utcnow()
        }
        result = db.users.insert_one(user_data)
        user_data['_id'] = result.inserted_id
        return User(user_data)
    
    @staticmethod
    def get_by_email(db, email):
        if not email:
            return None
        import re
        clean_email = email.strip()
        pattern = re.compile('^' + re.escape(clean_email) + '$', re.IGNORECASE)
        user_data = db.users.find_one({'email': pattern})
        if user_data:
            return User(user_data)
        return None
    
    @staticmethod
    def get_by_id(db, user_id):
        from bson.objectid import ObjectId
        if not user_id or not ObjectId.is_valid(user_id):
            return None
        user_data = db.users.find_one({'_id': ObjectId(user_id)})
        if user_data:
            return User(user_data)
        return None

class Classroom:
    @staticmethod
    def create(db, name, latitude, longitude, created_by):
        classroom_data = {
            'name': name,
            'latitude': float(latitude),
            'longitude': float(longitude),
            'created_by': created_by,
            'created_at': datetime.utcnow()
        }
        result = db.classrooms.insert_one(classroom_data)
        classroom_data['_id'] = result.inserted_id
        return classroom_data
    
    @staticmethod
    def update(db, classroom_id, name=None, latitude=None, longitude=None):
        from bson.objectid import ObjectId
        if not classroom_id:
            return None
        query = {'_id': ObjectId(classroom_id)} if ObjectId.is_valid(classroom_id) else {'_id': classroom_id}
        update_data = {}
        if name is not None and str(name).strip():
            update_data['name'] = str(name).strip()
        if latitude is not None and str(latitude).strip():
            update_data['latitude'] = float(latitude)
        if longitude is not None and str(longitude).strip():
            update_data['longitude'] = float(longitude)
        if update_data:
            update_data['updated_at'] = datetime.utcnow()
            db.classrooms.update_one(query, {'$set': update_data})
        return Classroom.get_by_id(db, classroom_id)

    @staticmethod
    def delete(db, classroom_id):
        from bson.objectid import ObjectId
        if not classroom_id:
            return False
        query = {'_id': ObjectId(classroom_id)} if ObjectId.is_valid(classroom_id) else {'_id': classroom_id}
        res = db.classrooms.delete_one(query)
        return res.deleted_count > 0

    @staticmethod
    def get_all(db):
        return list(db.classrooms.find())
    
    @staticmethod
    def get_by_id(db, classroom_id):
        from bson.objectid import ObjectId
        if not classroom_id:
            return None
        if ObjectId.is_valid(classroom_id):
            found = db.classrooms.find_one({'_id': ObjectId(classroom_id)})
            if found:
                return found
        return db.classrooms.find_one({'_id': classroom_id})

class Session:
    @staticmethod
    def create(db, class_id, created_by, expiry_minutes=2):
        session_data = {
            'session_id': str(uuid.uuid4()),
            'class_id': class_id,
            'random_token': uuid.uuid4().hex,
            'created_by': created_by,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(minutes=expiry_minutes),
            'is_active': True
        }
        db.sessions.insert_one(session_data)
        return session_data
    
    @staticmethod
    def get_by_session_id(db, session_id):
        return db.sessions.find_one({'session_id': session_id})
    
    @staticmethod
    def is_valid(session):
        if not session or not session.get('is_active'):
            return False, "Invalid session"
        
        if datetime.utcnow() > session['expires_at']:
            return False, "QR code expired"
        
        return True, "Valid"
    
    @staticmethod
    def deactivate(db, session_id):
        db.sessions.update_one(
            {'session_id': session_id},
            {'$set': {'is_active': False}}
        )

class Attendance:
    @staticmethod
    def mark(db, student_id, session_id, latitude, longitude):
        attendance_data = {
            'student_id': student_id,
            'session_id': session_id,
            'latitude': latitude,
            'longitude': longitude,
            'marked_at': datetime.utcnow()
        }
        try:
            db.attendance.insert_one(attendance_data)
            return True
        except:
            return False
    
    @staticmethod
    def get_by_session(db, session_id):
        return list(db.attendance.find({'session_id': session_id}))
    
    @staticmethod
    def get_by_student(db, student_id):
        return list(db.attendance.find({'student_id': student_id}))
    
    @staticmethod
    def check_already_marked(db, student_id, session_id):
        return db.attendance.find_one({
            'student_id': student_id,
            'session_id': session_id
        }) is not None

class ProxyAttempt:
    @staticmethod
    def log(db, student_id, session_id, latitude, longitude, expected_lat, expected_lng, reason):
        attempt_data = {
            'student_id': student_id,
            'session_id': session_id,
            'scanned_location': {
                'latitude': latitude,
                'longitude': longitude
            },
            'expected_location': {
                'latitude': expected_lat,
                'longitude': expected_lng
            },
            'reason': reason,
            'timestamp': datetime.utcnow()
        }
        db.proxy_attempts.insert_one(attempt_data)
    
    @staticmethod
    def get_all(db):
        return list(db.proxy_attempts.find().sort('timestamp', -1))
    
    @staticmethod
    def get_by_session(db, session_id):
        return list(db.proxy_attempts.find({'session_id': session_id}))
