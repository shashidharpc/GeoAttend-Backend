import csv
import pandas as pd 
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from . import admin_bp
from models import User, Classroom, Session, Attendance, ProxyAttempt
from utils import generate_qr_code, generate_random_password, format_datetime, calculate_distance
# Don't import `db`/`mail` from `app` directly to avoid re-importing
# the script as module `app` when running `python ./app.py` (which
# results in `__main__`). Use `current_app` inside request handlers.
from flask_mail import Message
from bson.objectid import ObjectId
import json
from datetime import datetime, timedelta
import csv
from io import StringIO
from flask import make_response

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    db = current_app.db
    total_students = db.users.count_documents({'role': 'student'})
    total_classrooms = db.classrooms.count_documents({})
    total_sessions = db.sessions.count_documents({})
    total_proxy_attempts = db.proxy_attempts.count_documents({})
    
    recent_sessions = list(db.sessions.find().sort('created_at', -1).limit(5))
    
    # Check and update session status based on expiration
    now = datetime.utcnow()
    for session in recent_sessions:
        if session.get('is_active') and session.get('expires_at') < now:
            session['is_active'] = False
            db.sessions.update_one(
                {'_id': session['_id']},
                {'$set': {'is_active': False}}
            )
    
    # Get data for charts
    # 1. Attendance by classroom
    classrooms = list(db.classrooms.find())
    classroom_names = []
    classroom_attendance = []
    for classroom in classrooms:
        classroom_names.append(classroom['name'])
        # Count attendances for this classroom's sessions
        sessions = list(db.sessions.find({'class_id': str(classroom['_id'])}))
        session_ids = [s['session_id'] for s in sessions]
        count = db.attendance.count_documents({'session_id': {'$in': session_ids}})
        classroom_attendance.append(count)
    
    # 2. Attendance trend over last 7 days
    today = datetime.now()
    dates = []
    attendance_counts = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        start_of_day = datetime(date.year, date.month, date.day)
        end_of_day = start_of_day + timedelta(days=1)
        count = db.attendance.count_documents({
            'marked_at': {'$gte': start_of_day, '$lt': end_of_day}
        })
        dates.append(date.strftime('%b %d'))
        attendance_counts.append(count)
    
    # 3. Proxy attempts by reason
    proxy_reasons = {}
    for attempt in db.proxy_attempts.find():
        reason = attempt.get('reason', 'Unknown')
        proxy_reasons[reason] = proxy_reasons.get(reason, 0) + 1
    
    return render_template('admin/dashboard.html',
                         total_students=total_students,
                         total_classrooms=total_classrooms,
                         total_sessions=total_sessions,
                         total_proxy_attempts=total_proxy_attempts,
                         recent_sessions=recent_sessions,
                         classroom_names=classroom_names,
                         classroom_attendance=classroom_attendance,
                         dates=dates,
                         attendance_counts=attendance_counts,
                         proxy_reasons=proxy_reasons,
                         current_time=now)

@admin_bp.route('/classrooms', methods=['GET', 'POST'])
@login_required
@admin_required
def classrooms():
    db = current_app.db
    if request.method == 'POST':
        name = request.form.get('name')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        
        if name and latitude and longitude:
            Classroom.create(db, name, latitude, longitude, current_user.id)
            flash('Classroom created successfully!', 'success')
        else:
            flash('All fields are required', 'danger')
        
        return redirect(url_for('admin.classrooms'))
    
    classrooms = Classroom.get_all(db)
    return render_template('admin/classrooms.html', classrooms=classrooms)

@admin_bp.route('/students', methods=['GET', 'POST'])
@login_required
@admin_required
def students():
    db = current_app.db
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        class_id = request.form.get('class_id')
        
        # Generate random password
        password = generate_random_password()
        
        try:
            # Create user
            User.create_user(db, email, name, password, role='student', class_id=class_id)
            
            # Send email
            try:
                msg = Message('Your Attendance System Credentials', recipients=[email])
                # Plain-text fallback
                login_url = url_for('auth.login', _external=True)
                text_body = f"""
Hello {name},

An account has been created for you on the Attendance Geo Tracker system.

Login Credentials:
Email: {email}
Password: {password}

Please login at: {login_url}

Keep your credentials secure.

Best regards,
Attendance Geo Tracker
"""
                msg.body = text_body

                # HTML version rendered from a template
                try:
                    html_body = render_template('emails/student_credentials.html',
                                                name=name,
                                                email=email,
                                                password=password,
                                                login_url=login_url)
                    msg.html = html_body
                except Exception:
                    # If template rendering fails, fall back to plain text only
                    pass

                current_app.mail.send(msg)
                flash(f'Student added successfully! Credentials sent to {email}', 'success')
            except Exception as e:
                flash(f'Student added but email failed: {str(e)}', 'warning')
        except Exception as e:
            flash(f'Error creating student: {str(e)}', 'danger')
        
        return redirect(url_for('admin.students'))
    
    db = current_app.db
    students = list(db.users.find({'role': 'student'}))
    classrooms = Classroom.get_all(db)
    return render_template('admin/students.html', students=students, classrooms=classrooms)

