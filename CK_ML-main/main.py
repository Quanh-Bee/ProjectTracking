import cv2
import numpy as np
import threading
import time
from datetime import datetime
import os
import sys

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from app.models.database import db, init_db, Person
from app.services.face_recognition import FaceRecognitionService
from app.services.tracking import TrackingService
from app.services.attendance import AttendanceService
from app.api.routes import create_app

class FaceTrackingSystem:
    """Hệ thống nhận diện và tracking người chính"""
    
    def __init__(self, face_service=None, tracking_service=None, attendance_service=None):
        # Allow injecting services (useful when running API + camera in same process)
        self.face_service = face_service or FaceRecognitionService()
        self.tracking_service = tracking_service or TrackingService()
        self.attendance_service = attendance_service or AttendanceService()
        self.checkbox_states = {
            'check_in': False,
            'check_out': False
        }
        self.last_capture_time = None
        self.window_name = 'Face Tracking System'
        self.ui_regions = []
        self.last_display_frame = None
        self.last_tracking_results = []
        self.camera = None
        self.running = False
        self.frame_count = 0
        
    def initialize_camera(self):
        """Khởi tạo camera"""
        try:
            self.camera = cv2.VideoCapture(Config.CAMERA_INDEX)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, Config.CAMERA_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, Config.CAMERA_HEIGHT)
            self.camera.set(cv2.CAP_PROP_FPS, Config.CAMERA_FPS)
            cv2.namedWindow(self.window_name)
            cv2.setMouseCallback(self.window_name, self.handle_mouse_event)
            
            if not self.camera.isOpened():
                raise Exception("Cannot open camera")
            
            print(f"Camera initialized: {Config.CAMERA_WIDTH}x{Config.CAMERA_HEIGHT} @ {Config.CAMERA_FPS}fps")
            return True
            
        except Exception as e:
            print(f"Error initializing camera: {e}")
            return False
    
    def process_frame(self, frame):
        """Xử lý một frame"""
        self.frame_count += 1
        
        # Nhận diện khuôn mặt
        face_results = self.face_service.recognize_faces_in_frame(frame)
        
        # Tracking người
        tracking_results = self.tracking_service.process_frame(frame, self.face_service)
        
        # Xử lý attendance
        active_track_ids = [result['track_id'] for result in tracking_results]
        self.attendance_service.check_timeout_attendances(active_track_ids)
        
        # Log time_in cho các track mới
        for result in tracking_results:
            track_id = result['track_id']
            person_id = result['person_id']
            name = result['name']
            
            if track_id in self.attendance_service.active_attendances:
                # If an active attendance exists but person info was previously unknown
                # and now we've recognized the person, update the active attendance
                try:
                    if person_id is not None and person_id != self.attendance_service.active_attendances[track_id].get('person_id'):
                        self.attendance_service.update_active_attendance(track_id, person_id=person_id, person_name=name)
                    elif name and name != self.attendance_service.active_attendances[track_id].get('person_name'):
                        self.attendance_service.update_active_attendance(track_id, person_id=person_id, person_name=name)
                except Exception:
                    pass
        
        # Vẽ kết quả lên frame
        frame = self.face_service.draw_face_boxes(frame, face_results)
        frame = self.tracking_service.draw_tracking_boxes(frame, tracking_results)
        
        # Thêm thông tin hệ thống
        self.draw_system_info(frame, tracking_results)
        self.draw_ui_controls(frame)
        self.last_tracking_results = tracking_results
        try:
            self.last_display_frame = frame.copy()
        except Exception:
            self.last_display_frame = frame
        
        return frame, tracking_results
    
    def draw_system_info(self, frame, tracking_results):
        """Vẽ thông tin hệ thống lên frame"""
        # Thông tin cơ bản
        info_text = [
            f"Frame: {self.frame_count}",
            f"Active Tracks: {len(tracking_results)}",
            f"Active Attendances: {len(self.attendance_service.active_attendances)}",
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(frame, text, (10, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            y_offset += 25
    
    def draw_ui_controls(self, frame):
        """Vẽ checkbox và nút chức năng giả lập lên frame"""
        checkbox_positions = {
            'check_in': (10, 150),
            'check_out': (10, 190)
        }
        regions = []
        
        for key, (x, y) in checkbox_positions.items():
            checked = self.checkbox_states.get(key, False)
            color = (0, 255, 0) if checked else (180, 180, 180)
            cv2.rectangle(frame, (x, y), (x + 20, y + 20), color, 2)
            regions.append({
                'type': 'checkbox',
                'key': key,
                'rect': (x, y, x + 20, y + 20)
            })
            
            if checked:
                cv2.line(frame, (x + 4, y + 10), (x + 10, y + 16), color, 2)
                cv2.line(frame, (x + 10, y + 16), (x + 18, y + 4), color, 2)
            
            label = "Check-in" if key == 'check_in' else "Check-out"
            cv2.putText(frame, label, (x + 30, y + 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        button_top_left = (10, 230)
        button_bottom_right = (170, 270)
        cv2.rectangle(frame, button_top_left, button_bottom_right, (50, 150, 255), 2)
        cv2.putText(frame, "Xac nhan (C)", (button_top_left[0] + 10, button_top_left[1] + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        regions.append({
            'type': 'button',
            'key': 'capture',
            'rect': (button_top_left[0], button_top_left[1], button_bottom_right[0], button_bottom_right[1])
        })
        
        if self.last_capture_time:
            cv2.putText(frame, f"Last confirm: {self.last_capture_time}",
                       (10, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                       (200, 200, 200), 1)
        
        self.ui_regions = regions
    
    def handle_mouse_event(self, event, x, y, flags, param):
        """Xử lý click chuột trên cửa sổ video"""
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        for region in self.ui_regions:
            x1, y1, x2, y2 = region['rect']
            if x1 <= x <= x2 and y1 <= y <= y2:
                if region['type'] == 'checkbox':
                    key = region['key']
                    new_state = not self.checkbox_states[key]
                    self.set_checkbox_state(key, new_state)
                elif region['type'] == 'button' and region['key'] == 'capture':
                    self.capture_frame()
                break
    
    def set_checkbox_state(self, key, value):
        """Thiết lập trạng thái checkbox và đảm bảo loại trừ lẫn nhau"""
        if key not in self.checkbox_states:
            return
        if value:
            for other in self.checkbox_states:
                self.checkbox_states[other] = (other == key)
        else:
            self.checkbox_states[key] = False
        print(f"{key.replace('_', ' ').title()}: {self.checkbox_states[key]}")
    
    def capture_frame(self):
        """Xác nhận hành động hiện tại"""
        if self.last_display_frame is None:
            print("No frame available to confirm")
            return
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.last_capture_time = timestamp
            self.perform_attendance_action()
        except Exception as e:
            print(f"Confirmation failed: {e}")
    
    def get_primary_subject(self):
        """Lấy người đang xuất hiện nổi bật nhất trong frame (đầu tiên có nhận diện)"""
        if not self.last_tracking_results:
            return None
        
        for result in self.last_tracking_results:
            name = result.get('name')
            if not name or name == Config.UNKNOWN_PERSON_LABEL:
                continue
            person_id = result.get('person_id')
            if person_id is None and name:
                person_id = self.lookup_person_id_by_name(name)
                if person_id:
                    result['person_id'] = person_id
            return result
        return None
    
    def get_all_recognized_subjects(self):
        """Lấy TẤT CẢ người đang được nhận diện trong frame"""
        if not self.last_tracking_results:
            return []
        
        subjects = []
        for result in self.last_tracking_results:
            name = result.get('name')
            if not name or name == Config.UNKNOWN_PERSON_LABEL:
                continue
            person_id = result.get('person_id')
            if person_id is None and name:
                person_id = self.lookup_person_id_by_name(name)
                if person_id:
                    result['person_id'] = person_id
            subjects.append(result)
        return subjects
    
    def lookup_person_id_by_name(self, name):
        """Tra cứu person_id theo tên nếu có"""
        if not name or name == Config.UNKNOWN_PERSON_LABEL:
            return None
        try:
            app_ctx = getattr(self.attendance_service, 'app', None)
            if app_ctx:
                with app_ctx.app_context():
                    person = Person.query.filter_by(name=name).first()
                    return person.person_id if person else None
            from flask import current_app
            with current_app.app_context():
                person = Person.query.filter_by(name=name).first()
                return person.person_id if person else None
        except Exception:
            return None
    
    def perform_attendance_action(self):
        """Thực hiện hành động check-in/check-out dựa trên trạng thái checkbox"""
        action = None
        if self.checkbox_states.get('check_in'):
            action = 'check_in'
        elif self.checkbox_states.get('check_out'):
            action = 'check_out'
        
        if not action:
            print("No action selected (check-in/check-out)")
            return
        
        try:
            if action == 'check_in':
                # Lấy TẤT CẢ users đang được nhận diện
                subjects = self.get_all_recognized_subjects()
                if not subjects:
                    print("No recognized person available for check-in")
                    return
                
                # Tạo attendance mới cho TẤT CẢ users
                for subject in subjects:
                    track_id = subject.get('track_id')
                    person_id = subject.get('person_id')
                    name = subject.get('name')
                    # Tạo attendance mới với force_new=True để không check active_attendances
                    attendance = self.attendance_service.log_time_in_manual(track_id, person_id, name)
                    if attendance:
                        print(f"Manual check-in recorded for {name or person_id or track_id}")
            elif action == 'check_out':
                # Check-out user đang được nhận diện trong frame (hoặc có thể checkout user khác)
                subject = self.get_primary_subject()
                if not subject:
                    print("No recognized person available for check-out")
                    return
                
                person_id = subject.get('person_id')
                name = subject.get('name')
                # Dùng log_time_out_manual để checkout dựa vào person_id hoặc name
                attendance = self.attendance_service.log_time_out_manual(person_id=person_id, person_name=name)
                if attendance:
                    print(f"Manual check-out recorded for {name or person_id}")
                else:
                    print(f"Failed to check-out: No open attendance found for {name or person_id}")
        except Exception as e:
            print(f"Attendance action failed: {e}")
    
    def run_camera_loop(self):
        """Vòng lặp chính của camera"""
        print("Starting camera loop...")
        
        while self.running:
            ret, frame = self.camera.read()
            if not ret:
                print("Failed to read frame from camera")
                break
            
            try:
                # Xử lý frame
                processed_frame, tracking_results = self.process_frame(frame)
                
                # Hiển thị frame
                cv2.imshow(self.window_name, processed_frame)
                
                # Kiểm tra phím thoát
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("Quit key pressed")
                    break
                elif key == ord('r'):
                    print("Reset tracking")
                    self.tracking_service.reset_tracking()
                    self.attendance_service.active_attendances.clear()
                elif key == ord('i'):
                    new_state = not self.checkbox_states['check_in']
                    self.set_checkbox_state('check_in', new_state)
                elif key == ord('o'):
                    new_state = not self.checkbox_states['check_out']
                    self.set_checkbox_state('check_out', new_state)
                elif key == ord('c'):
                    self.capture_frame()
                
            except Exception as e:
                print(f"Error processing frame: {e}")
                continue
        
        print("Camera loop ended")
    
    def start(self):
        """Khởi động hệ thống"""
        print("Starting Face Tracking System...")
        
        # Khởi tạo camera
        if not self.initialize_camera():
            print("Failed to initialize camera. Exiting...")
            return False
        
        self.running = True
        
        try:
            # Chạy camera loop
            self.run_camera_loop()
        except KeyboardInterrupt:
            print("System interrupted by user")
        except Exception as e:
            print(f"System error: {e}")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """Dừng hệ thống"""
        print("Stopping Face Tracking System...")
        self.running = False
        
        if self.camera:
            self.camera.release()
        
        cv2.destroyAllWindows()
        print("System stopped")

def run_api_server(app=None):
    """Chạy API server; nếu truyền sẵn app thì chạy app đó (useful for sharing services)
    Nếu không truyền, tự tạo app mới (backward compatible)."""
    print("Starting API server...")
    if app is None:
        app = create_app()
    try:
        app.run(host=Config.API_HOST, port=Config.API_PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("API server stopped by user")
    except Exception as e:
        print(f"API server error: {e}")

def main():
    """Hàm main"""
    print("=" * 50)
    print("Face Recognition & People Tracking System")
    print("=" * 50)
    
    # Tạo thư mục cần thiết
    os.makedirs('database', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('known_faces', exist_ok=True)
    
    # Khởi tạo Flask app và database
    app = create_app()
    with app.app_context():
        init_db(app)
    
    # Chạy API server trong thread riêng
    api_thread = threading.Thread(target=run_api_server, args=(app,), daemon=True)
    api_thread.start()
    
    # Đợi API server khởi động
    time.sleep(2)
    print(f"API server started at http://{Config.API_HOST}:{Config.API_PORT}")
    
    # Khởi tạo hệ thống camera, dùng các service từ app nếu có
    try:
        face_service = getattr(app, 'face_service', None)
        tracking_service = getattr(app, 'tracking_service', None)
        attendance_service = getattr(app, 'attendance_service', None)

        system = FaceTrackingSystem(
            face_service=face_service,
            tracking_service=tracking_service,
            attendance_service=attendance_service
        )

        try:
            if system.tracking_service:
                system.tracking_service.reset_tracking()
        except Exception:
            pass

        try:
            if system.attendance_service:
                system.attendance_service.active_attendances.clear()
        except Exception:
            pass
        
        system.start()
        
    except KeyboardInterrupt:
        print("\nHệ thống được dừng bởi người dùng")
    except Exception as e:
        print(f"Lỗi khi chạy hệ thống camera: {e}")
    finally:
        # Dừng hệ thống camera
        if 'system' in locals():
            system.stop()
        
        # Dừng API server nếu có endpoint shutdown
        try:
            import requests
            requests.get(f'http://{Config.API_HOST}:{Config.API_PORT}/shutdown', timeout=1)
        except Exception:
            pass
        
        print("Tất cả processes đã được dừng!")

if __name__ == '__main__':
    main()
