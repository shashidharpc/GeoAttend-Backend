from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from . import student_bp
from models import Session, Attendance, ProxyAttempt, Classroom
from utils import calculate_distance
from bson.objectid import ObjectId
import json
from datetime import datetime

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            flash('Access denied. Student privileges required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    db = current_app.db
    # Get student's attendance records
    attendances = Attendance.get_by_student(db, current_user.id)
    
    # Get total classes for this student's classroom
    total_sessions = 0
    if current_user.class_id:
        total_sessions = db.sessions.count_documents({'class_id': current_user.class_id})
    
    attendance_percentage = 0
    if total_sessions > 0:
        attendance_percentage = (len(attendances) / total_sessions) * 100
    
    # Get recent attendance with session details
    recent_attendance = []
    for att in attendances[-10:]:
        session = Session.get_by_session_id(db, att['session_id'])
        if session:
            classroom = Classroom.get_by_id(db, session['class_id'])
            recent_attendance.append({
                'classroom': classroom['name'] if classroom else 'Unknown',
                'marked_at': att['marked_at']
            })
    
    return render_template('student/dashboard.html',
                         total_attended=len(attendances),
                         total_classes=total_sessions,
                         attendance_percentage=round(attendance_percentage, 2),
                         recent_attendance=recent_attendance)

@student_bp.route('/scan_qr')
@login_required
@student_required
def scan_qr():
    return render_template('student/scan_qr.html')

@student_bp.route('/verify_attendance', methods=['POST'])
@login_required
@student_required
def verify_attendance():
    try:
        data = request.get_json()
        qr_data = json.loads(data.get('qr_data'))
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
        
        session_id = qr_data.get('session_id')
        
        # Get session
        db = current_app.db
        session = Session.get_by_session_id(db, session_id)
        
        if not session:
            return jsonify({
                'success': False,
                'message': 'Invalid QR code'
            })
        
        # Check if session is valid
        is_valid, message = Session.is_valid(session)
        
        if not is_valid:
            # Log proxy attempt
            classroom = Classroom.get_by_id(db, session['class_id'])
            ProxyAttempt.log(
                db,
                current_user.id,
                session_id,
                latitude,
                longitude,
                classroom['latitude'] if classroom else 0,
                classroom['longitude'] if classroom else 0,
                message
            )
            return jsonify({
                'success': False,
                'message': message
            })
        
        # Check if student belongs to this class
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
                'Wrong class'
            )
            return jsonify({
                'success': False,
                'message': 'You are not enrolled in this class'
            })
        
        # Check if already marked
        if Attendance.check_already_marked(db, current_user.id, session_id):
            return jsonify({
                'success': False,
                'message': 'Attendance already marked for this session'
            })
        
        # Get classroom location
        classroom = Classroom.get_by_id(db, session['class_id'])
        
        if not classroom:
            return jsonify({
                'success': False,
                'message': 'Classroom not found'
            })
        
        # Calculate distance
        distance = calculate_distance(
            latitude,
            longitude,
            classroom['latitude'],
            classroom['longitude']
        )
        
        # Check geofence
        if distance > 30:  # 30 meters
            ProxyAttempt.log(
                db,
                current_user.id,
                session_id,
                latitude,
                longitude,
                classroom['latitude'],
                classroom['longitude'],
                f'Outside allowed radius (Distance: {round(distance, 2)}m)'
            )
            return jsonify({
                'success': False,
                'message': f'You are outside the allowed area (Distance: {round(distance, 2)}m)'
            })
        
        # Mark attendance
        success = Attendance.mark(db, current_user.id, session_id, latitude, longitude)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Attendance marked successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to mark attendance'
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })