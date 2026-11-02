"""groundtruth: shared pieces. Real head scans (the Lee Perry-Smith head, HSRD-100 subjects) against GNM.

Data lives OUTSIDE the repo under $HIFIPUSHIE_GROUNDTRUTH (default /mnt/data/hifipushie/groundtruth): lps/ (the head
scan), hsrd100/x/<pose>/ (scan, photos + RealityCapture .xmp), work/ (decimated / cropped working copies, fits),
out/ (tables, sheets). Nothing of the datasets goes into git. Notes: docs/notes/groundtruth.md.

Frames: everything is compared in "GNM world" (face_ruler._world of GNM's frame: Z up, the face looks along -Y, the
head's left is +X; metres). A scan is carried there by a similarity S = (s, R, t): x_gnm = s R x_scan + t.

surface distance (Surface.closest, two_sided): exact point-to-triangle distances, both directions; tested on
synthetic cases in tests/test_groundtruth.py."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("HIFIPUSHIE_GROUNDTRUTH", "/mnt/data/hifipushie/groundtruth"))
WORK, OUT = ROOT / "work", ROOT / "out"


# ---- meshes -----------------------------------------------------------------------------------------------------------

def read_obj(path) -> dict:
    """Our own OBJ reader (downloaded files are data: nothing of theirs is run). -> {"V" (n, 3), "C" (n, 3) vertex
    colours 0..1 or None, "UV" (m, 2) or None, "F" (k, 3) triangles (polygons fanned), "FUV" (k, 3) or None,
    "poly": the original polygons (lists of vertex ids) when the file is not all triangles}."""
    v, vt, fl = [], [], []
    with open(path, "rb") as fh:
        for ln in fh:
            if ln.startswith(b"v "):
                v.append(ln[2:])
            elif ln.startswith(b"vt "):
                vt.append(ln[3:])
            elif ln.startswith(b"f "):
                fl.append(ln[2:])
    A = np.array([x.split() for x in v], dtype=np.float64)
    V, C = A[:, :3], (A[:, 3:6] if A.shape[1] >= 6 else None)
    UV = np.array([x.split()[:2] for x in vt], dtype=np.float64) if vt else None
    polys, puv = [], []
    for ln in fl:
        it = [t.split(b"/") for t in ln.split()]
        polys.append([int(t[0]) - 1 for t in it])
        if UV is not None and len(it[0]) > 1 and it[0][1]:
            puv.append([int(t[1]) - 1 for t in it])
    F, FUV = [], []
    for i, p in enumerate(polys):
        for k in range(1, len(p) - 1):
            F.append((p[0], p[k], p[k + 1]))
            if puv:
                q = puv[i]
                FUV.append((q[0], q[k], q[k + 1]))
    tri = all(len(p) == 3 for p in polys)
    return {"V": V, "C": C, "UV": UV, "F": np.asarray(F, np.int64), "FUV": np.asarray(FUV, np.int64) if FUV else None,
            "poly": None if tri else polys, "polyuv": None if tri or not puv else puv}


def face_normals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def submesh(V, F, keep):
    """The faces whose three vertices are kept, re-indexed: (V', F', old index of each new vertex)."""
    keep = np.asarray(keep, bool)
    f = F[keep[F].all(1)]
    used = np.zeros(len(V), bool)
    used[f.ravel()] = True
    idx = np.flatnonzero(used)
    new = np.full(len(V), -1)
    new[idx] = np.arange(len(idx))
    return V[idx], new[f], idx


def largest_component(V, F):
    """Keep the largest connected piece (scan floaters off)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    e = np.r_[F[:, [0, 1]], F[:, [1, 2]]]
    n, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(V), len(V))), directed=False)
    big = np.argmax(np.bincount(lab))
    return lab == big


