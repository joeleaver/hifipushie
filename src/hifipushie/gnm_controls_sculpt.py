"""Sculpt: a zone moved the GNM way (`zone_row`, `sculpt`), its key and its parser. Part of GNM's controls (gnm_controls.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import gnm_controls
from .gnm_controls import gnm, zones

# ---------------------------------------------------------------- sculpt: a zone moved the GNM way
def _macro_jac() -> np.ndarray:
    """d macros (in their population sd) / d head comp, (40, 170), central differences at the template (the macros are
    linear in the identity: humanmacro's R2 0.97-1.00)."""
    if "MJ" not in gnm_controls._C:
        from . import humanmacro as hm
        sd = hm.table()["sd"]
        g = gnm()
        w = lambda V: np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # noqa: E731
        J = np.zeros((len(hm.NAMES), 170))
        for k in range(170):
            d = g["IB"][k].astype(float)
            mp, mn = hm.measures(w(g["T"] + d)), hm.measures(w(g["T"] - d))
            J[:, k] = [(mp[n] - mn[n]) / 2 / sd[i] for i, n in enumerate(hm.NAMES)]
        gnm_controls._C["MJ"] = J
    return gnm_controls._C["MJ"]


def zone_row(zone: str, kind: str = "zone") -> np.ndarray:
    """(170,): a zone's mean NORMAL move (mm, + out of the face) per head comp; kind "relief": against its 5 mm
    surround (+ rises, - sinks: a groove deepens). Exact: GNM is linear."""
    Z = zones()
    n = gnm_controls._C["normals"]
    IB = gnm()["IB"][:170]
    idx = Z[zone]
    row = np.einsum("kvd,vd->k", IB[:, idx, :].astype(float), n[idx]) / len(idx) * gnm_controls.MM
    if kind == "relief":
        sur = gnm_controls._C["surround"][zone]
        if not len(sur):
            raise ValueError(f"relief: zone {zone} has no surround (pick a face zone)")
        row = row - np.einsum("kvd,vd->k", IB[:, sur, :].astype(float), n[sur]) / len(sur) * gnm_controls.MM
    return row


def sculpt(zone: str, kind: str = "zone", hold: str | list = "all", hold_zones: tuple = (), locality: float = 3.0,
           release: float = 0.7) -> dict:
    """The least-cost identity change (170 head comps, |dc| in population sd) that moves `zone` 1 mm (its mean normal;
    kind "relief": against its 5 mm surround), with the MACROS held (hold "all" = every humanmacro measure, or a list;
    a held macro too much like the target itself (|cos| > release in the comps' space) is let go and reported), other
    zones held at 0 (hold_zones), and a LOCALITY penalty: locality^2 x the mean squared move (mm) of the face's skin more
    than 6 mm from the zone. Linear, so amount x the returned "dc" is the move for any amount. This is how Garrett's
    narrow bridge was made without a designed local (gnmcontrols: walls 0.746 -> 0.584, designed local 0.670)."""
    from . import humanmacro as hm
    from scipy.spatial import cKDTree
    key = ("sculpt", zone, kind, json_key(hold), tuple(hold_zones), float(locality), float(release))
    if key in gnm_controls._C:
        return gnm_controls._C[key]
    g = gnm()
    Z = zones()
    t = zone_row(zone, kind)
    rows, rhs, names_ = [t], [1.0], [f"{kind}:{zone}"]
    for z in hold_zones:
        rows.append(zone_row(z, "zone"))
        rhs.append(0.0)
        names_.append(f"held zone {z}")
    MJ = _macro_jac()
    want = list(hm.NAMES) if hold == "all" else list(hold)
    released = []
    for m in want:
        r = MJ[hm.NAMES.index(m)]
        cos = abs(r @ t) / max(np.linalg.norm(r) * np.linalg.norm(t), 1e-12)
        if cos > release:
            released.append(f"{m} (cos {cos:.2f})")
            continue
        rows.append(r)
        rhs.append(0.0)
        names_.append(m)
    T = g["T"]
    face = Z["face"]
    near = cKDTree(T[Z[zone]]).query(T[face])[0] < 0.006
    out = face[~near]
    IBo = g["IB"][:170, out, :].reshape(170, -1).astype(float) * gnm_controls.MM
    H = np.eye(170) + (locality ** 2) * (IBo @ IBo.T) / len(out)
    C = np.array(rows)
    d = np.array(rhs)
    n, k = 170, len(d)
    K = np.zeros((n + k, n + k))
    K[:n, :n], K[:n, n:], K[n:, :n] = H, C.T, C
    sol = np.linalg.lstsq(K, np.r_[np.zeros(n), d], rcond=None)[0]
    dc = sol[:n]
    mv = MJ @ dc
    top = np.argsort(-np.abs(mv))[:5]
    res = {"dc": dc, "cost": float(np.linalg.norm(dc)), "achieved": float(t @ dc), "released": released,
           "held": names_[1:], "outside_mm": float(np.sqrt(((IBo.T @ dc) ** 2).reshape(-1, 3).sum(1).mean())),
           "macros": {hm.NAMES[j]: round(float(mv[j]), 3) for j in top}}
    gnm_controls._C[key] = res
    return res


def json_key(x):
    return x if isinstance(x, str) else tuple(x)


def parse_sculpt(name: str) -> dict:
    """"sculpt:<zone>[|hold=<zone>+<zone>][|free=<macro>+..][|loc=<w>]" or "relief:<zone>[...]" -> sculpt's kwargs."""
    kind, rest = name.split(":", 1)
    parts = rest.split("|")
    kw = {"zone": parts[0], "kind": "relief" if kind == "relief" else "zone"}
    if kw["zone"] not in gnm_controls.ZONES:
        raise ValueError(f"{kind}: no zone {kw['zone']!r}; zones: {', '.join(gnm_controls.ZONES)}")
    for p_ in parts[1:]:
        k, _, v = p_.partition("=")
        if k == "hold":
            kw["hold_zones"] = tuple(v.split("+"))
        elif k == "free":
            from . import humanmacro as hm
            kw["hold"] = [m for m in hm.NAMES if m not in v.split("+")]
        elif k == "loc":
            kw["locality"] = float(v)
        else:
            raise ValueError(f"{name}: unknown option {k!r} (hold=, free=, loc=)")
    return kw
