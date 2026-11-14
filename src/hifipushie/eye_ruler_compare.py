"""Comparing picture and model: `mean`, `compare`, `text`, the overlay, the crease path. Part of the eye ruler (eye_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import eye_ruler
from .eye_ruler import patch
from .eye_ruler_model import model
from .eye_ruler_picture import read

def mean(eyes: list) -> dict:
    """Both eyes' mean of every measure (NaN-aware); "inner" / "outer" as (u, v)."""
    import warnings
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for k in eye_ruler.SCALARS + ("crease_dark",):
            out[k] = float(np.nanmean([e.get(k, np.nan) for e in eyes]))
        for k in eye_ruler.VECTORS + ("inner", "outer", "inner_lm", "platform"):
            if all(k in e for e in eyes):
                out[k] = np.nanmean([np.asarray(e[k], float) for e in eyes], 0).tolist()
    return out


def compare(name: str, model_name: str | None = None) -> dict:
    """The front picture of `name` read by the ruler against the model's mesh (model_name: another model through the
    same picture and camera; default name itself): {"rows": [{"measure", "photo", "model", "diff" (model - photo),
    "tol" (2 x the reader's rms error), "off" (|diff| > tol), "note"}], "photo", "model" (the two means), "pd": (photo,
    model) pupils apart, "moves": [text], "text"}. mm at the model; u = toward the outer corner, v = up, from each
    eye's iris centre; both eyes' mean."""
    from PIL import Image
    from . import humanfit, store
    from . import likeness_render
    from . import blockin_clay, blockin_models
    rj = blockin_models._refs(name)
    vi = blockin_clay._front(rj)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    P = blockin_clay.detect_view(img, v)
    if P is None:
        raise ValueError("eye_ruler: the detector found no face on the front picture")
    spec = store.load(model_name or name)
    st = humanfit.state(spec["base"])
    mm = likeness_render._mm_per_px(cam, st["L"][27:48])
    eyes = read(img, P, mm, debug=True)
    px = float(np.mean([e["iris"] for e in eyes])) / mm
    tru = model(spec, cam)
    ph, mo = mean(eyes), mean(tru)
    pd = (float(np.linalg.norm(np.subtract(eyes[0]["c"], eyes[1]["c"])) * mm),
          float(np.linalg.norm(np.subtract(tru[0]["c"], tru[1]["c"])) * mm))
    rows = []

    def row(measure, a, b, tol, note=""):
        d = b - a
        rows.append({"measure": measure, "photo": float(a), "model": float(b), "diff": float(d), "tol": float(tol),
                     "off": bool(np.isfinite(d) and abs(d) > tol), "note": note})
    from . import base_implied
    native = base_implied.eye_native(spec) is not None and not ((spec.get("skin") or {}).get("eyes") or {}).get("iris_size")
    row("iris diameter", ph["iris"], mo["iris"], 2 * eye_ruler.ERR["iris"],
        'block_in_step {"iris_mm": mm}: GNM\'s limbus for the identity (eyes_000); the eyeball stays GNM\'s' if native else
        "skin.eyes.iris_size (the drawn iris; the eyeball stays as it is)")
    row("pupils apart", pd[0], pd[1], 0.5, 'block_in_step {"mm:pupils_apart": mm}')
    row("inner canthus u", ph["inner"][0], mo["inner_lm"][0], 2 * eye_ruler.ERR["inner"], "model = GNM's inner-corner landmark (the caruncle's tip)")
    row("outer canthus u", ph["outer"][0], mo["outer"][0], 2 * eye_ruler.ERR["outer"], "where the visible eyeball ends")
    row("fissure length", ph["fissure"], float(np.hypot(mo["outer"][0] - mo["inner_lm"][0], mo["outer"][1] - mo["inner_lm"][1])), 2 * eye_ruler.ERR["fissure"])
    row("canthal tilt (deg)", ph["tilt"], float(np.degrees(np.arctan2(mo["outer"][1] - mo["inner_lm"][1], mo["outer"][0] - mo["inner_lm"][0]))),
        2 * eye_ruler.ERR["tilt"], "coarse: +-1.8 deg")
    for j, x in enumerate(eye_ruler.COLS):
        if abs(x) <= 6:
            row(f"upper margin v at u {x:+.0f}", ph["up"][j], mo["up"][j], 2 * eye_ruler.ERR["up"])
    for j, x in enumerate(eye_ruler.COLS):
        if abs(x) <= 6:
            row(f"lower margin v at u {x:+.0f}", ph["lo"][j] - eye_ruler.LO_BIAS, mo["lo"][j], 2 * eye_ruler.ERR["lo"], "picture read - 0.35 (waterline)")
    row("opening at the pupil", ph["mrd1"] + ph["mrd2"] + eye_ruler.LO_BIAS, mo["mrd1"] + mo["mrd2"], 2 * eye_ruler.ERR["open"])
    row("iris hidden by the upper lid", ph["cover_up"], mo["cover_up"], 2 * eye_ruler.ERR["mrd1"])
    row("upper lid's peak u", ph["peak_u"], mo["peak_u"], 2 * eye_ruler.ERR["peak_u"])
    row("caruncle showing", ph["caruncle"], float(mo["sclera_in"] - mo["inner_lm"][0]), 2 * eye_ruler.ERR["caruncle"],
        "model: IF the pocket is painted (skin.eyes.caruncle); unpainted it reads as skin and the eye ends at the eyeball")
    line = ph["crease_dark"] >= eye_ruler.CREASE_MIN
    for j, x in enumerate(eye_ruler.COLS):
        if abs(x) <= 6 and x % 6 == 0:
            row(f"fold line over the margin at u {x:+.0f}", ph["crease"][j] if line else float("nan"), mo["crease"][j], 2 * eye_ruler.ERR["crease"],
                "picture's line vs the mesh's crease (+-1 mm; a render's fold is not read)")
            row(f"lid platform shown at u {x:+.0f}", ph["crease"][j] if line else float("nan"), mo["platform"][j], 2 * eye_ruler.ERR["crease"])
    for j, x in enumerate(eye_ruler.COLS):
        if abs(x) <= 6 and x % 6 == 0:
            row(f"brow hair's lower edge over the margin at u {x:+.0f}", ph["brow"][j], mo["brow"][j], 2 * eye_ruler.ERR["brow"], "brow_read(match=True)")
    off = {r["measure"] for r in rows if r["off"]}
    moves = []
    if any(k.startswith(("upper margin", "lower margin", "inner canthus", "outer canthus", "opening", "iris hidden", "fissure")) for k in off):
        moves.append("lid_read(name, match=True): the eye step solves the identity for these margins and corners in mm, then "
                     "the lid as one structure (set the ORBIT first: face_ruler's orbit rows)")
    if "iris diameter" in off:
        if native:
            moves.append(f'block_in_step {{"iris_mm": {ph["iris"]:.2f}}} (GNM\'s limbus component, identity eyes_000: the iris, the pupil '
                         "and the cornea's base with it; the eyeball itself is GNM's 14.6 mm sphere x the head's scale, which its lids are shaped on)")
        elif base_implied.eye_native(spec) is None and ((spec.get("base") or {}).get("head") or {}).get("eye_radius"):
            moves.append(f"skin.eyes.iris_size {ph['iris'] / 1000:.4f} (the drawn iris). This head still OVERRIDES GNM's eyeball "
                         "(base.head.eye_radius: a smaller ball its lids stand off); a rebuild drops the key (block_in_start does)")
        else:
            moves.append(f"skin.eyes.iris_size {ph['iris'] / 1000:.4f} (the drawn iris, overriding GNM's limbus; unset it and step iris_mm instead)")
    if "pupils apart" in off:
        moves.append(f'block_in_step {{"mm:pupils_apart": {pd[0] - pd[1]:+.1f}}}')
    if "caruncle showing" in off or not ((spec.get("skin") or {}).get("eyes") or {}).get("caruncle"):
        moves.append("skin.eyes.caruncle 1 (the inner corner's pocket painted wet red: unpainted, the eye reads ~2 mm short at the nose side)")
    # (the picture's fold LINE is not drawn: Joe, 2026-10-11: the skin-over-skin overhang is left alone, no painted fold
    # line / crease make-up; the eye step puts the lid's TURN on the line's path, that is all. The crease option stays
    # in the skin code as an unused option; crease_path() still gives the path.)
    if any(k.startswith("brow") for k in off):
        moves.append("brow_read(name, match=True)")
    out = {"rows": rows, "photo": ph, "model": mo, "pd": pd, "moves": moves, "iris_px": px, "mm": mm, "eyes": eyes, "mesh": tru,
           "image": img}
    out["text"] = text(out)
    return out


