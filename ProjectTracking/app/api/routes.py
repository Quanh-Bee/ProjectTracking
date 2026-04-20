from flask import Flask, request, jsonify, render_template, send_file, make_response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import json
import numpy as np
import sys
import io
import csv

# Ensure project root is on sys.path so imports like `from config import config` work
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import config
from config import Config
from app.models.database import db, Person, Attendance, Device, Log, init_db, get_db_stats
from app.services.face_recognition import FaceRecognitionService
from app.services.tracking import TrackingService
from app.services.attendance import AttendanceService

def create_app(config_name='default'):
    """Tạo Flask app"""
    import os
    # Sử dụng đường dẫn tuyệt đối đến templates folder
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    template_path = os.path.join(project_root, 'templates')
    
    app = Flask(__name__, template_folder=template_path)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    CORS(app)
    
    # Initialize services
    face_service = FaceRecognitionService()
    tracking_service = TrackingService()
    attendance_service = AttendanceService()
    # Expose services on app so they can be reused by other parts of the program
    app.face_service = face_service
    app.tracking_service = tracking_service
    app.attendance_service = attendance_service
    # Allow services to access the Flask app (so they can push DB writes from other threads)
    try:
        face_service.app = app
        tracking_service.app = app
        attendance_service.app = app
    except Exception:
        pass
    # Also set reference to app on services so they can use app_context from other threads
    try:
        face_service.app = app
    except Exception:
        pass
    try:
        tracking_service.app = app
    except Exception:
        pass
    try:
        attendance_service.app = app
    except Exception:
        pass
    
    # Initialize database
    with app.app_context():
        init_db(app)
        # After DB init, reload known faces so filenames in known_faces/ map to Person records
        try:
            face_service.load_known_faces()
        except Exception:
            pass
    
    # API Routes
    @app.route('/')
    def index():
        """Trang chủ dashboard"""
        try:
            return render_template('dashboard.html')
        except Exception as e:
            return f'<html><body><h1>Error</h1><p>Dashboard error: {str(e)}</p></body></html>', 500
    
    @app.route('/api/stats', methods=['GET'])
    def get_stats():
        """Lấy thống kê tổng quan"""
        try:
            db_stats = get_db_stats()
            # Lấy thống kê realtime từ service in-memory
            realtime_stats = attendance_service.get_realtime_stats()

            # Nếu service in-memory không có active (ví dụ khi camera ghi vào DB hoặc chạy tác vụ process),
            # fallback sang dữ liệu từ database (attendance time_out is NULL)
            try:
                if not realtime_stats or realtime_stats.get('active_people', 0) == 0:
                    realtime_stats = realtime_stats or {}
                    realtime_stats['active_people'] = db_stats.get('active_attendances', 0)
                    # Provide active_tracks as empty list if not present
                    realtime_stats.setdefault('active_tracks', [])
                    realtime_stats.setdefault('timestamp', None)
            except Exception:
                # Bỏ qua, trả về default
                pass

            return jsonify({
                'success': True,
                'data': {
                    'database': db_stats,
                    'realtime': realtime_stats
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/attendance', methods=['GET'])
    def get_attendance():
        """Lấy danh sách attendance"""
        try:
            # Get attendance data directly from database
            from app.models.database import Attendance, Person

            # Support limit query parameter for pagination / templates
            limit = request.args.get('limit', 100, type=int)

            # Simple query without relationships
            attendances = db.session.query(
                Attendance.attendance_id,
                Attendance.person_id,
                Attendance.track_id,
                Attendance.time_in,
                Attendance.time_out,
                Attendance.status,
                Person.name.label('person_name')
            ).outerjoin(Person, Attendance.person_id == Person.person_id)\
             .order_by(Attendance.time_in.desc())\
             .limit(limit).all()
            
            # Convert to dict
            attendance_data = []
            for row in attendances:
                # Calculate duration manually
                duration_minutes = 0
                if row.time_in and row.time_out:
                    duration = row.time_out - row.time_in
                    duration_minutes = int(duration.total_seconds() / 60)
                elif row.time_in:
                    duration = datetime.now() - row.time_in
                    duration_minutes = int(duration.total_seconds() / 60)
                
                attendance_data.append({
                    'attendance_id': row.attendance_id,
                    'person_id': row.person_id,
                    'person_name': row.person_name or 'Unknown',
                    'track_id': row.track_id,
                    'time_in': row.time_in.isoformat() if row.time_in else None,
                    'time_out': row.time_out.isoformat() if row.time_out else None,
                    'status': row.status,
                    'duration_minutes': duration_minutes
                })
            
            return jsonify({
                'success': True,
                'data': attendance_data
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/attendance/stats', methods=['GET'])
    def get_attendance_stats():
        """Lấy thống kê attendance"""
        try:
            date_str = request.args.get('date')
            date = datetime.fromisoformat(date_str).date() if date_str else None
            
            stats = attendance_service.get_attendance_stats(date)
            
            return jsonify({
                'success': True,
                'data': stats
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/persons', methods=['GET'])
    def get_persons():
        """Lấy danh sách người dùng"""
        try:
            persons = Person.query.all()
            return jsonify({
                'success': True,
                'data': [person.to_dict() for person in persons]
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/persons', methods=['POST'])
    def create_person():
        """Tạo người dùng mới"""
        try:
            data = request.get_json()
            
            if not data or 'name' not in data:
                return jsonify({'success': False, 'error': 'Name is required'}), 400
            
            person = Person(
                name=data['name'],
                role=data.get('role', 'user')
            )
            
            db.session.add(person)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'data': person.to_dict()
            }), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/persons/<int:person_id>/attendance-summary', methods=['GET'])
    def get_person_attendance_summary(person_id):
        """Lấy tổng kết attendance của một người"""
        try:
            days = request.args.get('days', 30, type=int)
            
            summary = attendance_service.get_person_attendance_summary(person_id, days)
            
            return jsonify({
                'success': True,
                'data': summary
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/face-recognition/add-face', methods=['POST'])
    def add_face():
        """Thêm khuôn mặt mới"""
        try:
            data = request.get_json()
            
            if not data or 'name' not in data or 'face_encoding' not in data:
                return jsonify({'success': False, 'error': 'Name and face_encoding are required'}), 400
            
            # Save face to database
            face_encoding = np.array(data['face_encoding'])
            person = face_service.save_face_to_database(
                name=data['name'],
                face_encoding=face_encoding,
                role=data.get('role', 'user')
            )
            
            if person:
                return jsonify({
                    'success': True,
                    'data': person.to_dict()
                }), 201
            else:
                return jsonify({'success': False, 'error': 'Failed to save face'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/persons/register', methods=['POST'])
    def register_person():
        """Đăng ký người mới bằng tên + up to 3 ảnh upload (multipart/form-data)
        Fields: name (str), images (file[])"""
        try:
            name = request.form.get('name')
            if not name:
                return jsonify({'success': False, 'error': 'Name is required'}), 400

            files = request.files.getlist('images')
            if not files or not any(f.filename for f in files):
                return jsonify({'success': False, 'error': 'At least one image is required'}), 400

            saved_files = []
            encodings = []

            # Ensure known_faces directory exists
            os.makedirs(Config.KNOWN_FACES_DIR, exist_ok=True)

            # Save images and compute encodings
            idx = 0
            failed_files = []
            for f in files[:3]:
                if f and f.filename:
                    idx += 1
                    filename = f"{name.replace(' ', '_')}_{idx}{os.path.splitext(f.filename)[1]}"
                    path = os.path.join(Config.KNOWN_FACES_DIR, filename)
                    f.save(path)
                    saved_files.append(path)

                    # Compute encoding using face service
                    try:
                        enc = face_service.get_face_encoding_from_image(path)
                        if enc is not None:
                            encodings.append(enc)
                            print(f"Successfully processed {filename}, encoding shape: {enc.shape}")
                        else:
                            failed_files.append(filename)
                            print(f"No face detected in {filename}")
                    except Exception as e:
                        failed_files.append(filename)
                        print(f"Error processing {filename}: {e}")
                        import traceback
                        traceback.print_exc()

            if not encodings:
                error_msg = 'No valid faces detected in uploaded images'
                if failed_files:
                    error_msg += f'. Failed files: {", ".join(failed_files)}'
                error_msg += '. Please ensure images contain clear, front-facing faces with good lighting.'
                return jsonify({'success': False, 'error': error_msg}), 400

            # Create or update person record
            person = Person.query.filter_by(name=name).first()
            if not person:
                person = Person(name=name, role='user')
                db.session.add(person)
                db.session.commit()

            # Compute centroid encoding and save
            try:
                centroid = np.mean(encodings, axis=0)
                centroid = centroid / (np.linalg.norm(centroid) + 1e-7)
                
                person.face_encoding = json.dumps(centroid.tolist())
                db.session.commit()
                
                # Add to face service
                face_service.add_known_face(name, centroid, person.person_id)
                
                # Reload all face encodings to ensure consistency
                face_service.load_known_faces()
                
                print(f"Successfully registered {name} with {len(encodings)} face encodings")
                print(f"Total known faces after reload: {len(face_service.known_face_encodings)}")
                
            except Exception as e:
                db.session.rollback()
                print(f"Error saving person {name}: {e}")
                return jsonify({'success': False, 'error': f'Failed to save person: {str(e)}'}), 500

            return jsonify({
                'success': True, 
                'data': {
                    'person_id': person.person_id, 
                    'name': person.name,
                    'saved_files': saved_files,
                    'encodings_count': len(encodings)
                }
            }), 201
            
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/tracking/active', methods=['GET'])
    def get_active_tracks():
        """Lấy danh sách track đang hoạt động"""
        try:
            active_tracks = tracking_service.get_active_tracks()
            active_attendances = attendance_service.get_active_attendances()
            
            # Combine tracking and attendance data
            result = []
            for track_id, track_info in active_tracks.items():
                attendance = active_attendances.get(track_id)
                
                # Handle attendance data (could be dict or object)
                if attendance:
                    # attendance may be a SQLAlchemy model or our in-memory dict
                    if hasattr(attendance, 'time_in'):
                        time_in = attendance.time_in.isoformat() if attendance.time_in else None
                        duration_minutes = attendance.get_duration_minutes() if hasattr(attendance, 'get_duration_minutes') else 0
                    else:
                        # dict form
                        t_in = attendance.get('time_in')
                        if hasattr(t_in, 'isoformat'):
                            time_in = t_in.isoformat()
                        elif isinstance(t_in, str):
                            time_in = t_in
                        else:
                            time_in = None
                        # compute duration if time_in present
                        if attendance.get('time_in') and attendance.get('time_out'):
                            try:
                                duration_minutes = int((attendance.get('time_out') - attendance.get('time_in')).total_seconds() / 60)
                            except Exception:
                                duration_minutes = 0
                        elif attendance.get('time_in'):
                            try:
                                duration_minutes = int((datetime.now() - attendance.get('time_in')).total_seconds() / 60)
                            except Exception:
                                duration_minutes = 0
                        else:
                            duration_minutes = 0
                else:
                    time_in = None
                    duration_minutes = 0
                
                result.append({
                    'track_id': track_id,
                    'name': track_info['name'],
                    'person_id': track_info['person_id'],
                    'last_seen': track_info['last_seen'].isoformat(),
                    'time_in': time_in,
                    'duration_minutes': duration_minutes
                })
            
            return jsonify({
                'success': True,
                'data': result
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/logs', methods=['GET'])
    def get_logs():
        """Lấy logs hệ thống"""
        try:
            limit = request.args.get('limit', 100, type=int)
            event_type = request.args.get('event_type')
            
            query = Log.query
            
            if event_type:
                query = query.filter(Log.event_type.like(f'%{event_type}%'))
            
            logs = query.order_by(Log.timestamp.desc()).limit(limit).all()
            
            return jsonify({
                'success': True,
                'data': [log.to_dict() for log in logs]
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/realtime/update', methods=['POST'])
    def realtime_update():
        """Receive realtime updates from camera/process (time_in, time_out, active tracks)
        Expected JSON payload examples:
          {"event": "time_in", "track_id": "t1", "person_id": 1, "person_name": "Alice"}
          {"event": "time_out", "track_id": "t1"}
          {"event": "tracks", "active_tracks": [{"track_id":"t1","name":"Alice","person_id":1}, ...]}
        """
        try:
            # Simple API key protection: require X-API-KEY header matching SECRET_KEY
            api_key = request.headers.get('X-API-KEY')
            if not api_key or api_key != app.config.get('SECRET_KEY'):
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401

            data = request.get_json() or {}
            event = data.get('event')

            # Basic validation
            if not event:
                return jsonify({'success': False, 'error': 'Missing event field'}), 400

            if event == 'time_in':
                track_id = data.get('track_id')
                person_id = data.get('person_id')
                person_name = data.get('person_name')
                if not track_id:
                    return jsonify({'success': False, 'error': 'track_id required for time_in'}), 400
                attendance = attendance_service.log_time_in(track_id, person_id, person_name)
                # If attendance is a model instance, return its dict
                try:
                    result = attendance.to_dict() if hasattr(attendance, 'to_dict') else attendance
                except Exception:
                    result = None
                return jsonify({'success': True, 'data': result}), 200

            if event == 'time_out':
                track_id = data.get('track_id')
                attendance = attendance_service.log_time_out(track_id)
                return jsonify({'success': True}), 200

            if event == 'tracks':
                active_tracks = data.get('active_tracks', [])
                # Update tracking names/persons in tracking_service
                for t in active_tracks:
                    try:
                        tracking_service.assign_name_to_track(t.get('track_id'), t.get('name'), t.get('person_id'))
                    except Exception:
                        pass
                return jsonify({'success': True}), 200

            return jsonify({'success': False, 'error': 'Unknown event type'}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/export/attendance', methods=['GET'])
    def export_attendance():
        """Xuất dữ liệu attendance"""
        try:
            date_from = request.args.get('date_from')
            date_to = request.args.get('date_to')
            format_type = request.args.get('format', 'json')
            
            # Convert date strings
            if date_from:
                date_from = datetime.fromisoformat(date_from)
            if date_to:
                date_to = datetime.fromisoformat(date_to)
            
            normalized_format = (format_type or 'json').lower() if format_type else 'json'
            request_format = normalized_format if normalized_format in ('json', 'excel', 'xlsx', 'csv') else 'json'

            data = attendance_service.export_attendance_data(
                date_from=date_from,
                date_to=date_to,
                format='json' if request_format in ('excel', 'xlsx', 'csv') else request_format
            )

            if request_format == 'csv':
                output = io.StringIO()
                writer = csv.writer(output)
                headers = ['attendance_id', 'person_name', 'person_id', 'track_id', 'time_in', 'time_out', 'status', 'duration_minutes']
                writer.writerow(headers)
                for item in data:
                    writer.writerow([
                        item.get('attendance_id'),
                        item.get('person_name'),
                        item.get('person_id'),
                        item.get('track_id'),
                        item.get('time_in'),
                        item.get('time_out'),
                        item.get('status'),
                        item.get('duration_minutes')
                    ])
                csv_content = output.getvalue()
                output.close()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'attendance_report_{timestamp}.csv'
                response = make_response(csv_content)
                response.headers['Content-Disposition'] = f'attachment; filename={filename}'
                response.headers['Content-Type'] = 'text/csv; charset=utf-8'
                return response

            if request_format in ('excel', 'xlsx'):
                try:
                    from openpyxl import Workbook
                except ImportError as e:
                    # Fallback: generate CSV if openpyxl is unavailable
                    output = io.StringIO()
                    writer = csv.writer(output)
                    headers = ['attendance_id', 'person_name', 'person_id', 'track_id', 'time_in', 'time_out', 'status', 'duration_minutes']
                    writer.writerow(headers)
                    for item in data:
                        writer.writerow([
                            item.get('attendance_id'),
                            item.get('person_name'),
                            item.get('person_id'),
                            item.get('track_id'),
                            item.get('time_in'),
                            item.get('time_out'),
                            item.get('status'),
                            item.get('duration_minutes')
                        ])
                    csv_content = output.getvalue()
                    output.close()
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f'attendance_report_{timestamp}.csv'
                    response = make_response(csv_content)
                    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
                    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
                    return response

                workbook = Workbook()
                ws = workbook.active
                ws.title = 'Attendance'
                headers = ['Attendance ID', 'Tên', 'Person ID', 'Track ID', 'Time In', 'Time Out', 'Trạng thái', 'Thời lượng (phút)']
                ws.append(headers)

                for item in data:
                    ws.append([
                        item.get('attendance_id'),
                        item.get('person_name'),
                        item.get('person_id'),
                        item.get('track_id'),
                        item.get('time_in'),
                        item.get('time_out'),
                        item.get('status'),
                        item.get('duration_minutes')
                    ])

                # Auto width
                for column_cells in ws.columns:
                    length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
                    adjusted_width = min(length + 2, 40)
                    ws.column_dimensions[column_cells[0].column_letter].width = adjusted_width

                output = io.BytesIO()
                workbook.save(output)
                output.seek(0)
                filename_parts = ['attendance_report']
                if date_from:
                    filename_parts.append(f"from_{date_from.strftime('%Y%m%d')}")
                if date_to:
                    filename_parts.append(f"to_{date_to.strftime('%Y%m%d')}")
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename_parts.append(timestamp)
                filename = '_'.join(filename_parts) + '.xlsx'

                return send_file(
                    output,
                    as_attachment=True,
                    download_name=filename,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )

            return jsonify({
                'success': True,
                'data': data
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/attendance/checkout-all', methods=['POST'])
    def checkout_all_attendance():
        """Check-out tất cả attendance đang hoạt động"""
        try:
            results = attendance_service.checkout_all_active()
            return jsonify({
                'success': True,
                'data': {
                    'checked_out': len(results)
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/attendance/clear', methods=['POST'])
    def clear_attendance_history():
        """Xóa toàn bộ lịch sử attendance"""
        try:
            deleted = attendance_service.clear_all_history()
            return jsonify({
                'success': True,
                'data': {
                    'deleted': deleted
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/face-recognition/reload', methods=['POST'])
    def reload_face_encodings():
        """Reload face encodings từ database vào memory"""
        try:
            # Reload known faces
            face_service.load_known_faces()
            
            return jsonify({
                'success': True,
                'data': {
                    'known_faces_count': len(face_service.known_face_encodings),
                    'encoding_dimension': face_service.encoding_dim,
                    'embedding_enabled': face_service._embedding_enabled
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Internal server error'}), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
