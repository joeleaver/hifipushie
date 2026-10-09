"""structure.py: structure on the MAP head, one op at a time.
  run.sh structure.py mk <src model> <dst model> '<json patch of base.head>' [idscale]   (null deletes a key)
      -> saves dst (a copy of src with the patch), prints the evidence residual through the two references (this
         head's own best cameras on the same evidence), integrity against src, the macro readout, and writes the
         six-view sheet $D2/out/six_<dst>.png (for the blind readers).
  run.sh structure.py ev <model> ...     evidence residual + macros only
  run.sh structure.py reads <model> <tag> a.json b.json c.json    store blind reads, print diff + agreement + score
"""
import copy
import json
import os
import sys

import numpy as np

import garrett
from hifipushie import humanfit, humanfit_map, humanmacro as hm, likeness_read as lr, store

D2 = os.environ.get("D2", "/mnt/data/hifipushie/refstudy2")
REF = "rs_garrett_read3"   # whose human_refs.json (views + cameras) every copy carries


def merge(a, p):
    for k, v in p.items():
        if v is None:
            a.pop(k, None)
        elif isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = copy.deepcopy(v)
    return a


def evidence(b):
    vs = garrett.refs()
    _, rep = humanfit_map.fit(b, vs, free=())
    return [v["rms_mm"] for v in rep["views"]], rep


def info(tag, b, prev=None):
    r, rep = evidence(b)
    st = humanfit.state(b)
    line = f"{tag}: evidence residual front / desk {r[0]} / {r[1]} mm"
    if prev is not None:
        it = humanfit.integrity(b, st, humanfit.state(prev))
        line += " | " + humanfit.verdict(it)[:260]
        r0, _ = evidence(prev)
        line += f" | residual change {r[0] - r0[0]:+.2f} / {r[1] - r0[1]:+.2f}"
    print(line)
    z = hm.read(humanfit.identity(b))
    print("  plausibility", humanfit.plausibility(b))
    print(hm.text(z, 8))
    return r


def mk(src, dst, patch, idscale=None):
    sp = store.load(src)
    b = copy.deepcopy(sp["base"])
    merge(b["head"], patch)
    if idscale:
        idn = b["head"]["identity"]
        b["head"]["identity"] = {k: float(v) * idscale for k, v in idn.items()}
    info(dst, b, sp["base"])
    store.save(dst, {**copy.deepcopy(sp), "base": b}, f"refstudy2: {src} + {json.dumps(patch)[:200]}" + (f" identity x{idscale}" if idscale else ""))
    for f in ("human_refs.json", lr.READ):
        s = store.HOME / REF / f
        if s.exists() and not (store.HOME / dst / f).exists():
            (store.HOME / dst / f).write_text(s.read_text())
    out = f"{D2}/out/six_{dst}.png"
    lr.render_views(dst, out, base=b)
    print("six views:", out)


def reads(name, tag, files):
    src = json.loads((store.HOME / "lk_garrett5" / lr.READ).read_text())
    dst_f = store.HOME / name / lr.READ
    dst = json.loads(dst_f.read_text()) if dst_f.exists() else {"format": src.get("format"), "reads": {}}
    for k in ("reference", "reference_by"):
        if k in src["reads"]:
            dst["reads"][k] = src["reads"][k]
    tags = []
    for i, f in enumerate(files):
        dst["reads"][f"{tag}_r{i + 1}"] = json.loads(open(f).read())
        tags.append(f"{tag}_r{i + 1}")
    dst_f.write_text(json.dumps(dst, indent=1))
    for t in tags:
        print("---", t)
        print("\n".join(lr.diff(name, t).split("\n")[:12]))
    if len(tags) > 1:
        print(lr.agreement(name, tags))
    import score
    print(score.text(name, tags))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "mk":   # mk <dst> ...: the steps are in steps.json beside this file ({dst: {"src", "patch", "idscale"}})
        S = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "steps.json")))
        for dst in a[1:]:
            s = S[dst]
            mk(s["src"], dst, s.get("patch", {}), s.get("idscale"))
    elif a[0] == "ev":
        for n in [x for x in a[1:] if x != "-q"]:
            info(n, store.load(n)["base"])
    elif a[0] == "reads":
        reads(a[1], a[2], a[3:])
    elif a[0] == "rd":   # rd <model> ...: store $D2/reads/<model>_<n>.json as tag "b", then the score table
        import glob
        import score
        rows = []
        for n in [x for x in a[1:] if x != "-q"]:
            fs = sorted(glob.glob(f"{D2}/reads/{n}_*.json"))
            if "-q" not in a:
                reads(n, "b", fs)
            else:
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):
                    reads(n, "b", fs)
            rows.append((n, score.shares(n, score.tags_of(n, "b"))))
        ks = list(score.WANT) + list(score.AVOID)
        print("\n" + " " * 16 + " ".join(f"{k.split('_', 1)[1][:6]:>6s}" for k in ks) + "   score")
        for n, sh in rows:
            print(f"{n[-16:]:16s}" + " ".join(f"{sh.get(k, 0):6.2f}" for k in ks) + f"   {score.total(sh):+.2f}")
