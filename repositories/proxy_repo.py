"""
Proxy Attempt Repository for Firestore
Logs and audits geofencing violations and suspicious scan attempts.
"""
from datetime import datetime

class ProxyAttemptRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.collection('proxy_attempts')

    @staticmethod
    def _format_doc(doc_id, data):
        if not data:
            return None
        res = dict(data)
        res['id'] = doc_id
        res['_id'] = doc_id
        return res

    def log(self, student_id, session_id, latitude, longitude, expected_lat, expected_lng, reason):
        now = datetime.utcnow()
        attempt_data = {
            'student_id': str(student_id) if student_id else None,
            'session_id': str(session_id) if session_id else None,
            'scanned_location': {
                'latitude': float(latitude),
                'longitude': float(longitude)
            },
            'expected_location': {
                'latitude': float(expected_lat),
                'longitude': float(expected_lng)
            },
            'reason': str(reason),
            'timestamp': now
        }
        try:
            _, doc_ref = self.col.add(attempt_data)
            return self._format_doc(doc_ref.id, attempt_data)
        except Exception as e:
            print(f"[ProxyAttemptRepository Error] log failed: {e}")
            return None

    def get_all(self, limit_count=None):
        try:
            docs = list(self.col.stream())
            attempts = [self._format_doc(d.id, d.to_dict()) for d in docs]
            attempts.sort(
                key=lambda a: a.get('timestamp') or datetime.min,
                reverse=True
            )
            if limit_count:
                return attempts[:limit_count]
            return attempts
        except Exception as e:
            print(f"[ProxyAttemptRepository Error] get_all failed: {e}")
            return []

    def get_by_session(self, session_id):
        if not session_id:
            return []
        try:
            query = self.col.where('session_id', '==', str(session_id))
            return [self._format_doc(d.id, d.to_dict()) for d in query.stream()]
        except Exception as e:
            print(f"[ProxyAttemptRepository Error] get_by_session({session_id}) failed: {e}")
            return []

    def count(self):
        try:
            return len(list(self.col.stream()))
        except Exception:
            return 0
