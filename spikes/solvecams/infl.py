"""infl.py <model> [start=<class-mean start>] [freeze=all] [dense=1]: WHERE the "nothing forced" sigma inflation comes
from: one block_in_solve's compare() (3 Gauss-Newton rounds, today's defaults), and at every round's capped solve:
the factor, and the factor with each read type / view left out (the same reads, replayed)."""
import sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, store
import common as C

name = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
fr.DENSE = kw.get("dense", "0") == "1"
sd6 = {k: (1e-4,) * 6 for k in fr.PHOTO_CAM_SD6} if kw.get("freeze") == "all" else {kk: tuple(x / 3 for x in v) for kk, v in fr.PHOTO_CAM_SD6.items()}
rj = C.refs(name)
c0 = bi.identity(store.load(name))
start = kw.get("start")
off = c0 - bi.identity(store.load(start)) if start else None
solve0 = fr.solve
log = []


def spy(obs, head, **k):
    out = solve0(obs, head, **k)
    if k.get("cmax"):
        log.append((obs, head, dict(k), out))
    return out


fr.solve = spy
b0 = rj.get("blockin") or {}
fr.compare(name, rounds=3, prior_off=off, cam_sd=sd6, lids=True, lips=True, parse="auto", adapt=True, cmax=3.0,
           cam_done0=np.zeros((len(rj["views"]), 6)), kinds=b0.get("kinds"), readers=b0.get("readers"))
fr.solve = solve0
print(f"== {name}: {len(log)} capped solves (a round may solve twice: + the size / neck rows)")
for i, (obs, head, k, out) in enumerate(log):
    c_at = np.asarray(head["c"], float)
    done = k.get("done")
    raw = solve0(obs, head, **{**k, "cmax": None})
    cc = c_at + raw["dc"]
    types = sorted({ob["type"] for ob in obs} - {"hold"})
    res = {t: float(np.sqrt(np.mean([(ob["o"] / ob["sig"]) ** 2 for ob in obs if ob["type"] == t]))) for t in types}
    print(f"-- solve {i}: {len(obs)} reads; the head stands |c| {np.linalg.norm(c_at):.2f} max {np.abs(c_at).max():.2f}; step so far |done| {0.0 if done is None else np.linalg.norm(done):.2f}; "
          f"uncapped step |dc| {np.linalg.norm(raw['dc']):.2f} -> max {np.abs(cc).max():.2f} sd (component {int(np.abs(cc).argmax())}, {int((np.abs(cc) > 3).sum())} past 3); FACTOR x{out['relax']:.2f}, capped |dc| {np.linalg.norm(out['dc']):.2f}")
    print("   residual rms in sigmas: " + " ".join(f"{t} {v:.1f}" for t, v in res.items()))
    if out["relax"] > 1.05:
        for t in types:
            o_ = [ob for ob in obs if ob["type"] != t]
            print(f"   without {t:9s}: x{solve0(o_, head, **k)['relax']:.2f}")
        for kd in sorted({ob['view'] for ob in obs if ob['type'] != 'hold'}):
            o_ = [ob for ob in obs if ob["view"] != kd]
            print(f"   without view {kd:8s}: x{solve0(o_, head, **k)['relax']:.2f}")
        for hb in (1.5, 1.0):
            print(f"   huber at {hb} sigma (today 2.5): x{solve0(obs, head, **{**k, 'huber': hb})['relax']:.2f}")
