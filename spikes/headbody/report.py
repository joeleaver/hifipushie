import sys
from hifipushie import onemesh, store
for m in sys.argv[1:]:
    print("==", m); print(onemesh.attach_report(store.load(m)["base"])["text"])
