"""Re-encode person face embeddings in the database using the project's
FaceRecognitionService.

This script will:
 - create the Flask app and app context
 - for each Person in the DB, attempt to find an image in `known_faces/`
   that matches the person's name (simple filename heuristics)
 - compute a fresh encoding with FaceRecognitionService.get_face_encoding_from_image
 - update the Person.face_encoding field in the DB with the new encoding
 - reload known faces and rebuild centroids

Run from project root with the project's Python environment:
  python .\tools\reencode_db_faces.py
"""

import os
import sys
import json

# Ensure project root is on sys.path when running this script directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.api.routes import create_app


def find_image_for_person(name, known_dir):
    """Try to find an image file in known_dir that matches the person name.
    Matching heuristics: filename startswith name (spaces -> underscores),
    or contains name tokens. Case-insensitive.
    """
    if not os.path.isdir(known_dir):
        return None

    norm_name = name.lower().replace(' ', '_')
    candidates = []
    for fn in os.listdir(known_dir):
        if not fn.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        base = os.path.splitext(fn)[0].lower()
        if base.startswith(norm_name) or norm_name in base:
            candidates.append(os.path.join(known_dir, fn))

    # fallback: return first image with the same tokens
    if candidates:
        return candidates[0]
    return None


def main():
    app = create_app()
    known_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'known_faces'))

    with app.app_context():
        from app.models.database import Person, db
        face_service = app.face_service

        persons = Person.query.all()
        print(f"Found {len(persons)} person(s) in DB")

        updated = 0
        for p in persons:
            try:
                # skip if face_encoding matches expected dim and not empty
                if p.face_encoding:
                    try:
                        arr = json.loads(p.face_encoding)
                        if isinstance(arr, list) and face_service.encoding_dim is not None and len(arr) == face_service.encoding_dim:
                            # looks good
                            continue
                    except Exception:
                        pass

                # find image
                img = find_image_for_person(p.name, known_dir)
                if not img:
                    print(f"No image found for person '{p.name}', skipping")
                    continue

                enc = face_service.get_face_encoding_from_image(img)
                if enc is None:
                    print(f"Could not compute encoding for '{p.name}' from {img}")
                    continue

                # ensure numpy array -> list and json serializable
                try:
                    from numpy import array as _nparr
                    enc_list = _nparr(enc).tolist()
                except Exception:
                    enc_list = list(enc)

                p.face_encoding = json.dumps(enc_list)
                db.session.commit()
                updated += 1
                print(f"Updated encoding for '{p.name}' from {img}")
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"Error updating {p.name}: {e}")

        # reload known faces and rebuild centroids
        try:
            face_service.load_known_faces()
            face_service._rebuild_centroids()
        except Exception as e:
            print(f"Error reloading faces: {e}")

        print(f"Done. Updated {updated} encodings.")


if __name__ == '__main__':
    main()
