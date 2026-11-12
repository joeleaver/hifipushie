"""tab.py <model> ...: the block-in's acceptance table per model (blockin.table_text) and the delta to the first."""
import sys

from hifipushie import blockin as bi
from hifipushie import blockin_table

t0 = None
for n in sys.argv[1:]:
    t = blockin_table.table(n)
    print("==", n)
    print(blockin_table.table_text(t))
    if t0 is not None:
        print("delta vs", sys.argv[1], ":", blockin_table.table_delta(t0, t))
    t0 = t0 or t
