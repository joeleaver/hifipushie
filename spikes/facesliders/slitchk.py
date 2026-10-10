"""slitchk.py <model>: the expanded spec's mouth interior blobs."""
import sys

from hifipushie import spec as specmod, store

e = specmod.expand_mirror(store.load(sys.argv[1]))
import json
for k in ("face_mouth_bag",):
    print(k, json.dumps((e.get("blobs") or {}).get(k))[:400])
print([k for k in (e.get("blobs") or {}) if "mouth" in k or "teeth" in k or "tongue" in k or "slit" in k])
