"""
MongoDB to Firebase Firestore Migration Tool
Transfers all classrooms, users, sessions, attendances, and proxy logs
from MongoDB (Local or Atlas) directly into Google Cloud Firestore.
"""
import sys
import os
from datetime import datetime
from pymongo import MongoClient
from google.cloud.firestore import GeoPoint

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from firebase_init import get_firestore_client

def migrate(mongo_uri=None, cred_path=None):
    if not mongo_uri:
        mongo_uri = os.getenv("LOCAL_MONGO_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "qr_attendance_db")

    if cred_path:
        os.environ["FIREBASE_CREDENTIALS_PATH"] = cred_path

    print("=" * 65)
    print(">> GeoAttend Database Migration: MongoDB -> Firebase Firestore")
    print("=" * 65)
    print(f"Source Database (MongoDB) : {mongo_uri} -> {db_name}")

    # 1. Connect to Source (MongoDB)
    try:
        mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[db_name]
        available_collections = mongo_db.list_collection_names()
        print(f"Connected to MongoDB. Collections found: {available_collections}\n")
    except Exception as e:
        print(f"[Error] Failed to connect to MongoDB: {e}")
        return False

    # 2. Connect to Target (Firestore)
    firestore_client, is_mock = get_firestore_client()
    if is_mock:
        print("\n[Notice] Running migration against in-memory mock Firestore.")
        print("To migrate to your live cloud project, please specify your service account key:")
        print('Usage: python migrate_to_firestore.py [MONGO_URI] [PATH_TO_SERVICE_ACCOUNT_JSON]')
        print('Example: python migrate_to_firestore.py "mongodb://localhost:27017/" "serviceAccountKey.json"\n')

    total_synced = 0

    # ─── 3. Migrate Users ─────────────────────────────────────────────────────────
    if 'users' in available_collections:
        print("[*] Migrating 'users' collection...")
        user_docs = list(mongo_db.users.find())
        print(f"  Found {len(user_docs)} users in MongoDB.")
        
        batch = firestore_client.batch()
        batch_count = 0
        migrated_users = 0

        for u in user_docs:
            user_id = str(u['_id'])
            ref = firestore_client.collection('users').document(user_id)
            
            # Format password
            pwd = u.get('password')
            if isinstance(pwd, bytes):
                pwd = pwd.decode('utf-8', errors='ignore')

            # Format created_at
            created_at = u.get('created_at')
            if not isinstance(created_at, datetime):
                created_at = datetime.utcnow()

            data = {
                'email': (u.get('email') or '').strip().lower(),
                'name': (u.get('name') or '').strip(),
                'password': pwd,
                'role': u.get('role', 'student'),
                'class_id': str(u.get('class_id')) if u.get('class_id') else None,
                'created_at': created_at
            }
            batch.set(ref, data, merge=True)
            batch_count += 1
            migrated_users += 1

            if batch_count >= 400:
                batch.commit()
                batch = firestore_client.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()
        print(f"  [OK] Synced {migrated_users} users to Firestore 'users' collection.\n")
        total_synced += migrated_users

    # ─── 4. Migrate Classrooms ────────────────────────────────────────────────────
    if 'classrooms' in available_collections:
        print("[*] Migrating 'classrooms' collection...")
        classroom_docs = list(mongo_db.classrooms.find())
        print(f"  Found {len(classroom_docs)} classrooms in MongoDB.")

        batch = firestore_client.batch()
        batch_count = 0
        migrated_rooms = 0

        for c in classroom_docs:
            room_id = str(c['_id'])
            ref = firestore_client.collection('classrooms').document(room_id)

            lat = float(c.get('latitude', 0.0))
            lng = float(c.get('longitude', 0.0))
            created_at = c.get('created_at') if isinstance(c.get('created_at'), datetime) else datetime.utcnow()
            updated_at = c.get('updated_at') if isinstance(c.get('updated_at'), datetime) else created_at

            data = {
                'name': (c.get('name') or '').strip(),
                'latitude': lat,
                'longitude': lng,
                'location': GeoPoint(lat, lng),
                'created_by': str(c.get('created_by')) if c.get('created_by') else None,
                'created_at': created_at,
                'updated_at': updated_at
            }
            batch.set(ref, data, merge=True)
            batch_count += 1
            migrated_rooms += 1

            if batch_count >= 400:
                batch.commit()
                batch = firestore_client.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()
        print(f"  [OK] Synced {migrated_rooms} classrooms to Firestore 'classrooms' collection.\n")
        total_synced += migrated_rooms

    # ─── 5. Migrate Sessions ──────────────────────────────────────────────────────
    if 'sessions' in available_collections:
        print("[*] Migrating 'sessions' collection...")
        session_docs = list(mongo_db.sessions.find())
        print(f"  Found {len(session_docs)} sessions in MongoDB.")

        batch = firestore_client.batch()
        batch_count = 0
        migrated_sessions = 0

        for s in session_docs:
            sid = s.get('session_id') or str(s['_id'])
            ref = firestore_client.collection('sessions').document(str(sid))

            created_at = s.get('created_at') if isinstance(s.get('created_at'), datetime) else datetime.utcnow()
            expires_at = s.get('expires_at') if isinstance(s.get('expires_at'), datetime) else datetime.utcnow()

            data = {
                'session_id': str(sid),
                'class_id': str(s.get('class_id', '')),
                'random_token': s.get('random_token', ''),
                'created_by': str(s.get('created_by', '')),
                'created_at': created_at,
                'expires_at': expires_at,
                'is_active': bool(s.get('is_active', False))
            }
            batch.set(ref, data, merge=True)
            batch_count += 1
            migrated_sessions += 1

            if batch_count >= 400:
                batch.commit()
                batch = firestore_client.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()
        print(f"  [OK] Synced {migrated_sessions} sessions to Firestore 'sessions' collection.\n")
        total_synced += migrated_sessions

    # ─── 6. Migrate Attendance ────────────────────────────────────────────────────
    if 'attendance' in available_collections:
        print("[*] Migrating 'attendance' collection...")
        attendance_docs = list(mongo_db.attendance.find())
        print(f"  Found {len(attendance_docs)} attendance records in MongoDB.")

        batch = firestore_client.batch()
        batch_count = 0
        migrated_attendance = 0

        for a in attendance_docs:
            student_id = str(a.get('student_id', '')).strip()
            session_id = str(a.get('session_id', '')).strip()
            doc_id = f"{student_id}_{session_id}" if (student_id and session_id) else str(a['_id'])
            ref = firestore_client.collection('attendance').document(doc_id)

            lat = float(a.get('latitude', 0.0))
            lng = float(a.get('longitude', 0.0))
            marked_at = a.get('marked_at') if isinstance(a.get('marked_at'), datetime) else datetime.utcnow()

            data = {
                'student_id': student_id,
                'session_id': session_id,
                'latitude': lat,
                'longitude': lng,
                'location': GeoPoint(lat, lng),
                'marked_at': marked_at
            }
            batch.set(ref, data, merge=True)
            batch_count += 1
            migrated_attendance += 1

            if batch_count >= 400:
                batch.commit()
                batch = firestore_client.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()
        print(f"  [OK] Synced {migrated_attendance} attendance check-ins to Firestore 'attendance' collection.\n")
        total_synced += migrated_attendance

    # ─── 7. Migrate Proxy Attempts ────────────────────────────────────────────────
    if 'proxy_attempts' in available_collections:
        print("[*] Migrating 'proxy_attempts' collection...")
        proxy_docs = list(mongo_db.proxy_attempts.find())
        print(f"  Found {len(proxy_docs)} proxy attempts in MongoDB.")

        batch = firestore_client.batch()
        batch_count = 0
        migrated_proxy = 0

        for p in proxy_docs:
            attempt_id = str(p['_id'])
            ref = firestore_client.collection('proxy_attempts').document(attempt_id)

            scanned = p.get('scanned_location', {}) or {}
            expected = p.get('expected_location', {}) or {}
            ts = p.get('timestamp') if isinstance(p.get('timestamp'), datetime) else datetime.utcnow()

            data = {
                'student_id': str(p.get('student_id')) if p.get('student_id') else None,
                'session_id': str(p.get('session_id')) if p.get('session_id') else None,
                'scanned_location': {
                    'latitude': float(scanned.get('latitude', 0.0)),
                    'longitude': float(scanned.get('longitude', 0.0))
                },
                'expected_location': {
                    'latitude': float(expected.get('latitude', 0.0)),
                    'longitude': float(expected.get('longitude', 0.0))
                },
                'reason': str(p.get('reason', 'Security Alert')),
                'timestamp': ts
            }
            batch.set(ref, data, merge=True)
            batch_count += 1
            migrated_proxy += 1

            if batch_count >= 400:
                batch.commit()
                batch = firestore_client.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()
        print(f"  [OK] Synced {migrated_proxy} security logs to Firestore 'proxy_attempts' collection.\n")
        total_synced += migrated_proxy

    print("=" * 65)
    print(f">> MIGRATION FINISHED! Total documents transferred: {total_synced}")
    print("Your collections are ready in Firebase Firestore.")
    print("=" * 65)
    return True
    return True

if __name__ == "__main__":
    m_uri = sys.argv[1] if len(sys.argv) > 1 else None
    c_path = sys.argv[2] if len(sys.argv) > 2 else None
    migrate(m_uri, c_path)
