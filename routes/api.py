from flask import Blueprint, request, jsonify, current_app, make_response
from flask_login import login_user, logout_user, login_required, current_user
from bson.objectid import ObjectId
import json
import csv
from io import StringIO
from datetime import datetime, timedelta
from models import User, Classroom, Session, Attendance, ProxyAttempt
from utils import generate_qr_code, generate_random_password, calculate_distance, format_datetime

api_bp = Blueprint('api', __name__, url_prefix='/api')

def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    if isinstance(doc, dict):
        new_doc = {}
        for k, v in doc.items():
            if isinstance(v, ObjectId):
                new_doc[k] = str(v)
            elif isinstance(v, datetime):
                iso_str = v.isoformat()
                if not iso_str.endswith('Z') and '+' not in iso_str and '-' not in iso_str[10:]:
                    iso_str += 'Z'
                new_doc[k] = iso_str
            elif isinstance(v, bytes):
                new_doc[k] = v.decode('utf-8', errors='ignore')
            elif isinstance(v, (dict, list)):
                new_doc[k] = serialize_doc(v)
            else:
                new_doc[k] = v
        return new_doc
    return doc

# ================= AUTH API =================

@api_bp.route('/auth/status', methods=['GET'])
def auth_status():
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': current_user.id,
                'email': current_user.email,
                'name': current_user.name,
                'role': current_user.role,
                'class_id': getattr(current_user, 'class_id', None)
            }
        })
    return jsonify({'authenticated': False, 'user': None})

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400

    db = current_app.db
    user = User.get_by_email(db, email)
    if not user:
        return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

    user_data = db.users.find_one({'_id': ObjectId(user.id)})
    if not user_data:
        return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

    is_valid = User.verify_password(password, user_data.get('password'))

    if is_valid:
        login_user(user, remember=True)
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'role': user.role,
                'class_id': getattr(user, 'class_id', None)
            }
        })

    return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

@api_bp.route('/auth/logout', methods=['POST', 'GET'])
def api_logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

# ================= ADMIN APIS =================

@api_bp.route('/admin/dashboard', methods=['GET'])
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    now = datetime.utcnow()

    # Update expired sessions
    db.sessions.update_many(
        {'is_active': True, 'expires_at': {'$lt': now}},
        {'$set': {'is_active': False}}
    )

    total_students = db.users.count_documents({'role': 'student'})
    total_classrooms = db.classrooms.count_documents({})
    total_sessions = db.sessions.count_documents({})
    total_proxy_attempts = db.proxy_attempts.count_documents({})

    recent_sessions = list(db.sessions.find().sort('created_at', -1).limit(6))
    for s in recent_sessions:
        cls = db.classrooms.find_one({'_id': ObjectId(s['class_id'])}) if ObjectId.is_valid(s.get('class_id', '')) else None
        s['classroom_name'] = cls['name'] if cls else 'General Class'
        s['attendance_count'] = db.attendance.count_documents({'session_id': s['session_id']})

    # Classroom attendance stats
    classrooms = list(db.classrooms.find())
    classroom_stats = []
    for c in classrooms:
        cid_str = str(c['_id'])
        c_sessions = list(db.sessions.find({'class_id': cid_str}))
        c_session_ids = [s['session_id'] for s in c_sessions]
        count = db.attendance.count_documents({'session_id': {'$in': c_session_ids}})
        classroom_stats.append({
            'id': cid_str,
            'name': c.get('name', 'Unnamed'),
            'attendance_count': count
        })

    # Trend last 7 days
    today = datetime.utcnow()
    dates = []
    attendance_counts = []
    for i in range(6, -1, -1):
        day_date = today - timedelta(days=i)
        start_of_day = datetime(day_date.year, day_date.month, day_date.day)
        end_of_day = start_of_day + timedelta(days=1)
        count = db.attendance.count_documents({
            'marked_at': {'$gte': start_of_day, '$lt': end_of_day}
        })
        dates.append(day_date.strftime('%b %d'))
        attendance_counts.append(count)

    # Proxy reasons breakdown
    proxy_reasons = {}
    for attempt in db.proxy_attempts.find():
        reason = attempt.get('reason', 'Unknown')
        proxy_reasons[reason] = proxy_reasons.get(reason, 0) + 1

    return jsonify({
        'stats': {
            'total_students': total_students,
            'total_classrooms': total_classrooms,
            'total_sessions': total_sessions,
            'total_proxy_attempts': total_proxy_attempts,
        },
        'recent_sessions': serialize_doc(recent_sessions),
        'classroom_stats': classroom_stats,
        'trend': {
            'dates': dates,
            'counts': attendance_counts
        },
        'proxy_reasons': proxy_reasons
    })

