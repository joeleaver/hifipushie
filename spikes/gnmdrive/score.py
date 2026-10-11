"""score.py oracle|score <case>...|all <set>: the driving test's scorer (NEVER shown to a driver).
oracle: the least-cost block-in moves reaching B from A (greedy orthogonal matching pursuit over the vocabulary,
        measured as face-skin vertex error, refit amounts each step) -> hidden/<case>_oracle.json
score:  start / driver's result vs B: face + per-region rms (mm), face-ID distance (SFace / ArcFace, 1 - cos, mean of
        front and 3/4 renders), moves taken; the driver's moves against the oracle's."""
import json
import sys

import numpy as np

import drv
import gnmc
from hifipushie import blockin as bi, faceid, gnm_controls as gcm, humanmacro as hm

SKIP_ZONES = {"face", "ears", "cranium", "neck", "iris", "pupil", "sclera", "teeth_upper", "teeth_lower", "tongue"}
_D = {}


def dictionary():
    if "D" in _D:
        return _D["names"], _D["D"]
    names = []
    for m in hm.NAMES:
        names += [m, m + "!"]
    names += ["nd:" + n for n in bi.gap_names()]
    from hifipushie import base as basemod
    regs = sorted(k for k in basemod._gnm_data()["groups"] if k.endswith("_region"))
    # (left_ / right_ region PCs move ONE side: a symmetric difference can't use them; the oracle leaves them out)
    names += [f"pc:{r}{k}" for r in regs if not r.startswith(("left_", "right_")) for k in range(8)]
    for z in gcm.ZONES:
        if z in SKIP_ZONES:
            continue
        names += [f"sculpt:{z}", f"relief:{z}"]
    cols, ok = [], []
    for n in names:
        try:
            cols.append(bi.direction(n))
            ok.append(n)
        except Exception as e:  # noqa: BLE001
            print("skip", n, e)
    _D["names"], _D["D"] = ok, np.array(cols).T     # (170, K)
    return _D["names"], _D["D"]


def face_basis():
    if "F" not in _D:
        Z = gcm.zones()
        idx = np.unique(np.r_[Z["face"], Z["neck"][::3], Z["cranium"][::3]])
        _D["F"] = drv.IBH[:, idx, :].reshape(170, -1).T * drv.MM / np.sqrt(len(idx))   # rms mm per comp
    return _D["F"]


def oracle(cA, cB, kmax=10, stop=0.02, ridge=0.02, named=False):
    """greedy: each step the move that closes the most face error PER UNIT PRIOR COST (|dc| of its unit), amounts
    refit (a small ridge on the prior cost) over the chosen moves."""
    names, D = dictionary()
    F = face_basis()
    FD = F @ D
    nrm = np.linalg.norm(D, axis=0)
    r = F @ (cB - cA)
    e0 = np.linalg.norm(r)
    sel, amt, hist = [], None, []
    res = r.copy()
    for _ in range(kmax):
        score = np.abs(FD.T @ res) / np.maximum(nrm, 1e-9)
        score[sel] = -1
        if named:
            score[[i for i, n in enumerate(names) if n.startswith("pc:")]] = -1
        j = int(np.argmax(score))
        trial = sel + [j]
        Dt = D[:, trial]
        a = np.linalg.solve(FD[:, trial].T @ FD[:, trial] + ridge * Dt.T @ Dt, FD[:, trial].T @ r)
        res_t = r - FD[:, trial] @ a
        if hist and (hist[-1][1] - np.linalg.norm(res_t)) / e0 < stop:
            break
        sel, amt, res = trial, a, res_t
        hist.append((names[j], float(np.linalg.norm(res))))
    moves = {names[j]: round(float(a), 3) for j, a in zip(sel, amt)}
    return {"moves": moves, "order": [h[0] for h in hist], "err_after": [round(h[1], 3) for h in hist],
            "err0": round(float(e0), 3), "dc": float(np.linalg.norm(D[:, sel] @ amt)) if sel else 0.0}


def idist(cs, cB):
    ims = []
    for c in list(cs) + [cB]:
        ims += [drv.render(c, 0.0, px=320, half=0.12), drv.render(c, -30.0, px=320, half=0.12)]
    E = faceid.embed(ims)
    eB = E[-2:]
    out = []
    for i in range(len(cs)):
        e = E[2 * i: 2 * i + 2]
        v = [1 - faceid.cosine(a[m], b[m]) for a, b in zip(e, eB) if a is not None and b is not None for m in faceid.MODELS]
        out.append(float(np.mean(v)) if v else None)
    return out


