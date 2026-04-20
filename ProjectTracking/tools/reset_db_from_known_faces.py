"""Reset the database persons and related attendance/logs using images in known_faces/.

This script will:
 - create the Flask app and app context
 - delete Attendance and Log records and Person records (but keep Device table)
 - for each image in known_faces/, create a Person record and compute+store face_encoding
 - reload known faces in FaceRecognitionService and rebuild centroids

Run from project root in the project's environment:
  python .\tools\reset_db_from_known_faces.py
"""

import os
import sys
import re
import json
import numpy as np

# ensure project root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.api.routes import create_app


def name_from_filename(fn):
    base = os.path.splitext(fn)[0]
    # if filename ends with _1, _2 etc, strip the suffix
    m = re.match(r"^(.+)_\d+$", base)
    if m:
        base = m.group(1)
    # replace underscores with spaces, collapse multiple spaces
    name = re.sub(r"[_\s]+", ' ', base).strip()
    return name


def main():
    app = create_app()
    known_dir = os.path.join(ROOT, 'known_faces')

    if not os.path.isdir(known_dir):
        print(f"known_faces directory not found: {known_dir}")
        return

    files = [f for f in os.listdir(known_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    if not files:
        print("No images found in known_faces/; aborting.")
        return

    with app.app_context():
        from app.models.database import Person, Attendance, Log, db

        # Delete dependent records first
        try:
            num_att = db.session.query(Attendance).delete()
            num_logs = db.session.query(Log).delete()
            db.session.commit()
            print(f"Deleted {num_att} Attendance rows and {num_logs} Log rows")
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting Attendance/Log: {e}")

        # Delete persons
        try:
            num_p = db.session.query(Person).delete()
            db.session.commit()
            print(f"Deleted {num_p} Person rows")
        except Exception as e:
            db.session.rollback()
            print(f"Error deleting Person rows: {e}")

        face_service = app.face_service

        # Group files by base name (strip trailing _1/_2 etc)
        groups = {}
        for fn in sorted(files):
            base = name_from_filename(fn)
            groups.setdefault(base, []).append(fn)

        created = 0
        skipped = 0
        for name, fns in groups.items():
            encs = []
            for fn in fns:
                path = os.path.join(known_dir, fn)
                try:
                    enc = face_service.get_face_encoding_from_image(path)
                    if enc is None:
                        print(f"No face found in {fn}; skipping this file for person '{name}'")
                        continue
                    encs.append(np.array(enc))
                except Exception as e:
                    print(f"Error extracting encoding from {fn}: {e}")

            if not encs:
                print(f"No valid encodings found for group '{name}'; skipping person creation")
                skipped += len(fns)
                continue

            # compute centroid (mean) and normalize
            try:
                centroid = np.mean(np.stack(encs, axis=0), axis=0)
                centroid = centroid / (np.linalg.norm(centroid) + 1e-7)
                enc_list = centroid.tolist()

                person = Person(name=name, role='user', face_encoding=json.dumps(enc_list))
                db.session.add(person)
                db.session.commit()
                created += 1
                print(f"Created Person '{name}' from files {fns} (id={person.person_id})")
            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"Error creating person '{name}': {e}")

        # reload known faces and rebuild centroids
        try:
            face_service.load_known_faces()
            face_service._rebuild_centroids()
        except Exception as e:
            print(f"Error reloading known faces: {e}")

        print(f"Done. Created {created} persons, skipped {skipped} files.")


if __name__ == '__main__':
    main()
