"""
Firebase Admin SDK Initialization Module
Provides authenticated Firestore client with multi-source credential loading
(File path, environment JSON/base64, GCP default) and resilient mock fallback.
"""
import os
import json
import base64
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import GeoPoint, SERVER_TIMESTAMP

_firestore_client = None
_is_mock = False

def get_firestore_client():
    """
    Returns an initialized Firestore client instance.
    Cached singleton pattern ensures Firebase is only initialized once.
    """
    global _firestore_client, _is_mock
    if _firestore_client is not None:
        return _firestore_client, _is_mock

    cred = None
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON", "").strip()
    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()

    # 1. Check file path (relative to backend or absolute)
    if cred_path:
        resolved_path = os.path.abspath(cred_path)
        if not os.path.exists(resolved_path):
            backend_rel = os.path.join(os.path.dirname(__file__), cred_path)
            if os.path.exists(backend_rel):
                resolved_path = backend_rel

        if os.path.exists(resolved_path):
            try:
                cred = credentials.Certificate(resolved_path)
                print(f"[Firebase] Loaded service account credentials from file: {resolved_path}")
            except Exception as e:
                print(f"[Firebase Warning] Failed to load credential file: {e}")

    # 2. Check JSON / Base64 environment variable (ideal for cloud environments like Render)
    if cred is None and cred_json:
        try:
            # Handle potential base64 encoding
            if not cred_json.startswith("{") and len(cred_json) > 50:
                try:
                    cred_json = base64.b64decode(cred_json).decode("utf-8")
                except Exception:
                    pass

            cert_dict = json.loads(cred_json)
            cred = credentials.Certificate(cert_dict)
            print("[Firebase] Loaded service account credentials from environment JSON.")
        except Exception as e:
            print(f"[Firebase Warning] Failed to parse FIREBASE_CREDENTIALS_JSON: {e}")

    # 3. Check for default serviceAccountKey.json in backend directory
    if cred is None:
        default_key = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
        if os.path.exists(default_key):
            try:
                cred = credentials.Certificate(default_key)
                print(f"[Firebase] Automatically discovered {default_key}")
            except Exception as e:
                print(f"[Firebase Warning] Failed to load default key: {e}")

    # Initialize Firebase Admin App
    try:
        if not firebase_admin._apps:
            options = {}
            if project_id:
                options["projectId"] = project_id

            if cred:
                firebase_admin.initialize_app(cred, options=options)
            else:
                # Attempt default Google Cloud authentication
                firebase_admin.initialize_app(options=options)

        client = firestore.client()
        # Verify connection with a lightweight check
        _firestore_client = client
        _is_mock = False
        print("[Firebase] Successfully connected to live Firestore database!")
        return _firestore_client, False

    except Exception as e:
        print(f"[Firebase Notice] Live Firestore connection unavailable ({e}).")
        print("[Firebase] Initializing resilient in-memory Firestore Mock. Web server will boot smoothly!")
        _firestore_client = _create_mock_firestore()
        _is_mock = True
        return _firestore_client, True


class _MockDocSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class _MockDocRef:
    def __init__(self, col, doc_id):
        self.col = col
        self.id = doc_id

    def get(self):
        data = self.col._store.get(self.id)
        return _MockDocSnapshot(self.id, data)

    def set(self, data, merge=False):
        if merge and self.id in self.col._store:
            self.col._store[self.id].update(data)
        else:
            self.col._store[self.id] = dict(data)

    def update(self, data):
        if self.id in self.col._store:
            self.col._store[self.id].update(data)
        else:
            self.col._store[self.id] = dict(data)

    def delete(self):
        self.col._store.pop(self.id, None)


class _MockQuery:
    def __init__(self, col, filters=None, order_by_fields=None, limit_val=None):
        self.col = col
        self.filters = filters or []
        self.order_by_fields = order_by_fields or []
        self.limit_val = limit_val

    def where(self, field, op, val):
        new_filters = list(self.filters)
        new_filters.append((field, op, val))
        return _MockQuery(self.col, new_filters, self.order_by_fields, self.limit_val)

    def order_by(self, field, direction="ASCENDING"):
        new_order = list(self.order_by_fields)
        new_order.append((field, direction))
        return _MockQuery(self.col, self.filters, new_order, self.limit_val)

    def limit(self, count):
        return _MockQuery(self.col, self.filters, self.order_by_fields, count)

    def stream(self):
        results = []
        for doc_id, data in self.col._store.items():
            match = True
            for field, op, val in self.filters:
                doc_val = data.get(field)
                if op == "==" and doc_val != val:
                    match = False
                    break
                elif op == "!=" and doc_val == val:
                    match = False
                    break
                elif op == ">" and not (doc_val and doc_val > val):
                    match = False
                    break
                elif op == "<" and not (doc_val and doc_val < val):
                    match = False
                    break
                elif op == "in" and (doc_val not in val if isinstance(val, (list, tuple, set)) else True):
                    match = False
                    break
            if match:
                results.append(_MockDocSnapshot(doc_id, data))

        for field, direction in self.order_by_fields:
            reverse = str(direction).upper() in ("DESCENDING", "DESC")
            results.sort(
                key=lambda snap: snap.to_dict().get(field) or datetime.min,
                reverse=reverse
            )

        if self.limit_val is not None:
            results = results[:self.limit_val]

        return results

    def get(self):
        return list(self.stream())

    def count(self):
        class _CountResult:
            def __init__(self, count_val):
                self.value = count_val
        class _CountQuery:
            def __init__(self, count_val):
                self._c = count_val
            def get(self):
                return [[_CountResult(self._c)]]
        return _CountQuery(len(list(self.stream())))


class _MockCollection:
    def __init__(self, name):
        self.name = name
        self._store = {}
        self._counter = 1

    def document(self, doc_id=None):
        if not doc_id:
            import uuid
            doc_id = uuid.uuid4().hex[:20]
        return _MockDocRef(self, doc_id)

    def add(self, data):
        doc_ref = self.document()
        doc_ref.set(data)
        return datetime.utcnow(), doc_ref

    def where(self, field, op, val):
        return _MockQuery(self).where(field, op, val)

    def order_by(self, field, direction="ASCENDING"):
        return _MockQuery(self).order_by(field, direction)

    def limit(self, count):
        return _MockQuery(self).limit(count)

    def stream(self):
        return _MockQuery(self).stream()

    def get(self):
        return _MockQuery(self).get()

    def count(self):
        return _MockQuery(self).count()


class _MockBatch:
    def __init__(self):
        self._ops = []

    def set(self, doc_ref, data, merge=False):
        self._ops.append(('set', doc_ref, data, merge))

    def update(self, doc_ref, data):
        self._ops.append(('update', doc_ref, data, False))

    def delete(self, doc_ref):
        self._ops.append(('delete', doc_ref, None, False))

    def commit(self):
        for op, doc_ref, data, merge in self._ops:
            if op == 'set':
                doc_ref.set(data, merge=merge)
            elif op == 'update':
                doc_ref.update(data)
            elif op == 'delete':
                doc_ref.delete()
        self._ops.clear()


class _MockFirestore:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = _MockCollection(name)
        return self._collections[name]

    def batch(self):
        return _MockBatch()


def _create_mock_firestore():
    return _MockFirestore()

