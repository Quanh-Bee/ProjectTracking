from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

db = SQLAlchemy()

class Person(db.Model):
    """Bảng lưu thông tin người dùng"""
    __tablename__ = 'person'
    
    person_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    face_encoding = db.Column(db.Text)  # JSON string của face encoding
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationship
    attendances = db.relationship('Attendance', backref='person', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Person {self.name} ({self.role})>'
    
    def to_dict(self):
        return {
            'person_id': self.person_id,
            'name': self.name,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Attendance(db.Model):
    """Bảng ghi nhận vào/ra"""
    __tablename__ = 'attendance'
    
    attendance_id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('person.person_id'), nullable=True)
    track_id = db.Column(db.String(50), nullable=True)
    time_in = db.Column(db.DateTime, nullable=False)
    time_out = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='Present')
    
    def __repr__(self):
        return f'<Attendance {self.person_id} - {self.time_in}>'
    
    def to_dict(self):
        # Safe access to person name to avoid lazy loading issues
        person_name = 'Unknown'
        
        # First try to use preloaded person name
        if hasattr(self, '_person_name'):
            person_name = self._person_name
        else:
            try:
                if self.person:
                    person_name = self.person.name
            except:
                # If lazy loading fails, try to get name from database
                try:
                    from app.models.database import Person
                    person = Person.query.get(self.person_id)
                    if person:
                        person_name = person.name
                except:
                    person_name = f'Person {self.person_id}' if self.person_id else 'Unknown'
        
        return {
            'attendance_id': self.attendance_id,
            'person_id': self.person_id,
            'person_name': person_name,
            'track_id': self.track_id,
            'time_in': self.time_in.isoformat() if self.time_in else None,
            'time_out': self.time_out.isoformat() if self.time_out else None,
            'status': self.status,
            'duration_minutes': self.get_duration_minutes()
        }
    
    def get_duration_minutes(self):
        """Tính thời gian hiện diện (phút)"""
        if self.time_in and self.time_out:
            duration = self.time_out - self.time_in
            return int(duration.total_seconds() / 60)
        elif self.time_in:
            # Nếu chưa có time_out, tính từ time_in đến hiện tại
            duration = datetime.now() - self.time_in
            return int(duration.total_seconds() / 60)
        return 0

class Device(db.Model):
    """Bảng lưu thông tin thiết bị"""
    __tablename__ = 'device'
    
    device_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(50))
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Active')
    
    # Relationship
    logs = db.relationship('Log', backref='device', lazy=True)
    
    def __repr__(self):
        return f'<Device {self.name} ({self.location})>'
    
    def to_dict(self):
        return {
            'device_id': self.device_id,
            'name': self.name,
            'ip_address': self.ip_address,
            'location': self.location,
            'status': self.status
        }

class Log(db.Model):
    """Bảng ghi nhận log hệ thống"""
    __tablename__ = 'log'
    
    log_id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.device_id'), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    details = db.Column(db.Text)
    
    def __repr__(self):
        return f'<Log {self.event_type} - {self.timestamp}>'
    
    def to_dict(self):
        return {
            'log_id': self.log_id,
            'device_id': self.device_id,
            'device_name': self.device.name if self.device else 'Unknown',
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'details': self.details
        }

def init_db(app):
    """Khởi tạo database"""
    with app.app_context():
        # Tạo thư mục database nếu chưa có
        os.makedirs('database', exist_ok=True)
        
        # Tạo tất cả bảng
        db.create_all()
        
        # Tạo device mặc định nếu chưa có
        if not Device.query.first():
            default_device = Device(
                name='Main Camera',
                location='Room Entrance',
                status='Active'
            )
            db.session.add(default_device)
            db.session.commit()
        
        print("Database initialized successfully!")

def get_db_stats():
    """Lấy thống kê database"""
    stats = {
        'total_persons': Person.query.count(),
        'total_attendances': Attendance.query.count(),
        'active_attendances': Attendance.query.filter(Attendance.time_out.is_(None)).count(),
        'total_devices': Device.query.count(),
        'total_logs': Log.query.count()
    }
    return stats
