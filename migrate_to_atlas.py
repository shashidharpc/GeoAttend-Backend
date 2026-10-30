"""
Database Migration Script: Local MongoDB -> MongoDB Atlas
Transfers all classrooms, users, attendance sessions, and logs from local MongoDB to cloud Atlas.
"""
import sys
import os
from pymongo import MongoClient

def migrate(atlas_uri=None):
    local_uri = os.getenv("LOCAL_MONGO_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "qr_attendance_db")
    
    if not atlas_uri:
        atlas_uri = os.getenv("ATLAS_MONGO_URI") or os.getenv("MONGO_URI")
    
    if not atlas_uri or "<db_password>" in atlas_uri or "localhost" in atlas_uri:
        print("\n[Error] Please provide a valid MongoDB Atlas connection string.")
        print("Usage: python migrate_to_atlas.py <YOUR_ATLAS_URI_WITH_PASSWORD>")
        print("Example: python migrate_to_atlas.py \"mongodb+srv://shashidharpc_db_user:YourPass123@cluster0.lanadsm.mongodb.net/?retryWrites=true&w=majority\"")
        return False

    print("=" * 60)
    print("🚀 Starting GeoAttend Database Migration to MongoDB Atlas")
    print("=" * 60)
    print(f"Source Database (Local) : {local_uri} -> {db_name}")
    print(f"Target Database (Atlas) : {atlas_uri.split('@')[-1] if '@' in atlas_uri else atlas_uri} -> {db_name}")
    print("-" * 60)

    try:
        # Connect to local MongoDB
        local_client = MongoClient(local_uri, serverSelectionTimeoutMS=4000)
        local_db = local_client[db_name]
        local_collections = local_db.list_collection_names()
        print(f"Connected to local MongoDB. Collections found: {local_collections}")
    except Exception as e:
        print(f"[Error] Failed to connect to local MongoDB at {local_uri}: {e}")
        return False

    try:
        # Connect to Atlas
        atlas_client = MongoClient(atlas_uri, serverSelectionTimeoutMS=10000)
        atlas_client.admin.command('ping')
        atlas_db = atlas_client[db_name]
        print(f"Successfully authenticated and connected to MongoDB Atlas!\n")
    except Exception as e:
        print(f"[Error] Failed to connect to MongoDB Atlas: {e}")
        print("Tip: Check your password, username, and ensure Atlas Network Access allows 0.0.0.0/0 (any IP).")
        return False

    collections_to_migrate = ['users', 'classrooms', 'sessions', 'attendance', 'proxy_attempts']

    total_migrated = 0
    for col_name in collections_to_migrate:
        local_col = local_db[col_name]
        atlas_col = atlas_db[col_name]
        
        docs = list(local_col.find())
        count = len(docs)
        
        if count == 0:
            print(f" - [{col_name}] 0 documents (skipped)")
            continue

        print(f" - [{col_name}] Found {count} documents. Migrating to Atlas...")
        
        # Upsert documents by _id so migration is idempotent (can run multiple times safely)
        migrated_in_col = 0
        for doc in docs:
            atlas_col.replace_one({'_id': doc['_id']}, doc, upsert=True)
            migrated_in_col += 1
            
        print(f"   ✓ Successfully synced {migrated_in_col} records to Atlas '{col_name}' collection.")
        total_migrated += migrated_in_col

    # Recreate essential indexes on Atlas
    print("\nRebuilding database indexes on Atlas...")
    try:
        atlas_db.users.create_index('email', unique=True)
        atlas_db.users.create_index('role')
        atlas_db.classrooms.create_index('name')
        atlas_db.sessions.create_index('session_id', unique=True)
        atlas_db.sessions.create_index('expires_at')
        atlas_db.sessions.create_index('class_id')
        atlas_db.attendance.create_index([('student_id', 1), ('session_id', 1)], unique=True)
        atlas_db.attendance.create_index('session_id')
        atlas_db.attendance.create_index('student_id')
        atlas_db.proxy_attempts.create_index('timestamp')
        print("✓ All indexes created successfully on Atlas.")
    except Exception as e:
        print(f"! Notice during index creation: {e}")

    print("\n" + "=" * 60)
    print(f"🎉 MIGRATION COMPLETE! Total records synced: {total_migrated}")
    print(f"Your database 'qr_attendance_db' is now live on MongoDB Atlas with all data.")
    print("=" * 60)
    return True

if __name__ == "__main__":
    uri = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(uri)
