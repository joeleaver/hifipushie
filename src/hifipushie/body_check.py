"""Body girths against ANSUR II (2026-10-15, dress-tess; the coordinator: "a body below p1 on any girth should be
flagged before any garment is drafted on it"). Tess's calf (277 mm) was under the smallest of 1986 ANSUR II women
(282) and the jeans' leg ease was being tuned against it.

`girths(V, faces, J)`: the tailor's tape (`tailor.measure`) plus the forearm, as ANSUR II names them.
`percentiles(mm, sex)`: each girth's percentile among ANSUR II women (sex 0) or men (sex 1), flags under p1 / over p99.
`predict(known, targets, sex)`: a girth predicted from the ones a body is right on (OLS over ANSUR II, residual SD).
`check(model)`: all of it for a model's base body. CLI: `python -m hifipushie.body_check <model> [sex]`.

Data: the ANSUR II public CSVs (US Army, public domain), in $HIFIPUSHIE_ANSUR or /mnt/data/hifipushie/headbody/ansur.
Level caveats (ours = tailor.measure): ANSUR II has NO knee girth; `knee` (at the knee joint) is compared with
lowerthighcircumference (just above the patella), so it reads a little low. Biceps and forearm are FLEXED in ANSUR
(a relaxed arm reads ~5-8% under). `upperLeg` is the tailor's at the crotch; ANSUR thigh is at the gluteal furrow.

CALIBRATED to ANSUR II's landmarks (2026-10-15, dress-tess; `girths(..., ansur=True)`, the default). The tailor's tapes
are drafting tapes and sat elsewhere (MakeHuman's default young woman, old -> landmark): waist at the natural waist
(0.62 H) -> ANSUR's waist is at the OMPHALION (navel; 0.604 H, ANSUR median ratio): 683 -> 715 mm; thigh LEVEL 5 cm under
the crotch -> PERPENDICULAR to the thigh's axis at the gluteal furrow (~ the crotch standing): 516 -> 556 mm; seat the
largest level section (it slid down onto the thigh tops, 0.48 H) -> the level of the buttocks' greatest backward
protrusion; chest the fullest level 2-12 cm under the armpit -> the level of the bust point (the chest's most forward
point); biceps relaxed -> x FLEX (1.05, basis THIN: ANSUR measures it flexed, nothing here can flex). Calf (maximum
level) and neck are as the tailor's. The tailor's own values stay in the result as "tailor_<name>". ANSUR II
definitions from the ANSUR II measurer's handbook (Hotzman et al. 2011, NATICK/TR-11/017) as cited in its summary
report; the handbook itself could not be fetched here (DTIC 403, the Penn State mirror serves an app shell).
POPULATION caveat: ANSUR II is US Army personnel; its women aged 18-30 have BMI p5 20.1, p25 22.6, p50 24.7. A
slender civilian young woman (BMI ~19-21) sits near ANSUR's p5-10 on every girth, not p25."""
from __future__ import annotations

import csv
import json
import os
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

ANSUR_DIR = Path(os.environ.get("HIFIPUSHIE_ANSUR", "/mnt/data/hifipushie/headbody/ansur"))
# ours (tailor.measure / forearm) -> ANSUR II column
MAP = {"neck": "neckcircumference", "chest": "chestcircumference", "waist": "waistcircumference",
       "seat": "buttockcircumference", "upperLeg": "thighcircumference", "knee": "lowerthighcircumference",
       "calf": "calfcircumference", "ankle": "anklecircumference", "biceps": "bicepscircumferenceflexed",
       "forearm": "forearmcircumferenceflexed", "wrist": "wristcircumference", "height": "stature",
       "biacromial": "biacromialbreadth", "shoulderLength": "shoulderlength"}
LOW, HIGH = 1.0, 99.0
FLEX = 1.05  # relaxed -> flexed biceps / forearm (basis THIN: the old docstring's "5-8% under", its low end)
LANDMARK_COLS = ("stature", "waistheightomphalion", "buttockheight", "crotchheight", "chestheight", "Age")


