"""lipsonly3.py <model with a picture-hue atlas>: the stack with the lips from INDICATIONS (skin_layers lips="indications"),
then ONLY the lips layer laid. LIGHT."""
import sys
from hifipushie import blockin as bi, skin_layers as sl, store
m = sys.argv[1]
r = sl.apply(m, log=print, lips="indications")
s = sl.only(store.load(m), ("lips",))
bi._save(m, s, "lips layer only, from indications (outline + mid-lip colour)", bi._refs(m))
