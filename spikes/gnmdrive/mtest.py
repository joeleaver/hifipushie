"""mtest.py: the manual's suggest() on driver phrases, and every control it names is a valid block-in move."""
from hifipushie import blockin as bi, gnm_manual as gm

es = gm.entries()
print(len(es), "entries")
bad = []
for e in es:
    for m in e["moves"]:
        for part in m.replace(" + ", ",").split(","):
            p = part.strip().split(" ")[0]
            if not p or p.startswith(("local:", "lid_")):
                continue
            try:
                bi.direction(p)
            except Exception as ex:  # noqa: BLE001
                bad.append((e["see"][:40], p, str(ex)[:60]))
print("bad:", bad)
for ph in ["the mouth stands forward in profile", "muzzle forward", "pupils further apart", "double chin",
           "fluffy heavy lower face", "nose stands further out", "eyes bulge, prominent", "brows sit lower",
           "skull a rim too big all round", "upper lip longer, mouth lower under the nose", "forehead more upright",
           "cheek stands forward in 3/4", "ears stick out", "chin hangs lower", "lips fuller", "eyes and brows sit lower over the nose"]:
    r = gm.suggest(ph, top=2)
    print(f"{ph!r}: " + " || ".join(f"{e['use'][:60]} [{e['score']}]" for e in r["entries"]))
