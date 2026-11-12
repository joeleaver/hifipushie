"""atlas_model.py <src> <dst>: skin_project.apply(src -> dst) with the model's tone, opacity 0 (the measurement). LIGHT."""
import sys
from hifipushie import skin_project as sp
from hifipushie import skin_project_model
print(skin_project_model.apply(sys.argv[1], out=sys.argv[2], opacity=0.0, log=lambda s: None)["text"])
