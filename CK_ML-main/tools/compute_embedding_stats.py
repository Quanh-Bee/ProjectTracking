
import sys, os
import numpy as np

# Ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import Config
from app.services.face_recognition import FaceRecognitionService


def pairwise_distances(X):
    # X is (n, d)
    if X.size == 0:
        return np.array([[]])
    d2 = np.sum((X[:, None, :] - X[None, :, :])**2, axis=-1)
    return np.sqrt(d2)


def main():
    fr = FaceRecognitionService()

    encs = np.array(fr.known_face_encodings)
    names = list(fr.known_face_names)
    ids = list(fr.known_face_ids)

    if encs.size == 0:
        print('No known face encodings found. Ensure known_faces/ has images and they were loaded.')
        return

    D = pairwise_distances(encs)
    n = len(encs)

    intra_dists = []
    inter_dists = []

    for i in range(n):
        for j in range(i+1, n):
            if ids[i] == ids[j] and ids[i] is not None:
                intra_dists.append(D[i, j])
            else:
                inter_dists.append(D[i, j])

    max_intra = float(max(intra_dists)) if intra_dists else 0.0
    min_inter = float(min(inter_dists)) if inter_dists else float('inf')
    suggested = (max_intra + min_inter) / 2.0 if inter_dists and intra_dists else None

    print('\n=== Embedding distance summary ===')
    print(f'Known encodings: {n}')
    print(f'Max intra-person distance: {max_intra:.6f}')
    print(f'Min inter-person distance: {min_inter:.6f}')
    if suggested is not None:
        print(f'Recommended threshold (midpoint): {suggested:.6f}')
    else:
        print('Not enough data to suggest a threshold')

    # Per-person intra stats
    from collections import defaultdict
    per_person = defaultdict(list)
    for i in range(n):
        per_person[ids[i]].append(i)

    print('\nPer-person intra distances:')
    for pid, idxs in per_person.items():
        if pid is None:
            label = 'None'
        else:
            label = str(pid)
        if len(idxs) < 2:
            print(f'  person_id={label}: only {len(idxs)} sample(s)')
            continue
        vals = []
        for a in range(len(idxs)):
            for b in range(a+1, len(idxs)):
                vals.append(D[idxs[a], idxs[b]])
        print(f'  person_id={label}: max intra = {np.max(vals):.6f} over {len(vals)} pairs')

    # If sample images provided, evaluate them
    samples = sys.argv[1:]
    if samples:
        print('\nSample image evaluations:')
        for s in samples:
            if not os.path.exists(s):
                print(f'  {s}: file not found')
                continue
            enc = fr.get_face_encoding_from_image(s)
            if enc is None:
                print(f'  {s}: no face found')
                continue
            dists = np.linalg.norm(enc - encs, axis=1)
            order = np.argsort(dists)
            best = order[0]
            print(f"  {s}: best match -> {names[best]} (person_id={ids[best]}) dist={dists[best]:.6f}")
            print('    Top 5:')
            for k in order[:5]:
                print(f"      {names[k]} (id={ids[k]}) dist={dists[k]:.6f}")

if __name__ == '__main__':
    main()
