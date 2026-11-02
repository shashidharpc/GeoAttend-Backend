"""
Attendance Repository for Firestore
Manages attendance check-ins with composite-key deduplication and spatial coordinates.
"""
from datetime import datetime
from google.cloud.firestore import GeoPoint

class AttendanceRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.collection('attendance')

    @staticmethod
    def _doc_id(student_id, session_id):
        return f"{str(student_id).strip()}_{str(session_id).strip()}"

    @staticmethod
    def _format_doc(doc_id, data):
        if not data:
            return None
        res = dict(data)
        res['id'] = doc_id
        res['_id'] = doc_id
        if 'latitude' in res and res['latitude'] is not None:
            res['latitude'] = float(res['latitude'])
        elif 'location' in res and hasattr(res['location'], 'latitude'):
            res['latitude'] = float(res['location'].latitude)
            res['longitude'] = float(res['location'].longitude)

        if 'longitude' in res and res['longitude'] is not None:
            res['longitude'] = float(res['longitude'])
        return res

    def check_already_marked(self, student_id, session_id):
        if not student_id or not session_id:
            return False
        doc_key = self._doc_id(student_id, session_id)
        try:
            doc = self.col.document(doc_key).get()
            if doc.exists:
                return True

            # Fallback search if doc key format differs
            query = self.col.where('student_id', '==', str(student_id)).where('session_id', '==', str(session_id)).limit(1)
            return len(list(query.stream())) > 0
        except Exception as e:
            print(f"[AttendanceRepository Error] check_already_marked failed: {e}")
            return False

    def mark(self, student_id, session_id, latitude, longitude):
        if not student_id or not session_id:
            return False

        if self.check_already_marked(student_id, session_id):
            return False

        doc_key = self._doc_id(student_id, session_id)
        lat = float(latitude)
        lng = float(longitude)
        now = datetime.utcnow()

        attendance_data = {
            'student_id': str(student_id),
            'session_id': str(session_id),
            'latitude': lat,
            'longitude': lng,
            'location': GeoPoint(lat, lng),
            'marked_at': now
        }

        try:
            self.col.document(doc_key).set(attendance_data)
            return True
        except Exception as e:
            print(f"[AttendanceRepository Error] mark failed: {e}")
            return False

    def get_by_session(self, session_id):
        if not session_id:
            return []
        try:
            query = self.col.where('session_id', '==', str(session_id))
            docs = [self._format_doc(d.id, d.to_dict()) for d in query.stream()]
            docs.sort(
                key=lambda a: a.get('marked_at') or datetime.min,
                reverse=True
            )
            return docs
        except Exception as e:
            print(f"[AttendanceRepository Error] get_by_session({session_id}) failed: {e}")
            return []

    def get_by_student(self, student_id):
        if not student_id:
            return []
        try:
            query = self.col.where('student_id', '==', str(student_id))
            docs = [self._format_doc(d.id, d.to_dict()) for d in query.stream()]
            docs.sort(
                key=lambda a: a.get('marked_at') or datetime.min
            )
            return docs
        except Exception as e:
            print(f"[AttendanceRepository Error] get_by_student({student_id}) failed: {e}")
            return []

    def count_for_session(self, session_id):
        if not session_id:
            return 0
        try:
            query = self.col.where('session_id', '==', str(session_id))
            return len(list(query.stream()))
        except Exception:
            return 0

    def count_for_sessions(self, session_ids):
        if not session_ids:
            return 0
        try:
            session_set = set(str(sid) for sid in session_ids)
            total = 0
            for doc in self.col.stream():
                if doc.to_dict().get('session_id') in session_set:
                    total += 1
            return total
        except Exception:
            return 0

    def count_all(self):
        try:
            return len(list(self.col.stream()))
        except Exception:
            return 0

