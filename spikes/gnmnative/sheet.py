"""sheet.py <out.png> <title> new=<model> old=<model> new_open=<model> old_open=<model> [turn=1] [open_ref=<picture>]
[old_label=..] [tile=520]: Joe's sheet for one subject: REFERENCE | new GNM-native head | current head; rows eyes
front, eyes turned (view `turn`), mouth front, mouth open (jawOpen 0.6; a reference only if one is given), whole face
front. Tiles are shots.py's (dressed EEVEE through the references' fitted cameras): out/<model>/<feature>_v<i>.png."""
import sys

from strip import row, stack

O = "/mnt/data/hifipushie/gnmnative/out"
out, title = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
T = int(kw.get("tile", 520))
new, old = kw["new"], kw["old"]
tv = kw.get("turn", "1")
nl, ol = "NEW: GNM's eye + mouth", kw.get("old_label", "CURRENT head")


def t(m, f):
    import os
    p = f"{O}/{m}/{f}.png"
    return p if os.path.exists(p) else None


rows = [
    row([("REFERENCE", t(new, "eyes_v0_ref")), (nl, t(new, "eyes_v0")), (ol, t(old, "eyes_v0"))], T),
    row([("eyes, turned", t(new, f"eyes_v{tv}_ref")), ("", t(new, f"eyes_v{tv}")), ("", t(old, f"eyes_v{tv}"))], T),
    row([("mouth", t(new, "mouth_v0_ref")), ("", t(new, "mouth_v0")), ("", t(old, "mouth_v0"))], T),
    row([("mouth open (jawOpen 0.6)", kw.get("open_ref")), ("", t(kw["new_open"], "mouth_v0")), ("", t(kw["old_open"], "mouth_v0"))], T),
    row([("whole face", t(new, "face_v0_ref")), ("", t(new, "face_v0")), ("", t(old, "face_v0"))], T),
]
stack(rows, title, fs=44).save(out)
print(out)
