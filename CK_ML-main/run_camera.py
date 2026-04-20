#!/usr/bin/env python3
"""
Script để chạy hệ thống camera tự động
"""
import cv2
import numpy as np
import os
import sys
import time
from datetime import datetime

# Add project root to path
ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import Config
from app.models.database import db, init_db
from app.services.face_recognition import FaceRecognitionService
from app.services.tracking import TrackingService
from app.services.attendance import AttendanceService
from app.api.routes import create_app

def run_camera_system():
    """Chạy hệ thống camera với nhận diện và tracking"""
    print("=" * 50)
    print("Face Recognition & People Tracking System")
    print("=" * 50)
    
    # Tạo thư mục cần thiết
    os.makedirs('database', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('known_faces', exist_ok=True)
    
    # Khởi tạo database
    app = create_app()
    with app.app_context():
        init_db(app)
    
    # Khởi tạo services
    face_service = app.face_service
    tracking_service = app.tracking_service
    attendance_service = app.attendance_service
    
    print(f"Loaded {len(face_service.known_face_encodings)} known faces")
    print(f"Encoding dimension: {face_service.encoding_dim}")
    print(f"Recognition threshold: {Config.FACE_RECOGNITION_TOLERANCE}")
    print("Press 'r' to reset tracking, 'l' to reload face encodings, 'q' to quit")
    
    # Khởi tạo camera
    camera = cv2.VideoCapture(Config.CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAMERA_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAMERA_HEIGHT)
    camera.set(cv2.CAP_PROP_FPS, Config.CAMERA_FPS)
    
    if not camera.isOpened():
        print("Cannot open camera!")
        return False
    
    print(f"Camera initialized: {Config.CAMERA_WIDTH}x{Config.CAMERA_HEIGHT} @ {Config.CAMERA_FPS}fps")
    
    frame_count = 0
    running = True
    
    try:
        while running:
            ret, frame = camera.read()
            if not ret:
                print("Failed to read frame from camera")
                break
            
            frame_count += 1
            
            # Nhận diện khuôn mặt
            face_results = face_service.recognize_faces_in_frame(frame)
            
            # Tracking người
            tracking_results = tracking_service.process_frame(frame, face_service)
            
            # Xử lý attendance
            active_track_ids = [result['track_id'] for result in tracking_results]
            attendance_service.check_timeout_attendances(active_track_ids)
            
            # Log time_in cho các track mới
            for result in tracking_results:
                track_id = result['track_id']
                person_id = result['person_id']
                name = result['name']
                
                if track_id not in attendance_service.active_attendances:
                    attendance_service.log_time_in(track_id, person_id, name)
                else:
                    # Update active attendance if person info was previously unknown
                    try:
                        if person_id is not None and person_id != attendance_service.active_attendances[track_id].get('person_id'):
                            attendance_service.update_active_attendance(track_id, person_id=person_id, person_name=name)
                        elif name and name != attendance_service.active_attendances[track_id].get('person_name'):
                            attendance_service.update_active_attendance(track_id, person_id=person_id, person_name=name)
                    except Exception:
                        pass
            
            # Vẽ kết quả lên frame
            frame = face_service.draw_face_boxes(frame, face_results)
            frame = tracking_service.draw_tracking_boxes(frame, tracking_results)
            
            # Thêm thông tin hệ thống
            info_text = [
                f"Frame: {frame_count}",
                f"Active Tracks: {len(tracking_results)}",
                f"Active Attendances: {len(attendance_service.active_attendances)}",
                f"Time: {datetime.now().strftime('%H:%M:%S')}",
                f"Threshold: {Config.FACE_RECOGNITION_TOLERANCE}"
            ]
            
            y_offset = 30
            for text in info_text:
                cv2.putText(frame, text, (10, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset += 25
            
            # Hiển thị frame
            cv2.imshow('Face Tracking System', frame)
            
            # Kiểm tra phím thoát
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("Quit key pressed")
                break
            elif key == ord('r'):
                print("Reset tracking")
                tracking_service.reset_tracking()
                attendance_service.active_attendances.clear()
            elif key == ord('l'):
                print("Reloading face encodings...")
                face_service.load_known_faces()
                print(f"Reloaded {len(face_service.known_face_encodings)} known faces")
            
            # Print results every 30 frames
            if frame_count % 30 == 0 and face_results:
                print(f"Frame {frame_count}: Found {len(face_results)} faces")
                for result in face_results:
                    print(f"  - {result['name']} (confidence: {result['confidence']:.3f})")
    
    except KeyboardInterrupt:
        print("System interrupted by user")
    except Exception as e:
        print(f"System error: {e}")
    finally:
        # Cleanup
        camera.release()
        cv2.destroyAllWindows()
        print("System stopped")
    
    return True

if __name__ == '__main__':
    run_camera_system()