def text(c: dict) -> str:
    """compare()'s table."""
    L = ["EYE RULER: the front picture (edges, through its fitted camera) vs the model's mesh; mm at the model, each eye's "
         "frame from its iris centre (u toward the outer corner, v up), both eyes' mean. diff = model - picture; "
         "* = more than the reader's error (2 x rms on dressed renders of known heads)",
         f"  {'measure':46s} {'picture':>8s} {'model':>8s} {'diff':>7s} {'tol':>5s}"]
    for r in c["rows"]:
        f = lambda x: f"{x:8.2f}" if np.isfinite(x) else "       -"  # noqa: E731
        L.append(f"{'*' if r['off'] else ' '} {r['measure']:46s} {f(r['photo'])} {f(r['model'])} {f(r['diff'])[1:]} {r['tol']:5.1f}"
                 + (f"  ({r['note']})" if r["note"] and (r["off"] or "coarse" in r["note"] or "IF" in r["note"]) else ""))
    if c["iris_px"] < 30:
        L.append(f"  NOTE: the picture's iris is {c['iris_px']:.0f} px across ({c['mm']:.2f} mm / px): every read is +- a pixel or worse; "
                 "use a closer picture of the eyes")
    if c["photo"]["crease_dark"] < eye_ruler.CREASE_MIN:
        L.append(f"  the picture shows no fold line (darkness {c['photo']['crease_dark']:.2f}): hooded, or too soft to read")
    L.append("  MOVES: " + ("; ".join(c["moves"]) if c["moves"] else "none: within the reader's error"))
    return "\n".join(L)


