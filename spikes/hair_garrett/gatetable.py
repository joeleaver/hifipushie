"""gatetable.py <model> <checklist.json> [views=0,1,2]: the gates' MEASURE step (docs/notes/gates.md): every numeric item
of a hair checklist measured on the model's tiles, printed as item | reference | ours | pass, and written to
$TOUT/table_<model>.md. Runs cmp.py (hair_read.compare), hlinetrace.py and hcover.py (render=0: the magenta tiles must
exist) as light jobs and parses their output. Visual items are listed as "LOOK" (the review decides them).
The strand-texture items (lay_top, flow_coherence, striping, hairline_edge, back_lightness: texmeas.py) are measured
on the LOOK pairs ($TOUT/pairs_<model>, written by mksheet.py: run this after it), one row per crop."""
import json
import numpy as np
import os
import re
import subprocess
import sys

m, ck = sys.argv[1], sys.argv[2]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
OUT = os.environ["TOUT"]
HG = os.environ.get("HG", "/mnt/data/hifipushie/hair_garrett")
C = json.load(open(ck))


def run(*a):
    r = subprocess.run([f"{HG}/runl.sh", *a], capture_output=True, text=True)
    return r.stdout + r.stderr


cmp_ = run("cmp.py", m, "views=" + kw.get("views", "0,1,2"))
hl = run("hlinetrace.py", m)
cov = run("hcover.py", m, "render=0")
so = {k: (float(a), float(b)) for k, a, b in re.findall(r"stand-off (\w+): ([-\d.]+) \| ([-\d.]+) mm", cmp_)}
col = re.search(r"view 0 \(AUTHORITY\) colour L\*/chroma/hue mean ([\d.]+)/[\d.]+/[\d.]+ \| ([\d.]+)/", cmp_)
share = re.search(r"view 0 \(AUTHORITY\).*?light share ([\d.]+) \| ([\d.]+)", cmp_, re.S)
v0 = hl.split("view 1:")[0]
bins = {b: float(d) for b, d in re.findall(r"(\d+-\d+): ([-+\d.]+)", v0)}
cv = {v: float(p) for v, p in re.findall(r"(t60|y180|y125|v1) ([\d.]+) %", cov)}


def mean_bins(keys):
    vals = [bins[k] for k in keys if k in bins]
    return round(sum(vals) / len(vals), 1) if vals else None


# strand-texture items: texmeas field, reference key, how ours passes (abs = within tolerance, max = at most ref + tol,
# min = at least the item's floor)
TEX = {"lay_top": ("lay", "reference_deg", "tolerance_deg", "abs"), "flow_coherence": ("coh", "reference", "min", "min"),
       "striping": ("band", "reference", "tolerance", "max"), "hairline_edge": ("edgec", "reference", "tolerance", "max"),
       "back_lightness": ("Lmean", "reference", "tolerance_L", "abs")}
PAIRS = kw.get("pairs", f"{OUT}/pairs_{m}")
_tex = {}


def tex(crop):
    if crop not in _tex:
        import texmeas
        isedge = "hairline" in crop or "temple" in crop
        a, b = (f"{PAIRS}/{crop}_{k}.png" for k in ("ref", "res"))
        _tex[crop] = (texmeas.measure(a, isedge), texmeas.measure(b, isedge)) if os.path.exists(a) and os.path.exists(b) \
            else (None, None)
    return _tex[crop]


rows = []
for it in C["items"]:
    if it["id"] in TEX:
        fld, rk, tk, how = TEX[it["id"]]
        for crop, target in it[rk].items():
            a, b = tex(crop)
            name = f"{it['id']} / {crop}"
            if b is None or a is None:
                rows.append((name, str(target), "no pair" if b is None else "too few hair px", "n/a"))
                continue
            ours, photo = round(float(b[fld]), 2), round(float(a[fld]), 2)
            if how == "abs":
                ok, ref = abs(ours - target) <= it[tk], f"{target} +- {it[tk]} (pair photo {photo})"
            elif how == "max":
                ok, ref = ours <= target + it[tk], f"<= {round(target + it[tk], 2)} (pair photo {photo})"
            else:
                ok, ref = ours >= it[tk], f">= {it[tk]} (pair photo {photo})"
            rows.append((name, ref, str(ours), "PASS" if ok else "FAIL"))
        continue
    i, ref, ours, ok = it["id"], "", "", None
    if i.startswith("standoff_"):
        r_ = so.get(i.split("_", 1)[1])
        if r_:
            ours, ref = r_
            ok = abs(ours - ref) <= it["tolerance_mm"]
            ref, ours = f"{ref} mm", f"{ours} mm"
        else:
            ref, ours = f"{it.get('reference_mm')} mm", "not measured"
    elif i == "hairline_centre":
        d = mean_bins(["0-10", "10-20"])
        ref, ours = "photo boundary", ("none traced" if d is None else f"{d:+} mm")
        ok = None if d is None else abs(d) <= it["tolerance_mm"]
    elif i == "temple_corners":
        d = mean_bins(["30-40", "40-50"])
        ref, ours = "photo boundary", ("none traced" if d is None else f"{d:+} mm")
        ok = None if d is None else abs(d) <= it["tolerance_mm"]
    elif i == "colour_front" and col:
        ours, ref = float(col.group(1)), float(col.group(2))
        ok = abs(ours - ref) <= it["tolerance_L"]
        ref, ours = f"L* {ref}", f"L* {ours}"
    elif i == "colour_regions":
        # whole-head colour (successor 17): per VIEW and region, the region's median L*, ours vs photo. (Averaged over
        # views it passed: the front / 3q views read +4..+7 too light, the profile -4..-7 too dark, and cancelled.)
        for vi, blk in re.findall(r"view (\d) .*?\n((?:    .*\n)+)", cmp_):
            mm_ = re.search(r"L\* by region: (.*)", blk)
            if not mm_ or str(vi) not in it.get("views", "01"):
                continue
            for k, a, b in re.findall(r"(\w+) ([-\d.]+|None) \| ([-\d.]+|None)", mm_.group(1)):
                if a != "None" and b != "None" and k in it["regions"]:
                    o_, p_ = float(a), float(b)
                    rows.append((f"colour_regions / v{vi} {k}", f"L* {p_:.1f} +- {it['tolerance_L']} (photo)",
                                 f"L* {o_:.1f}", "PASS" if abs(o_ - p_) <= it["tolerance_L"] else "FAIL"))
        continue
    elif i == "grey_mix" and share:
        ours, ref = float(share.group(1)), float(share.group(2))
        ok = abs(ours - ref) <= it["tolerance"]
    elif i.startswith("coverage_"):
        v = "t60" if i == "coverage_above" else "y180"
        ref = f"<= {it['max_pct']} %"
        if v in cv:
            ours = f"{cv[v]} %"
            ok = cv[v] <= it["max_pct"]
        else:
            ours = "not rendered"
    elif it.get("visual"):
        ref, ours, ok = it["reference"], "LOOK (review)", "look"
    rows.append((i, str(ref), str(ours), "PASS" if ok is True else "FAIL" if ok is False else ("LOOK" if ok == "look" else "n/a")))
lines = [f"# {m}: {C['piece']} (checklist {ck})", "", "| item | reference | ours | pass |", "|---|---|---|---|"]
lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
txt = "\n".join(lines)
open(f"{OUT}/table_{m}.md", "w").write(txt + "\n")
print(txt)
print(f"{OUT}/table_{m}.md")