@api_bp.route('/admin/classrooms', methods=['GET', 'POST'])
@login_required
def admin_classrooms():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if not name or latitude is None or longitude is None:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        try:
            created = Classroom.create(db, name, float(latitude), float(longitude), current_user.id)
            return jsonify({'success': True, 'message': 'Classroom created successfully', 'classroom': serialize_doc(created)})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    classrooms = list(db.classrooms.find().sort('created_at', -1))
    for c in classrooms:
        cid = str(c['_id'])
        c['student_count'] = db.users.count_documents({'role': 'student', 'class_id': cid})
        c['session_count'] = db.sessions.count_documents({'class_id': cid})

    return jsonify({'classrooms': serialize_doc(classrooms)})

@api_bp.route('/admin/classrooms/<classroom_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_manage_classroom(classroom_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    if not ObjectId.is_valid(classroom_id):
        return jsonify({'success': False, 'message': 'Invalid Classroom ID'}), 400

    if request.method == 'DELETE':
        deleted = Classroom.delete(db, classroom_id)
        if deleted:
            return jsonify({'success': True, 'message': 'Classroom deleted successfully'})
        return jsonify({'success': False, 'message': 'Classroom not found'}), 404

    # PUT: Update classroom
    data = request.get_json() or {}
    name = data.get('name')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    updated = Classroom.update(db, classroom_id, name=name, latitude=latitude, longitude=longitude)
    if updated:
        return jsonify({
            'success': True,
            'message': 'Classroom updated successfully',
            'classroom': serialize_doc(updated)
        })
    return jsonify({'success': False, 'message': 'Failed to update classroom'}), 400

@api_bp.route('/admin/students', methods=['GET', 'POST'])
@login_required
def admin_students():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        class_id = data.get('class_id', '').strip()
        password = data.get('password', '').strip() or generate_random_password()

        if not name or not email or not class_id:
            return jsonify({'success': False, 'message': 'Name, email, and class are required'}), 400

        existing = User.get_by_email(db, email)
        if existing:
            return jsonify({'success': False, 'message': 'Student with this email already exists'}), 400

        try:
            created = User.create_user(db, email, name, password, role='student', class_id=class_id)

            # Send credentials email to the new student
            email_status = 'sent'
            try:
                from flask_mail import Message
                from flask import render_template
                login_url = request.host_url.rstrip('/') + '/login'
                msg = Message('Your Attendance System Credentials', recipients=[email])
                msg.body = (
                    f"Hello {name},\n\n"
                    f"An account has been created for you on the Attendance Geo Tracker system.\n\n"
                    f"Login Credentials:\nEmail: {email}\nPassword: {password}\n\n"
                    f"Please login at: {login_url}\n\nKeep your credentials secure.\n\nBest regards,\nAttendance Geo Tracker"
                )
                try:
                    msg.html = render_template(
                        'emails/student_credentials.html',
                        name=name,
                        email=email,
                        password=password,
                        login_url=login_url
                    )
                except Exception:
                    pass
                current_app.mail.send(msg)
            except Exception as mail_err:
                email_status = f'failed ({str(mail_err)})'

            return jsonify({
                'success': True,
                'message': f'Student created successfully. Credentials email {email_status}.',
                'student': {
                    'id': created.id,
                    'name': created.name,
                    'email': created.email,
                    'class_id': created.class_id,
                    'generated_password': password
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    students = list(db.users.find({'role': 'student'}).sort('created_at', -1))
    # Enrich student classroom name
    for s in students:
        if s.get('class_id') and ObjectId.is_valid(s['class_id']):
            cls = db.classrooms.find_one({'_id': ObjectId(s['class_id'])})
            s['classroom_name'] = cls['name'] if cls else 'Unassigned'
        else:
            s['classroom_name'] = 'Unassigned'
        s.pop('password', None)

    classrooms = list(db.classrooms.find())
    return jsonify({
        'students': serialize_doc(students),
        'classrooms': serialize_doc(classrooms)
    })

@api_bp.route('/admin/import_students', methods=['POST'])
@login_required
def admin_import_students():
    """Bulk-import students from an uploaded Excel (.xlsx) or CSV file.
    Expected columns: name, email, password (optional), class
    The 'class' column must match an existing classroom name exactly.
    Sends a credentials email to each imported student.
    """
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400

    filename = file.filename.lower()
    db = current_app.db

    try:
        import pandas as pd
        from io import BytesIO
        raw = BytesIO(file.read())
        if filename.endswith('.csv'):
            df = pd.read_csv(raw)
        else:
            df = pd.read_excel(raw)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Could not parse file: {str(e)}'}), 400

    # Normalize column names (strip whitespace, lowercase)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {'name', 'email', 'class'}
    missing = required - set(df.columns)
    if missing:
        return jsonify({'success': False, 'message': f'Missing required columns: {", ".join(missing)}'}), 400

    imported, skipped, errors = 0, 0, []

    for _, row in df.iterrows():
        try:
            name = str(row.get('name', '')).strip()
            email = str(row.get('email', '')).strip()
            class_name = str(row.get('class', '')).strip()
            password = str(row.get('password', '')).strip() or generate_random_password()

            if not name or not email or not class_name:
                skipped += 1
                continue

            # Resolve classroom by name
            classroom = db.classrooms.find_one({'name': class_name})
            if not classroom:
                errors.append(f'{email}: classroom "{class_name}" not found')
                skipped += 1
                continue

            # Skip duplicates
            if User.get_by_email(db, email):
                skipped += 1
                continue

            User.create_user(db, email, name, password, role='student', class_id=str(classroom['_id']))

            # Send credentials email
            try:
                from flask_mail import Message
                from flask import render_template
                login_url = request.host_url.rstrip('/') + '/login'
                msg = Message('Your Attendance System Credentials', recipients=[email])
                msg.body = (
                    f"Hello {name},\n\n"
                    f"An account has been created for you on the Attendance Geo Tracker system.\n\n"
                    f"Login Credentials:\nEmail: {email}\nPassword: {password}\n\n"
                    f"Please login at: {login_url}\n\nKeep your credentials secure.\n\nBest regards,\nAttendance Geo Tracker"
                )
                try:
                    msg.html = render_template(
                        'emails/student_credentials.html',
                        name=name,
                        email=email,
                        password=password,
                        login_url=login_url
                    )
                except Exception:
                    pass
                current_app.mail.send(msg)
            except Exception:
                pass  # Don't fail the import if email fails; student is still created

            imported += 1
        except Exception as row_err:
            errors.append(f'Row error: {str(row_err)}')
            skipped += 1

    return jsonify({
        'success': True,
        'message': f'{imported} student(s) imported, {skipped} skipped.',
        'imported': imported,
        'skipped': skipped,
        'errors': errors
    })


@api_bp.route('/admin/test_email', methods=['POST'])
@login_required
def admin_test_email():
    """Test the email delivery configuration by sending a test credential email."""
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    recipient = data.get('recipient', '').strip() or current_app.config.get('MAIL_USERNAME')

    if not recipient:
        return jsonify({'success': False, 'message': 'No recipient email specified'}), 400

    try:
        from flask_mail import Message
        from flask import render_template
        login_url = request.host_url.rstrip('/') + '/login'
        msg = Message('Test: Attendance Geo Tracker Credentials Delivery', recipients=[recipient])
        msg.body = (
            "Hello Admin,\n\n"
            "This is a test verifying that the Attendance Geo Tracker email delivery system is working.\n\n"
            "Sample Student Credentials:\n"
            "Email: student@edu.com\n"
            "Password: SamplePassword123\n\n"
            f"Login URL: {login_url}\n\n"
            "Best regards,\nAttendance Geo Tracker Team"
        )
        try:
            msg.html = render_template(
                'emails/student_credentials.html',
                name='Test Student',
                email='student@edu.com',
                password='SamplePassword123',
                login_url=login_url
            )
        except Exception:
            pass

        current_app.mail.send(msg)
        return jsonify({
            'success': True,
            'message': f'Test email delivered successfully to {recipient}!'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Failed to send email: {str(e)}'
        }), 500


@api_bp.route('/admin/students/<student_id>', methods=['DELETE', 'PUT'])
@login_required
def admin_manage_student(student_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    if not ObjectId.is_valid(student_id):
        return jsonify({'success': False, 'message': 'Invalid ID'}), 400

    if request.method == 'DELETE':
        result = db.users.delete_one({'_id': ObjectId(student_id), 'role': 'student'})
        if result.deleted_count > 0:
            return jsonify({'success': True, 'message': 'Student deleted successfully'})
        return jsonify({'success': False, 'message': 'Student not found'}), 404

    # PUT: Update student record
    data = request.get_json() or {}
    update_fields = {}
    if 'name' in data and data['name'].strip():
        update_fields['name'] = data['name'].strip()
    if 'email' in data and data['email'].strip():
        new_email = data['email'].strip()
        existing = db.users.find_one({'email': new_email, '_id': {'$ne': ObjectId(student_id)}})
        if existing:
            return jsonify({'success': False, 'message': 'Email already in use by another student'}), 400
        update_fields['email'] = new_email
    if 'class_id' in data:
        update_fields['class_id'] = data['class_id'].strip()

    if not update_fields:
        return jsonify({'success': False, 'message': 'No update data provided'}), 400

    db.users.update_one({'_id': ObjectId(student_id)}, {'$set': update_fields})
    return jsonify({'success': True, 'message': 'Student record updated successfully'})


@api_bp.route('/user/profile', methods=['PUT'])
@login_required
def update_user_profile():
    """Allow logged in user to update their display name"""
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Name cannot be empty'}), 400
    db = current_app.db
    db.users.update_one({'_id': ObjectId(current_user.id)}, {'$set': {'name': name}})
    return jsonify({'success': True, 'message': 'Profile name updated successfully', 'name': name})

@api_bp.route('/admin/generate_qr', methods=['POST'])
@api_bp.route('/admin/generate-qr', methods=['POST'])
@login_required
def admin_generate_qr():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    data = request.get_json() or {}
    classroom_id = data.get('classroom_id')
    default_expiry = current_app.config.get('QR_EXPIRY_MINUTES', 2)
    expiry_minutes = int(data.get('expiry_minutes', default_expiry))

    if not classroom_id:
        return jsonify({'success': False, 'message': 'Classroom ID is required'}), 400

    classroom = Classroom.get_by_id(db, classroom_id)
    if not classroom:
        return jsonify({'success': False, 'message': 'Classroom not found'}), 404

    session_data = Session.create(db, str(classroom['_id']), current_user.id, expiry_minutes=expiry_minutes)

    qr_payload = {
        'session_id': session_data['session_id'],
        'class_id': str(classroom['_id']),
        'timestamp': session_data['created_at'].isoformat(),
        'random_token': session_data['random_token']
    }
    qr_code_image = generate_qr_code(qr_payload)

    return jsonify({
        'success': True,
        'session': serialize_doc(session_data),
        'classroom': serialize_doc(classroom),
        'qr_code_image': qr_code_image,
        'qr_payload': qr_payload
    })

@api_bp.route('/admin/attendance_report/<session_id>', methods=['GET'])
@api_bp.route('/admin/attendance-report/<session_id>', methods=['GET'])
@login_required
def admin_attendance_report(session_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    session = Session.get_by_session_id(db, session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    classroom = Classroom.get_by_id(db, session['class_id'])
    attendances = Attendance.get_by_session(db, session_id)

    attendance_details = []
    for att in attendances:
        student = db.users.find_one({'_id': ObjectId(att['student_id'])}) if ObjectId.is_valid(att['student_id']) else None
        if student:
            dist = 0
            if classroom:
                dist = calculate_distance(att['latitude'], att['longitude'], classroom['latitude'], classroom['longitude'])
            attendance_details.append({
                'student_id': att['student_id'],
                'student_name': student['name'],
                'student_email': student['email'],
                'marked_at': att['marked_at'].isoformat() if isinstance(att['marked_at'], datetime) else att['marked_at'],
                'latitude': att['latitude'],
                'longitude': att['longitude'],
                'distance': round(dist, 1)
            })

    all_students = list(db.users.find({'role': 'student', 'class_id': session['class_id']}))
    attended_ids = [att['student_id'] for att in attendances]
    absent_students = []
    for s in all_students:
        if str(s['_id']) not in attended_ids:
            absent_students.append({
                'student_id': str(s['_id']),
                'name': s.get('name'),
                'email': s.get('email')
            })

    return jsonify({
        'session': serialize_doc(session),
        'classroom': serialize_doc(classroom),
        'attendances': attendance_details,
        'absent_students': absent_students,
        'summary': {
            'total_students': len(all_students),
            'present_count': len(attendance_details),
            'absent_count': len(absent_students),
            'attendance_rate': round((len(attendance_details) / max(len(all_students), 1)) * 100, 1)
        }
    })

@api_bp.route('/admin/proxy_attempts', methods=['GET'])
@api_bp.route('/admin/proxy-attempts', methods=['GET'])
@login_required
def admin_proxy_attempts():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    attempts = ProxyAttempt.get_all(db)

    enriched = []
    for attempt in attempts:
        student = db.users.find_one({'_id': ObjectId(attempt['student_id'])}) if ObjectId.is_valid(attempt['student_id']) else None
        session = Session.get_by_session_id(db, attempt['session_id']) if attempt.get('session_id') else None
        classroom = Classroom.get_by_id(db, session['class_id']) if session and ObjectId.is_valid(session.get('class_id', '')) else None

        enriched.append({
            'id': str(attempt['_id']),
            'student_name': student['name'] if student else 'Unknown Student',
            'student_email': student['email'] if student else 'N/A',
            'classroom_name': classroom['name'] if classroom else 'Unknown Room',
            'reason': attempt.get('reason', 'Security Alert'),
            'timestamp': attempt.get('timestamp').isoformat() if isinstance(attempt.get('timestamp'), datetime) else attempt.get('timestamp'),
            'scanned_location': attempt.get('scanned_location', {}),
            'expected_location': attempt.get('expected_location', {})
        })

    return jsonify({'proxy_attempts': enriched})

# ================= STUDENT APIS =================

@api_bp.route('/student/dashboard', methods=['GET'])
@login_required
def student_dashboard():
    if current_user.role != 'student':
        return jsonify({'error': 'Unauthorized'}), 403

    db = current_app.db
    attendances = Attendance.get_by_student(db, current_user.id)

    total_sessions = 0
    classroom_name = 'Not Assigned'
    if current_user.class_id:
        total_sessions = db.sessions.count_documents({'class_id': current_user.class_id})
        cls = Classroom.get_by_id(db, current_user.class_id)
        classroom_lat = None
        classroom_lng = None
        if cls:
            classroom_name = cls.get('name')
            classroom_lat = cls.get('latitude')
            classroom_lng = cls.get('longitude')

    attendance_pct = (len(attendances) / total_sessions * 100) if total_sessions > 0 else 0

    recent_attendance = []
    for att in attendances[-10:]:
        session = Session.get_by_session_id(db, att['session_id'])
        room_name = 'Classroom'
        if session:
            classroom = Classroom.get_by_id(db, session['class_id'])
            if classroom:
                room_name = classroom.get('name')
        recent_attendance.append({
            'classroom': room_name,
            'marked_at': att['marked_at'].isoformat() if isinstance(att['marked_at'], datetime) else att['marked_at'],
            'session_id': att['session_id']
        })

    return jsonify({
        'student': {
            'id': current_user.id,
            'name': current_user.name,
            'email': current_user.email,
            'classroom_name': classroom_name,
            'class_id': current_user.class_id,
            'classroom_latitude': classroom_lat,
            'classroom_longitude': classroom_lng
        },
        'total_attended': len(attendances),
        'total_classes': total_sessions,
        'attendance_percentage': round(attendance_pct, 1),
        'recent_attendance': list(reversed(recent_attendance))
    })

@api_bp.route('/student/verify_attendance', methods=['POST'])
@login_required
def student_verify_attendance():
    if current_user.role != 'student':
        return jsonify({'success': False, 'message': 'Student role required'}), 403

    try:
        data = request.get_json() or {}
        raw_qr = data.get('qr_data')
        if isinstance(raw_qr, str):
            try:
                qr_data = json.loads(raw_qr)
            except Exception:
                qr_data = {'session_id': raw_qr}
        elif isinstance(raw_qr, dict):
            qr_data = raw_qr
        else:
            return jsonify({'success': False, 'message': 'Invalid QR payload'}), 400

        latitude = float(data.get('latitude', 0))
        longitude = float(data.get('longitude', 0))
        session_id = qr_data.get('session_id')

        db = current_app.db
        session = Session.get_by_session_id(db, session_id)
        if not session:
            return jsonify({'success': False, 'message': 'Invalid QR code session'}), 400

        is_valid, msg = Session.is_valid(session)
        if not is_valid:
            classroom = Classroom.get_by_id(db, session['class_id'])
            ProxyAttempt.log(
                db,
                current_user.id,
                session_id,
                latitude,
                longitude,
                classroom['latitude'] if classroom else 0,
                classroom['longitude'] if classroom else 0,
                msg
            )
            return jsonify({'success': False, 'message': msg}), 400

        if current_user.class_id != session['class_id']:
            classroom = Classroom.get_by_id(db, session['class_id'])
            ProxyAttempt.log(
                db,
                current_user.id,
                session_id,
                latitude,
                longitude,
                classroom['latitude'] if classroom else 0,
                classroom['longitude'] if classroom else 0,
                'Enrolled in different class'
            )
            return jsonify({'success': False, 'message': 'You are not enrolled in this classroom'}), 403

        if Attendance.check_already_marked(db, current_user.id, session_id):
            return jsonify({'success': False, 'message': 'Attendance has already been marked for this session'}), 400

        classroom = Classroom.get_by_id(db, session['class_id'])
        if not classroom:
            return jsonify({'success': False, 'message': 'Classroom not found'}), 404

        distance = calculate_distance(latitude, longitude, classroom['latitude'], classroom['longitude'])

        allowed_radius = current_app.config.get('ALLOWED_RADIUS_METERS', 30)

        if distance > allowed_radius:  # Configurable geofence radius
            ProxyAttempt.log(
                db,
                current_user.id,
                session_id,
                latitude,
                longitude,
                classroom['latitude'],
                classroom['longitude'],
                f'Outside allowed radius ({round(distance, 1)}m away)'
            )
            return jsonify({
                'success': False,
                'message': f'Outside allowed classroom radius ({round(distance, 1)} meters away, maximum allowed is {int(allowed_radius)}m)',
                'distance': round(distance, 1),
                'classroom_name': classroom.get('name'),
                'classroom_coords': {'lat': classroom['latitude'], 'lng': classroom['longitude']},
                'student_coords': {'lat': latitude, 'lng': longitude}
            }), 400

        marked = Attendance.mark(db, current_user.id, session_id, latitude, longitude)
        if marked:
            return jsonify({
                'success': True,
                'message': 'Attendance marked successfully!',
                'distance': round(distance, 1),
                'classroom': classroom.get('name')
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to record attendance'}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f'Verification error: {str(e)}'}), 500
