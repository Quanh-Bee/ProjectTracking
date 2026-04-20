import cv2
import numpy as np
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from datetime import datetime
from app.models.database import Log, Device, db
from config import Config
import json

class TrackingService:
    """Service xử lý tracking người với YOLOv8 + DeepSORT"""
    
    def __init__(self):
        self.yolo_model = None
        self.tracker = None
        self.tracked_objects = {}  # {track_id: {'name': str, 'last_seen': datetime, 'person_id': int}}
        self.load_models()
    
    def load_models(self):
        """Load YOLO model và DeepSORT tracker"""
        try:
            # Load YOLO model
            self.yolo_model = YOLO(Config.YOLO_MODEL_PATH)
            print(f"Loaded YOLO model: {Config.YOLO_MODEL_PATH}")
            
            # Load DeepSORT tracker
            self.tracker = DeepSort(max_age=Config.DEEPSORT_MAX_AGE)
            print("Loaded DeepSORT tracker")
            
        except Exception as e:
            print(f"Error loading tracking models: {e}")
            self.yolo_model = None
            self.tracker = None
    
    def detect_people(self, frame):
        """Phát hiện người trong frame bằng YOLO"""
        if self.yolo_model is None:
            return []
        
        try:
            results = self.yolo_model(frame, verbose=False)
            detections = []
            
            for r in results[0].boxes:
                cls = int(r.cls)
                conf = float(r.conf)
                
                # Class 0 = "person" trong COCO dataset
                if cls == 0 and conf >= Config.TRACKING_CONFIDENCE_THRESHOLD:
                    x1, y1, x2, y2 = map(int, r.xyxy[0])
                    width = x2 - x1
                    height = y2 - y1
                    
                    detections.append(([x1, y1, width, height], conf, "person"))
            
            return detections
            
        except Exception as e:
            print(f"Error in people detection: {e}")
            return []
    
    def update_tracking(self, frame, detections):
        """Cập nhật tracking với DeepSORT"""
        if self.tracker is None:
            return []
        
        try:
            tracks = self.tracker.update_tracks(detections, frame=frame)
            return tracks
        except Exception as e:
            print(f"Error in tracking update: {e}")
            return []
    
    def process_frame(self, frame, face_recognition_service=None):
        """Xử lý frame để detect và track người"""
        # Detect people
        detections = self.detect_people(frame)
        
        # Update tracking
        tracks = self.update_tracking(frame, detections)
        
        # Process tracking results
        current_track_ids = []
        frame_results = []
        # If face_recognition_service provided, detect faces once on the full frame
        face_results = []
        if face_recognition_service:
            try:
                face_results = face_recognition_service.recognize_faces_in_frame(frame)
            except Exception as e:
                print(f"Error running face recognition on frame: {e}")

        for track in tracks:
            if not track.is_confirmed():
                continue
            track_id = track.track_id
            # to_ltrb() returns left, top, right, bottom
            left, top, right, bottom = track.to_ltrb()

            # normalize to ints
            left_i, top_i, right_i, bottom_i = int(left), int(top), int(right), int(bottom)

            current_track_ids.append(track_id)

            # Ensure tracked_objects entry
            if track_id not in self.tracked_objects:
                self.tracked_objects[track_id] = {
                    'name': Config.UNKNOWN_PERSON_LABEL,
                    'last_seen': datetime.now(),
                    'person_id': None
                }

            self.tracked_objects[track_id]['last_seen'] = datetime.now()

            frame_results.append({
                'track_id': track_id,
                'bbox': (left_i, top_i, right_i, bottom_i),
                'name': self.tracked_objects[track_id]['name'],
                'person_id': self.tracked_objects[track_id]['person_id']
            })

        # Match detected faces to tracks by spatial containment (face center in track bbox)
        try:
            for fr in face_results:
                ftop, fright, fbottom, fleft = fr.get('location', (None, None, None, None))
                if None in (ftop, fright, fbottom, fleft):
                    continue
                # compute face center
                cx = (fleft + fright) / 2.0
                cy = (ftop + fbottom) / 2.0

                # find candidate tracks containing the center
                candidates = []
                for item in frame_results:
                    tid = item['track_id']
                    l, t, r, b = item['bbox']
                    if (cx >= l and cx <= r and cy >= t and cy <= b):
                        candidates.append((tid, l, t, r, b))

                if not candidates:
                    continue

                # if multiple, pick the one with smallest bbox-center distance
                best_tid = None
                best_dist = None
                for tid, l, t, r, b in candidates:
                    tx = (l + r) / 2.0
                    ty = (t + b) / 2.0
                    dist = ((tx - cx)**2 + (ty - cy)**2)**0.5
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_tid = tid

                # assign if we found a match and face result is known
                if best_tid is not None and fr.get('name') and fr.get('name') != Config.UNKNOWN_PERSON_LABEL:
                    if best_tid in self.tracked_objects:
                        self.tracked_objects[best_tid]['name'] = fr.get('name')
                        self.tracked_objects[best_tid]['person_id'] = fr.get('person_id')
        except Exception as e:
            print(f"Error matching faces to tracks: {e}")
        
        # Kiểm tra các track đã mất
        self.check_lost_tracks(current_track_ids)
        
        return frame_results
    
    def check_lost_tracks(self, current_track_ids):
        """Kiểm tra các track đã mất dấu"""
        current_time = datetime.now()
        lost_tracks = []
        
        for track_id, track_info in self.tracked_objects.items():
            if track_id not in current_track_ids:
                time_since_last_seen = (current_time - track_info['last_seen']).total_seconds()
                
                # Nếu mất dấu quá lâu, coi như đã rời khỏi phòng
                if time_since_last_seen > Config.CHECKOUT_TIMEOUT:
                    lost_tracks.append(track_id)
        
        # Xóa các track đã mất
        for track_id in lost_tracks:
            del self.tracked_objects[track_id]
            self.log_tracking_event('track_lost', {'track_id': track_id})
    
    def draw_tracking_boxes(self, frame, tracking_results):
        """Vẽ khung tracking lên frame"""
        for result in tracking_results:
            track_id = result['track_id']
            l, t, w, h = result['bbox']
            name = result['name']
            
            # Màu sắc khác nhau cho người đã biết và chưa biết
            color = (255, 0, 0) if name != Config.UNKNOWN_PERSON_LABEL else (0, 0, 255)
            
            # Vẽ khung
            cv2.rectangle(frame, (int(l), int(t)), (int(w), int(h)), color, 2)
            
            # Vẽ nhãn
            label = f"{name} (ID:{track_id})"
            cv2.putText(frame, label, (int(l), int(t) - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame
    
    def get_tracked_objects(self):
        """Lấy danh sách các object đang được track"""
        return self.tracked_objects.copy()
    
    def get_active_tracks(self):
        """Lấy danh sách các track đang hoạt động"""
        current_time = datetime.now()
        active_tracks = {}
        
        for track_id, track_info in self.tracked_objects.items():
            time_since_last_seen = (current_time - track_info['last_seen']).total_seconds()
            if time_since_last_seen <= Config.CHECKOUT_TIMEOUT:
                active_tracks[track_id] = track_info
        
        return active_tracks
    
    def assign_name_to_track(self, track_id, name, person_id=None):
        """Gán tên cho một track"""
        if track_id in self.tracked_objects:
            self.tracked_objects[track_id]['name'] = name
            self.tracked_objects[track_id]['person_id'] = person_id
            self.log_tracking_event('name_assigned', {
                'track_id': track_id,
                'name': name,
                'person_id': person_id
            })
    
    def log_tracking_event(self, event_type, details):
        """Ghi log sự kiện tracking"""
        try:
            from flask import current_app
            with current_app.app_context():
                device = Device.query.first()
                log = Log(
                    device_id=device.device_id if device else None,
                    event_type=f'tracking_{event_type}',
                    details=json.dumps(details) if isinstance(details, dict) else str(details)
                )
                db.session.add(log)
                db.session.commit()
        except RuntimeError:
            # Không có application context, bỏ qua logging
            pass
        except Exception as e:
            print(f"Error logging tracking event: {e}")
    
    def reset_tracking(self):
        """Reset tất cả tracking"""
        self.tracked_objects.clear()
        if self.tracker:
            self.tracker = DeepSort(max_age=Config.DEEPSORT_MAX_AGE)
        print("Tracking reset")
