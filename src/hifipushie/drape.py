"""DRAPE BAND: wrapped folds drafted by draping, the pattern maker's method (Joe 2026-10-21, drape band round 1).

A band that wraps a body curve and folds over itself (a shirt collar's stand + fall, a jacket collar, a cuff turned
back, a waistband, a turtleneck, a hem on a curve) is NOT drafted flat and then folded on the form: twelve shirt
rounds and twenty-six jacket rounds failed that way (spring too short then too long, rigid turns, capes, wings, torn
corners). A pattern maker drapes it: describes the WORN shape, builds it on the stand (here: in 3D on the body and the
garment's own cloth under it), and takes the flat piece off it. The flat piece stays the source of truth: it is
generated FROM the worn spec (never the reverse), stored with the worn spec's key, and the pattern gate refuses a piece
whose worn spec has changed since (row drape_band_current).

Interface (garment key "drape": a list of bands; `draft` fills each entry's "out"):
  {"name": "shirt collar",
   "along": ["front.R:cfNeck>neck", "yoke:neck.m>cbNeck>neck", "front.L:neck>cfNeck"],  # the body curve: the garment
        # edges it is sewn to, CB in the middle (the band is draped on the +X half and mirrored: cut on the fold)
   "worn": "closed",             # the ONE worn state it is draped in: the DESIGN's state ("open" | "closed",
        # default closed; the older "state" key is read the same: drape_state); "target": the other state's sweep,
        # its reach reported as an INFO gate row (drape_band_reach), never a gate. Garrett's shirt is worn open
   "layers": [                   # the worn cross-section, inside out; every value {"cb": v, "end": v} or a number (m)
     {"piece": "stand", "kind": "stand", "height": 0.032, "ext": 0.009},      # up the neck from the seam; ext: past CF
     {"piece": "collar", "kind": "fall", "rise": 0.006, "land": {"cb": 0.008, "end": 0.012},
      "end_in": 0.012, "point": 0.0}],   # fall: sewn on the stand top, rises `rise`, turns over (turn of cloth, C43),
        # comes down outside the stand and LIES on the cloth under it to `land` below the neck seam (C125's landing
        # line: "on the layer below at X mm"); end_in: its sewn end short of the stand's CF; point: the tip's offset
        # along the curve from the sewn end (+ toward CF)
   "source": "why these numbers"}
  A cuff: one "fall" layer on a "stand" of height 0 (a turn-back) or a "stand" alone (a band cuff / waistband: height).
  Round 4 (C133, an OPEN collar): any value may be measured stations {"at": [[u, v], ...]} (u: 0 CB .. 1 end, linear
  between); stand "lean": {"at": [[u, "neck" | deg]]} (+ in / - out; "neck" = the neck solve), an open collar's stand
  lies back at CF; fall "land_dir": deg out of straight down (the fall's ends land out on the open fronts: walked over
  the body, lifted onto the cloth). The stand's top carries leftTopJoin / rightTopJoin where the fall's sewn ends
  join it; the stand|fall seam is sewn between them (joined_seams), not CF to CF.

`draft(entry, base)` builds the band ON what is under it: base = {"curve": (n, 3) CB -> end, "body": Surf (the neck /
wrist / waist skin), "under": Surf (the garment's own cloth, the fall lies on it), "s_cf": the curve's arc at CF}; the
turn of cloth (C43: the fall's mid-surface one stack out over the stand's, never closer than the form's THICK);
flattens each layer with an ARAP flattener (CB held straight: it is cut on the fold), reports its distortion (edge
strain p99 / max), trues the seams (the stand's neck edge vs the neckline, the collar's sewn edge vs the stand top) and
emits pattern pieces (outline, named points as the design table's piece had them, notches, the fall's roll line as a
fold). `reach(...)`: the same flat piece put on another worn state's sweep (a shirt collar open): its strain; above
REACH_LIMIT the state is out of the piece's reach (an open spread too deep) and is flagged.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree

STAND_MODE = "neck"  # round 2: the stand on the NECK (neck_stand). "skin": r1's (flares); "lean": r1 lever 2 (DEAD:


# ---------------------------------------------------------------- surfaces


# ---------------------------------------------------------------- the worn spec


def drape_state(entry: dict) -> str:
    """The worn state the band is draped in: the DESIGN's state (entry "worn": "open" | "closed"; the older "state"
    key read the same), default "closed". Garrett's shirt is worn open (the concept), so its collar is draped open and
    the closed state is the secondary reach check (drape band round 3, coordinator 2026-10-21)."""
    return str(entry.get("worn") or entry.get("state") or "closed")


MESH_FRAME = 2  # the drape mesh's flat coords = the piece's (flat_frame, round 3); frame-1 drapes are stale


def worn_key(entry: dict) -> str:
    """The worn spec's key: what the flat pieces were generated from (the gate compares it)."""
    k = {kk: entry.get(kk) for kk in ("along", "layers", "turn", "base")}
    k["state"] = drape_state(entry)
    k["stand_mode"] = entry.get("stand_mode") or STAND_MODE  # (round 2: the stand's build changed: r1 pieces are stale)
    k["mesh_frame"] = MESH_FRAME  # (round 3: a frame-1 stand placed mirrored: its drape mesh is stale)
    return hashlib.sha1(json.dumps(k, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- building the band


# ---------------------------------------------------------------- flattening


# ---------------------------------------------------------------- pieces


# ---------------------------------------------------------------- what it is draped on


# ---------------------------------------------------------------- the drape as the form's placement
def place_on_drape(uv: np.ndarray, dm: dict) -> np.ndarray:
    """Mesh vertices of a draped piece (pattern coords uv) -> their worn positions (barycentric in the drape's flat
    triangulation; a vertex outside it takes its nearest triangle's extension)."""
    Uf, Xf, Ff = (np.asarray(dm[k], float) for k in ("uv", "X", "F"))
    Ff = Ff.astype(int)
    A, B, C = (Uf[Ff[:, i]] for i in range(3))
    tree = cKDTree((A + B + C) / 3)
    _, idx = tree.query(uv, k=min(12, len(Ff)))
    idx = idx.reshape(len(uv), -1)
    a, b_, c = A[idx], B[idx], C[idx]
    v0, v1, v2 = b_ - a, c - a, uv[:, None, :] - a
    d00 = np.sum(v0 * v0, -1)
    d01 = np.sum(v0 * v1, -1)
    d11 = np.sum(v1 * v1, -1)
    d20 = np.sum(v2 * v0, -1)
    d21 = np.sum(v2 * v1, -1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-20, 1e-20, d00 * d11 - d01 * d01)
    w1 = (d11 * d20 - d01 * d21) / den
    w2 = (d00 * d21 - d01 * d20) / den
    w0 = 1 - w1 - w2
    out_ = -np.minimum(np.minimum(w0, w1), w2)  # how far outside (0 = inside)
    j = np.argmin(out_, 1)
    r = np.arange(len(uv))
    t = idx[r, j]
    W = np.c_[w0[r, j], w1[r, j], w2[r, j]]
    return np.einsum("ni,nij->nj", W, Xf[Ff[t]])


def load_mesh(path: str) -> dict:
    z = np.load(path)
    out = {}
    for k in z.files:
        nm, kk = k.split("__", 1)
        out.setdefault(nm, {})[kk] = z[k]
    return out


def stored_pieces(entry: dict) -> dict:
    """A drape entry's emitted pieces (entry["out"]: written by `record`) as pattern pieces + their drape meshes."""
    o = entry.get("out") or {}
    mesh = load_mesh(o["file"]) if o.get("file") else {}
    pcs = {}
    for nm, d in (o.get("pieces") or {}).items():
        pc = {"name": nm, "P": np.asarray(d["P"], float), "names": {k: int(v) for k, v in d["names"].items()},
              "marks": {k: np.asarray(v, float) for k, v in (d.get("marks") or {}).items()}, "lines": {},
              "grain": float(d.get("grain", 90.0)), "draped": True}
        if nm in mesh:
            pc["drape"] = mesh[nm]
        pcs[nm] = pc
    return pcs


def gate_rows(g: dict) -> list:
    """Pattern gate rows: each drape entry's pieces must have been generated from its CURRENT worn spec
    (drape_band_current), and the flattening's distortion within the limit (drape_band_flat)."""
    rows = []
    for e in g.get("drape") or []:
        o = e.get("out") or {}
        cur = worn_key(e)
        ok = bool(o) and o.get("key") == cur
        rows.append({"id": f"drape_band_current:{e.get('name', '')}", "stage": 2, "status": "PASS" if ok else "FAIL",
                     "measure": "drape.worn_key", "ours": {"stored": o.get("key"), "worn_spec": cur},
                     "why": "the flat pieces are generated FROM the worn spec (Joe 2026-10-21); a changed worn spec "
                            "needs drape.draft again"})
        lay = (o.get("report") or {}).get("layers") or {}
        if lay:
            worst = max(v["strain_p99_pct"] for v in lay.values())
            rows.append({"id": f"drape_band_flat:{e.get('name', '')}", "stage": 2,
                         "status": "PASS" if worst <= FLAT_P99_LIMIT * 100 else "FAIL", "measure": "drape.flatten",
                         "ours": {nm: v["strain_p99_pct"] for nm, v in lay.items()},
                         "target": f"edge strain p99 <= {FLAT_P99_LIMIT * 100:.1f} %"})
        rc = o.get("reach") or {}
        if rc:  # (the other state's reach: reported, not a gate; the design's own state is the one draped)
            rows.append({"id": f"drape_band_reach:{e.get('name', '')}", "stage": 2, "status": "INFO",
                         "measure": "drape.reach",
                         "ours": {"draped": drape_state(e), "other": rc.get("state"), "ok": rc.get("ok"),
                                  "p99_pct": {nm: v.get("strain_p99_pct") for nm, v in (rc.get("layers") or {}).items()}},
                         "target": f"info only: the secondary state within {rc.get('limit_pct')} % p99"})
    return rows


FLAT_P99_LIMIT = 0.02  # a draped band that can't be flattened within this isn't a pattern piece (needs a dart / seam)


def replace_pieces(out: dict, g: dict) -> tuple[dict, list]:
    """cloth.pieces: the design's pieces a drape entry generated replaced by them (the table's wrap / role kept);
    -> (out, the entries' folds, which replace the table's of the same piece)."""
    folds = []
    for e in g.get("drape") or []:
        if not e.get("out"):
            continue
        for nm, pc in stored_pieces(e).items():
            old = out.get(nm) or {}
            if old.get("wrap") is not None:
                pc["wrap"] = old["wrap"]
            if old.get("role"):
                pc["role"] = old["role"]
            out[nm] = pc
        folds += [dict(f) for f in e["out"].get("folds") or []]
    return out, folds


def joined_seams(seams: list, g: dict, pieces: dict) -> list:
    """The seams a drape entry's layers sew, measured between the notches that actually join (round 4): a fall whose
    sewn ends stop `end_in` short of its stand's CF is sewn to the stand top between the stand's TopJoin notches,
    not CF to CF (the design table's stand|collar seam ran the stand top to CF: -4.7 % ease on Garrett d3o was the
    2 x 12 mm the collar never covers, not a drafting fault). A seam side "<stand>:leftTopCf>...>rightTopCf" paired
    with the fall's sewn edge becomes "<stand>:leftTopJoin>...>rightTopJoin" when the stand piece has those names."""
    out = []
    for e in g.get("drape") or []:
        st = next((L["piece"] for L in e.get("layers") or [] if L.get("kind") == "stand"), None)
        fa = [L["piece"] for L in e.get("layers") or [] if L.get("kind") == "fall"]
        nm = (pieces.get(st) or {}).get("names") or {}
        if st and fa and "leftTopJoin" in nm and "rightTopJoin" in nm:
            out.append((st, set(fa)))
    if not out:
        return seams
    res = []
    for s in seams:
        s = list(s)
        for st, fa in out:
            for i in (0, 1):
                a, b = s[i], s[1 - i]
                if isinstance(a, str) and isinstance(b, str) and a.startswith(st + ":") and b.split(":")[0] in fa:
                    s[i] = a.replace("leftTopCf", "leftTopJoin").replace("rightTopCf", "rightTopJoin")
        res.append(s)
    return res


def draped_start(B: dict, M: dict) -> dict | None:
    """The placement given by the drape (cloth.place): {"pieces", "U", "X"} for the draped pieces' vertices, or None."""
    pcs = B.get("pieces") or {}
    names = list(M["names"])
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    hit, X = [], None
    for k, nm in enumerate(names):
        dm = (pcs.get(nm) or {}).get("drape")
        if dm is None:
            continue
        sel = pid == k
        if X is None:
            X = np.full((len(uv), 3), np.nan)
        X[sel] = place_on_drape(uv[sel], dm)
        hit.append(nm)
    return {"pieces": hit, "X": X} if hit else None

