"""hsrd_vary.py: what the poses of one subject VARY on the head, from the set itself: the head's turn in the rig
(degrees between the head's forward and the rig's horizontal reference of the subject's first pose) and its nod, the
expression the direct fit needed (norm of the expression components; the largest), how many dl3 labels a front photo
shows (occluders: hats, phones, hands), the identity's repeatability between poses of one person (errmap face rms and
jaw / nose widths between the fits: the same person scanned twice should give the same identity)."""
import json
import sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import hsrdset as H

idx = H.index()
by = {}
for p, d in idx["poses"].items():
    by.setdefault(d["subject"], []).append(p)
try:
    import errmap
except Exception:
    errmap = None
print("| subject | pose (the dataset's words; head accessory) | head turn / nod in the rig, deg | expression norm (largest) | good dl3 labels in the best front photo | fit face mean mm | identity vs the first pose: errmap face mm, jaw / nose-base width mm |")
print("|---|---|---|---|---|---|---|")
for s, ps in sorted(by.items()):
    c0 = None
    for p in sorted(ps, key=lambda p: (not p in ("HSR0040-Body-023", "HSR0112-Body-018"), p)):
        P = H.Pose(p)
        d = idx["poses"][p]
        hd = P.cams["head"]
        f, u = np.asarray(hd["forward"]), np.asarray(hd["up"])
        turn = np.degrees(np.arctan2(f[0], f[1]))
        nod = np.degrees(np.arcsin(np.clip(-f[2], -1, 1)))
        fit = P.fit()
        e = np.asarray(fit["identity_expression"]["e"])
        en = fit["identity_expression"]["enames"]
        fr = P.photos(az=(-30, 30))
        best = max((int(P.good(c).sum()) for c in fr), default=0)
        c = np.asarray(fit["identity"]["c"])
        rep = "-"
        if c0 is None:
            c0, m0 = c, fit["identity"]["measures"]
        elif errmap is not None:
            r = errmap.rms(c, c0)
            m = fit["identity"]["measures"]
            rep = f"{r['face']:.2f}, {m['jaw_width'] - m0['jaw_width']:+.1f} / {m['nose_width'] - m0['nose_width']:+.1f}"
        print(f"| {s} | {p}: {d['pose_type']}, {d['activity']}; {d['head_accessory'] or 'None'} | {turn:+.0f} / {nod:+.0f} | {np.linalg.norm(e):.2f} ({en[int(np.abs(e).argmax())]} {e[int(np.abs(e).argmax())]:+.2f}) | {best} | {d['fit_face_mean_mm']:.2f} | {rep} |")
