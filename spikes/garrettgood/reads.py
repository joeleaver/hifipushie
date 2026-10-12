"""reads.py <model> [a1 copy]: the reads the guide prescribes after a solve, nothing applied: face_ruler, eye_ruler,
lid_read, lip_read, brow_read (+ eye_ruler / lid_read / lip_read of the a1 copy against the same pictures)."""
import sys
from hifipushie import server
O = "/mnt/data/hifipushie/garrettgood/out/"


def txt(r):
    return r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str))


for m in sys.argv[1:]:
    for tool, kw in (("face_ruler", {"save": O + f"fr_{m}.png"}), ("eye_ruler", {"save": O + f"er_{m}.png"}),
                     ("lid_read", {}), ("lip_read", {}), ("brow_read", {})):
        try:
            print(f"\n===== {tool}({m})\n" + txt(getattr(server, tool)(m, **kw)), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"\n===== {tool}({m}) FAILED: {e!r}"[:600], flush=True)
