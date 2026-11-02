"""
Session Repository for Firestore
Manages dynamic ephemeral QR sessions and validity windows.
"""
from datetime import datetime, timedelta
import uuid

class SessionRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.collection('sessions')

    @staticmethod
    def _format_doc(doc_id, data):
        if not data:
            return None
        res = dict(data)
        res['id'] = doc_id
        res['_id'] = doc_id
        return res

    def create(self, class_id, created_by, expiry_minutes=2, custom_session_id=None):
        session_id = str(custom_session_id) if custom_session_id else str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=int(expiry_minutes))

        session_data = {
            'session_id': session_id,
            'class_id': str(class_id),
            'random_token': uuid.uuid4().hex,
            'created_by': str(created_by),
            'created_at': now,
            'expires_at': expires_at,
            'is_active': True
        }

        # Store using session_id as the document ID for O(1) instantaneous lookup
        self.col.document(session_id).set(session_data)
        return self._format_doc(session_id, session_data)

    def get_by_session_id(self, session_id):
        if not session_id:
            return None
        sid = str(session_id).strip()
        try:
            # Primary O(1) lookup
            doc = self.col.document(sid).get()
            if doc.exists:
                return self._format_doc(doc.id, doc.to_dict())

            # Fallback search if doc ID differs
            query = self.col.where('session_id', '==', sid).limit(1)
            docs = list(query.stream())
            if docs:
                return self._format_doc(docs[0].id, docs[0].to_dict())
        except Exception as e:
            print(f"[SessionRepository Error] get_by_session_id({sid}) failed: {e}")
        return None

    def is_valid(self, session):
        if not session or not session.get('is_active'):
            return False, "Invalid session"

        expires_at = session.get('expires_at')
        if not expires_at:
            return False, "Malformed session"

        # Handle Firestore DatetimeWithNanoseconds vs Python datetime
        if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
            # Aware datetime (convert to naive UTC for comparison)
            from datetime import timezone
            now_aware = datetime.now(timezone.utc)
            if now_aware > expires_at:
                return False, "QR code expired"
        else:
            if datetime.utcnow() > expires_at:
                return False, "QR code expired"

        return True, "Valid"

    def deactivate(self, session_id):
        if not session_id:
            return False
        sid = str(session_id).strip()
        try:
            doc_ref = self.col.document(sid)
            if doc_ref.get().exists:
                doc_ref.update({'is_active': False})
                return True
            
            query = self.col.where('session_id', '==', sid).limit(1)
            docs = list(query.stream())
            if docs:
                docs[0].reference.update({'is_active': False})
                return True
        except Exception as e:
            print(f"[SessionRepository Error] deactivate({sid}) failed: {e}")
        return False

    def get_by_classroom(self, class_id):
        if not class_id:
            return []
        try:
            query = self.col.where('class_id', '==', str(class_id))
            return [self._format_doc(d.id, d.to_dict()) for d in query.stream()]
        except Exception as e:
            print(f"[SessionRepository Error] get_by_classroom failed: {e}")
            return []

    def get_recent(self, limit_count=6):
        try:
            docs = list(self.col.stream())
            sessions = [self._format_doc(d.id, d.to_dict()) for d in docs]
            sessions.sort(
                key=lambda s: s.get('created_at') or datetime.min,
                reverse=True
            )
            return sessions[:limit_count]
        except Exception as e:
            print(f"[SessionRepository Error] get_recent failed: {e}")
            return []

    def count(self, class_id=None):
        try:
            if class_id:
                query = self.col.where('class_id', '==', str(class_id))
                return len(list(query.stream()))
            return len(list(self.col.stream()))
        except Exception:
            return 0

    def expire_past_sessions(self):
        """Auto-deactivates expired sessions"""
        try:
            now = datetime.utcnow()
            for doc in self.col.where('is_active', '==', True).stream():
                data = doc.to_dict()
                exp = data.get('expires_at')
                if exp and exp < now:
                    doc.reference.update({'is_active': False})
        except Exception as e:
            print(f"[SessionRepository Notice] Session auto-expiration check: {e}")

