"""parse_try.py <out png> <model>...: first look at the face-parsing candidates on a block-in model's reference
pictures (crop round the model's projected landmarks): picture | BiSeNet resnet18 | resnet34 | MediaPipe multiclass.
Runs the nets in the detector venv through hifipushie.faceparse once that exists; here: raw, for choosing."""
import json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, humanfit, likeness, store

D = "/mnt/data/hifipushie/refread/dl/parse"
SRC = r'''
import sys, json, numpy as np, cv2
out, d = sys.argv[1], sys.argv[2]
res = {}
for nm in ("resnet18", "resnet34"):
    net = cv2.dnn.readNet(d + "/" + nm + ".onnx")
    for p in sys.argv[3:]:
        im = cv2.imread(p)
        x = cv2.resize(im, (512, 512), interpolation=cv2.INTER_LINEAR)[:, :, ::-1].astype(np.float32) / 255.0
        x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        net.setInput(x.transpose(2, 0, 1)[None].astype(np.float32))
        y = net.forward()
        lab = y[0].argmax(0).astype(np.uint8)
        cv2.imwrite(p + "." + nm + ".png", lab)
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision
seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
    base_options=mpt.BaseOptions(model_asset_path=d + "/selfie_multiclass_256x256.tflite"), output_category_mask=True))
for p in sys.argv[3:]:
    im = cv2.imread(p)[:, :, ::-1]
    r = seg.segment(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(im)))
    cv2.imwrite(p + ".mp.png", r.category_mask.numpy_view())
'''
PAL = np.array([[0, 0, 0], [255, 200, 170], [120, 80, 40], [120, 80, 40], [255, 255, 255], [255, 255, 255], [0, 255, 255],
                [255, 0, 255], [255, 0, 255], [255, 255, 0], [0, 200, 0], [150, 0, 0], [255, 0, 0], [200, 0, 80],
                [0, 120, 255], [0, 255, 150], [60, 60, 160], [90, 60, 30], [200, 200, 0]], np.uint8)
PALM = np.array([[0, 0, 0], [90, 60, 30], [0, 120, 255], [255, 200, 170], [60, 60, 160], [200, 200, 0]], np.uint8)
out, models = sys.argv[1], sys.argv[2:]
rows = []
with tempfile.TemporaryDirectory(dir="/mnt/data/hifipushie/refread/out") as td:
    paths = []
    for m in models:
        rj = bi._refs(m)
        L = humanfit.state(store.load(m)["base"])["L"]
        for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
            P = humanfit.project(cam, np.asarray(L, float)[:68])
            c = 0.5 * (P.min(0) + P.max(0))
            s = 2.1 * float(np.ptp(P[:, 1]))
            img = Image.open(v["image"]).convert("RGB")
            cr = img.crop((int(c[0] - s / 2), int(c[1] - 0.55 * s), int(c[0] + s / 2), int(c[1] + 0.45 * s))).resize((512, 512), Image.LANCZOS)
            p = f"{td}/{m}_{vi}.png"
            cr.save(p)
            paths.append(p)
    src = f"{td}/s.py"
    open(src, "w").write(SRC)
    r = subprocess.run([likeness.VENV + "/bin/python", src, td + "/o.json", D, *paths], capture_output=True, text=True)
    print(r.stderr[-2000:])
    for p in paths:
        im = Image.open(p)
        t = [im]
        for nm, pal in (("resnet18", PAL), ("resnet34", PAL), ("mp", PALM)):
            lab = np.asarray(Image.open(f"{p}.{nm}.png").resize((512, 512), Image.NEAREST))
            t.append(Image.blend(im, Image.fromarray(pal[np.minimum(lab, len(pal) - 1)]), 0.6))
        rows.append(t)
W = Image.new("RGB", (4 * 512, 512 * len(rows)))
for i, t in enumerate(rows):
    for j, x in enumerate(t):
        W.paste(x, (j * 512, i * 512))
W.save(out)
print(out)
