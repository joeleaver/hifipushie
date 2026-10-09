"""fid.py <model> <img>...: face-ID (YuNet-aligned) of the front photo's face crop vs each image."""
import sys

from PIL import Image

from hifipushie import faceid, likeness

refs = likeness._refs(sys.argv[1])
v = refs["views"][0]
img = Image.open(v["image"]).convert("RGB")
b = likeness._box(v["points"], img.size)
photo = img.transform((900, int(900 * (b[3] - b[1]) / (b[2] - b[0]))), Image.EXTENT, b, Image.BICUBIC)
for p, s in zip(sys.argv[2:], faceid.scores(photo, [Image.open(p).convert("RGB") for p in sys.argv[2:]])):
    print(p.rsplit("/", 1)[-1], s)