def overlay(img, eyes: list, mesh: list | None = None, mm: float | None = None, top: float = 16.0, bottom: float = -8.0,
            zoom: int = 1):
    """A picture's two eye patches (0.05 mm / px, subject's right eye first; both shown with the nose side on the left)
    with the ruler's read drawn: the lid rims' outer sides (orange), the margins (green), the limbus circle (yellow),
    canthi (red, with their vertical lines), where the eyeball starts (white tick), the fold line (cyan), the brow
    edge (magenta). mesh (model()'s list, mm = mm per picture px): the model's margin ring, its visible margins at
    COLS and its inner-corner landmark (blue), laid over by iris centre. eyes must come from read(debug=True)."""
    from PIL import Image, ImageDraw
    A = np.asarray(img.convert("RGB"), float) / 255
    tiles = []
    for s in (0, 1):
        e = eyes[s]
        fr = {k: np.asarray(v) for k, v in e["frame"].items() if k != "k"}
        pat = patch(A, fr, e["frame"]["k"])[::-1]
        Vr = eye_ruler.V[::-1]
        sel = (Vr < top) & (Vr > bottom)
        v_top = Vr[sel][0]
        t = Image.fromarray((pat[sel] * 255).astype(np.uint8))
        d = ImageDraw.Draw(t)
        X = lambda u: (u - eye_ruler.U[0]) / eye_ruler.STEP  # noqa: E731
        Y = lambda v: (v_top - v) / eye_ruler.STEP  # noqa: E731
        g = e.get("_dbg")
        if g:
            a, b = g["a"], g["b"]
            for arr in (g["T"], g["B"]):
                d.line([(X(u), Y(v)) for u, v in zip(g["uu"], arr)], fill=(255, 200, 0), width=1)
            for arr in (g["up"], g["lo"]):
                d.line([(X(u), Y(v)) for u, v in zip(g["uu"][a:b + 1], arr[a:b + 1]) if np.isfinite(v)], fill=(0, 255, 0), width=2)
            if g["cr"] is not None:
                d.line([(X(u), Y(v)) for u, v in zip(*g["cr"])], fill=(0, 255, 255), width=1)
            for (u, v) in g["br"] or []:
                d.ellipse([X(u) - 4, Y(v) - 4, X(u) + 4, Y(v) + 4], outline=(255, 0, 255))
        for key in ("inner", "outer"):
            u, v = e[key]
            d.line([(X(u), 0), (X(u), t.size[1])], fill=(255, 0, 0), width=1)
            d.ellipse([X(u) - 5, Y(v) - 5, X(u) + 5, Y(v) + 5], outline=(255, 0, 0), width=2)
        d.line([(X(e["sclera_in"]), Y(-3)), (X(e["sclera_in"]), Y(3))], fill=(255, 255, 255), width=1)
        rr = e["iris"] / 2 / eye_ruler.STEP
        d.ellipse([X(0) - rr, Y(0) - rr, X(0) + rr, Y(0) + rr], outline=(255, 255, 0))
        d.line([(X(0) - 6, Y(0)), (X(0) + 6, Y(0))], fill=(255, 255, 0))
        if mesh is not None:
            m = mesh[s]
            R = np.asarray(m["ring"])
            o = np.argsort(np.arctan2(R[:, 1] - R[:, 1].mean(), R[:, 0] - R[:, 0].mean()))
            d.line([(X(u), Y(v)) for u, v in np.r_[R[o], R[o][:1]]], fill=(80, 120, 255), width=2)
            for x, a_, b_ in zip(eye_ruler.COLS, m["up"], m["lo"]):
                for v in (a_, b_):
                    if np.isfinite(v):
                        d.ellipse([X(x) - 3, Y(v) - 3, X(x) + 3, Y(v) + 3], fill=(80, 120, 255))
            if "inner_lm" in m:
                u, v = m["inner_lm"]
                d.rectangle([X(u) - 5, Y(v) - 5, X(u) + 5, Y(v) + 5], outline=(80, 120, 255), width=2)
        d.line([(12, t.size[1] - 14), (12 + 5 / eye_ruler.STEP, t.size[1] - 14)], fill=(255, 255, 255), width=3)
        d.text((16 + 5 / eye_ruler.STEP, t.size[1] - 20), "5 mm", fill=(255, 255, 255))
        tiles.append(t)
    out = Image.new("RGB", (tiles[0].size[0] * 2 + 6, tiles[0].size[1]), "white")
    out.paste(tiles[0], (0, 0))
    out.paste(tiles[1], (tiles[0].size[0] + 6, 0))
    return out if zoom == 1 else out.resize((out.size[0] * zoom, out.size[1] * zoom), Image.LANCZOS)


def crease_path(m: dict) -> list | None:
    """The picture's fold line as skin.eyes.crease's "path": [[u, v]] mm from the iris centre, from a mean() of read()
    (the upper margin + the line's height over it at COLS); None when the line is not read (darkness < CREASE_MIN)."""
    if m.get("crease_dark", 0.0) < eye_ruler.CREASE_MIN:
        return None
    up, cr = np.asarray(m["up"], float), np.asarray(m["crease"], float)
    ok = np.isfinite(up) & np.isfinite(cr)
    if ok.sum() < 4:
        return None
    return [[float(u), round(float(a + b), 2)] for u, a, b in zip(eye_ruler.COLS[ok], up[ok], cr[ok])]
