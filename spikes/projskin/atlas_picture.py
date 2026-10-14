"""atlas_picture.py <src> <dst>: skin_project.apply(src -> dst) with tone="picture" (the photo's own hue; only the lightness
is the model's), opacity 0."""
import sys
from hifipushie import skin_project as sp
print(sp.apply(sys.argv[1], out=sys.argv[2], opacity=0.0, tone="picture", log=lambda s: None)["text"])
