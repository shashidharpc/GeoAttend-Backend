"""
Firestore Repositories Package
Provides unified access to Firestore collections via repository pattern.
"""
from firebase_init import get_firestore_client
from .user_repo import UserRepository
from .classroom_repo import ClassroomRepository
from .session_repo import SessionRepository
from .attendance_repo import AttendanceRepository
from .proxy_repo import ProxyAttemptRepository

class FirestoreService:
    def __init__(self):
        self.client, self.is_mock = get_firestore_client()
        self.users = UserRepository(self.client)
        self.classrooms = ClassroomRepository(self.client)
        self.sessions = SessionRepository(self.client)
        self.attendance = AttendanceRepository(self.client)
        self.proxy_attempts = ProxyAttemptRepository(self.client)

    def ping(self):
        """Validates database connectivity"""
        if self.is_mock:
            return True, "connected (mock mode)"
        try:
            # Query a single document to verify network & auth
            list(self.client.collection('users').limit(1).stream())
            return True, "connected"
        except Exception as e:
            return False, str(e)

# Global singleton instance
firestore_service = FirestoreService()

__all__ = [
    'FirestoreService',
    'firestore_service',
    'UserRepository',
    'ClassroomRepository',
    'SessionRepository',
    'AttendanceRepository',
    'ProxyAttemptRepository',
]
