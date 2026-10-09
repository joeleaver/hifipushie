"""addpts.py <name>: give every image-only view in <name>/human_refs.json a few lm points from the detector (MediaPipe
indices -> the 68 convention's outline / nose / brows), so likeness() can box the face. The fit itself ignores
lm points on views with an image."""
import json, sys
from PIL import Image
from hifipushie import likeness as lk, store

MP = {"lm0": 234, "lm16": 454, "lm8": 152, "lm27": 168, "lm30": 1, "lm19": 105, "lm24": 334, "lm36": 33, "lm45": 263,
      "lm48": 61, "lm54": 291}
name = sys.argv[1]
f = store.HOME / name / "human_refs.json"
refs = json.loads(f.read_text())
for v in refs["views"]:
    if v.get("points"):
        continue
    img = Image.open(v["image"]).convert("RGB")
    info = lk.detect_region(img, (0, 0, img.size[0], img.size[1]), info=True)
    P = info["P"]
    v["points"] = {k: [float(P[i, 0]), float(P[i, 1])] for k, i in MP.items()}
    print(v["image"].split("/")[-1], v["points"]["lm30"])
f.write_text(json.dumps(refs, indent=1))
