import cv2
import numpy as np
import os
import json
from datetime import datetime
from app.models.database import Person, Log, Device, db
from config import Config

class FaceRecognitionService:
    """Service xử lý nhận diện khuôn mặt sử dụng OpenCV"""
    
    def __init__(self):
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        # Centroid (mean) encoding per person name for more stable matching
        self.centroids = {}
        # Embedding model (facenet-pytorch) lazy-loaded
        self._embedding_model = None
        # choose device if torch available
        try:
            import torch
            self._embedding_device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except Exception:
            self._embedding_device = 'cpu'
        # optional MTCNN detector
        self._mtcnn = None
        # expected encoding dimension (set after model/hist chosen)
        self.encoding_dim = None
        self._embedding_enabled = False
        
        # Load OpenCV face cascade
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        self.load_known_faces()
    
    def load_known_faces(self):
        """Load các khuôn mặt đã biết từ database và thư mục known_faces"""
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        
        # Load từ database (chỉ khi có application context)
        try:
            from flask import current_app
            with current_app.app_context():
                persons = Person.query.filter(Person.face_encoding.isnot(None)).all()
                for person in persons:
                    try:
                        encoding = json.loads(person.face_encoding)
                        arr = np.array(encoding)
                        # normalize loaded encoding to unit length for consistent distance metrics
                        try:
                            arr = arr / (np.linalg.norm(arr) + 1e-7)
                        except Exception:
                            pass
                        # If we already determined encoding_dim, ensure shapes match
                        if self.encoding_dim is not None and arr.shape != (self.encoding_dim,):
                            print(f"Skipping DB encoding for {person.name}: dimension {arr.shape} != expected {self.encoding_dim}")
                            continue
                        self.known_face_encodings.append(arr)
                        self.known_face_names.append(person.name)
                        self.known_face_ids.append(person.person_id)
                    except (json.JSONDecodeError, ValueError) as e:
                        print(f"Error loading face encoding for {person.name}: {e}")
        except RuntimeError:
            # Không có application context, bỏ qua database
            print("No application context, skipping database load")
        
        # Load từ thư mục known_faces
        if os.path.exists(Config.KNOWN_FACES_DIR):
            for filename in os.listdir(Config.KNOWN_FACES_DIR):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_path = os.path.join(Config.KNOWN_FACES_DIR, filename)
                    try:
                        name = os.path.splitext(filename)[0]
                        # Skip if this name was already loaded from DB
                        if name in self.known_face_names:
                            continue

                        # Robust image load to support Unicode paths on Windows
                        image = None
                        try:
                            with open(image_path, 'rb') as f:
                                file_bytes = f.read()
                            import numpy as _np
                            nparr = _np.frombuffer(file_bytes, dtype=_np.uint8)
                            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        except Exception:
                            try:
                                image = cv2.imread(image_path)
                            except Exception:
                                image = None

                        if image is None:
                            continue

                        # Detect face and create encoding
                        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
                        if len(faces) == 0:
                            continue
                        x, y, w, h = faces[0]
                        face_roi = gray[y:y+h, x:x+w]
                        encoding = self._create_face_encoding(face_roi)
                        # normalize encoding
                        try:
                            encoding = np.array(encoding)
                            encoding = encoding / (np.linalg.norm(encoding) + 1e-7)
                        except Exception:
                            encoding = np.array(encoding)

                        # Set encoding_dim if not yet set
                        if self.encoding_dim is None:
                            try:
                                self.encoding_dim = int(np.array(encoding).shape[0])
                            except Exception:
                                pass

                        # Associate with DB person (create if missing)
                        person_id = None
                        try:
                            app_ctx = getattr(self, 'app', None)
                            if app_ctx:
                                with app_ctx.app_context():
                                    person = Person.query.filter_by(name=name).first()
                                    if person:
                                        person_id = person.person_id
                                    else:
                                        person = Person(name=name, role='user', face_encoding=json.dumps(encoding.tolist()))
                                        db.session.add(person)
                                        db.session.commit()
                                        person_id = person.person_id
                            else:
                                from flask import current_app
                                with current_app.app_context():
                                    person = Person.query.filter_by(name=name).first()
                                    if person:
                                        person_id = person.person_id
                                    else:
                                        person = Person(name=name, role='user', face_encoding=json.dumps(encoding.tolist()))
                                        db.session.add(person)
                                        db.session.commit()
                                        person_id = person.person_id
                        except RuntimeError:
                            person_id = None
                        except Exception as e:
                            print(f"Error associating known face '{name}' with DB: {e}")

                        # Ensure encoding shape matches expected dim (if set)
                        if self.encoding_dim is not None and np.array(encoding).shape[0] != self.encoding_dim:
                            print(f"Skipping file {filename}: encoding dim {np.array(encoding).shape} != expected {self.encoding_dim}")
                            continue
                        self.known_face_encodings.append(np.array(encoding))
                        self.known_face_names.append(name)
                        self.known_face_ids.append(person_id)
                    except Exception as e:
                        print(f"Error loading face from {filename}: {e}")
        
        # Rebuild centroids for stable matching now that we loaded faces
        try:
            self._rebuild_centroids()
        except Exception:
            pass

        print(f"Loaded {len(self.known_face_encodings)} known faces")
    
    def recognize_faces_in_frame(self, frame):
        """Nhận diện khuôn mặt trong frame sử dụng OpenCV"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
        
        results = []
        
        for (x, y, w, h) in faces:
            # Extract face ROI
            face_roi = gray[y:y+h, x:x+w]
            
            # Create face encoding
            face_encoding = self._create_face_encoding(face_roi)
            
            # Compare with centroids if available, otherwise fall back to known encodings
            name = Config.UNKNOWN_PERSON_LABEL
            person_id = None
            confidence = 0.0

            if len(self.centroids) > 0:
                # compute distances to centroids
                centroid_items = list(self.centroids.items())
                centroid_names = [c[0] for c in centroid_items]
                centroid_vecs = [c[1] for c in centroid_items]
                distances = []
                for v in centroid_vecs:
                    try:
                        a, b = self._align_vectors(face_encoding, v)
                        distances.append(np.linalg.norm(a - b))
                    except Exception as e:
                        print(f"Error computing distance to centroid: {e}")
                        distances.append(float('inf'))
                min_distance = min(distances)
                if min_distance < Config.FACE_RECOGNITION_TOLERANCE:
                    best_index = distances.index(min_distance)
                    name = centroid_names[best_index]
                    # Resolve person_id by finding first known_face_ids matching name
                    try:
                        pid_index = self.known_face_names.index(name)
                        person_id = self.known_face_ids[pid_index]
                    except ValueError:
                        person_id = None
                    confidence = 1 - (min_distance / Config.FACE_RECOGNITION_TOLERANCE)
            elif len(self.known_face_encodings) > 0:
                distances = []
                for k in self.known_face_encodings:
                    try:
                        a, b = self._align_vectors(face_encoding, k)
                        distances.append(np.linalg.norm(a - b))
                    except Exception as e:
                        print(f"Error computing distance to known encoding: {e}")
                        distances.append(float('inf'))
                min_distance = min(distances)
                if min_distance < Config.FACE_RECOGNITION_TOLERANCE:
                    best_match_index = distances.index(min_distance)
                    name = self.known_face_names[best_match_index]
                    person_id = self.known_face_ids[best_match_index]
                    confidence = 1 - (min_distance / Config.FACE_RECOGNITION_TOLERANCE)
            
            results.append({
                'location': (y, x+w, y+h, x),  # (top, right, bottom, left)
                'name': name,
                'person_id': person_id,
                'confidence': confidence,
                'face_encoding': face_encoding.tolist()
            })
        
        return results
    
    def add_known_face(self, name, face_encoding, person_id=None):
        """Thêm khuôn mặt mới vào danh sách đã biết"""
        # ensure encoding is normalized and numpy array
        try:
            enc = np.array(face_encoding)
            enc = enc / (np.linalg.norm(enc) + 1e-7)
        except Exception:
            enc = np.array(face_encoding)
        self.known_face_encodings.append(enc)
        self.known_face_names.append(name)
        self.known_face_ids.append(person_id)
        
        # Lưu vào database nếu có person_id
        if person_id:
            try:
                from flask import current_app
                with current_app.app_context():
                    person = Person.query.get(person_id)
                    if person:
                        person.face_encoding = json.dumps(face_encoding.tolist())
                        db.session.commit()
            except RuntimeError:
                # Không có application context, bỏ qua database update
                pass
            except Exception as e:
                print(f"Error updating person face encoding: {e}")
        # Rebuild centroid for stable matching
        try:
            self._rebuild_centroids()
        except Exception:
            pass
    
    def save_face_to_database(self, name, face_encoding, role='user'):
        """Lưu khuôn mặt mới vào database"""
        try:
            from flask import current_app
            with current_app.app_context():
                # If a person with the same name exists, update their encoding
                person = Person.query.filter_by(name=name).first()
                if person:
                    person.face_encoding = json.dumps(face_encoding.tolist())
                    db.session.commit()
                else:
                    person = Person(
                        name=name,
                        role=role,
                        face_encoding=json.dumps(face_encoding.tolist())
                    )
                    db.session.add(person)
                    db.session.commit()

                # Thêm vào danh sách hiện tại
                self.add_known_face(name, face_encoding, person.person_id)

                return person
        except RuntimeError:
            print("No application context, cannot save face to database.")
            return None
        except Exception as e:
            try:
                db.session.rollback()
            except:
                pass
            print(f"Error saving face to database: {e}")
            return None
    
    def log_recognition_event(self, event_type, details):
        """Ghi log sự kiện nhận diện"""
        try:
            from flask import current_app
            with current_app.app_context():
                device = Device.query.first()  # Sử dụng device đầu tiên
                log = Log(
                    device_id=device.device_id if device else None,
                    event_type=event_type,
                    details=json.dumps(details) if isinstance(details, dict) else str(details)
                )
                db.session.add(log)
                db.session.commit()
        except RuntimeError:
            # Không có application context, bỏ qua logging
            pass
        except Exception as e:
            print(f"Error logging recognition event: {e}")
    
    def _create_face_encoding(self, face_roi):
        """Tạo face encoding từ face ROI sử dụng histogram"""
        # Try to use facenet-pytorch embedding if available
        if not self._embedding_enabled:
            try:
                # Lazy import to avoid hard dependency
                from facenet_pytorch import InceptionResnetV1
                import torch
                model = InceptionResnetV1(pretrained='vggface2').eval()
                model.to(self._embedding_device)
                self._embedding_model = model
                self._embedding_enabled = True
            except Exception:
                self._embedding_model = None
                self._embedding_enabled = False

        if self._embedding_enabled and self._embedding_model is not None:
            try:
                # prefer MTCNN-based detection/alignment if available
                try:
                    from facenet_pytorch import MTCNN
                    if self._mtcnn is None:
                        # create single-face detector; keep_all=False
                        self._mtcnn = MTCNN(keep_all=False, device=self._embedding_device)
                except Exception:
                    self._mtcnn = None

                # face_roi may be grayscale; convert to RGB
                face_rgb = None
                try:
                    face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_GRAY2RGB)
                except Exception:
                    try:
                        face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_BGR2RGB)
                    except Exception:
                        # as a fallback, stack
                        face_rgb = cv2.cvtColor(face_roi, cv2.COLOR_GRAY2RGB)

                # If we have mtcnn, try to detect a tighter face box inside this ROI
                crop_img = None
                if self._mtcnn is not None:
                    try:
                        # mtcnn.detect accepts RGB numpy arrays
                        boxes, probs = self._mtcnn.detect(face_rgb)
                        if boxes is not None and len(boxes) > 0 and probs[0] is not None and probs[0] > 0.1:
                            x1, y1, x2, y2 = boxes[0]
                            # Ensure integer bounds and within image
                            h, w = face_rgb.shape[:2]
                            x1i = max(int(x1), 0)
                            y1i = max(int(y1), 0)
                            x2i = min(int(x2), w - 1)
                            y2i = min(int(y2), h - 1)
                            if x2i > x1i and y2i > y1i:
                                crop_img = face_rgb[y1i:y2i, x1i:x2i]
                    except Exception:
                        crop_img = None

                if crop_img is None:
                    # no mtcnn crop found; use original ROI
                    crop_img = face_rgb

                try:
                    crop_resized = cv2.resize(crop_img, (160, 160))
                except Exception:
                    crop_resized = cv2.resize(crop_img, (64, 64))

                import torch
                img = torch.tensor(crop_resized, dtype=torch.float32).permute(2, 0, 1).unsqueeze(0)
                img = (img - 127.5) / 128.0
                with torch.no_grad():
                    emb = self._embedding_model(img.to(self._embedding_device))
                emb = emb.squeeze(0).cpu().numpy()
                emb = emb / (np.linalg.norm(emb) + 1e-7)
                return emb
            except Exception as e:
                print(f"Embedding error, falling back to histogram: {e}")

        # Fallback: histogram-based encoding with CLAHE
        try:
            proc = cv2.resize(face_roi, (160, 160))
        except Exception:
            proc = cv2.resize(face_roi, (64, 64))

        try:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            face_proc = clahe.apply(proc)
        except Exception:
            face_proc = proc

        hist = cv2.calcHist([face_proc], [0], None, [128], [0, 256]).flatten()
        hist = hist / (np.linalg.norm(hist) + 1e-7)
        return hist

    def _rebuild_centroids(self):
        """Recompute mean encoding per person name (centroid)"""
        centroids = {}
        counts = {}
        for enc, name in zip(self.known_face_encodings, self.known_face_names):
            if name not in centroids:
                centroids[name] = np.array(enc, dtype=float)
                counts[name] = 1
            else:
                centroids[name] += np.array(enc, dtype=float)
                counts[name] += 1

        for name in centroids:
            centroids[name] = centroids[name] / counts[name]
            # normalize centroid
            centroids[name] = centroids[name] / (np.linalg.norm(centroids[name]) + 1e-7)

        self.centroids = centroids

    def _align_vectors(self, a, b):
        """Align two 1-D numpy vectors to same length by truncating or padding with zeros.

        This is a defensive measure: ideally all encodings share the same dim. If not,
        truncation/padding is used to allow distance computation rather than crashing.
        """
        a = np.array(a, dtype=float)
        b = np.array(b, dtype=float)
        la = a.shape[0]
        lb = b.shape[0]
        if la == lb:
            return a, b
        # If dimensions differ, raise so callers can treat this as non-match.
        # Silent padding/truncation can produce false positives.
        raise ValueError(f"Encoding dimension mismatch: {la} vs {lb}")
    
    def get_face_encoding_from_image(self, image_path):
        """Lấy face encoding từ file ảnh"""
        try:
            # Robust image load to support Unicode paths on Windows
            image = None
            try:
                with open(image_path, 'rb') as f:
                    file_bytes = f.read()
                import numpy as _np
                nparr = _np.frombuffer(file_bytes, dtype=_np.uint8)
                image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception:
                try:
                    image = cv2.imread(image_path)
                except Exception:
                    image = None

            if image is None:
                print(f"Failed to load image: {image_path}")
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Try multiple detection parameters for better face detection
            # First try: standard parameters
            faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
            
            # If no faces found, try more sensitive parameters
            if len(faces) == 0:
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(20, 20))
            
            # If still no faces, try even more sensitive parameters
            if len(faces) == 0:
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=2, minSize=(30, 30))
            
            # If still no faces, try with image enhancement (CLAHE)
            if len(faces) == 0:
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                enhanced_gray = clahe.apply(gray)
                faces = self.face_cascade.detectMultiScale(enhanced_gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                if len(faces) > 0:
                    gray = enhanced_gray
            
            # If still no faces, try resizing image (sometimes helps with detection)
            if len(faces) == 0:
                # Resize if image is too large or too small
                h, w = gray.shape
                if w > 2000 or h > 2000:
                    scale = min(2000.0 / w, 2000.0 / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    resized = cv2.resize(gray, (new_w, new_h))
                    faces = self.face_cascade.detectMultiScale(resized, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                    if len(faces) > 0:
                        gray = resized
                elif w < 200 or h < 200:
                    scale = max(200.0 / w, 200.0 / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    resized = cv2.resize(gray, (new_w, new_h))
                    faces = self.face_cascade.detectMultiScale(resized, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                    if len(faces) > 0:
                        gray = resized
            
            if len(faces) > 0:
                # Use the largest face if multiple faces detected
                if len(faces) > 1:
                    faces = sorted(faces, key=lambda x: x[2] * x[3], reverse=True)
                x, y, w, h = faces[0]
                face_roi = gray[y:y+h, x:x+w]
                print(f"Face detected in {image_path}: size {w}x{h}")
                return self._create_face_encoding(face_roi)
            else:
                print(f"No face detected in {image_path} after trying multiple methods")
                return None
        except Exception as e:
            print(f"Error getting face encoding from {image_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def draw_face_boxes(self, frame, face_results):
        """Vẽ khung khuôn mặt lên frame"""
        for result in face_results:
            top, right, bottom, left = result['location']
            name = result['name']
            confidence = result['confidence']
            
            # Màu sắc khác nhau cho người đã biết và chưa biết
            color = (0, 255, 0) if name != Config.UNKNOWN_PERSON_LABEL else (0, 0, 255)
            
            # Vẽ khung
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            
            # Vẽ nhãn
            label = f"{name} ({confidence:.2f})" if confidence > 0 else name
            cv2.putText(frame, label, (left, top - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return frame