def _closest_tri(p, a, b, c):
    """Closest point of triangles (a, b, c) to points p (all (..., 3)): barycentric (u, v, w) (Ericson, Real-Time
    Collision Detection 5.1.5, vectorised)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp = p - b
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    cp = p - c
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-30, 1e-30, den)
    v, w = vb / den, vc / den
    with np.errstate(divide="ignore", invalid="ignore"):
        m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
        t = (d4 - d3) / np.where(m, (d4 - d3) + (d5 - d6), 1.0)
        v, w = np.where(m, 1 - t, v), np.where(m, t, w)
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        t = d2 / np.where(m, d2 - d6, 1.0)
        v, w = np.where(m, 0.0, v), np.where(m, t, w)
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        t = d1 / np.where(m, d1 - d3, 1.0)
        v, w = np.where(m, t, v), np.where(m, 0.0, w)
    m = (d6 >= 0) & (d5 <= d6)
    v, w = np.where(m, 0.0, v), np.where(m, 1.0, w)
    m = (d3 >= 0) & (d4 <= d3)
    v, w = np.where(m, 1.0, v), np.where(m, 0.0, w)
    m = (d1 <= 0) & (d2 <= 0)
    v, w = np.where(m, 0.0, v), np.where(m, 0.0, w)
    v, w = np.nan_to_num(v), np.nan_to_num(w)
    return np.stack([1 - v - w, v, w], -1)


class Surface:
    """A triangle mesh for closest-point queries. Candidates: the faces round the k nearest vertices AND the faces
    whose centroid is among the k nearest centroids (long triangles); the exact closest point on each is taken."""

    def __init__(self, V, F, valence: int = 12):
        from scipy.spatial import cKDTree
        self.V, self.F = np.asarray(V, float), np.asarray(F, np.int64)
        self.tree = cKDTree(self.V)
        self.ctree = cKDTree(self.V[self.F].mean(1))
        vf = np.full((len(self.V), valence), -1, np.int64)
        cnt = np.zeros(len(self.V), np.int64)
        for c in range(3):
            for fi, vi in enumerate(self.F[:, c]):
                if cnt[vi] < valence:
                    vf[vi, cnt[vi]] = fi
                    cnt[vi] += 1
        self.vf = vf
        self.fn = face_normals(self.V, self.F)

    def closest(self, P, k: int = 4, chunk: int = 20000):
        """-> (Q closest points (n, 3), d distances (n,), face ids (n,), barycentric (n, 3))."""
        P = np.asarray(P, float)
        Q, D, FI, BW = np.zeros_like(P), np.zeros(len(P)), np.zeros(len(P), np.int64), np.zeros((len(P), 3))
        k = min(k, len(self.V))
        kc = min(2 * k, len(self.F))
        for s in range(0, len(P), chunk):
            p = P[s:s + chunk]
            _, nn = self.tree.query(p, k=k)
            _, nc = self.ctree.query(p, k=kc)
            cand = np.concatenate([self.vf[nn.reshape(len(p), -1)].reshape(len(p), -1), nc.reshape(len(p), -1)], 1)
            ok = cand >= 0
            cs = np.where(ok, cand, 0)
            T = self.V[self.F[cs]]                               # (n, m, 3, 3)
            bw = _closest_tri(p[:, None, :], T[:, :, 0], T[:, :, 1], T[:, :, 2])
            q = (bw[..., None] * T).sum(2)
            d = np.linalg.norm(q - p[:, None, :], axis=-1)
            d[~ok] = np.inf
            j = d.argmin(1)
            r = np.arange(len(p))
            Q[s:s + chunk], D[s:s + chunk], FI[s:s + chunk], BW[s:s + chunk] = q[r, j], d[r, j], cs[r, j], bw[r, j]
        return Q, D, FI, BW


def two_sided(Va, Fa, Vb, Fb, sa=None, sb=None) -> dict:
    """Surface distance both ways between meshes a and b: a's vertices (or sample points sa) to b's surface and b's
    (sb) to a's. -> {"a2b", "b2a": distances, "mean", "p90": over both sets together}."""
    A, B = Surface(Va, Fa), Surface(Vb, Fb)
    d1 = B.closest(Va if sa is None else sa)[1]
    d2 = A.closest(Vb if sb is None else sb)[1]
    d = np.r_[d1, d2]
    return {"a2b": d1, "b2a": d2, "mean": float(d.mean()), "p90": float(np.percentile(d, 90))}