def score(case):
    h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
    st = json.loads((drv.CASES / case / "state.json").read_text())
    cA, cB, c = np.array(h["A"]), np.array(h["B"]), np.array(st["c"])
    regs = [x["region"] for x in h["changes"]]
    e0, e1 = drv.zone_err(cA, cB), drv.zone_err(c, cB)
    F = face_basis()
    f0, f1 = np.linalg.norm(F @ (cB - cA)), np.linalg.norm(F @ (cB - c))
    orc = json.loads((drv.HIDDEN / f"{case}_oracle.json").read_text()) if (drv.HIDDEN / f"{case}_oracle.json").exists() else None
    cO = cA.copy()
    for k, v in (orc or {"moves": {}})["moves"].items():
        cO = cO + v * bi.direction(k)
    id0, id1, idO = idist([cA, c, cO], cB)
    fO = np.linalg.norm(F @ (cB - cO))
    eO = drv.zone_err(cO, cB)
    names, D = dictionary()
    # each kept move: how much of the residual (face metric) it closed
    cur = cA.copy()
    steps = []
    for m in st["moves"]:
        nxt = cur.copy()
        for k, v in m["moves"].items():
            nxt = nxt + float(v) * bi.direction(k)
        steps.append({"moves": m["moves"], "seen": m.get("seen", ""), "closed": round(float(np.linalg.norm(F @ (cB - cur)) - np.linalg.norm(F @ (cB - nxt))), 3)})
        cur = nxt
    res = {"case": case, "difficulty": h["difficulty"], "regions": regs, "n_moves": len(st["moves"]),
           "n_rejected": len(st.get("rejected", [])),
           "face_err": [round(float(f0), 3), round(float(f1), 3)], "closed": round(float(1 - f1 / f0), 3),
           "region_err": {r: [round(e0[f"R:{r}"], 2), round(e1[f"R:{r}"], 2)] for r in regs},
           "region_closed": {r: round(1 - e1[f"R:{r}"] / e0[f"R:{r}"], 3) for r in regs},
           "id": [None if id0 is None else round(id0, 4), None if id1 is None else round(id1, 4)],
           "steps": steps, "oracle": orc,
           "oracle_score": {"face_err": round(float(fO), 3), "closed": round(float(1 - fO / f0), 3),
                            "region_closed": {r: round(1 - eO[f"R:{r}"] / e0[f"R:{r}"], 3) for r in regs},
                            "id": None if idO is None else round(idO, 4)}}
    res["id_closed"] = None if (id0 is None or id1 is None) else round(1 - id1 / id0, 3)
    res["region_closed_mean"] = round(float(np.mean(list(res["region_closed"].values()))), 3)
    # PASS: the changed regions closed >= 40 % on average, the face-ID distance closed >= 25 %, the whole face's error
    # no more than 10 % worse than the start (a region won at the face's expense is not a pass)
    res["pass"] = bool(res["region_closed_mean"] >= 0.4 and res["id_closed"] is not None and res["id_closed"] >= 0.25
                       and f1 <= 1.1 * f0)
    return res


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "oracle":
        for case in sys.argv[2:]:
            h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
            o = oracle(np.array(h["A"]), np.array(h["B"]))
            o["named"] = oracle(np.array(h["A"]), np.array(h["B"]), named=True)
            (drv.HIDDEN / f"{case}_oracle.json").write_text(json.dumps(o, indent=1))
            print(case, h["difficulty"], [x["region"] for x in h["changes"]], "err", o["err0"], "->", o["err_after"][-1] if o["err_after"] else None,
                  json.dumps(o["moves"]))
            print("   named:", o["named"]["err_after"][-1] if o["named"]["err_after"] else None, json.dumps(o["named"]["moves"]))
    elif cmd == "score":
        out = []
        for case in sys.argv[2:]:
            r = score(case)
            out.append(r)
            print(json.dumps({k: v for k, v in r.items() if k not in ("oracle", "steps")}))
        p0 = drv.G / "out" / "scores.json"
        sc = json.loads(p0.read_text()) if p0.exists() else {}
        for r in out:
            sc[f"{r['case']}:state"] = r
        p0.write_text(json.dumps(sc))
        p = drv.G / "out" / f"score_{sys.argv[2].split('_')[0]}_{len(out)}.json"
        p.write_text(json.dumps(out, indent=1))
        print(p)