@lru_cache(maxsize=2)
def table(sex: int) -> dict:
    """ANSUR II columns (mm) for women (0) or men (1): {column: np.ndarray}."""
    f = ANSUR_DIR / ("ANSUR_II_FEMALE_Public.csv" if int(sex) == 0 else "ANSUR_II_MALE_Public.csv")
    if not f.exists():
        raise FileNotFoundError(f"ANSUR II data not found: {f} (set HIFIPUSHIE_ANSUR)")
    with open(f, encoding="latin-1") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for c in set(MAP.values()) | set(LANDMARK_COLS):
        out[c] = np.array([float(r[c]) for r in rows])
    return out


def ratio(col: str, sex: int) -> float:
    """ANSUR II's median landmark height / stature (all ages) for that sex."""
    t = table(sex)
    return float(np.median(t[col] / t["stature"]))


def ages(sex: int, lo: float = 18, hi: float = 30) -> np.ndarray:
    """A mask of ANSUR II subjects aged lo..hi (for `percentiles(..., age=)`)."""
    a = table(sex)["Age"]
    return (a >= lo) & (a <= hi)


def percentile_of(value: float, col: str, sex: int, age: tuple | None = None) -> float:
    v = table(sex)[col]
    if age is not None:
        v = v[ages(sex, *age)]
    return float(100.0 * (np.sum(v < value) + 0.5 * np.sum(v == value)) / len(v))


def percentiles(mm: dict, sex: int, age: tuple | None = None) -> dict:
    """{ours: {"mm", "ansur", "pct", "p1", "p50", "p99", "flag"}} for every girth ANSUR II has (age=(lo, hi): only
    subjects of those ages, e.g. (18, 30))."""
    out = {}
    for k, col in MAP.items():
        if k not in mm or mm[k] is None:
            continue
        v = table(sex)[col]
        if age is not None:
            v = v[ages(sex, *age)]
        p = percentile_of(float(mm[k]), col, sex, age)
        out[k] = {"mm": round(float(mm[k]), 1), "ansur": col, "pct": round(p, 1),
                  "p1": float(np.percentile(v, 1)), "p50": float(np.percentile(v, 50)), "p99": float(np.percentile(v, 99)),
                  "flag": "under p1" if p < LOW else ("over p99" if p > HIGH else "")}
    return out


def predict(known: dict, targets: list, sex: int) -> dict:
    """Each target girth (ours) predicted by OLS over ANSUR II from the `known` ones ({ours: mm}): {target: {"mm",
    "resid_sd", "r2", "coef" {ours: per mm, "const"}}}."""
    t = table(sex)
    ks = [k for k in known if k in MAP]
    X = np.c_[[t[MAP[k]] for k in ks]].T
    X1 = np.c_[X, np.ones(len(X))]
    x = np.r_[[float(known[k]) for k in ks], 1.0]
    out = {}
    for tg in targets:
        y = t[MAP[tg]]
        b, *_ = np.linalg.lstsq(X1, y, rcond=None)
        r = y - X1 @ b
        out[tg] = {"mm": round(float(x @ b), 1), "resid_sd": round(float(r.std(ddof=len(b))), 1),
                   "r2": round(float(1 - r.var() / y.var()), 3),
                   "coef": {**{k: round(float(c), 4) for k, c in zip(ks, b[:-1])}, "const": round(float(b[-1]), 1)}}
    return out


