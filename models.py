"""
Application Models & Database Interface
Provides model wrappers for Flask-Login, User management, Classrooms,
Ephemeral Sessions, Attendance marking, and Anti-Proxy auditing.
Powered by the Firestore repository layer.
"""
from datetime import datetime, timedelta
from flask_login import UserMixin
from repositories import firestore_service

class Database:
    """
    Database compatibility layer wrapping FirestoreService.
    Provides direct repository access:
    db.users, db.classrooms, db.sessions, db.attendance, db.proxy_attempts
    """
    def __init__(self, *args, **kwargs):
        self.service = firestore_service
        self.is_mock = self.service.is_mock
        self.client = self.service.client
        self.db = self

        self.users = self.service.users
        self.classrooms = self.service.classrooms
        self.sessions = self.service.sessions
        self.attendance = self.service.attendance
        self.proxy_attempts = self.service.proxy_attempts

    def command(self, cmd):
        """Simulates database ping for healthcheck verification"""
        ok, msg = self.service.ping()
        if not ok:
            raise Exception(msg)
        return {'ok': 1.0}


class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data.get('id') or user_data.get('_id'))
        self.email = user_data.get('email')
        self.name = user_data.get('name')
        self.role = user_data.get('role', 'student')
        self.class_id = user_data.get('class_id')
        self.created_at = user_data.get('created_at')

    @staticmethod
    def hash_password(password):
        return firestore_service.users.hash_password(password)

    @staticmethod
    def verify_password(password, hashed):
        return firestore_service.users.verify_password(password, hashed)

    @staticmethod
    def create_user(db, email, name, password, role='student', class_id=None):
        data = firestore_service.users.create_user(
            email=email,
            name=name,
            password=password,
            role=role,
            class_id=class_id
        )
        return User(data)

    @staticmethod
    def get_by_email(db, email):
        data = firestore_service.users.get_by_email(email)
        return User(data) if data else None

    @staticmethod
    def get_by_id(db, user_id):
        data = firestore_service.users.get_by_id(user_id)
        return User(data) if data else None


class Classroom:
    @staticmethod
    def create(db, name, latitude, longitude, created_by):
        return firestore_service.classrooms.create(name, latitude, longitude, created_by)

    @staticmethod
    def update(db, classroom_id, name=None, latitude=None, longitude=None):
        return firestore_service.classrooms.update(classroom_id, name=name, latitude=latitude, longitude=longitude)

    @staticmethod
    def delete(db, classroom_id):
        return firestore_service.classrooms.delete(classroom_id)

    @staticmethod
    def get_all(db):
        return firestore_service.classrooms.get_all()

    @staticmethod
    def get_by_id(db, classroom_id):
        return firestore_service.classrooms.get_by_id(classroom_id)


class Session:
    @staticmethod
    def create(db, class_id, created_by, expiry_minutes=2):
        return firestore_service.sessions.create(class_id, created_by, expiry_minutes=expiry_minutes)

    @staticmethod
    def get_by_session_id(db, session_id):
        return firestore_service.sessions.get_by_session_id(session_id)

    @staticmethod
    def is_valid(session):
        return firestore_service.sessions.is_valid(session)

    @staticmethod
    def deactivate(db, session_id):
        return firestore_service.sessions.deactivate(session_id)


class Attendance:
    @staticmethod
    def mark(db, student_id, session_id, latitude, longitude):
        return firestore_service.attendance.mark(student_id, session_id, latitude, longitude)

    @staticmethod
    def get_by_session(db, session_id):
        return firestore_service.attendance.get_by_session(session_id)

    @staticmethod
    def get_by_student(db, student_id):
        return firestore_service.attendance.get_by_student(student_id)

    @staticmethod
    def check_already_marked(db, student_id, session_id):
        return firestore_service.attendance.check_already_marked(student_id, session_id)


class ProxyAttempt:
    @staticmethod
    def log(db, student_id, session_id, latitude, longitude, expected_lat, expected_lng, reason):
        return firestore_service.proxy_attempts.log(
            student_id, session_id, latitude, longitude, expected_lat, expected_lng, reason
        )

    @staticmethod
    def get_all(db):
        return firestore_service.proxy_attempts.get_all()

    @staticmethod
    def get_by_session(db, session_id):
        return firestore_service.proxy_attempts.get_by_session(session_id)
