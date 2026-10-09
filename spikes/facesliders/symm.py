"""symm.py: each slider's mirror asymmetry (mm): max |dR - mirror(dL)|."""
import numpy as np

from hifipushie import faceslide

T = faceslide.template()
for k, (dR, dL) in faceslide.fields().items():
    e = np.abs(dR - dL[T["mirror"]] * [-1, 1, 1]).max(1)
    i = int(np.argmax(e))
    print(k, round(1000 * float(e.max()), 4), "at", (1000 * T["X"][i]).round(1))