def girths(V, faces, J: dict, ansur: bool = True, sex: int = 0) -> dict:
    """tailor.measure's girths (mm) + the forearm (the largest section across elbow -> wrist, 10-45% down). ansur=True:
    waist, seat, upperLeg (thigh), chest and biceps re-taken at ANSUR II's landmarks (module docstring; `sex` picks
    the omphalion's height ratio), the tailor's kept as "tailor_<name>"."""
    from . import tailor
    V = np.asarray(V, float)
    m = tailor.measure(V, faces, J)
    mm = dict(m["mm"])
    T = tailor.triangles(faces) if not isinstance(faces, np.ndarray) or np.asarray(faces).shape[1] != 3 else faces
    if ansur:
        mm.update(_landmark_girths(V, T, {k: np.asarray(v, float) for k, v in J.items()}, m, sex))
    # shoulders (coordinator 2026-10-15, after dress-garrett's HPS work: Tess's shoulder breadth read under p5):
    # biacromial = 2 x the tailor's shoulder point's |x| (the creature is centred on x = 0; ANSUR: acromion to acromion,
    # straight); shoulderLength = HPS (neck point) -> shoulder point, STRAIGHT (ANSUR takes it over the skin: ours a
    # few mm under; basis THIN). Both from tailor.measure's "at" (shoulder.L = the acromion-like top, hps.L).
    at_ = m.get("at") or {}
    if "shoulder.L" in at_ and "hps.L" in at_:
        sp, hp = np.asarray(at_["shoulder.L"], float), np.asarray(at_["hps.L"], float)
        mm["biacromial"] = round(2000 * abs(float(sp[0])), 1)
        mm["shoulderLength"] = round(1000 * float(np.linalg.norm(sp - hp)), 1)
    el, wr = np.asarray(J["elbow.L"], float), np.asarray(J["wrist.L"], float)
    d = (wr - el) / np.linalg.norm(wr - el)
    best = 0.0
    for f in np.linspace(0.10, 0.45, 8):
        p = el + f * (wr - el)
        try:
            loop = tailor.section(V, T, p, d, p)
        except Exception:
            continue
        L = _perimeter(loop)
        if L and L > best:
            best = L
    if best:
        mm["forearm"] = round(1000 * best * (FLEX if ansur else 1.0), 1)
    return mm


def _landmark_girths(V, T, J: dict, m: dict, sex: int) -> dict:
    """Waist at the omphalion, seat at the buttocks' greatest protrusion, thigh square to its axis at the gluteal
    furrow (the crotch), chest at the bust point, biceps x FLEX (mm); the tailor's as "tailor_<name>"."""
    from . import tailor
    Z = np.array([0, 0, 1.0])
    mm, at = m["mm"], m["at"]
    z0 = float(V[:, 2].min())
    H = float(V[:, 2].max()) - z0
    pel, ch, nk = J["pelvis"], J["chest"], J["neck"]
    ax = lambda z: np.array([0.0, float(np.interp(z, [pel[2], ch[2], nk[2]], [pel[1], ch[1], nk[1]])), z])
    tor = lambda z: tailor.section(V, T, ax(z), Z, ax(z))
    out = {f"tailor_{k}": mm[k] for k in ("waist", "seat", "upperLeg", "chest", "biceps") if k in mm}
    zo = z0 + H * ratio("waistheightomphalion", sex)
    L = tor(zo)
    if L is not None:
        out["waist"], out["waist_z"] = round(1000 * tailor.girth(L, Z), 1), round(zo, 4)
    zc = at.get("crotch_z", z0 + H * ratio("crotchheight", sex))
    zw = at["waist_z"]
    best = None  # the level where the torso reaches furthest back (+Y), crotch .. waist
    for z in np.arange(zc + 0.02, zw, 0.004):
        L = tor(z)
        if L is not None and L[:, 0].min() < -0.02 < 0.02 < L[:, 0].max():
            if best is None or L[:, 1].max() > best[0]:
                best = (float(L[:, 1].max()), z, L)
    if best:
        out["seat"], out["seat_z"] = round(1000 * tailor.girth(best[2], Z), 1), round(best[1], 4)
    hp, kn = J["hip.L"], J["knee.L"]
    d = (kn - hp) / np.linalg.norm(kn - hp)
    p = hp + (zc - hp[2]) / (kn[2] - hp[2]) * (kn - hp)
    Ls = [L for L in tailor.slice_loops(V, T, p, d)
          if np.max(np.linalg.norm(L - p, axis=1)) < 0.16 and tailor._encloses(L, p, d)]
    if Ls:
        out["upperLeg"] = round(1000 * max(tailor.girth(L, d) for L in Ls), 1)
    za = at["armpit_z"]
    best = None  # the bust point: the chest's most forward (-Y) point, 2-20 cm under the armpit
    for z in np.arange(za - 0.02, za - 0.20, -0.004):
        L = tor(z)
        if L is not None and (best is None or -L[:, 1].min() > best[0]):
            best = (float(-L[:, 1].min()), z, L)
    if best:
        out["chest"], out["chest_z"] = round(1000 * tailor.girth(best[2], Z), 1), round(best[1], 4)
    if "biceps" in mm:
        out["biceps"] = round(FLEX * mm["biceps"], 1)
    return out


