"""mpdet.py <out.npz> <dir> [<dir> ..]: MediaPipe Face Landmarker (478 points) on every picture of denselm sample
directories (RGBA 320 px, the background transparent: laid on mid grey, scaled x2.4 as likeness.detect_region does).
Runs in MediaPipe's own venv ($HIFIPUSHIE_MEDIAPIPE, default /mnt/data/hifipushie/facerefs_venv); nothing of the
package is imported. -> out.npz {P (n, 478, 2) px of the 320 px picture (nan = no face), dir (n,), idx (n,), M (n, 4, 4), bs (n, 52) blendshape scores, bs_names}."""
import sys
from pathlib import Path

import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision
from PIL import Image

VENV = Path(sys.executable).resolve().parents[1] if False else Path("/mnt/data/hifipushie/facerefs_venv")
PX = 768


def main():
    out, dirs = sys.argv[1], sys.argv[2:]
    opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=str(VENV / "face_landmarker.task")), num_faces=1,
                                        output_face_blendshapes=True, output_facial_transformation_matrixes=True)
    det = vision.FaceLandmarker.create_from_options(opts)
    P, D, I, M, B, bn = [], [], [], [], [], None
    for d in dirs:
        files = sorted(Path(d).glob("[0-9]*.png"))
        for f in files:
            im = Image.open(f).convert("RGBA")
            bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
            im = Image.alpha_composite(bg, im).convert("RGB")
            s = PX / max(im.size)
            big = im.resize((int(round(im.size[0] * s)), int(round(im.size[1] * s))), Image.LANCZOS)
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(np.asarray(big))))
            if res.face_landmarks:
                P.append([[q.x * im.size[0], q.y * im.size[1]] for q in res.face_landmarks[0]])
                M.append(np.asarray(res.facial_transformation_matrixes[0], float) if res.facial_transformation_matrixes else np.eye(4))
                bn = bn or [b.category_name for b in res.face_blendshapes[0]]
                B.append([float(b.score) for b in res.face_blendshapes[0]])
            else:
                P.append(np.full((478, 2), np.nan))
                M.append(np.full((4, 4), np.nan))
                B.append([np.nan] * 52)
            D.append(Path(d).name)
            I.append(int(f.stem))
        print(d, len(files), "found", int(np.isfinite(np.array(P[-len(files):])[:, 0, 0]).sum()), flush=True)
    np.savez_compressed(out, P=np.array(P, np.float32), dir=np.array(D), idx=np.array(I), M=np.array(M, np.float32),
                        bs=np.array(B, np.float32), bs_names=np.array(bn))


main()
