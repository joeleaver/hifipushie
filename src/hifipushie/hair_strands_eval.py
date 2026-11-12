"""Evaluated strands: evaluate and its cache, strands of a model, the tile job and lines, the cap chart. Part of the hair strands (hair_strands.py has the overview)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import hair_strands
from . import hair_cards as hc
from .hair_strands import _ss, physical
from .hair_strands_job import key

# ------------------------------------------------------------------------------------------------ evaluated strands
def evaluate(sd: dict, out: str | None = None, abc: str | None = None, usd: str | None = None) -> str:
    """Build a strands job in an empty Blender scene and dump every evaluated strand to `out` (npz: pts, counts,
    lock, sub, rand, radius, obj, names) and / or write the groom as Alembic / USD. Seconds; returns Blender's
    "@@" lines."""
    from .scene import _blender
    r = _blender({"mode": "hair_strands_eval", "strands": sd, "out": out, "abc": abc, "usd": usd}, timeout=1800)
    return "\n".join(ln for ln in r.splitlines() if ln.startswith("@@"))


def _cache() -> Path:
    from . import store
    d = store.HOME / "_cache" / "hair_strands"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _code() -> str:
    from . import moved
    here = Path(__file__).parent  # (hair_strands with every module it was split into: moved.files)
    return hashlib.sha1(b"".join((here / f).read_bytes() for f in moved.files("hair_strands", "blender_strands"))).hexdigest()[:12]


def strands_of_model(sd: dict) -> dict:
    """The model's evaluated strands (cached on disk by the job's content + this code)."""
    f = _cache() / f"groom_{key(sd)}_{_code()}.npz"
    if not f.exists():
        evaluate(sd, out=str(f))
        old = sorted(_cache().glob("groom_*.npz"), key=lambda p: p.stat().st_mtime)[:-hair_strands.GROOM_KEEP]
        for p in old:  # (each is 10-40 MB)
            p.unlink(missing_ok=True)
    else:
        f.touch()
    return dict(np.load(f, allow_pickle=False))


def tile_job(S: dict, tmp: Path, seed: int = 11) -> dict:
    """The atlas's clump variants as a strands job: one flat straight guide lock a tile (dense .. sparse, fly-away,
    baby, hairline), its strands made by the same lens group and deformers as the head's, with the groom's numbers."""
    n = 24
    kinds = [(i, k, w) for i, (k, w) in enumerate(hc.TILES) if k in hair_strands.TILE_KIND]
    ph = physical(S, free=True)
    P, Sd, O, N, K, RS, TS, FD, LK = ([] for _ in range(9))
    for i, kind, w in kinds:
        cnt, clumps, ts, start, ln = hair_strands.TILE_KIND[kind]
        width = hair_strands.TILE_LEN * w / 1024.0
        y = -np.linspace(0, hair_strands.TILE_LEN * ln, n)
        P.append(np.stack([np.full(n, i * 0.2), y, np.zeros(n)], 1))
        Sd.append(np.tile([(0.3 if kind in ("fly", "baby") else 0.46) * width, 0.0, 0.0], (n, 1)))
        O.append(np.tile([0.0, 0.0, 0.002], (n, 1)))
        N.append(max(1, int(round(cnt * w / 160 / 8.0))))
        K.append(clumps)
        RS.append(start)
        TS.append(ts)
        FD.append(0.3 * width)
        LK.append(i)
    np.savez(tmp / "hair_tiles.npz", counts=np.full(len(kinds), n, np.int32), pts=np.concatenate(P).astype(np.float32),
             side=np.concatenate(Sd).astype(np.float32), out=np.concatenate(O).astype(np.float32),
             n=np.asarray(N, np.int32), k=np.asarray(K, np.int32), rs=np.asarray(RS, np.float32),
             ts=np.asarray(TS, np.float32), fd=np.asarray(FD, np.float32), lock=np.asarray(LK, np.int32),
             ws=np.ones(len(kinds), np.float32), wl=np.ones(len(kinds), np.float32),
             names=np.asarray([k for _, k, _ in kinds]))
    tips = 0.25 + 0.75 * float(np.clip(S["tips"], 0, 1))
    st = [[hair_strands.LENS, {"Amount": 8.0, "Tips": tips, "Roots": 1.0, "Flyaway": 0.0, "Flyaway Distance": 1.0, "Edge": 1.0,
                  "Clump": ph["clump"], "Clump Shape": ph["clump_shape"], "Tip Spread": ph["tip_spread01"],
                  "Wave": float(min(0.12 * ph["wave"], 0.0012)), "Wavelength": ph["wavelength"], "Curl": 0.0,
                  "Loose": ph["wander"], "Wave Random": 0.15, "Stray": ph["stray"],
                  "Seed": int(seed)}]]
    if ph["loose"] > 0:
        st.append(["Hair Curves Noise", {"Cumulative Offset": False, "Factor": 1.0, "Distance": 0.5 * ph["loose"],
                                         "Shape": 0.5, "Scale": ph["loose_scale"], "Scale along Curve": 0.35,
                                         "Offset per Curve": 0.15, "Seed": int(seed), "Preserve Length": True}])
    if ph["frizz"] > 0:
        st.append(["Frizz Hair Curves", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["frizz"],
                                         "Shape": 0.5, "Seed": int(seed), "Preserve Length": True}])
    return {"groups": [{"name": "hair_tiles", "guides": str(tmp / "hair_tiles.npz"), "stack": st}], "look": {}}


def tile_lines(S: dict) -> dict:
    """{tile index: [(x across 0..1, v along 0..1, depth 0..1, id 0..1), ...]}: the strands of each atlas tile,
    evaluated by Blender from `tile_job` (cached by the strand numbers that shape them)."""
    import tempfile
    kk = hashlib.sha1(json.dumps([{k: S[k] for k in ("clump", "clump_shape", "tip_spread", "frizz", "loose", "tips",
                                                     "wave", "wavelength", "curl", "random", "stray")}, hair_strands.TILE_KIND, hc.TILES, hair_strands.TILE_LEN],
                                 sort_keys=True, default=float).encode()).hexdigest()[:16]
    f = _cache() / f"tiles_{kk}_{_code()}.npz"
    if not f.exists():
        with tempfile.TemporaryDirectory(prefix="hifipushie-tiles-") as tmp:
            evaluate(tile_job(S, Path(tmp)), out=str(f))
    z = np.load(f, allow_pickle=False)
    first = np.r_[0, np.cumsum(z["counts"])]
    out: dict = {}
    for j in range(len(z["counts"])):
        i = int(z["lock"][j])
        w = hc.TILES[i][1]
        width = hair_strands.TILE_LEN * w / 1024.0
        q = z["pts"][first[j]:first[j + 1]]
        if len(q) < 2:
            continue
        out.setdefault(i, []).append(((q[:, 0] - i * 0.2) / width + 0.5, -q[:, 1] / hair_strands.TILE_LEN,
                                      float(np.clip(0.5 + q[:, 2].mean() / 0.006, 0, 1)), float(z["rand"][j])))
    return out


def cap_chart(sc, g: dict, line, S: dict, D: dict | None, e0: float, size: int = 1024, short: bool = False) -> dict:
    """The scalp's hair as a picture on the scalp chart (u = azimuth / 360, v = elevation over e0..90, row 0 = the
    top): every strand that runs close over the scalp drawn where it lies, over an opaque base that starts `soft` m
    inside the hairline. So the hairline is an alpha edge of single hairs, and no skin shows under the cards: the
    game hair's cap texture. {"alpha", "id", "depth"} (size, size)."""
    from PIL import Image, ImageDraw
    from .hair_groom import _part, inside
    W = H = int(size)
    ss = 2
    ims = [Image.new("L", (W * ss, H * ss), 0) for _ in range(2)]
    da, di = (ImageDraw.Draw(i) for i in ims)
    if D is not None and len(D["counts"]):
        first = np.r_[0, np.cumsum(D["counts"])]
        az, el, hh = sc.coords(D["pts"])
        names = [str(n) for n in D["names"]]
        free = names.index("hair_guides_free") if "hair_guides_free" in names else -1
        for j in range(len(D["counts"])):
            if D["obj"][j] == free and not short:  # (short=True: a short cut's own hair lies ON the head: the
                continue  # cap carries it, every strand drawn where it lies, 1 texel wide)
            sl = slice(first[j], first[j + 1])
            a, e, h_ = az[sl], el[sl], hh[sl]
            # (round the pole the chart stretches a strand into an arc; a short cut is drawn up to it all the same:
            # left out, the crown was a plain dark disc on the cap)
            ok = (h_ < (0.035 if short else 0.012)) & (e < (88.5 if short else 78.0))
            if ok.sum() < 2:
                continue
            a = np.unwrap(np.radians(a)) * 180 / np.pi
            for shift in (0.0, -360.0, 360.0):  # (a strand across the seam is drawn on both edges)
                u = (a + shift) / 360.0 * W * ss
                if u.max() < 0 or u.min() > W * ss:
                    continue
                v = (1 - (e - e0) / (90.0 - e0)) * H * ss
                pts = [(float(x), float(y)) for x, y, k_ in zip(u, v, ok) if k_]
                wd = 1 if short else 2
                da.line(pts, fill=255, width=wd)
                di.line(pts, fill=int(1 + 254 * float(D["rand"][j])), width=wd)
    a_, idm = (np.asarray(i.resize((W, H), Image.BOX), np.float32) / 255 for i in ims)
    idm = np.clip(idm / np.maximum(a_, 1e-3), 0, 1)
    AA, EE = np.meshgrid((np.arange(W) + 0.5) / W * 360.0, 90.0 - (np.arange(H) + 0.5) / H * (90.0 - e0), indexing="xy")
    d_in = inside(sc, line, AA, EE)
    soft = max(float(S["soft"]), 0.001)
    rng = np.random.default_rng(5)
    streak = np.repeat(rng.uniform(0, 1, (1, W)), H, 0).astype(np.float32)
    base = _ss((d_in - hair_strands.CAP_BASE_IN * soft) / soft)
    pw = float(g["parting"].get("width", 0.012))
    base = base * (1 - hair_strands.CAP_PART_CUT * np.clip(_part(sc, g, AA, EE, 0.25 * pw), 0, 1))
    if short:  # the crown is hair whatever the parting's mask says there (a bald disc at the pole of a crop)
        base = np.where((EE > 72.0) & (d_in > 0.02), 1.0, base)
    a_ = np.where(d_in > -0.004, a_, 0.0)
    from scipy import ndimage
    idm = np.where(a_ > 0.05, idm, 0.5 + 0.3 * (ndimage.gaussian_filter1d(streak, 2.0, axis=1, mode="wrap") - 0.5))
    # as deep as a dense card's strands, a little deeper between the drawn strands: the cap reads as the same hair
    dep = np.clip(0.45 + 0.35 * a_, 0, 1)
    return {"alpha": np.maximum(a_, base).astype(np.float32), "id": idm.astype(np.float32),
            "depth": dep.astype(np.float32)}
