"""pairs.py <set> <seed>: make the driving test's cases. A from GNM's prior N(0, I) or the identity sampler (random
sex / ethnicity); B = A with one to three regions transplanted from a donor (least change in the 170 comps, the rest
of the face held). Donors are chosen among 160 candidates so the change is NAMEABLE (the largest change of the region's
character macros, in population sd), signed for the special cases (jaw_full = fuller, heavier; mouth = profile angle).
Writes cases/<case>/case.json (what a driver may see: id, difficulty) + hidden/<case>.json (A, B, regions, donors)."""
import json
import sys

import numpy as np

import drv
from hifipushie import gnm_sampler as S

SETS = {
    # case: (difficulty, [(region, amount)], A source)
    "easy": [("skull", 1.0), ("jaw_full", 1.0), ("mouth", 1.0), ("nose", 1.0), ("eyes", 1.0), ("brows", 1.0),
             ("cheeks", 1.0), ("chin", 1.0)],
    "medium": [[("jaw", 0.7)], [("nose", 0.7), ("mouth", 0.7)], [("eyes", 0.7), ("brows", 0.7)]],
    "hard": [[("chin", 0.5), ("mouth", 0.5), ("nose", 0.5)], [("cheeks", 0.5), ("jaw", 0.5), ("eyes", 0.5)],
             [("skull", 0.5), ("brows", 0.5), ("mouth", 0.5)]],
}
SIGNED = {"jaw_full": {"cheek_fullness": 1, "neck_width": 1, "under_chin": -1, "jaw_width": 0.5}}


def draw_A(rng, kind):
    if kind == "prior":
        return rng.normal(size=170)
    lab = S.id_label(float(rng.integers(0, 2)), S.ETH[int(rng.integers(0, 4))])
    return S.identity()(rng.normal(size=64), lab)[0][:170]


def pick(cA, region, amount, rng, top=True, n=160):
    m0 = drv.macros(cA)
    best = None
    cands = []
    for i in range(n):
        cD = draw_A(rng, "prior" if i % 2 else "sampler")
        cB = drv.transplant(cA, cD, region, amount)
        m1 = drv.macros(cB)
        dz = {k: m1[k] - m0[k] for k in drv.REGION_MACROS[region]}
        if region in SIGNED:
            s = sum(w * dz.get(k, m1[k] - m0[k]) for k, w in SIGNED[region].items())
        else:
            s = max(abs(v) for v in dz.values())
        cands.append((s, i, cD, cB, dz))
    cands.sort(key=lambda t: -t[0])
    k = 0 if top else len(cands) // 4      # hard: an upper-quartile donor, not the most extreme
    return cands[k]


def main(setname, seed):
    rng = np.random.default_rng(int(seed))
    drv.CASES.mkdir(exist_ok=True)
    drv.HIDDEN.mkdir(exist_ok=True)
    n = 0
    for diff, items in SETS.items():
        for it in items:
            regs = [it] if isinstance(it, tuple) else it
            kind = "prior" if n % 2 == 0 else "sampler"
            cA = draw_A(rng, kind)
            cB = cA.copy()
            info = []
            for reg, amt in regs:
                s, i, cD, cBn, dz = pick(cB, reg, amt, rng, top=(diff != "hard"))
                cB = cBn
                info.append({"region": reg, "amount": amt, "score": round(float(s), 2),
                             "macro_change": {k: round(float(v), 2) for k, v in dz.items()}})
            case = f"{setname}_{n:02d}"
            d = drv.CASES / case
            d.mkdir(exist_ok=True)
            (d / "case.json").write_text(json.dumps({"case": case, "difficulty": diff}))
            (d / "state.json").write_text(json.dumps({"c": cA.tolist(), "moves": [], "trial": None}))
            err = drv.zone_err(cA, cB)
            (drv.HIDDEN / f"{case}.json").write_text(json.dumps({
                "case": case, "difficulty": diff, "A_kind": kind, "A": cA.tolist(), "B": cB.tolist(), "changes": info,
                "start_err": {"face": err["face"], **{k: v for k, v in err.items() if k.startswith("R:")}},
                "dc_norm": float(np.linalg.norm(cB - cA))}, indent=1))
            print(case, diff, kind, [(x["region"], x["score"]) for x in info], f"|dB-A| {np.linalg.norm(cB - cA):.2f}",
                  f"face err {err['face']:.2f} mm", {r: round(err[f'R:{r}'], 2) for r, _ in regs})
            n += 1


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