@admin_bp.route('/import_students', methods=['POST'])
@login_required
@admin_required
def import_students():
    db = current_app.db

    if 'file' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('admin.students'))

    file = request.files['file']

    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin.students'))

    try:
        df = pd.read_excel(file)

        imported = 0

        for _, row in df.iterrows():

            classroom = db.classrooms.find_one({
                'name': str(row['class']).strip()
            })

            if not classroom:
                continue

            existing = User.get_by_email(
                db,
                str(row['email']).strip()
            )

            if existing:
                continue

            User.create_user(
                db,
                str(row['email']).strip(),
                str(row['name']).strip(),
                str(row['password']).strip(),
                role='student',
                class_id=str(classroom['_id'])
            )

            imported += 1

        flash(f'{imported} students imported successfully!', 'success')

    except Exception as e:
        flash(f'Import failed: {str(e)}', 'danger')

    return redirect(url_for('admin.students'))
@admin_bp.route('/delete_student/<student_id>')
@login_required
@admin_required
def delete_student(student_id):
    db = current_app.db
    db.users.delete_one({'_id': ObjectId(student_id)})
    flash('Student deleted successfully', 'success')
    return redirect(url_for('admin.students'))

@admin_bp.route('/generate_qr/<classroom_id>')
@login_required
@admin_required
def generate_qr(classroom_id):
    db = current_app.db
    classroom = Classroom.get_by_id(db, classroom_id)
    
    if not classroom:
        flash('Classroom not found', 'danger')
        return redirect(url_for('admin.classrooms'))
    
    # Create session
    session_data = Session.create(db, str(classroom['_id']), current_user.id, expiry_minutes=10)
    
    # Generate QR code data
    qr_data = {
        'session_id': session_data['session_id'],
        'class_id': str(classroom['_id']),
        'timestamp': session_data['created_at'].isoformat(),
        'random_token': session_data['random_token']
    }
    
    qr_code_image = generate_qr_code(qr_data)
    
    return render_template('admin/generate_qr.html',
                         classroom=classroom,
                         session=session_data,
                         qr_code=qr_code_image)

@admin_bp.route('/attendance_report/<session_id>')
@login_required
@admin_required
def attendance_report(session_id):
    db = current_app.db
    session = Session.get_by_session_id(db, session_id)
    
    if not session:
        flash('Session not found', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    classroom = Classroom.get_by_id(db, session['class_id'])
    attendances = Attendance.get_by_session(db, session_id)
    
    # Get student details
    attendance_details = []
    for att in attendances:
        student = db.users.find_one({'_id': ObjectId(att['student_id'])})
        if student:
            attendance_details.append({
                'student_name': student['name'],
                'student_email': student['email'],
                'marked_at': att['marked_at'],
                'latitude': att['latitude'],
                'longitude': att['longitude']
            })
    
    # Get all students in this class
    all_students = list(db.users.find({'role': 'student', 'class_id': session['class_id']}))
    attended_ids = [att['student_id'] for att in attendances]
    absent_students = [s for s in all_students if str(s['_id']) not in attended_ids]
    
    return render_template('admin/attendance_report.html',
                         session=session,
                         classroom=classroom,
                         attendances=attendance_details,
                         absent_students=absent_students)

@admin_bp.route('/proxy_attempts')
@login_required
@admin_required
def proxy_attempts():
    db = current_app.db
    attempts = ProxyAttempt.get_all(db)
    
    # Enrich with student and session details
    enriched_attempts = []
    for attempt in attempts:
        student = db.users.find_one({'_id': ObjectId(attempt['student_id'])})
        session = Session.get_by_session_id(db, attempt['session_id'])
        classroom = Classroom.get_by_id(db, session['class_id']) if session else None
        
        enriched_attempts.append({
            'student_name': student['name'] if student else 'Unknown',
            'student_email': student['email'] if student else 'Unknown',
            'classroom_name': classroom['name'] if classroom else 'Unknown',
            'reason': attempt['reason'],
            'timestamp': attempt['timestamp'],
            'scanned_location': attempt['scanned_location'],
            'expected_location': attempt['expected_location']
        })
    
    return render_template('admin/proxy_attempts.html', attempts=enriched_attempts)

@admin_bp.route('/export_attendance/<session_id>')
@login_required
@admin_required
def export_attendance(session_id):
    db = current_app.db
    session = Session.get_by_session_id(db, session_id)
    classroom = Classroom.get_by_id(db, session['class_id'])
    attendances = Attendance.get_by_session(db, session_id)
    
    # Create CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Student Name', 'Email', 'Marked At', 'Latitude', 'Longitude'])
    
    for att in attendances:
        student = db.users.find_one({'_id': ObjectId(att['student_id'])})
        if student:
            writer.writerow([
                student['name'],
                student['email'],
                att['marked_at'].strftime('%Y-%m-%d %H:%M:%S'),
                att['latitude'],
                att['longitude']
            ])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=attendance_{session_id}.csv"
    output.headers["Content-type"] = "text/csv"
    return output