def bmi(V, faces, density: float = 1010.0) -> dict:
    """The closed body's volume (L), mass at `density` kg/m3 (whole-body ~1010) and BMI by its height: what the girths'
    percentiles mean for build (ANSUR II women 18-30: BMI p5 20.1, p25 22.6, p50 24.7)."""
    from . import tailor
    V = np.asarray(V, float)
    T = np.asarray(tailor.triangles(faces) if not isinstance(faces, np.ndarray) or np.asarray(faces).shape[1] != 3 else faces)
    vol = abs(float(np.einsum("ij,ij->i", V[T[:, 0]], np.cross(V[T[:, 1]], V[T[:, 2]])).sum()) / 6.0)
    h = float(V[:, 2].max() - V[:, 2].min())
    return {"litres": round(1000 * vol, 1), "kg": round(density * vol, 1), "bmi": round(density * vol / h ** 2, 1)}


def _perimeter(loop) -> float:
    if loop is None:
        return 0.0
    if isinstance(loop, dict):
        loop = loop.get("loop", loop.get("P"))
    if isinstance(loop, (int, float)):
        return float(loop)
    P = np.asarray(loop, float)
    if P.ndim != 2 or len(P) < 3:
        return 0.0
    return float(np.linalg.norm(np.diff(np.vstack([P, P[:1]]), axis=0), axis=1).sum())


def sex_of(spec: dict) -> int | None:
    b = (spec.get("base") or {})
    s = (b.get("body") or {}).get("sex")
    if s is not None:
        return 1 if float(s) >= 0.5 else 0
    tp = str(b.get("template", ""))
    if "female" in tp:
        return 0
    if "male" in tp:
        return 1
    return None


def check(model: str, sex: int | None = None, age: tuple | None = None) -> dict:
    """A model's base body: {"sex", "girths" (percentiles), "flags" [ours under p1 / over p99]}."""
    from . import cloth, store
    spec = store.load(model)
    sex = sex_of(spec) if sex is None else int(sex)
    if sex is None:
        raise ValueError(f"{model}: body sex unknown (base.body.sex / template): pass sex=0 (women) or 1 (men)")
    b = cloth.body_mesh(spec)
    mm = girths(b["V"], b["F"], b["J"], sex=sex)
    pc = percentiles(mm, sex, age)
    return {"model": model, "sex": sex, "girths": pc, "flags": [f"{k} {v['mm']} mm {v['flag']} ({v['ansur']} p1 {v['p1']:.0f})"
                                                             for k, v in pc.items() if v["flag"]]}


if __name__ == "__main__":
    r = check(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
    for k, v in r["girths"].items():
        print(f"{k:9s} {v['mm']:7.1f} mm  p{v['pct']:5.1f}  (ANSUR {v['ansur']}: p1 {v['p1']:.0f}, p50 {v['p50']:.0f}, p99 {v['p99']:.0f}) {v['flag']}")
    print("FLAGS", json.dumps(r["flags"]))
