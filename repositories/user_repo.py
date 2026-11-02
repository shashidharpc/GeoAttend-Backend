"""
User Repository for Firestore
Manages authentication, student records, and role-based access.
"""
from datetime import datetime
import bcrypt
import re

class UserRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.collection('users')

    @staticmethod
    def hash_password(password):
        if isinstance(password, str):
            password = password.encode('utf-8')
        return bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')

    @staticmethod
    def verify_password(password, hashed):
        if not password or not hashed:
            return False
        try:
            if isinstance(password, str):
                password = password.encode('utf-8')
            if isinstance(hashed, str):
                hashed = hashed.encode('utf-8')
            return bcrypt.checkpw(password, hashed)
        except Exception:
            return False

    @staticmethod
    def _format_doc(doc_id, data):
        if not data:
            return None
        res = dict(data)
        res['id'] = doc_id
        res['_id'] = doc_id
        return res

    def get_by_id(self, user_id):
        if not user_id:
            return None
        try:
            doc = self.col.document(str(user_id)).get()
            if doc.exists:
                return self._format_doc(doc.id, doc.to_dict())
        except Exception as e:
            print(f"[UserRepository Error] get_by_id({user_id}) failed: {e}")
        return None

    def get_by_email(self, email):
        if not email:
            return None
        clean_email = email.strip().lower()
        try:
            # First attempt exact lowercase match
            query = self.col.where('email', '==', clean_email).limit(1)
            docs = list(query.stream())
            if docs:
                return self._format_doc(docs[0].id, docs[0].to_dict())

            # Fallback search for mixed-case email entries
            all_users = self.col.stream()
            for doc in all_users:
                data = doc.to_dict()
                if (data.get('email') or '').strip().lower() == clean_email:
                    return self._format_doc(doc.id, data)
        except Exception as e:
            print(f"[UserRepository Error] get_by_email({email}) failed: {e}")
        return None

    def create_user(self, email, name, password, role='student', class_id=None, custom_id=None):
        clean_email = email.strip().lower()
        hashed = self.hash_password(password)
        now = datetime.utcnow()
        user_data = {
            'email': clean_email,
            'name': name.strip() if name else '',
            'password': hashed,
            'role': role,
            'class_id': class_id,
            'created_at': now
        }
        if custom_id:
            doc_ref = self.col.document(str(custom_id))
            doc_ref.set(user_data)
        else:
            _, doc_ref = self.col.add(user_data)

        return self._format_doc(doc_ref.id, user_data)

    def update_user(self, user_id, update_fields):
        if not user_id or not update_fields:
            return False
        try:
            fields = dict(update_fields)
            if 'password' in fields and fields['password']:
                fields['password'] = self.hash_password(fields['password'])
            if 'email' in fields and fields['email']:
                fields['email'] = fields['email'].strip().lower()
            fields['updated_at'] = datetime.utcnow()

            self.col.document(str(user_id)).update(fields)
            return True
        except Exception as e:
            print(f"[UserRepository Error] update_user failed: {e}")
            return False

    def delete_user(self, user_id):
        if not user_id:
            return False
        try:
            self.col.document(str(user_id)).delete()
            return True
        except Exception as e:
            print(f"[UserRepository Error] delete_user failed: {e}")
            return False

    def get_students(self, class_id=None):
        try:
            query = self.col.where('role', '==', 'student')
            if class_id:
                query = query.where('class_id', '==', str(class_id))
            
            docs = query.stream()
            students = [self._format_doc(d.id, d.to_dict()) for d in docs]
            # Sort by created_at descending in memory (avoids requiring compound indexes in Firestore)
            students.sort(
                key=lambda s: s.get('created_at') or datetime.min,
                reverse=True
            )
            return students
        except Exception as e:
            print(f"[UserRepository Error] get_students failed: {e}")
            return []

    def count_students(self, class_id=None):
        try:
            query = self.col.where('role', '==', 'student')
            if class_id:
                query = query.where('class_id', '==', str(class_id))
            return len(list(query.stream()))
        except Exception:
            return 0

    def count_all(self):
        try:
            return len(list(self.col.stream()))
        except Exception:
            return 0

