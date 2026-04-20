from datetime import datetime, timedelta
from app.models.database import Attendance, Person, Log, Device, db
from config import Config
import json

class AttendanceService:
    """Service quản lý chấm công và theo dõi hiện diện"""
    
    def __init__(self):
        # Store active attendances as serializable dicts to avoid keeping
        # SQLAlchemy model instances across sessions (which causes detached
        # instance errors). Structure:
        # { track_id: {
        #     'attendance_id': int or None,
        #     'person_id': int or None,
        #     'person_name': str or None,
        #     'track_id': str,
        #     'time_in': datetime,
        #     'time_out': datetime or None,
        #     'status': str
        #   }
        # }
        self.active_attendances = {}
    
    def log_time_in_manual(self, track_id, person_id=None, person_name=None):
        """Ghi log thời gian vào thủ công - chỉ tạo mới nếu user chưa có attendance đang mở"""
        try:
            try:
                app_ctx = getattr(self, 'app', None)
                if app_ctx:
                    with app_ctx.app_context():
                        # Kiểm tra xem user đã có attendance đang mở (time_out = null) chưa
                        existing_attendance = None
                        if person_id:
                            existing_attendance = Attendance.query.filter(
                                Attendance.person_id == person_id,
                                Attendance.time_out.is_(None)
                            ).first()
                        elif person_name:
                            # Tìm person_id từ name
                            person = Person.query.filter_by(name=person_name).first()
                            if person:
                                existing_attendance = Attendance.query.filter(
                                    Attendance.person_id == person.person_id,
                                    Attendance.time_out.is_(None)
                                ).first()
                        
                        # Nếu đã có attendance đang mở, return attendance đó
                        if existing_attendance:
                            print(f"User {person_name or person_id} already has an open attendance. Skipping check-in.")
                            return {
                                'attendance_id': existing_attendance.attendance_id,
                                'person_id': existing_attendance.person_id,
                                'person_name': existing_attendance.person.name if getattr(existing_attendance, 'person', None) else person_name,
                                'track_id': existing_attendance.track_id,
                                'time_in': existing_attendance.time_in,
                                'time_out': existing_attendance.time_out,
                                'status': existing_attendance.status
                            }
                        
                        # Tạo attendance record mới
                        attendance = Attendance(
                            person_id=person_id,
                            track_id=track_id,
                            time_in=datetime.now(),
                            status='Present'
                        )

                        db.session.add(attendance)
                        db.session.commit()

                        attendance_data = {
                            'attendance_id': attendance.attendance_id,
                            'person_id': attendance.person_id,
                            'person_name': attendance.person.name if getattr(attendance, 'person', None) else person_name,
                            'track_id': track_id,
                            'time_in': attendance.time_in,
                            'time_out': attendance.time_out,
                            'status': attendance.status
                        }

                        self.log_attendance_event('time_in_manual', {
                            'track_id': track_id,
                            'person_id': person_id,
                            'person_name': person_name,
                            'attendance_id': attendance.attendance_id
                        })

                        print(f"Manual time in logged: {person_name or 'Unknown'} (Track ID: {track_id})")
                        return attendance_data
                else:
                    from flask import current_app
                    with current_app.app_context():
                        # Kiểm tra xem user đã có attendance đang mở chưa
                        existing_attendance = None
                        if person_id:
                            existing_attendance = Attendance.query.filter(
                                Attendance.person_id == person_id,
                                Attendance.time_out.is_(None)
                            ).first()
                        elif person_name:
                            person = Person.query.filter_by(name=person_name).first()
                            if person:
                                existing_attendance = Attendance.query.filter(
                                    Attendance.person_id == person.person_id,
                                    Attendance.time_out.is_(None)
                                ).first()
                        
                        if existing_attendance:
                            print(f"User {person_name or person_id} already has an open attendance. Skipping check-in.")
                            return {
                                'attendance_id': existing_attendance.attendance_id,
                                'person_id': existing_attendance.person_id,
                                'person_name': existing_attendance.person.name if getattr(existing_attendance, 'person', None) else person_name,
                                'track_id': existing_attendance.track_id,
                                'time_in': existing_attendance.time_in,
                                'time_out': existing_attendance.time_out,
                                'status': existing_attendance.status
                            }
                        
                        attendance = Attendance(
                            person_id=person_id,
                            track_id=track_id,
                            time_in=datetime.now(),
                            status='Present'
                        )

                        db.session.add(attendance)
                        db.session.commit()

                        attendance_data = {
                            'attendance_id': attendance.attendance_id,
                            'person_id': attendance.person_id,
                            'person_name': attendance.person.name if getattr(attendance, 'person', None) else person_name,
                            'track_id': track_id,
                            'time_in': attendance.time_in,
                            'time_out': attendance.time_out,
                            'status': attendance.status
                        }

                        self.log_attendance_event('time_in_manual', {
                            'track_id': track_id,
                            'person_id': person_id,
                            'person_name': person_name,
                            'attendance_id': attendance.attendance_id
                        })

                        print(f"Manual time in logged: {person_name or 'Unknown'} (Track ID: {track_id})")
                        return attendance_data
            except RuntimeError:
                attendance_data = {
                    'attendance_id': None,
                    'track_id': track_id,
                    'person_id': person_id,
                    'person_name': person_name,
                    'time_in': datetime.now(),
                    'time_out': None,
                    'status': 'Present'
                }
                print(f"Manual time in logged (memory only): {person_name or 'Unknown'} (Track ID: {track_id})")
                return attendance_data
            
        except Exception as e:
            print(f"Error logging manual time in: {e}")
            return None
    
    def log_time_out_manual(self, person_id=None, person_name=None):
        """Check-out user dựa vào person_id hoặc name (không cần track_id, user có thể không có mặt trên camera)"""
        try:
            try:
                app_ctx = getattr(self, 'app', None)
                if app_ctx:
                    with app_ctx.app_context():
                        # Tìm attendance đang mở (time_out = null) của user
                        existing_attendance = None
                        if person_id:
                            existing_attendance = Attendance.query.filter(
                                Attendance.person_id == person_id,
                                Attendance.time_out.is_(None)
                            ).first()
                        elif person_name:
                            person = Person.query.filter_by(name=person_name).first()
                            if person:
                                existing_attendance = Attendance.query.filter(
                                    Attendance.person_id == person.person_id,
                                    Attendance.time_out.is_(None)
                                ).first()
                        
                        if not existing_attendance:
                            print(f"No open attendance found for user {person_name or person_id}")
                            return None
                        
                        # Update time_out
                        existing_attendance.time_out = datetime.now()
                        db.session.commit()
                        
                        person_name = existing_attendance.person.name if getattr(existing_attendance, 'person', None) else person_name
                        try:
                            duration_minutes = existing_attendance.get_duration_minutes()
                        except Exception:
                            duration_minutes = 0
                        
                        self.log_attendance_event('time_out_manual', {
                            'person_id': existing_attendance.person_id,
                            'person_name': person_name,
                            'attendance_id': existing_attendance.attendance_id,
                            'duration_minutes': duration_minutes
                        })
                        
                        print(f"Manual time out logged: {person_name} (Attendance ID: {existing_attendance.attendance_id})")
                        return {
                            'attendance_id': existing_attendance.attendance_id,
                            'person_id': existing_attendance.person_id,
                            'person_name': person_name,
                            'track_id': existing_attendance.track_id,
                            'time_in': existing_attendance.time_in,
                            'time_out': existing_attendance.time_out,
                            'status': existing_attendance.status
                        }
                else:
                    from flask import current_app
                    with current_app.app_context():
                        existing_attendance = None
                        if person_id:
                            existing_attendance = Attendance.query.filter(
                                Attendance.person_id == person_id,
                                Attendance.time_out.is_(None)
                            ).first()
                        elif person_name:
                            person = Person.query.filter_by(name=person_name).first()
                            if person:
                                existing_attendance = Attendance.query.filter(
                                    Attendance.person_id == person.person_id,
                                    Attendance.time_out.is_(None)
                                ).first()
                        
                        if not existing_attendance:
                            print(f"No open attendance found for user {person_name or person_id}")
                            return None
                        
                        existing_attendance.time_out = datetime.now()
                        db.session.commit()
                        
                        person_name = existing_attendance.person.name if getattr(existing_attendance, 'person', None) else person_name
                        try:
                            duration_minutes = existing_attendance.get_duration_minutes()
                        except Exception:
                            duration_minutes = 0
                        
                        self.log_attendance_event('time_out_manual', {
                            'person_id': existing_attendance.person_id,
                            'person_name': person_name,
                            'attendance_id': existing_attendance.attendance_id,
                            'duration_minutes': duration_minutes
                        })
                        
                        print(f"Manual time out logged: {person_name} (Attendance ID: {existing_attendance.attendance_id})")
                        return {
                            'attendance_id': existing_attendance.attendance_id,
                            'person_id': existing_attendance.person_id,
                            'person_name': person_name,
                            'track_id': existing_attendance.track_id,
                            'time_in': existing_attendance.time_in,
                            'time_out': existing_attendance.time_out,
                            'status': existing_attendance.status
                        }
            except RuntimeError:
                print(f"No app context for manual time out")
                return None
            
        except Exception as e:
            print(f"Error logging manual time out: {e}")
            return None
    
    def log_time_in(self, track_id, person_id=None, person_name=None):
        """Ghi log thời gian vào"""
        try:
            # Kiểm tra xem đã có attendance đang mở chưa
            if track_id in self.active_attendances:
                return self.active_attendances[track_id]
            
            # Tạo attendance record mới (chỉ lưu trong memory nếu không có app context)
            try:
                # Prefer using self.app if set (allows other threads to push DB writes)
                app_ctx = getattr(self, 'app', None)
                if app_ctx:
                    with app_ctx.app_context():
                        attendance = Attendance(
                            person_id=person_id,
                            track_id=track_id,
                            time_in=datetime.now(),
                            status='Present'
                        )

                        db.session.add(attendance)
                        db.session.commit()

                        # Build serializable dict to store in-memory
                        attendance_data = {
                            'attendance_id': attendance.attendance_id,
                            'person_id': attendance.person_id,
                            'person_name': attendance.person.name if getattr(attendance, 'person', None) else person_name,
                            'track_id': track_id,
                            'time_in': attendance.time_in,
                            'time_out': attendance.time_out,
                            'status': attendance.status
                        }

                        self.active_attendances[track_id] = attendance_data

                        # Log sự kiện
                        self.log_attendance_event('time_in', {
                            'track_id': track_id,
                            'person_id': person_id,
                            'person_name': person_name,
                            'attendance_id': attendance.attendance_id
                        })

                        print(f"Time in logged: {person_name or 'Unknown'} (Track ID: {track_id})")
                        return attendance_data
                else:
                    # fallback to current_app if available
                    from flask import current_app
                    with current_app.app_context():
                        attendance = Attendance(
                            person_id=person_id,
                            track_id=track_id,
                            time_in=datetime.now(),
                            status='Present'
                        )

                        db.session.add(attendance)
                        db.session.commit()

                        attendance_data = {
                            'attendance_id': attendance.attendance_id,
                            'person_id': attendance.person_id,
                            'person_name': attendance.person.name if getattr(attendance, 'person', None) else person_name,
                            'track_id': track_id,
                            'time_in': attendance.time_in,
                            'time_out': attendance.time_out,
                            'status': attendance.status
                        }

                        self.active_attendances[track_id] = attendance_data

                        self.log_attendance_event('time_in', {
                            'track_id': track_id,
                            'person_id': person_id,
                            'person_name': person_name,
                            'attendance_id': attendance.attendance_id
                        })

                        print(f"Time in logged: {person_name or 'Unknown'} (Track ID: {track_id})")
                        return attendance_data
            except RuntimeError:
                # Không có application context, lưu phiên bản memory-only
                attendance_data = {
                    'attendance_id': None,
                    'track_id': track_id,
                    'person_id': person_id,
                    'person_name': person_name,
                    'time_in': datetime.now(),
                    'time_out': None,
                    'status': 'Present'
                }
                self.active_attendances[track_id] = attendance_data
                print(f"Time in logged (memory only): {person_name or 'Unknown'} (Track ID: {track_id})")
                return attendance_data
            
        except Exception as e:
            print(f"Error logging time in: {e}")
            return None
    
    def log_time_out(self, track_id):
        """Ghi log thời gian ra"""
        try:
            if track_id not in self.active_attendances:
                return None

            attendance = self.active_attendances[track_id]

            try:
                app_ctx = getattr(self, 'app', None)
                if app_ctx:
                    with app_ctx.app_context():
                        # If attendance was persisted, update the DB record
                        if attendance.get('attendance_id'):
                            db_att = Attendance.query.get(attendance.get('attendance_id'))
                            if db_att:
                                db_att.time_out = datetime.now()
                                db.session.commit()

                                person_name = db_att.person.name if getattr(db_att, 'person', None) else attendance.get('person_name', 'Unknown')
                                try:
                                    duration_minutes = db_att.get_duration_minutes()
                                except Exception:
                                    duration_minutes = 0
                                self.log_attendance_event('time_out', {
                                    'track_id': track_id,
                                    'person_id': db_att.person_id,
                                    'person_name': person_name,
                                    'attendance_id': db_att.attendance_id,
                                    'duration_minutes': duration_minutes
                                })
                                print(f"Time out logged: {person_name} (Track ID: {track_id})")
                else:
                    # fallback to current_app if available
                    from flask import current_app
                    with current_app.app_context():
                        if attendance.get('attendance_id'):
                            db_att = Attendance.query.get(attendance.get('attendance_id'))
                            if db_att:
                                db_att.time_out = datetime.now()
                                db.session.commit()

                                person_name = db_att.person.name if getattr(db_att, 'person', None) else attendance.get('person_name', 'Unknown')
                                try:
                                    duration_minutes = db_att.get_duration_minutes()
                                except Exception:
                                    duration_minutes = 0
                                self.log_attendance_event('time_out', {
                                    'track_id': track_id,
                                    'person_id': db_att.person_id,
                                    'person_name': person_name,
                                    'attendance_id': db_att.attendance_id,
                                    'duration_minutes': duration_minutes
                                })
                                print(f"Time out logged: {person_name} (Track ID: {track_id})")
                    # If attendance was persisted, update the DB record
                    if attendance.get('attendance_id'):
                        db_att = Attendance.query.get(attendance.get('attendance_id'))
                        if db_att:
                            db_att.time_out = datetime.now()
                            db.session.commit()

                            person_name = db_att.person.name if getattr(db_att, 'person', None) else attendance.get('person_name', 'Unknown')
                            try:
                                duration_minutes = db_att.get_duration_minutes()
                            except Exception:
                                duration_minutes = 0
                            self.log_attendance_event('time_out', {
                                'track_id': track_id,
                                'person_id': db_att.person_id,
                                'person_name': person_name,
                                'attendance_id': db_att.attendance_id,
                                'duration_minutes': duration_minutes
                            })
                            print(f"Time out logged: {person_name} (Track ID: {track_id})")
                    else:
                        # Memory-only data
                        attendance['time_out'] = datetime.now()
                        person_name = attendance.get('person_name', 'Unknown')
                        print(f"Time out logged (memory only): {person_name} (Track ID: {track_id})")
            except RuntimeError:
                # No app context: update memory-only record
                attendance['time_out'] = datetime.now()
                person_name = attendance.get('person_name', 'Unknown')
                print(f"Time out logged (memory only): {person_name} (Track ID: {track_id})")

            # Remove from active attendances
            del self.active_attendances[track_id]

            return attendance
            
        except Exception as e:
            print(f"Error logging time out: {e}")
            return None
    
    def checkout_all_active(self):
        """Check-out tất cả attendance còn đang mở trong hệ thống (in-memory + database)."""
        try:
            results = []

            # Khi có app context: cập nhật trực tiếp các bản ghi trong DB
            app_ctx = getattr(self, 'app', None)
            ctx = None
            if app_ctx:
                ctx = app_ctx.app_context()
            else:
                try:
                    from flask import current_app
                    ctx = current_app.app_context()
                except RuntimeError:
                    ctx = None

            if ctx:
                with ctx:
                    open_attendances = Attendance.query.filter(Attendance.time_out.is_(None)).all()
                    now = datetime.now()
                    now = datetime.now()
                    updated_attendances = []
                    for att in open_attendances:
                        att.time_out = now
                        updated_attendances.append(att)

                    if updated_attendances:
                        try:
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                            updated_attendances = []

                    for att in updated_attendances:
                        person_name = att.person.name if getattr(att, 'person', None) else 'Unknown'
                        try:
                            duration_minutes = att.get_duration_minutes()
                        except Exception:
                            duration_minutes = 0

                        self.log_attendance_event('time_out', {
                            'track_id': att.track_id,
                            'person_id': att.person_id,
                            'person_name': person_name,
                            'attendance_id': att.attendance_id,
                            'duration_minutes': duration_minutes
                        })

                        # Sync lại in-memory nếu track_id tồn tại
                        if att.track_id in self.active_attendances:
                            try:
                                del self.active_attendances[att.track_id]
                            except Exception:
                                pass

                        results.append(att)

            # Nếu còn bản ghi trong bộ nhớ (hoặc không có context), check-out thủ công
            remaining_tracks = list(self.active_attendances.keys())
            for track_id in remaining_tracks:
                res = self.log_time_out(track_id)
                if res:
                    results.append(res)

            return results
        except Exception as e:
            print(f"Error in checkout_all_active: {e}")
            return []
    
    def clear_all_history(self):
        """Xóa toàn bộ lịch sử attendance (DB và bộ nhớ)."""
        deleted = 0
        try:
            app_ctx = getattr(self, 'app', None)
            ctx = None
            if app_ctx:
                ctx = app_ctx.app_context()
            else:
                try:
                    from flask import current_app
                    ctx = current_app.app_context()
                except RuntimeError:
                    ctx = None

            if ctx:
                with ctx:
                    try:
                        deleted = Attendance.query.delete()
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        print(f"Error clearing attendance table: {e}")
                        deleted = 0

            self.active_attendances.clear()
            return deleted
        except Exception as e:
            print(f"Error in clear_all_history: {e}")
            return deleted
    
    def check_timeout_attendances(self, active_track_ids):
        """Kiểm tra và đóng các attendance đã timeout"""
        current_time = datetime.now()
        timeout_tracks = []
        
        for track_id in list(self.active_attendances.keys()):
            if track_id not in active_track_ids:
                # Track không còn active, kiểm tra timeout
                attendance = self.active_attendances[track_id]
                
                # Lấy time_in từ attendance object hoặc dict
                if hasattr(attendance, 'time_in'):
                    time_in = attendance.time_in
                else:
                    time_in = attendance.get('time_in', current_time)
                
                time_since_last_seen = (current_time - time_in).total_seconds()
                
                if time_since_last_seen > Config.CHECKOUT_TIMEOUT:
                    timeout_tracks.append(track_id)
        
        # Đóng các attendance timeout
        for track_id in timeout_tracks:
            self.log_time_out(track_id)
    
    def get_active_attendances(self):
        """Lấy danh sách attendance đang active"""
        return self.active_attendances.copy()
    
    def get_attendance_stats(self, date=None):
        """Lấy thống kê attendance"""
        if date is None:
            date = datetime.now().date()
        
        try:
            app_ctx = getattr(self, 'app', None)
            if app_ctx:
                with app_ctx.app_context():
                    start_date = datetime.combine(date, datetime.min.time())
                    end_date = start_date + timedelta(days=1)

                    # Attendance trong ngày
                    daily_attendances = Attendance.query.filter(
                        Attendance.time_in >= start_date,
                        Attendance.time_in < end_date
                    ).all()

                    # Thống kê
                    stats = {
                        'date': date.isoformat(),
                        'total_checkins': len(daily_attendances),
                        'active_now': len(self.active_attendances),
                        'completed_sessions': len([a for a in daily_attendances if a.time_out is not None]),
                        'ongoing_sessions': len([a for a in daily_attendances if a.time_out is None]),
                        'unique_people': len(set([a.person_id for a in daily_attendances if a.person_id is not None])),
                        'unknown_people': len([a for a in daily_attendances if a.person_id is None])
                    }

                    return stats
        except RuntimeError:
            # Không có application context, trả về thống kê cơ bản
            return {
                'date': date.isoformat(),
                'total_checkins': 0,
                'active_now': len(self.active_attendances),
                'completed_sessions': 0,
                'ongoing_sessions': len(self.active_attendances),
                'unique_people': 0,
                'unknown_people': 0
            }
    
    def get_attendance_history(self, person_id=None, date_from=None, date_to=None, limit=100):
        """Lấy lịch sử attendance"""
        try:
            app_ctx = getattr(self, 'app', None)
            if app_ctx:
                with app_ctx.app_context():
                    from app.models.database import Person

                    # Use join to avoid lazy loading issues
                    query = db.session.query(Attendance, Person).outerjoin(Person, Attendance.person_id == Person.person_id)

                    if person_id:
                        query = query.filter(Attendance.person_id == person_id)

                    if date_from:
                        query = query.filter(Attendance.time_in >= date_from)

                    if date_to:
                        query = query.filter(Attendance.time_in <= date_to)

                    query = query.order_by(Attendance.time_in.desc()).limit(limit)

                    # Return attendance objects with person data preloaded
                    results = []
                    for attendance, person in query.all():
                        # Manually set person name to avoid lazy loading
                        if person:
                            attendance._person_name = person.name
                        else:
                            attendance._person_name = 'Unknown'
                        results.append(attendance)

                    # Commit session to ensure data is available
                    db.session.commit()
                    return results
        except RuntimeError:
            # Không có application context, trả về danh sách rỗng
            return []
    
    def get_person_attendance_summary(self, person_id, days=30):
        """Lấy tổng kết attendance của một người"""
        try:
            from flask import current_app
            with current_app.app_context():
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                attendances = Attendance.query.filter(
                    Attendance.person_id == person_id,
                    Attendance.time_in >= start_date,
                    Attendance.time_in <= end_date
                ).all()
                
                total_hours = 0
                total_days = 0
                avg_session_hours = 0
                
                for attendance in attendances:
                    if attendance.time_out:
                        duration_hours = attendance.get_duration_minutes() / 60
                        total_hours += duration_hours
                        total_days += 1
                
                if total_days > 0:
                    avg_session_hours = total_hours / total_days
                
                return {
                    'person_id': person_id,
                    'period_days': days,
                    'total_hours': round(total_hours, 2),
                    'total_sessions': total_days,
                    'avg_session_hours': round(avg_session_hours, 2),
                    'attendance_rate': round((total_days / days) * 100, 2) if days > 0 else 0
                }
        except RuntimeError:
            # Không có application context, trả về thống kê cơ bản
            return {
                'person_id': person_id,
                'period_days': days,
                'total_hours': 0,
                'total_sessions': 0,
                'avg_session_hours': 0,
                'attendance_rate': 0
            }
    
    def export_attendance_data(self, date_from=None, date_to=None, format='json'):
        """Xuất dữ liệu attendance"""
        try:
            app_ctx = getattr(self, 'app', None)
            if app_ctx:
                with app_ctx.app_context():
                    query = Attendance.query

                    if date_from:
                        query = query.filter(Attendance.time_in >= date_from)

                    if date_to:
                        query = query.filter(Attendance.time_in <= date_to)

                    attendances = query.order_by(Attendance.time_in.desc()).all()

                    if format == 'json':
                        return [attendance.to_dict() for attendance in attendances]
                    elif format == 'csv':
                        # Implement CSV export
                        pass

                    return attendances
        except RuntimeError:
            # Không có application context, trả về danh sách rỗng
            return []
    
    def log_attendance_event(self, event_type, details):
        """Ghi log sự kiện attendance"""
        try:
            app_ctx = getattr(self, 'app', None)
            if app_ctx:
                with app_ctx.app_context():
                    device = Device.query.first()
                    log = Log(
                        device_id=device.device_id if device else None,
                        event_type=f'attendance_{event_type}',
                        details=json.dumps(details) if isinstance(details, dict) else str(details)
                    )
                    db.session.add(log)
                    db.session.commit()
            else:
                from flask import current_app
                with current_app.app_context():
                    device = Device.query.first()
                    log = Log(
                        device_id=device.device_id if device else None,
                        event_type=f'attendance_{event_type}',
                        details=json.dumps(details) if isinstance(details, dict) else str(details)
                    )
                    db.session.add(log)
                    db.session.commit()
        except RuntimeError:
            # Không có application context, bỏ qua logging
            pass
        except Exception as e:
            print(f"Error logging attendance event: {e}")
    
    def cleanup_old_logs(self, days=30):
        """Dọn dẹp logs cũ"""
        try:
            from flask import current_app
            with current_app.app_context():
                cutoff_date = datetime.now() - timedelta(days=days)
                old_logs = Log.query.filter(Log.timestamp < cutoff_date).all()
                
                for log in old_logs:
                    db.session.delete(log)
                
                db.session.commit()
                print(f"Cleaned up {len(old_logs)} old logs")
        except RuntimeError:
            # Không có application context, bỏ qua cleanup
            pass
        except Exception as e:
            print(f"Error cleaning up logs: {e}")
    
    def get_realtime_stats(self):
        """Lấy thống kê realtime"""
        return {
            'active_people': len(self.active_attendances),
            'active_tracks': list(self.active_attendances.keys()),
            'timestamp': datetime.now().isoformat()
        }

    def update_active_attendance(self, track_id, person_id=None, person_name=None):
        """Update an existing active attendance when a later recognition provides identity.

        - Updates the in-memory active_attendances entry.
        - If the attendance was persisted (attendance_id present), updates the DB record's person_id.
        - Logs an event 'identity_updated'.
        """
        try:
            if track_id not in self.active_attendances:
                return None

            attendance = self.active_attendances[track_id]

            updated = False

            # Update in-memory
            if person_id is not None and attendance.get('person_id') != person_id:
                attendance['person_id'] = person_id
                updated = True

            if person_name and attendance.get('person_name') != person_name:
                attendance['person_name'] = person_name
                updated = True

            # Update DB record if present
            if updated and attendance.get('attendance_id'):
                try:
                    app_ctx = getattr(self, 'app', None)
                    if app_ctx:
                        with app_ctx.app_context():
                            db_att = Attendance.query.get(attendance.get('attendance_id'))
                            if db_att:
                                db_att.person_id = person_id
                                db.session.commit()
                    else:
                        from flask import current_app
                        with current_app.app_context():
                            db_att = Attendance.query.get(attendance.get('attendance_id'))
                            if db_att:
                                db_att.person_id = person_id
                                db.session.commit()
                except Exception as e:
                    try:
                        db.session.rollback()
                    except:
                        pass
                    print(f"Error updating attendance DB record for track {track_id}: {e}")

            if updated:
                # Log identity update event
                self.log_attendance_event('identity_updated', {
                    'track_id': track_id,
                    'person_id': person_id,
                    'person_name': person_name,
                    'attendance_id': attendance.get('attendance_id')
                })

            return attendance
        except Exception as e:
            print(f"Error in update_active_attendance: {e}")
            return None
