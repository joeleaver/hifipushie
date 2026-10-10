"""agesex.py <image>...: faces6 GATE reader (the coordinator: "Tess must read as a young woman"): a perceptual sex / age
read of a picture (photo or clay render) by InsightFace buffalo_l's genderage net (asset pack "faceage"; non-commercial
research licence: a measuring tool, never shipped), the face found by YuNet (pack "faceid"), cropped the way
InsightFace's Attribute model does (bbox centre, 1.5x the longer side, 96 px). Prints / returns per image
{"p_female", "age", "box"}; a clay render's absolute age is biased (no skin, no hair), so read it RELATIVE to the
accepted fit's clay through the same cameras, and the photo for calibration."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from hifipushie import assets, likeness

_SRC = r'''
import sys, json
import cv2, numpy as np
out, det_p, ga_p = sys.argv[1], sys.argv[2], sys.argv[3]
det = cv2.FaceDetectorYN.create(det_p, "", (320, 320), 0.3, 0.3, 5000)
ga = cv2.dnn.readNet(ga_p)
res = []
for p in sys.argv[4:]:
    im = cv2.imread(p)
    h, w = im.shape[:2]
    det.setInputSize((w, h))
    n, faces = det.detect(im)
    if faces is None or len(faces) == 0:
        res.append(None)
        continue
    f = max(faces, key=lambda r: r[2] * r[3])
    x, y, bw, bh = [float(v) for v in f[:4]]
    cx, cy = x + bw / 2, y + bh / 2
    s = 96.0 / (max(bw, bh) * 1.5)
    M = np.array([[s, 0, 48 - s * cx], [0, s, 48 - s * cy]], np.float32)
    crop = cv2.warpAffine(im, M, (96, 96), borderValue=0.0)
    ga.setInput(cv2.dnn.blobFromImage(crop, 1.0, (96, 96), (0.0, 0.0, 0.0), swapRB=True))
    o = ga.forward().ravel()
    e = np.exp(o[:2] - o[:2].max())
    res.append({"p_female": float(e[0] / e.sum()), "age": float(o[2] * 100), "box": [x, y, bw, bh], "raw": o.tolist()})
json.dump(res, open(out, "w"))
'''


def read(paths):
    fid = Path(assets.pack("faceid"))
    ga = Path(assets.pack("faceage")) / "genderage.onnx"
    with tempfile.TemporaryDirectory() as td:
        src, out = Path(td) / "ga.py", Path(td) / "out.json"
        src.write_text(_SRC)
        subprocess.run([str(Path(likeness.VENV) / "bin" / "python"), "-I", str(src), str(out), str(fid / "yunet.onnx"),
                        str(ga), *[str(p) for p in paths]], check=True, capture_output=True)
        return json.loads(out.read_text())


if __name__ == "__main__":
    for p, r in zip(sys.argv[1:], read(sys.argv[1:])):
        print(p, None if r is None else {"p_female": round(r["p_female"], 3), "age": round(r["age"], 1)})
