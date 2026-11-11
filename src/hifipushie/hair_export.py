"""The hair export: tangents, parts, the export's constants, strands and cards, the shared atlas. Part of hair
(hair.py has the overview)."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import numpy as np

from . import hair
from . import store
from . import hair_head
from .hair import _unit
from .hair_groom import groom_params, look_of
from .hair_job import job
from .hair_look import check_tiers, tiers_text
from .hair_spec import hair_of, resolve

# ------------------------------------------------------------------------------------------------ export
def srgb_to_linear(hexc: str) -> list:
    c = hexc.lstrip("#")
    v = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in v]


def _srgb8(px):
    """Linear floats -> sRGB 8-bit."""
    c = np.clip(px, 0, 1)
    s = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return (s * 255 + 0.5).astype(np.uint8)


def _tangents(V, T, UV):
    """Per-corner normals (smooth, by vertex) and tangents (dP/du, orthogonalised) + bitangent sign, for a triangle
    mesh with per-corner uv (T (n, 3) vertex ids, UV (n*3, 2))."""
    P = V[T]
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    fn = np.cross(e1, e2)
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, T[:, k], fn)
    vn = _unit(vn)
    u = UV.reshape(-1, 3, 2)
    d1, d2 = u[:, 1] - u[:, 0], u[:, 2] - u[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) > 1e-12, 1.0 / np.where(np.abs(det) > 1e-12, det, 1.0), 0.0)
    t = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
    b = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
    vt, vb = np.zeros_like(V), np.zeros_like(V)
    for k in range(3):
        np.add.at(vt, T[:, k], t)
        np.add.at(vb, T[:, k], b)
    n = vn[T].reshape(-1, 3)
    tt = vt[T].reshape(-1, 3)
    tt = tt - (tt * n).sum(1, keepdims=True) * n
    tt = np.where(np.linalg.norm(tt, axis=1, keepdims=True) > 1e-12, _unit(tt), np.array([1.0, 0, 0]))
    sign = np.sign((np.cross(n, tt) * vb[T].reshape(-1, 3)).sum(1))
    return n, tt, np.where(sign == 0, 1.0, sign)


EXPORT = {"segments": 24, "sides": 10}  # per lock (spec["hair"]["export"] overrides): 12 x 8 read faceted in the


# export (the lens's thin edges shaded as flat planes), 24 x 10 is ~20k triangles for 45 locks
def export_part(name: str, out_dir: Path, spec: dict | None = None, texture: int = 1024, segments: int | None = None,
                sides: int | None = None, log: list | None = None) -> tuple[dict, dict] | None:
    """The hair as an export part: (part dict as asset.lowpoly makes them: verts, corner_vert, uv, normal, tangent,
    sign; atlas set by the caller) and its maps {basecolor, orm, normal, specular: png}. Low poly = the curve locks at
    `segments` x `sides` + the underlayer decimated; maps = Cycles bakes from the full-resolution locks (Blender)."""
    from PIL import Image
    from .scene import _blender
    log = [] if log is None else log
    spec = store.load(name) if spec is None else spec
    if not hair_of(spec).get("locks"):
        return None
    if hair_of(spec).get("style") in ("cards", "strands"):  # (a strand groom ships as cards cut from it)
        return export_cards(name, Path(out_dir), spec, log)
    ex = {**EXPORT, **((spec.get("hair") or {}).get("export") or {})}
    segments = int(segments or ex["segments"])
    sides = int(sides or ex["sides"])
    t = time.time()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    j = {"mode": "hair_export", "blend": "", "out": str(out_dir), "hair": job(name, spec), "texture": texture,
         "segments": segments, "sides": sides}
    _blender(j, timeout=1800)
    z = np.load(out_dir / "hair_low.npz")
    V, T, UV = z["verts"].astype(np.float64), z["tris"], z["uv"].astype(np.float64)
    n, tt, sg = _tangents(V, T, UV)
    part = {"verts": V.astype(np.float32), "corner_vert": T.ravel().astype(np.int64), "uv": UV.astype(np.float32),
            "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32)}
    col = np.load(out_dir / "hair_color.npy")[::-1]  # Blender's pixels run bottom-up
    rough = np.load(out_dir / "hair_rough.npy")[::-1]
    files = {"basecolor": out_dir / "hair_basecolor.png", "orm": out_dir / "hair_orm.png",
             "normal": out_dir / "hair_normal.png", "specular": out_dir / "hair_specular_gltf.png"}
    Image.fromarray(_srgb8(col[..., :3])).save(files["basecolor"])
    r8 = (np.clip(rough[..., 0], 0, 1) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(np.stack([np.full_like(r8, 255), r8, np.zeros_like(r8)], -1)).save(files["orm"])
    Image.fromarray(np.full((4, 4, 4), [255, 255, 255, 64], np.uint8), "RGBA").save(files["specular"])
    log.append(f"hair: {len(T)} triangles ({segments} x {sides} per lock + the underlayer), maps {texture}^2 baked by Cycles "
               f"from the locks' own material in {time.time() - t:.1f}s")
    return part, files


EXPORT_CARDS = {"triangles": 12000, "tier": None, "cap_step": 6.0, "alpha_cutoff": 0.33, "shadow_proxy": True}  # spec["hair"]["export"] overrides


CARD_RECIPE = (
    "Hair cards. Draw two-sided with one normal for both faces (the mesh's normals are already bent toward the hair "
    "volume: do not flip them on back faces). Alpha: the base colour's alpha, alpha-tested at alpha_cutoff with "
    "dithering + temporal AA, or alpha-to-coverage with MSAA; keep the alpha's coverage in the mips (or bias mips "
    "-1). COLOR_0 multiplies the base colour: the root-to-tip ramp, a value per lock and per card, lower layers "
    "darker. Anisotropic highlight along the hair: TANGENT's bitangent (the atlas's v) runs root to tip. The aux "
    "texture holds R = root gradient (1 at the root), G = a value per strand (shift the highlight and the value "
    "with it), B = depth in the clump (0 deep: darker, less specular; usable as pixel depth offset), A = alpha. "
    "LODs: drop the cards of `layer` 2, then 1 (extras.layers gives each layer's triangle range).")


BACK_FACES = 1  # (c6) export each card's back face as its own triangles (outward normals) + a single-sided material


BUDGET_UNIT = "card_faces"  # (hair-budget rule 2026-10-19) a tier's budget counts card faces (one side);


# drawn triangles (back faces included) must fit the role's range max (checked at export: asset.hair_budget)
CARD_RECIPE_FACES = CARD_RECIPE.replace(
    "Draw two-sided with one normal for both faces (the mesh's normals are already bent toward the hair "
    "volume: do not flip them on back faces).",
    "Every card's back is its own triangles (reversed winding, the SAME outward normal): draw single-sided with "
    "back-face culling (the material is not doubleSided), so no engine flips a normal.")


def _gpu_vertices(part: dict) -> int:
    """(c13) vertices as an engine draws them: one per distinct (position, uv, normal) corner (a GLB splits shared
    positions at uv / normal seams; back faces share their front's corners)."""
    cv = np.asarray(part["corner_vert"])
    cols = [cv[:, None].astype(np.float64)]
    for k in ("uv", "normal"):
        if part.get(k) is not None and len(part[k]) == len(cv):
            cols.append(np.round(np.asarray(part[k], np.float64), 5))
    return int(len(np.unique(np.concatenate(cols, 1), axis=0)))


def export_hair(name: str, out_dir, tiers=("main", "npc", "far"), groom: bool = True, spec: dict | None = None,
                check: bool = False, sheet: str | None = None, textures: str = "shared") -> dict:
    """The hair alone, game-ready, from a strand (or card) groom: one GLB a tier (`<name>_hair_<tier>.glb`: LODs that
    share ONE atlas: cards cut from the groom's locks, the cap wearing the scalp chart) and, groom=True, the strands
    themselves for engines and renderers that draw them (`<name>_groom.abc` in centimetres for Unreal's groom
    importer / Unity's hair package, `<name>_groom.usdc` with the groom_* attributes as primvars). Returns the
    report (also `<name>_hair.json`)."""
    from . import asset, hair_cards as hc
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = store.load(name) if spec is None else spec
    with export_constants(hair_of(spec)):
        return _export_hair(name, out_dir, tiers, groom, spec, check, sheet, textures)


def export_constants(h: dict):
    """(sh5) hair.export.constants = {"hair_cap.GREY_MAP": {...}, "hair.SHELL_EDGE_LIFT": 0.0, ...}: module constants the
    export runs with (the shells style's look was tuned as constants: Garrett's sh4T), restored afterwards. Modules:
    hair, hair_cap, hair_cards."""
    import contextlib
    import importlib

    @contextlib.contextmanager
    def cm():
        old = []
        for k, v in ((h.get("export") or {}).get("constants") or {}).items():
            mod_, _, att = k.rpartition(".")
            if mod_ not in ("hair", "hair_cap", "hair_cards"):
                raise ValueError(f"hair.export.constants: {k}: module must be hair, hair_cap or hair_cards")
            m = importlib.import_module(f"hifipushie.{mod_}")
            if mod_ == "hair" and not hasattr(m, att):  # (hair.py was split, C414: a spec still says "hair.X")
                m = next((x for x in (importlib.import_module(f"hifipushie.{n}") for n in hair.MODULES) if hasattr(x, att)), m)
            if not hasattr(m, att):
                raise ValueError(f"hair.export.constants: {k}: no such constant")
            old.append((m, att, getattr(m, att)))
            o = getattr(m, att)
            setattr(m, att, type(o)(v) if isinstance(o, (int, float)) and not isinstance(o, bool) and isinstance(v, (int, float)) else v)
        try:
            yield
        finally:
            for m, att, o in reversed(old):
                setattr(m, att, o)
    return cm()


def _export_hair(name, out_dir, tiers, groom, spec, check, sheet, textures) -> dict:
    from . import asset, hair_cards as hc
    import shutil
    out_dir = Path(out_dir)
    h = hair_of(spec)
    lk = look_of(spec, h)
    rep = {"tiers": {}, "recipe": CARD_RECIPE}
    log: list = []
    fade_note = None
    if (h.get("export") or {}).get("fade"):  # (sh7) the short hair's edge fade, painted into the head's skin (hair_fade)
        from . import hair_fade
        out_dir.mkdir(parents=True, exist_ok=True)
        fm_ = hair_fade.build(hair_head.scalp(name, spec), h["export"]["fade"])
        fade_note = hair_fade.write(fm_, str(out_dir / f"{name}_hair"))
        (out_dir / f"{name}_hair_skin_fade.json").write_text(json.dumps(fade_note, indent=1))
        log.append(f"hair fade: {fm_['hairs']} cut hairs painted into the skin ({fade_note['file']})")
    import shutil
    files0 = None
    for tier in tiers:
        sp = {**spec, "hair": {**h, "export": {**(h.get("export") or {}), "tier": tier}}}
        if files0 is None:  # the first tier's maps are the shared atlas; the others' uv are put onto it (share_atlas)
            part, files = export_cards(name, out_dir, sp, log)
            files0, own = files, False
        else:  # (each tier wrote its maps over the last: every GLB but the last tier's read the wrong atlas)
            part, files = export_cards(name, out_dir / f"_{tier}", sp, log)
            own = not share_atlas(part, files, files0)
            if own:  # its own maps beside the GLBs
                files = {k: Path(shutil.copyfile(f, out_dir / f"hair_{tier}_{k}.png")) for k, f in files.items()}
                log.append(f"hair tier {tier}: its atlas differs from {tiers[0]}'s: own maps")
            else:
                files = files0
            shutil.rmtree(out_dir / f"_{tier}", ignore_errors=True)
        hc_ = part.pop("hair")
        sp_ = part.pop("shadow_proxy", None)
        if sp_ is not None and len(sp_["tris"]):  # a shadow-only caster beside the GLB (shading.py hair_cards "shadows")
            spf = out_dir / f"{name}_hair_{tier}_shadow.obj"
            hc.write_obj(spf, sp_["verts"], sp_["tris"], f"{name}_hair_shadow")
            hc_["shadow_proxy"] = {"file": spf.name, "triangles": int(len(sp_["tris"])), "inset": sp_["inset"],
                                   "use": "cast shadows only, hidden from camera; the cards cast none"}
        hc_["aux_texture"] = list(files).index("aux")
        if fade_note:
            hc_["skin_fade"] = fade_note
        # (engines: COLOR_0 multiplies the base colour (the root-to-tip ramp, a value per card). glTF says so, but
        # Godot's importer leaves BaseMaterial3D.vertex_color_use_as_albedo off: set it, or the hair is pale and flat)
        hc_["vertex_color"] = "multiplies base colour; Godot: set vertex_color_use_as_albedo = true"
        part["atlas"] = 0
        glb = out_dir / f"{name}_hair_{tier}.glb"
        sheen = [round(float(c), 3) for c in srgb_to_linear(lk["sheen"])]
        ani = {"anisotropyStrength": float(lk.get("anisotropic", 0.7)), "anisotropyRotation": 1.5708}
        if "flow" in files:  # the hair's direction per texel (the cap's strands turn; a card's run down its picture)
            ani = {"anisotropyStrength": float(lk.get("anisotropic", 0.7)), "anisotropyRotation": 0.0,
                   "anisotropyTexture": {"index": list(files).index("flow")}}
            hc_["flow_texture"] = list(files).index("flow")
        hc_["textures"] = textures
        asset.write_glb(glb, f"{name}_hair", {"hair": part}, [("hair", files)], external=textures == "shared",
                        looks={"hair": {"alpha_cutoff": hc_["alpha_cutoff"], "double_sided": not hc_.get("back_faces"),
                                         "extras": {"hifipushie_hair": hc_}}},
                        extra_ext={0: {"KHR_materials_specular": {  # (a card is a sheet standing for many round
                            # hairs: at a dielectric's white F0 it mirrors a light as one pale plate; half of it, and
                            # in the hair's own colour, as light off and through hairs is)
                            "specularFactor": 0.5, "specularColorFactor": [round(float(c / max(max(sheen), 1e-6)), 3) for c in sheen]},
                                       "KHR_materials_anisotropy": ani,
                                       "KHR_materials_sheen": {"sheenColorFactor": sheen, "sheenRoughnessFactor": 0.35}}})
        n_idx_ = len(part["corner_vert"]) // 3
        n_back_ = (sum(int(v[1]) for k, v in (hc_.get("layers") or {}).items() if k != "cap") // 2
                   if hc_.get("back_faces") else 0)
        # "triangles" = DRAWN triangles, back faces included: the budgets' unit (c10, coordinator 2026-10-18; cards_job
        # fits the cards to it). "card_faces" = the cards' faces without their BACK_FACES copies (round 36's count);
        # "index_triangles" = "triangles" (kept for round 36's readers)
        # (round 40) "vertices" = the GLB's vertices (back faces have their own, outward normals); "drawn_max" = the
        # role's range maximum the drawn triangles must stay within ("budget"'s card faces = the role's default)
        rep["tiers"][tier] = {"glb": str(glb), "triangles": n_idx_, "card_faces": n_idx_ - n_back_, "index_triangles": n_idx_,
                              "vertices": _gpu_vertices(part), "positions": int(len(part["verts"])),
                              "drawn_max": (hc_.get("budget") or {}).get("drawn_max"),
                              "layers": hc_["layers"],
                              "atlas": "own" if own else "shared",
                              "budget": hc_["budget"], "bytes": glb.stat().st_size, "clearance": hc_.get("clearance")}
    rep["maps"] = {k: str(v) for k, v in files0.items()}
    rep["log"] = log
    if groom and h.get("style") == "strands":
        from . import hair_strands as hs
        import re
        sc = hair_head.scalp(name, spec)
        g = groom_params(spec)
        tmp = Path(tempfile.mkdtemp(prefix="hifipushie-groom-"))
        locks = [k for k in resolve(spec, sc) if not re.fullmatch(r"t\d*band", k["name"])]
        colg = None
        if g.get("loose"):
            from . import hair_loose
            colg = hair_loose.collider(name, spec, sc)
        sd = hs.job(sc, g, spec, locks, tmp, count=int((h.get("export") or {}).get("strands", 0)) or None, col=colg)
        abc, usd = out_dir / f"{name}_groom.abc", out_dir / f"{name}_groom.usdc"  # (binary: the .usda was 33 MB)
        r = hs.evaluate(sd, abc=str(abc), usd=str(usd))
        got = next((json.loads(ln[8:]) for ln in r.splitlines() if ln.startswith("@@groom")), {})
        rep["groom"] = {**{k: v for k, v in got.items() if k not in ("abc", "usd")}, "alembic": str(abc), "usd": str(usd),
                        "bytes": {"alembic": abc.stat().st_size if abc.exists() else 0,
                                  "usd": usd.stat().st_size if usd.exists() else 0},
                        "note": "Alembic: curves + widths in cm (Unreal groom import; guides, ids and root uv are "
                                "the importer's defaults: Blender's Alembic writer drops per-curve attributes). USD: "
                                "BasisCurves + widths + groom_id / groom_guide / groom_group_id primvars, metres."}
    (out_dir / f"{name}_hair.json").write_text(json.dumps(rep, indent=1, default=float))
    if check or sheet:  # every tier re-imported and judged against the strands (check_tiers): WARNINGs in the report
        chk = check_tiers(name, rep, tiers=tiers, save=sheet, spec=spec)
        rep["checks"] = {t: {k: r[k] for k in ("test", "dither", "warnings")} for t, r in chk["tiers"].items()}
        rep["warnings"] = chk["warnings"]
        rep["checks_text"] = tiers_text(chk)
        if sheet:
            rep["sheet"] = str(sheet)
        (out_dir / f"{name}_hair.json").write_text(json.dumps(rep, indent=1, default=float))
    return rep


def share_atlas(part: dict, files: dict, files0: dict, tol: int = 2) -> bool:
    """Put a card tier's uv onto another tier's atlas (`files0`), in place: True when every map of `files` is the
    same picture as `files0`'s, or the same as its TOP rows (hair_cards.atlas stacks a tier's baked clump tiles UNDER
    the tiles + chart: the hero tier's atlas is 2048 x 2048 where main / npc / far, with no baked cards, are 2048 x
    1024), its v then remapped onto those rows (hair_cards.remap_v). False: the pictures differ, the tier needs its
    own maps (its uv untouched). Round 28: asset's LOD1-3 hair indexed LOD0's atlas with uv made for a half-height
    one: a bald crown and a torn tail."""
    from PIL import Image
    from . import hair_cards as hc
    keys = [k for k in files0 if k != "specular"]
    if set(keys) != {k for k in files if k != "specular"}:
        return False
    rows = rows0 = None
    for k in keys:
        a = np.asarray(Image.open(files[k]))
        b = np.asarray(Image.open(files0[k]))
        if a.ndim != b.ndim or a.shape[1:] != b.shape[1:] or a.shape[0] > b.shape[0]:
            return False
        if (rows, rows0) not in ((None, None), (a.shape[0], b.shape[0])):
            return False
        rows, rows0 = a.shape[0], b.shape[0]
        d = np.abs(a.astype(np.int16) - b[:rows].astype(np.int16)).reshape(rows, a.shape[1], -1).max(-1)
        if (d > tol).mean() > 1e-3:  # (the normal map's last tile rows see the baked block under them: 0.005% of
            return False  # texels differ there by up to 28 levels; a different picture differs nearly everywhere)
    if rows != rows0:
        part["uv"] = hc.remap_v({"uv": part["uv"]}, {"rows": rows, "rows_total": rows0})["uv"]
    return True


def back_faces(T, lay, corner: tuple) -> tuple:
    """(c6) Each card triangle followed (within its layer's range) by its back: the same corners in reverse order, so the
    same vertices, normals (outward), tangents and signs; layers < 0 (the cap) keep one face. T (n, 3) vertex indices,
    lay (n,) layer per triangle, sorted; corner: per-corner arrays (3n, ...). Returns T', corner'."""
    ci = np.arange(len(T) * 3).reshape(-1, 3)
    keep = []
    for k in np.unique(lay):
        ix = np.nonzero(lay == k)[0]
        keep.append(ci[ix].ravel())
        if k >= 0:
            keep.append(ci[ix][:, ::-1].ravel())
    cr = np.concatenate(keep)
    return np.asarray(T).ravel()[cr].reshape(-1, 3), tuple(a[cr] for a in corner)


CARD_ROUGH_MIN = 0.6  # (r59) the cards' roughness floor in the export's ORM: the outer, lit hair (aux.b high) came out at


# 0.425 (the 0.5 floor x 0.85), and an isotropic engine lobe at that mirrored the key light off the crown's flat cards as
# one white plate (Tess rc2i's "white glossy crown"; 0.65 / 0.75 in the game preview took it away, 0.6 + the tinted half
# specular below leaves a faint warm sheen). The baked-cap path already says it: "glossy, it was tin foil".
CARD_SPECULAR = 0.5  # (r59) the combined character GLB's hair KHR_materials_specular factor (half a dielectric's) ...


def card_specular_tint(sheen_linear) -> list:
    """(r59) ... and its colour: the hair's sheen, normalised to max 1 (light off and through hairs takes their colour).
    The character export (asset.py) writes specularFactor CARD_SPECULAR, specularColorFactor this, no specular texture,
    i.e. F0 0.04 x 0.5 x tint = 0.02 x tint = Blender's IOR level 0.25 tinted,
    as blender_hair's card material and the game preview (blender_game, notes params specular_level / specular_tint)."""
    m = max(max(float(c) for c in sheen_linear), 1e-6)
    return [round(float(c) / m, 3) for c in sheen_linear]


def export_cards(name: str, out_dir: Path, spec: dict, log: list) -> tuple[dict, dict]:
    """export_cards with hair.export.constants applied (export_constants): every export path (export_hair, export_part,
    asset's hair LODs) runs with the spec's constants."""
    with export_constants(hair_of(spec)):
        return _export_cards(name, out_dir, spec, log)


def _export_cards(name: str, out_dir: Path, spec: dict, log: list) -> tuple[dict, dict]:
    """The hair as cards for an engine: the card mesh + the cap (coarse) in one mesh on the strand atlas, within
    `hair.export.triangles`. Part keys as export_part's, plus "vcolor" (per vertex: COLOR_0) and "hair" (the
    material's facts: alpha cutoff, layers' triangle ranges, the recipe); maps basecolor (RGBA), orm, normal,
    specular, aux."""
    from PIL import Image
    from . import hair_cards as hc
    t = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hair_of(spec)
    ex = {**EXPORT_CARDS, **{k: v for k, v in (h.get("export") or {}).items() if k in EXPORT_CARDS}}
    j = job(name, {**spec, "hair": {**h, "style": "cards"}},
            budget=ex["tier"] or int(ex["triangles"]), cap_step=float(ex["cap_step"]))
    cd = j["cards"]
    cap, cards = dict(np.load(cd["cap"])), dict(np.load(cd["mesh"]))
    o = np.argsort(cards["layer"][cards["tris"][:, 0]], kind="stable")  # triangles by layer: a LOD is a range
    cards["tris"] = cards["tris"][o]
    M = hc.join(cap, cards)
    V, T = M["verts"].astype(np.float64), M["tris"]
    UV = M["uv"][T].reshape(-1, 2).astype(np.float64)
    _, tt, sg = _tangents(V, T, UV)
    n = M["normal"][T].reshape(-1, 3).astype(np.float64)
    tt = tt - (tt * n).sum(1, keepdims=True) * n
    tt = np.where(np.linalg.norm(tt, axis=1, keepdims=True) > 1e-9, _unit(tt), _unit(np.cross(n, [0.0, 0.0, 1.0])))
    lay = M["layer"][T[:, 0]]
    if BACK_FACES:  # (c6) each card's back as its own triangles, wound the other way, with the SAME (outward) normal,
        # tangent and sign: a single-sided material then never flips a normal, in any viewer (glTF's doubleSided rule
        # reverses a back face's normal: a card on the head seen from below its plane went black = the crown shards).
        # Vertices are shared (same position / normal / uv), so only the index count grows; layers stay ranges.
        T, (UV, n, tt, sg) = back_faces(T, lay, (UV, n, tt, sg))
        lay = M["layer"][T[:, 0]]
    ranges = {("cap" if k < 0 else "tie" if k > 8 else f"layer{int(k)}"): [int(np.nonzero(lay == k)[0][0]), int((lay == k).sum())]
              for k in np.unique(lay)}
    lk = j["look"]
    part = {"verts": V.astype(np.float32), "corner_vert": T.ravel().astype(np.int64), "uv": UV.astype(np.float32),
            "normal": n.astype(np.float32), "tangent": tt.astype(np.float32), "sign": sg.astype(np.float32),
            "vcolor": M["col"].astype(np.float32),
            "hair": {"alpha_cutoff": float(ex["alpha_cutoff"]), "layers": ranges, "recipe": CARD_RECIPE if not BACK_FACES else CARD_RECIPE_FACES,
                     "back_faces": bool(BACK_FACES),
                     "strands": hc.strands_of(spec), "budget": cd["budget"], "clearance": cd.get("clearance")}}
    if ex.get("shadow_proxy", True):  # the hair's shadow caster (opaque hull of the cards, shadow-only)
        sp_ = hc.shadow_proxy(M["verts"], M["tris"])
        part["shadow_proxy"] = sp_
    aux = np.asarray(Image.open(cd["aux"]).convert("RGBA"), np.float32) / 255
    files = {"basecolor": out_dir / "hair_basecolor.png", "orm": out_dir / "hair_orm.png",
             "normal": out_dir / "hair_normal.png", "specular": out_dir / "hair_specular_gltf.png",
             "aux": out_dir / "hair_aux.png"}
    Image.open(cd["color"]).save(files["basecolor"])
    Image.open(cd["normal"]).convert("RGB").save(files["normal"])
    Image.open(cd["aux"]).save(files["aux"])
    if cd.get("flow"):
        files["flow"] = out_dir / "hair_flow.png"
        Image.open(cd["flow"]).convert("RGB").save(files["flow"])
    rough = np.clip(max(float(lk.get("roughness", 0.42)), 0.5) * (1.25 - 0.4 * aux[..., 2]), CARD_ROUGH_MIN, 1.0)
    if cd.get("short"):  # a baked cap is a surface of many hairs' highlights already in its picture and normal map:
        rough = np.clip(max(float(lk.get("roughness", 0.42)), 0.85) * (1.12 - 0.15 * aux[..., 2]), 0.05, 1.0)  # glossy, it was tin foil
    occ = 0.55 + 0.45 * aux[..., 2]
    Image.fromarray((np.stack([occ, rough, np.zeros_like(occ)], -1) * 255 + 0.5).astype(np.uint8)).save(files["orm"])
    Image.fromarray(np.full((4, 4, 4), [255, 255, 255, 128], np.uint8), "RGBA").save(files["specular"])
    log.append(f"hair: {len(T)} triangles as cards (asked {ex['triangles']}: {cd['cards']} cards + {cd['baby']} baby "
               f"hairs, the cap {cd['cap_triangles']}; {cd['budget']}), strand atlas {aux.shape[1]}^2 generated, "
               f"{time.time() - t:.1f}s")
    return part, files