# ---- similarity -------------------------------------------------------------------------------------------------------

def umeyama(A, B, scale=True):
    """The similarity (s, R, t) with s R a + t ~ b (least squares)."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    a0, b0 = A.mean(0), B.mean(0)
    U, S, Vt = np.linalg.svd((B - b0).T @ (A - a0))
    D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / ((A - a0) ** 2).sum()) if scale else 1.0
    return s, R, b0 - s * R @ a0


def apply(S, X):
    s, R, t = S
    return s * np.asarray(X, float) @ np.asarray(R).T + np.asarray(t)


def compose(S2, S1):
    """apply(compose(S2, S1), x) = apply(S2, apply(S1, x))."""
    s1, R1, t1 = S1
    s2, R2, t2 = S2
    return s1 * s2, np.asarray(R2) @ np.asarray(R1), s2 * np.asarray(R2) @ np.asarray(t1) + np.asarray(t2)


def inverse(S):
    s, R, t = S
    R = np.asarray(R)
    return 1.0 / s, R.T, -(R.T @ np.asarray(t)) / s


def rotvec(r):
    from scipy.spatial.transform import Rotation
    return Rotation.from_rotvec(np.asarray(r, float)).as_matrix()


def save_sim(path, S, **extra):
    Path(path).write_text(json.dumps({"s": float(S[0]), "R": np.asarray(S[1]).tolist(), "t": np.asarray(S[2]).tolist(), **extra}))


def load_sim(path):
    j = json.loads(Path(path).read_text())
    return j["s"], np.asarray(j["R"]), np.asarray(j["t"])


# ---- GNM --------------------------------------------------------------------------------------------------------------

_C: dict = {}
EXPR_COMPS = {"lower_face_region": 20, "left_eye_region": 6, "right_eye_region": 6}      # blockin's nuisance set
EXPR_SD = {"lower_face_region": 0.8, "left_eye_region": 0.5, "right_eye_region": 0.5}


def gnm() -> dict:
    """GNM in GNM world: T (V, 3), B (170, V, 3) identity, E (ne, V, 3) expression (EXPR_COMPS) + its prior sd,
    F = the exterior skin's triangles, gr = vertex groups, regions = report regions (vertex masks), fit = the vertices
    a direct fit may use (exterior skin of face / jaw / skull / ears; no eyeballs, mouth bag, neck below the jaw)."""
    if "g" in _C:
        return _C["g"]
    from hifipushie import base as basemod, face_ruler as fr, gnm_mm
    sp = gnm_mm._space()
    g = basemod._gnm_data()
    gr = sp["gr"]
    W = fr._world
    T = W(sp["T"])
    B = W(sp["IB"]).astype(np.float64)
    en = [str(n) for n in g["expression_names"]]
    ei, esd = [], []
    for reg, n in EXPR_COMPS.items():
        ids = [i for i, nm in enumerate(en) if nm.rsplit("_", 1)[0] == reg][:n]
        ei += ids
        esd += [EXPR_SD[reg]] * len(ids)
    E = W(np.asarray(g["expression_basis"])[ei].astype(np.float64))
    # + two whole-expression directions the local sets cannot make with 6 components an eye: the lids CLOSED
    # (the sampler's wink prototypes: a scan taken with the eyes shut, like the Lee Perry-Smith head)
    E = np.concatenate([E, W(fr._expr_fields(("wink_left", "wink_right")).astype(np.float64))])
    esd += [1.0, 1.0]
    Q = np.asarray(g["quads"], int)
    ext = gr["skin_exterior"] & ~gr["mouth_sock"] & ~gr["eyes"]
    q = Q[ext[Q].all(1)]
    F = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)
    L = sp["WL"] @ T
    S = sp["sets"]

    def setmask(ids):
        m = np.zeros(len(T), bool)
        m[np.asarray(ids, int)] = True
        return m
    z_chin, z_lip = L[8, 2], L[57, 2]
    face = gr["hockey_mask"] & ext
    low = face & (T[:, 2] < z_lip)
    R = {
        "forehead": gr["forehead_region"],
        "brow": gr["left_brow_region"] | gr["right_brow_region"] | gr["middle_brow_region"],
        "eye sockets": gr["left_orbital_region"] | gr["right_orbital_region"] | gr["eye_sockets"],
        "nose": gr["nose_region"],
        "cheeks": gr["left_cheek_region"] | gr["right_cheek_region"] | gr["left_zygomatic_region"] | gr["right_zygomatic_region"]
                  | gr["left_infraorbital_region"] | gr["right_infraorbital_region"],
        "lips": gr["upper_lip_region"] | gr["lower_lip_region"] | gr["upper_lip"] | gr["lower_lip"],
        "chin": gr["chin_region"],
        "jaw line": (gr["left_parotid_region"] | gr["right_parotid_region"]
                     | (low & (np.abs(T[:, 0]) >= 0.022) & ~gr["chin_region"])),
        "under-chin": setmask(S["under_chin"]),
        "temples": gr["left_temple_region"] | gr["right_temple_region"],
        "ears": gr["ears"],
        "scalp": setmask(S["cranium"]) & ~gr["forehead_region"],
    }
    R = {k: v & ext for k, v in R.items()}
    # earlier names win where groups overlap (a vertex is reported once)
    seen = np.zeros(len(T), bool)
    for k in ("lips", "nose", "eye sockets", "brow", "chin", "ears", "under-chin", "forehead", "cheeks", "jaw line", "temples", "scalp"):
        R[k] = R[k] & ~seen
        seen |= R[k]
    R["face"] = face
    fit = seen | face
    neck = setmask(S["neck"]) & ~seen
    _C["g"] = {"T": T, "B": B, "E": E, "esd": np.asarray(esd), "F": F, "gr": gr, "regions": R, "fit": fit, "ext": ext,
               "neck": neck, "L": L, "WL": sp["WL"], "sets": S, "enames": [en[i] for i in ei] + ["proto:wink_left", "proto:wink_right"]}
    return _C["g"]


REGIONS = ("forehead", "brow", "eye sockets", "nose", "cheeks", "lips", "chin", "jaw line", "under-chin", "ears", "temples", "scalp", "face")


def verts(c, e=None):
    G = gnm()
    V = G["T"] + np.tensordot(np.asarray(c, float), G["B"], 1)
    if e is not None:
        V = V + np.tensordot(np.asarray(e, float), G["E"], 1)
    return V


def class_mean(sex: str):
    from hifipushie import blockin as bi
    D = bi.data()
    return np.asarray(D["m_m"] if sex == "male" else D["m_f"], float)


# ---- the scan as a head: load a working copy --------------------------------------------------------------------------

def load_scan(tag: str) -> dict:
    """A prepared head scan (prep.py): work/<tag>/head.npz {V, F (, C vertex colour 0..1)} in the scan's own frame and
    units, + info.json {"unit_m": metres per unit when the scan has real scale, else null, "sex", ...}."""
    d = WORK / tag
    z = np.load(d / "head.npz")
    out = {k: z[k] for k in z.files}
    out["info"] = json.loads((d / "info.json").read_text())
    out["tag"] = tag
    return out


# ---- the surface comparison of a GNM head and a scan ------------------------------------------------------------------

def outward_sign(V, F) -> float:
    """+1 when the mesh's winding gives outward normals, -1 when inward (a closed-ish head: normals against the
    direction from the centroid)."""
    fn = face_normals(V, F)
    return float(np.sign(np.median(((V[F].mean(1) - V.mean(0)) * fn).sum(1))) or 1.0)


def gaps(Vg, scan_gnm: Surface, skin=None, reach: float = 0.02, samples=None, sample_skin=None, sample_normals=None) -> dict:
    """GNM vertices Vg (GNM world, m) against a scan surface carried into GNM world. Two-sided, where the scan has
    skin. -> {"g2s": per GNM vertex unsigned distance (nan: not compared), "signed": + = the scan lies OUTSIDE GNM,
    "s_d", "s_reg_face": per scan sample distance to GNM and the GNM face it lands on, "table": region -> mean / p90
    (mm; both directions pooled, each direction's mean too)}.
    skin: per scan FACE bool (False = hair / cloth: a GNM vertex landing there is not compared)."""
    G = gnm()
    F = G["F"]
    Q, d, fi, _ = scan_gnm.closest(Vg)
    vn = vertex_normals(Vg, F)
    signed = ((Q - Vg) * vn).sum(1)
    sgn = outward_sign(scan_gnm.V, scan_gnm.F)
    ok = G["fit"] & (d < reach) & ((sgn * scan_gnm.fn[fi] * vn).sum(1) > 0.2)
    if skin is not None:
        ok &= np.asarray(skin, bool)[fi]
    g2s = np.where(ok, d, np.nan)
    out = {"g2s": g2s, "signed": np.where(ok, signed, np.nan)}
    reg_of_vert = np.full(len(Vg), -1)
    for i, k in enumerate(REGIONS[:-1]):
        reg_of_vert[G["regions"][k]] = i
    if samples is not None:
        Sg = Surface(Vg, F)
        Qs, ds, fs, bw = Sg.closest(samples)
        v = F[fs][np.arange(len(fs)), bw.argmax(1)]
        oks = G["fit"][v] & (ds < reach)
        if sample_normals is not None:      # the scan's INSIDE surfaces (a mouth bag, nostrils, an ear canal) face the other way
            oks &= (np.asarray(sample_normals) * Sg.fn[fs]).sum(1) > 0.2
        bnd = boundary_vertices(F, len(Vg))
        oks &= ~((bw * bnd[F[fs]]).sum(1) > 0.999)      # on an opening's edge (lid aperture, mouth, the neck's cut)
        if sample_skin is not None:
            oks &= np.asarray(sample_skin, bool)
        out.update(s_d=np.where(oks, ds, np.nan), s_vert=v)
    tab = {}
    for i, k in enumerate(REGIONS):
        m = G["regions"][k]
        a = g2s[m]
        a = a[np.isfinite(a)] * 1000
        b = np.zeros(0)
        if samples is not None:
            mm = m[out["s_vert"]]
            b = out["s_d"][mm]
            b = b[np.isfinite(b)] * 1000
        both = np.r_[a, b]
        if len(both) < 10:
            tab[k] = None
            continue
        tab[k] = {"mean": float(both.mean()), "p90": float(np.percentile(both, 90)), "g2s": float(a.mean()) if len(a) else None,
                  "s2g": float(b.mean()) if len(b) else None, "n": int(len(both)), "covered": float(np.isfinite(g2s[m]).mean()),
                  "signed": float(np.nanmean(out["signed"][m]) * 1000)}
    out["table"] = tab
    return out


def table_text(tab: dict, title: str = "") -> str:
    rows = [f"{title}", "| region | mean mm | p90 mm | GNM->scan | scan->GNM | signed (+ = scan outside) | GNM verts compared |", "|---|---|---|---|---|---|---|"]
    for k in REGIONS:
        t = tab.get(k)
        if t is None:
            rows.append(f"| {k} | - | - | - | - | - | none |")
        else:
            rows.append(f"| {k} | {t['mean']:.2f} | {t['p90']:.2f} | {t['g2s']:.2f} | " + (f"{t['s2g']:.2f}" if t["s2g"] is not None else "-")
                        + f" | {t['signed']:+.2f} | {100 * t['covered']:.0f} % |")
    return "\n".join(rows)


# ---- where the scan has skin ------------------------------------------------------------------------------------------

def scan_skin(scan: dict, S, radius: float = 0.004) -> np.ndarray:
    """Per scan VERTEX: True where the surface is skin (not hair, not cloth). A scan with vertex colours: a colour model
    of its own skin, taken from the middle of the face (the points that land on GNM's cheeks, nose and forehead under
    the similarity S), chroma within 3.5 sd and not much darker, then a vertex counts when most of its 4 mm
    neighbourhood does (the hairline's fuzz off). Inside the central face (brows, eyes, lips, the beard area's
    stubble) colour is not asked: brows and stubble are under a millimetre thick. A scan without colours (the Lee
    Perry-Smith head: shaved) is skin everywhere."""
    V = scan["V"]
    if scan.get("C") is None:
        return np.ones(len(V), bool)
    from scipy.spatial import cKDTree
    G = gnm()
    Vs = apply(S, V)
    Vg = verts(class_mean(scan["info"]["sex"]))
    tr = cKDTree(Vg[G["ext"]])
    d, i = tr.query(Vs)
    gi = np.flatnonzero(G["ext"])[i]
    R = G["regions"]
    C = np.clip(scan["C"].astype(float), 1e-3, 1)
    lum = C.mean(1)
    ch = np.stack([np.log(C[:, 0] / C[:, 1]), np.log(C[:, 1] / C[:, 2])], 1)
    ref = (R["cheeks"] | R["nose"])[gi] & (d < 0.012)
    mu, cov = ch[ref].mean(0), np.cov(ch[ref].T) + 1e-5 * np.eye(2)
    dm = np.sqrt(np.einsum("ni,ij,nj->n", ch - mu, np.linalg.inv(cov), ch - mu))
    sat = ch.sum(1)                                   # log(R / B): grey or dark hair is less saturated than skin
    col = (dm < 3.5) & (lum > 0.45 * np.median(lum[ref])) & (sat > sat[ref].mean() - 2.0 * sat[ref].std())
    ts = cKDTree(Vs)
    nb = ts.query_ball_point(Vs, radius, return_length=False, workers=4)
    vn = vertex_normals(Vs, scan["F"])
    frac = np.array([col[j].mean() for j in nb])
    # hair is ROUGH in a photogrammetry scan: the normals' spread over the 4 mm neighbourhood (skin: under ~0.03)
    rough = np.array([1.0 - np.linalg.norm(vn[j].mean(0)) for j in nb])
    ear = R["ears"][gi] & (d < 0.012)                 # an ear is rough by nature: colour alone there
    skin = (frac > 0.8) & ((rough < 0.06) | ear)
    nb2 = ts.query_ball_point(Vs, 2 * radius, return_length=False, workers=4)
    skin = np.array([skin[j].mean() for j in nb2]) > 0.7        # islands in the hair off, pinholes in the skin closed
    # the central face: colour not asked (brows, lashes, stubble, lips, nostril shadows)
    central = (R["brow"] | R["eye sockets"] | R["nose"] | R["lips"] | R["chin"] | R["cheeks"])[gi] & (d < 0.015)
    return skin | central


def boundary_vertices(F, n) -> np.ndarray:
    e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    u, c = np.unique(e, axis=0, return_counts=True)
    b = np.zeros(n, bool)
    b[u[c == 1].ravel()] = True
    return b


def voxel_sample(P, cell: float) -> np.ndarray:
    """Indices of one point per occupied cell (an even sampling of a dense scan)."""
    q = np.floor(np.asarray(P) / cell).astype(np.int64)
    _, idx = np.unique(q, axis=0, return_index=True)
    return np.sort(idx)
