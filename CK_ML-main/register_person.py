#!/usr/bin/env python3
"""
Script để đăng ký người mới với ảnh từ known_faces
"""
import os
import sys
import json
import numpy as np

# Add project root to path
ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.api.routes import create_app
from app.models.database import Person, db

def register_person_from_folder():
    """Đăng ký người từ thư mục known_faces"""
    app = create_app()
    
    with app.app_context():
        from app.services.face_recognition import FaceRecognitionService
        face_service = app.face_service
        
        print("=== Person Registration ===")
        print(f"Current known faces: {len(face_service.known_face_encodings)}")
        
        # List available images
        known_faces_dir = 'known_faces'
        if not os.path.exists(known_faces_dir):
            print(f"Directory {known_faces_dir} not found!")
            return
        
        image_files = [f for f in os.listdir(known_faces_dir) 
                      if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        
        if not image_files:
            print(f"No images found in {known_faces_dir}")
            return
        
        print(f"Found {len(image_files)} images:")
        for i, f in enumerate(image_files):
            print(f"  {i+1}. {f}")
        
        # Group by person name
        person_groups = {}
        for filename in image_files:
            # Extract person name (remove _1, _2, etc.)
            base_name = os.path.splitext(filename)[0]
            if '_' in base_name and base_name.split('_')[-1].isdigit():
                person_name = '_'.join(base_name.split('_')[:-1])
            else:
                person_name = base_name
            
            if person_name not in person_groups:
                person_groups[person_name] = []
            person_groups[person_name].append(filename)
        
        print(f"\nGrouped into {len(person_groups)} persons:")
        for name, files in person_groups.items():
            print(f"  - {name}: {files}")
        
        # Process each person
        for person_name, files in person_groups.items():
            print(f"\n=== Processing {person_name} ===")
            
            # Check if person already exists
            existing_person = Person.query.filter_by(name=person_name).first()
            if existing_person:
                print(f"Person '{person_name}' already exists (ID: {existing_person.person_id})")
                continue
            
            # Process images
            encodings = []
            valid_files = []
            
            for filename in files:
                image_path = os.path.join(known_faces_dir, filename)
                print(f"  Processing {filename}...")
                
                try:
                    encoding = face_service.get_face_encoding_from_image(image_path)
                    if encoding is not None:
                        encodings.append(encoding)
                        valid_files.append(filename)
                        print(f"    ✓ Face found, encoding shape: {encoding.shape}")
                    else:
                        print(f"    ✗ No face detected")
                except Exception as e:
                    print(f"    ✗ Error: {e}")
            
            if not encodings:
                print(f"  No valid encodings found for {person_name}")
                continue
            
            # Create person record
            try:
                # Compute centroid encoding
                centroid = np.mean(encodings, axis=0)
                centroid = centroid / (np.linalg.norm(centroid) + 1e-7)
                
                person = Person(
                    name=person_name,
                    role='user',
                    face_encoding=json.dumps(centroid.tolist())
                )
                
                db.session.add(person)
                db.session.commit()
                
                print(f"  ✓ Created person '{person_name}' (ID: {person.person_id})")
                print(f"    Encoding shape: {centroid.shape}")
                print(f"    Valid images: {valid_files}")
                
                # Add to face service
                face_service.add_known_face(person_name, centroid, person.person_id)
                
            except Exception as e:
                db.session.rollback()
                print(f"  ✗ Error creating person: {e}")
        
        # Reload face service
        face_service.load_known_faces()
        print(f"\n=== Final Status ===")
        print(f"Total known faces: {len(face_service.known_face_encodings)}")
        for i, (name, person_id) in enumerate(zip(face_service.known_face_names, face_service.known_face_ids)):
            print(f"  {i+1}. {name} (ID: {person_id})")

if __name__ == '__main__':
    register_person_from_folder()
