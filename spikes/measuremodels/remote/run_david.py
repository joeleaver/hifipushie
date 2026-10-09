"""Microsoft DAViD (ONNX) on a folder: <out>/<id>.npz with depth (raw, relative), normal, mask (soft foreground).
argv: multi | single, src, out.  Models are fetched into ~/work/mm/david_models."""
import glob, os, sys, time, urllib.request
import cv2, numpy as np
sys.path.insert(0, os.path.expanduser("~/work/mm/DAViD/runtime"))
from multi_task_estimator import MultiTaskEstimator
from depth_estimator import RelativeDepthEstimator
from surface_normal_estimator import SurfaceNormalEstimator
kind, src, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
MD = os.path.expanduser("~/work/mm/david_models")
os.makedirs(MD, exist_ok=True)
URL = "https://facesyntheticspubwedata.z6.web.core.windows.net/iccv-2025/models/"
def get(n):
    p = os.path.join(MD, n)
    if not os.path.exists(p):
        urllib.request.urlretrieve(URL + n, p)
    return p
prov = ["CUDAExecutionProvider", "CPUExecutionProvider"]
t0 = time.time()
if kind == "multi":
    est = MultiTaskEstimator(get("multi-task-model-vitl16_384.onnx"), providers=prov, is_inverse_depth=False)
else:
    de = RelativeDepthEstimator(get("depth-model-vitl16_384.onnx"), providers=prov, is_inverse=False)
    ne = SurfaceNormalEstimator(get("normal-model-vitl16_384.onnx"), providers=prov)
for p in sorted(glob.glob(src + "/*.png")):
    im = cv2.imread(p)
    if kind == "multi":
        o = est.estimate_all_tasks(im)
        d = {"depth": o["depth"], "normal": o["normal"], "mask": o["foreground"]}
    else:
        d = {"depth": de.estimate_relative_depth(im), "normal": ne.estimate_normal(im)}
    np.savez_compressed(os.path.join(out, os.path.basename(p)[:-4] + ".npz"), **{k: np.asarray(v, np.float32) for k, v in d.items()})
print("done", kind, time.time() - t0, {k: v.shape for k, v in d.items()})
