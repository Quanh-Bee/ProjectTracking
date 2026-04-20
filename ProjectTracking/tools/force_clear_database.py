#!/usr/bin/env python3
"""
Force clear the entire database - xóa tất cả dữ liệu trong database (không cần confirm)
"""
import os
import sys

# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.api.routes import create_app

def force_clear_database():
    """Xóa tất cả dữ liệu trong database"""
    print("=== Force Clearing Database ===")
    
    app = create_app()
    
    with app.app_context():
        from app.models.database import Person, Attendance, Log, Device, db
        
        print("Current database contents:")
        
        # Count records
        person_count = Person.query.count()
        attendance_count = Attendance.query.count()
        log_count = Log.query.count()
        device_count = Device.query.count()
        
        print(f"  Persons: {person_count}")
        print(f"  Attendances: {attendance_count}")
        print(f"  Logs: {log_count}")
        print(f"  Devices: {device_count}")
        
        if person_count == 0 and attendance_count == 0 and log_count == 0:
            print("Database is already empty!")
            return
        
        try:
            # Delete in correct order (respecting foreign keys)
            print("\nDeleting records...")
            
            # Delete attendances first (has foreign key to persons)
            deleted_attendances = db.session.query(Attendance).delete()
            print(f"  Deleted {deleted_attendances} attendances")
            
            # Delete logs
            deleted_logs = db.session.query(Log).delete()
            print(f"  Deleted {deleted_logs} logs")
            
            # Delete persons
            deleted_persons = db.session.query(Person).delete()
            print(f"  Deleted {deleted_persons} persons")
            
            # Keep devices (they don't have foreign key dependencies)
            print(f"  Kept {device_count} devices")
            
            # Commit changes
            db.session.commit()
            print("\n✅ Database cleared successfully!")
            
            # Verify
            print("\nVerification:")
            print(f"  Persons: {Person.query.count()}")
            print(f"  Attendances: {Attendance.query.count()}")
            print(f"  Logs: {Log.query.count()}")
            print(f"  Devices: {Device.query.count()}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error clearing database: {e}")
            return
    
    print("\n=== Database cleared ===")
    print("You can now:")
    print("1. Add images to known_faces/ and run reset_db_from_known_faces.py")
    print("2. Or register new people via web dashboard")

if __name__ == '__main__':
    force_clear_database()
