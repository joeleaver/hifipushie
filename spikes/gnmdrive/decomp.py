"""decomp.py <set>...: WHY drivers fail. Counterfactual replays of each case's own trials (never shown to a driver):
  driven   as the driver left it
  judge    the same trials in order, a move kept only if the face error (rms mm, score.face_basis) falls: a perfect
           keep / reject call, on kept AND rejected trials
  dose     the driver's kept directions, amounts refit (least squares on the face error, ridge 0.02 on the prior cost)
  dose_all the same over every direction tried (kept + rejected)
If `judge` passes where `driven` fails, the miss is JUDGING (the eye kept a bad move / dropped a good one); if `dose`
passes, DOSING; if not even dose_all passes, NAMING / MAPPING (the right control was never tried).
-> out/decomp_<set>.json and a table."""
import json
import sys

import numpy as np

import drv
import score as sc
from hifipushie import blockin as bi

VARS = ("driven", "judge", "dose", "dose_all")


def variants(cA, cB, st):
    F = sc.face_basis()
    err = lambda c: float(np.linalg.norm(F @ (cB - c)))
    trials = [dict(m, kept=True) for m in st["moves"]] + [dict(m, kept=False) for m in st.get("rejected", [])]
    trials.sort(key=lambda m: m.get("time", ""))
    out = {"driven": np.array(st["c"], float)}
    c = cA.copy()
    stats = {"kept_bad": 0, "kept": len(st["moves"]), "rej_good": 0, "rej": len(st.get("rejected", []))}
    cur = cA.copy()      # the driver's own path, to grade each of its calls where it was made
    for m in trials:
        d = sum(float(v) * bi.direction(k) for k, v in m["moves"].items())
        good = err(cur + d) < err(cur)
        if m["kept"]:
            stats["kept_bad"] += not good
            cur = cur + d
        else:
            stats["rej_good"] += good
        if err(c + d) < err(c):
            c = c + d
    out["judge"] = c

    def refit(keys):
        keys = list(dict.fromkeys(keys))
        if not keys:
            return cA.copy(), {}
        D = np.array([bi.direction(k) for k in keys]).T
        FD = F @ D
        a = np.linalg.solve(FD.T @ FD + 0.02 * D.T @ D, FD.T @ (F @ (cB - cA)))
        return cA + D @ a, dict(zip(keys, np.round(a, 2).tolist()))
    out["dose"], amt = refit([k for m in st["moves"] for k in m["moves"]])
    out["dose_all"], amt_all = refit([k for m in trials for k in m["moves"]])
    drv_amt = {}
    for m in st["moves"]:
        for k, v in m["moves"].items():
            drv_amt[k] = round(drv_amt.get(k, 0.0) + float(v), 2)
    return out, stats, {"driver": drv_amt, "refit": amt, "refit_all": amt_all}


def grade(cA, cB, cs, regs):
    F = sc.face_basis()
    e0 = drv.zone_err(cA, cB)
    f0 = np.linalg.norm(F @ (cB - cA))
    ids = sc.idist([cA] + cs, cB)
    res = []
    for c, i1 in zip(cs, ids[1:]):
        e1 = drv.zone_err(c, cB)
        f1 = np.linalg.norm(F @ (cB - c))
        rc = float(np.mean([1 - e1[f"R:{r}"] / e0[f"R:{r}"] for r in regs]))
        idc = 1 - i1 / ids[0]
        res.append({"region": round(rc, 3), "id": round(idc, 3), "face": round(float(1 - f1 / f0), 3),
                    "pass": bool(rc >= 0.4 and idc >= 0.25 and f1 <= 1.1 * f0)})
    return res


if __name__ == "__main__":
    for s in sys.argv[1:]:
        rows = {}
        for i in range(14):
            case = f"{s}_{i:02d}"
            if not (drv.CASES / case / "state.json").exists():
                continue
            h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
            st = json.loads((drv.CASES / case / "state.json").read_text())
            cA, cB = np.array(h["A"]), np.array(h["B"])
            regs = [x["region"] for x in h["changes"]]
            V, stats, amts = variants(cA, cB, st)
            g = grade(cA, cB, [V[k] for k in VARS], regs)
            rows[case] = {"difficulty": h["difficulty"], "regions": regs, "stats": stats, "amounts": amts,
                          **{k: x for k, x in zip(VARS, g)}}
            print(case, h["difficulty"][:4], "+".join(regs).ljust(18),
                  " | ".join(f"{k} {x['region']:.2f}/{x['id']:.2f}{'*' if x['pass'] else ' '}" for k, x in zip(VARS, g)),
                  f"| kept bad {stats['kept_bad']}/{stats['kept']}, rejected good {stats['rej_good']}/{stats['rej']}", flush=True)
        (drv.G / "out" / f"decomp_{s}.json").write_text(json.dumps(rows, indent=1))
        n = len(rows)
        print(f"== {s}: " + ", ".join(f"{k} {sum(r[k]['pass'] for r in rows.values())}/{n}" for k in VARS)
              + f" | kept moves that made the face WORSE {sum(r['stats']['kept_bad'] for r in rows.values())}/"
                f"{sum(r['stats']['kept'] for r in rows.values())}, rejected moves that were GOOD "
                f"{sum(r['stats']['rej_good'] for r in rows.values())}/{sum(r['stats']['rej'] for r in rows.values())}")
