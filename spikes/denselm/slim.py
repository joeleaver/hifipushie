"""slim.py <data root> <out root> [quality=93]: the dressings as a SMALL copy for upload to a training job (a 690 MB job
folder made the offload worker go quiet while fetching it): each picture as <i>.jpg (RGB) + <i>_a.png (alpha, 8
bit), labels / meta / landmarks as they are; ~4x smaller. train.py's pack reads either form."""
import shutil
import sys
from pathlib import Path

from PIL import Image

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
q = int(sys.argv[3]) if len(sys.argv) > 3 else 93
dst.mkdir(parents=True, exist_ok=True)
shutil.copy(src / "landmarks.json", dst / "landmarks.json")
n = 0
for d in sorted(p for p in src.iterdir() if (p / "labels.npz").exists() and (p / "meta.npz").exists()):
    o = dst / d.name
    o.mkdir(exist_ok=True)
    for f in sorted(d.glob("[0-9]*.png")):
        if (o / (f.stem + ".jpg")).exists():
            continue
        im = Image.open(f).convert("RGBA")
        im.convert("RGB").save(o / (f.stem + ".jpg"), quality=q, subsampling=0)
        im.getchannel("A").save(o / (f.stem + "_a.png"), optimize=True)
        n += 1
    for k in ("meta.npz", "dressing.json", "timing.json", "labels.npz"):
        if (d / k).exists():
            shutil.copy(d / k, o / k)
print(f"{n} pictures slimmed into {dst}")
