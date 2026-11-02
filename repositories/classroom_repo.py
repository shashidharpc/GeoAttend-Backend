"""
Classroom Repository for Firestore
Manages campus classroom coordinates, geofence definitions, and metadata.
"""
from datetime import datetime
from google.cloud.firestore import GeoPoint

class ClassroomRepository:
    def __init__(self, db):
        self.db = db
        self.col = db.collection('classrooms')

    @staticmethod
    def _format_doc(doc_id, data):
        if not data:
            return None
        res = dict(data)
        res['id'] = doc_id
        res['_id'] = doc_id
        # Ensure latitude/longitude are always floats
        if 'latitude' in res and res['latitude'] is not None:
            res['latitude'] = float(res['latitude'])
        elif 'location' in res and hasattr(res['location'], 'latitude'):
            res['latitude'] = float(res['location'].latitude)
            res['longitude'] = float(res['location'].longitude)

        if 'longitude' in res and res['longitude'] is not None:
            res['longitude'] = float(res['longitude'])
        return res

    def get_all(self):
        try:
            docs = self.col.stream()
            classrooms = [self._format_doc(d.id, d.to_dict()) for d in docs]
            classrooms.sort(
                key=lambda c: c.get('created_at') or datetime.min,
                reverse=True
            )
            return classrooms
        except Exception as e:
            print(f"[ClassroomRepository Error] get_all failed: {e}")
            return []

    def get_by_id(self, classroom_id):
        if not classroom_id:
            return None
        try:
            doc = self.col.document(str(classroom_id)).get()
            if doc.exists:
                return self._format_doc(doc.id, doc.to_dict())
        except Exception as e:
            print(f"[ClassroomRepository Error] get_by_id({classroom_id}) failed: {e}")
        return None

    def get_by_name(self, name):
        if not name:
            return None
        clean_name = name.strip()
        try:
            query = self.col.where('name', '==', clean_name).limit(1)
            docs = list(query.stream())
            if docs:
                return self._format_doc(docs[0].id, docs[0].to_dict())
            
            # Case-insensitive fallback
            for doc in self.col.stream():
                d = doc.to_dict()
                if (d.get('name') or '').strip().lower() == clean_name.lower():
                    return self._format_doc(doc.id, d)
        except Exception as e:
            print(f"[ClassroomRepository Error] get_by_name({name}) failed: {e}")
        return None

    def create(self, name, latitude, longitude, created_by, custom_id=None):
        lat = float(latitude)
        lng = float(longitude)
        now = datetime.utcnow()
        classroom_data = {
            'name': name.strip() if name else '',
            'latitude': lat,
            'longitude': lng,
            'location': GeoPoint(lat, lng),
            'created_by': str(created_by) if created_by else None,
            'created_at': now,
            'updated_at': now
        }
        if custom_id:
            doc_ref = self.col.document(str(custom_id))
            doc_ref.set(classroom_data)
        else:
            _, doc_ref = self.col.add(classroom_data)

        return self._format_doc(doc_ref.id, classroom_data)

    def update(self, classroom_id, name=None, latitude=None, longitude=None):
        if not classroom_id:
            return None
        try:
            doc_ref = self.col.document(str(classroom_id))
            doc = doc_ref.get()
            if not doc.exists:
                return None

            existing = doc.to_dict()
            update_data = {'updated_at': datetime.utcnow()}

            if name is not None and str(name).strip():
                update_data['name'] = str(name).strip()

            new_lat = float(latitude) if (latitude is not None and str(latitude).strip()) else existing.get('latitude')
            new_lng = float(longitude) if (longitude is not None and str(longitude).strip()) else existing.get('longitude')

            if new_lat is not None:
                update_data['latitude'] = float(new_lat)
            if new_lng is not None:
                update_data['longitude'] = float(new_lng)
            if new_lat is not None and new_lng is not None:
                update_data['location'] = GeoPoint(float(new_lat), float(new_lng))

            doc_ref.update(update_data)
            return self.get_by_id(classroom_id)
        except Exception as e:
            print(f"[ClassroomRepository Error] update failed: {e}")
            return None

    def delete(self, classroom_id):
        if not classroom_id:
            return False
        try:
            self.col.document(str(classroom_id)).delete()
            return True
        except Exception as e:
            print(f"[ClassroomRepository Error] delete failed: {e}")
            return False

    def count(self):
        try:
            return len(list(self.col.stream()))
        except Exception:
            return 0
