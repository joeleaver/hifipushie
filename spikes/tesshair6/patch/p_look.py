"""p_look.py: (applied once) hair.look views "ref<i>" + stage=, outline_measure / colour_bands / measure_ref."""
from pathlib import Path

p = Path(__file__).resolve().parents[3] / "src/hifipushie/hair.py"
s = p.read_text()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('''         budget: int | None = None, light=None, denoise: bool = True, debug: str | None = None) -> tuple:
    """A fast hair look: the head-cropped stage file + the hair from the spec, EEVEE, a few perspective views, a
    thumbnail (how it reads small) and the reference beside. Returns (sheet image, seconds)."""
    from PIL import Image, ImageDraw
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(name, spec=spec)
    sc = scalp(name, spec)
    cams = cameras(sc, views)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
''', '''         budget: int | None = None, light=None, denoise: bool = True, debug: str | None = None,
         stage: str | None = None) -> tuple:
    """A fast hair look: the head-cropped stage file + the hair from the spec, EEVEE, a few perspective views, a
    thumbnail (how it reads small) and the reference beside. Returns (sheet image, seconds).
    Views "ref0", "ref1", ...: the FITTED cameras of the model's reference pictures (human_refs.json, the block-in /
    solve's cameras), the whole picture squared: the hair as the picture shows it (look.ids[view] = its hair mask,
    look.images[view] = the render; outline_measure / colour_bands compare them with the picture).
    `stage`: another model with the same head whose scene the hair is shown on (a riff's copy needs no scene of its
    own). The hair is always the spec's CURRENT hair (a stage file holds none)."""
    from PIL import Image, ImageDraw
    from . import render
    from .scene import _blender
    t = time.time()
    spec = store.load(name) if spec is None else spec
    sp = make_stage(stage or name, spec=spec)
    sc = scalp(name, spec)
    ref_names = [v for v in views if re.fullmatch(r"ref\\d+", str(v))]
    views = [v for v in views if v not in ref_names]
    cams = cameras(sc, views)
    frames = [render.camera_frame(c, i) for i, c in enumerate(cams)] + human_ref_frames(name, ref_names, stage)
''')
rep('''                "size": 480 if f["name"].startswith("matched") else 240} for f in frames]  # (matched ones finer:''',
    '''                "size": 480 if f["name"].startswith(("matched", "ref")) else 240} for f in frames]  # (matched ones finer:''')
rep('''        look.mass_share, look.lit_mass, masks = {}, {}, {}
''', '''        look.mass_share, look.lit_mass, masks = {}, {}, {}
        look.ids, look.images = {}, {}
''')
rep('''            if f["name"] in mnames:
                masks[f["name"]] = red | green
''', '''            if f["name"] in mnames:
                masks[f["name"]] = red | green
            if f["name"] in ref_names:
                look.ids[f["name"]] = red | green
                look.images[f["name"]] = Image.open(fm["out"]).convert("RGB")
''')
rep('''def reference_image(name: str, reference: str | None = None):''', '''def human_refs(name: str, stage: str | None = None) -> dict:
    """The model's reference pictures and their fitted cameras (human_refs.json: {"views": [{"image", "size"}],
    "cameras": [{"r", "t", "f", "size", "centre"}]}; the stage model's when the model has none)."""
    for n in (name, stage):
        f = store._dir(n) / "human_refs.json" if n else None
        if f is not None and f.exists():
            return json.loads(f.read_text())
    raise HairError(f"{name}: no human_refs.json (reference pictures with fitted cameras: block_in / face solve make it)")


def human_ref_frames(name: str, names, stage: str | None = None) -> list:
    """Render frames "ref<i>" through the i-th fitted camera of the model's reference pictures: the whole picture,
    squared (a portrait 1152 x 1536 picture sits in the middle 3/4 of the frame's width)."""
    if not names:
        return []
    from . import humanfit
    refs = human_refs(name, stage)
    out = []
    for n in names:
        i = int(str(n)[3:])
        if i >= len(refs.get("cameras") or []):
            raise HairError(f"view {n}: {name} has {len(refs.get('cameras') or [])} fitted reference cameras")
        cam = refs["cameras"][i]
        R = humanfit._cam_rot(cam)
        eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
        fwd = R.T @ np.array([0.0, 0.0, 1.0])
        w, h = cam["size"]
        side = float(max(w, h))
        out.append({"name": str(n), "eye": eye.tolist(), "dir": (-fwd).tolist(), "up": (R.T @ np.array([0.0, -1.0, 0.0])).tolist(),
                    "fov": float(np.degrees(2 * np.arctan(side / 2 / cam["f"]))), "shift": [0.0, 0.0],
                    "center": (eye + fwd).tolist(), "near": 0.01, "scale": None, "axes": None})
    return out


def ref_square(img, size: int):
    """A reference picture (or its mask) on the square a "ref<i>" view renders: centred, padded, resized."""
    from PIL import Image
    im = Image.open(img) if not hasattr(img, "size") else img
    w, h = im.size
    side = max(w, h)
    sq = Image.new(im.mode, (side, side), 0 if im.mode in ("L", "1") else tuple([200] * len(im.getbands())))
    sq.paste(im, ((side - w) // 2, (side - h) // 2))
    return sq.resize((size, size), Image.NEAREST if im.mode in ("L", "1") else Image.LANCZOS)


def _tail_numbers(m, tx: int, ty: int, mm: float) -> dict:
    below = m[ty:]
    if not below.any():
        return {"below_px": 0, "length_mm": 0.0, "width_mm": 0.0, "back_mm": 0.0}
    cnt = below.sum(1)
    yy = np.repeat(np.arange(len(cnt)), cnt)
    wd = below[int(15 / mm):].sum(1)
    wd = wd[wd > 0]
    xs = np.nonzero(m.any(0))[0]
    return {"below_px": int(below.sum()), "length_mm": round(float(np.percentile(yy, 99)) * mm, 1),
            "width_mm": round(float(np.percentile(wd, 90)) * mm, 1) if len(wd) else 0.0,
            "back_mm": round(float(max(xs.max() - tx, tx - xs.min())) * mm, 1)}


def outline_measure(ours, ref, mm_px: float, tie=None) -> dict:
    """Our hair's mask against a reference hair mask, like with like (both bool arrays on the same square of the same
    camera): {"iou", "area": ours / hers, "chamfer_mm"} and, with `tie` = the tie's pixel [x, y] on that square, what
    hangs below it for each (`hers`, `ours`: below_px, length_mm = from the tie down to the mask's lowest 1%,
    width_mm = the 90th percentile row width below tie + 15 mm, back_mm = reach sideways from the tie's column) and
    `below` = ours / hers - 1. One draw of a tail moves these about +-10 %: judge a style over 3-4 groom seeds."""
    from scipy import ndimage as ndi
    ours = ndi.binary_closing(ndi.binary_opening(np.asarray(ours, bool), iterations=1), iterations=3)
    ref = np.asarray(ref, bool)
    out = {"iou": round(float((ours & ref).sum() / max((ours | ref).sum(), 1)), 3),
           "area": round(float(ours.sum() / max(ref.sum(), 1)), 3)}
    eh, eo = ref ^ ndi.binary_erosion(ref), ours ^ ndi.binary_erosion(ours)
    if eh.any() and eo.any():
        dh, do = ndi.distance_transform_edt(~eh), ndi.distance_transform_edt(~eo)
        out["chamfer_mm"] = round(float(0.5 * (do[eh].mean() + dh[eo].mean()) * mm_px), 1)
    if tie is not None:
        tx, ty = int(round(tie[0])), int(round(tie[1]))
        out["hers"], out["ours"] = _tail_numbers(ref, tx, ty, mm_px), _tail_numbers(ours, tx, ty, mm_px)
        out["below"] = round(out["ours"]["below_px"] / max(out["hers"]["below_px"], 1) - 1.0, 3)
    return out


def colour_bands(img, mask) -> dict:
    """The colour of `img` (RGB image or array, sRGB) inside `mask`, as CIE L*, chroma, hue (deg): the mean and the
    shadow / mid / highlight thirds by lightness. For matching a hair look to a picture: the same call on the render
    (mask = our hair AND hers, eroded: dense hair only) and on the picture, per engine (EEVEE reads look.eevee_gain /
    eevee_sat, Cycles look.cycles_fit / cycles_width / cycles_sat)."""
    a = np.asarray(img, float)[..., :3] / 255.0
    m = np.asarray(mask, bool)
    if m.sum() < 30:
        return {}
    c = a[m]
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]]) / [0.9505, 1.0, 1.089]
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L, A, B = 116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])
    q1, q2 = np.percentile(L, [33.3, 66.7])

    def band(k):
        return {"L": round(float(L[k].mean()), 1), "chroma": round(float(np.hypot(A[k], B[k]).mean()), 1),
                "hue": round(float(np.degrees(np.arctan2(B[k].mean(), A[k].mean())) % 360), 1)}
    return {"mean": band(np.ones(len(L), bool)), "shadow": band(L <= q1), "mid": band((L > q1) & (L <= q2)),
            "highlight": band(L > q2)}


def measure_ref(name: str, view: str, mask=None, tie=None, colour: bool = True, stage: str | None = None) -> dict:
    """After look(views=[.., view]) with view = "ref<i>": the CURRENT hair against that reference picture:
    `outline` (outline_measure against `mask`, a hair mask image in the picture's own pixels, white = hair; `tie` =
    the tie's pixel in the picture) and `colour` (colour_bands of our render and of the picture over the dense hair
    both have). Needs the look just made (look.ids / look.images)."""
    from PIL import Image
    from scipy import ndimage as ndi
    ids, imgs = getattr(look, "ids", {}), getattr(look, "images", {})
    if view not in ids:
        raise HairError(f"measure: look the model through {view!r} first (look_hair(views=[..., {view!r}]))")
    ours = ids[view]
    n = ours.shape[0]
    refs = human_refs(name, stage)
    i = int(view[3:])
    cam = refs["cameras"][i]
    w, h = cam["size"]
    side = float(max(w, h))
    mm = float(cam["t"][2]) / float(cam["f"]) * 1000.0 * side / n
    out = {"view": view, "mm_per_px": round(mm, 3)}
    mref = None
    if mask:
        mref = np.asarray(ref_square(Image.open(mask).convert("L"), n)) > 127
        t_ = None if tie is None else [(tie[0] + (side - w) / 2) * n / side, (tie[1] + (side - h) / 2) * n / side]
        out["outline"] = outline_measure(ours, mref, mm, t_)
    pic = ((refs.get("views") or [{}] * (i + 1))[i] or {}).get("image")
    if colour and pic and Path(pic).exists() and view in imgs:
        both = ours & mref if mref is not None else ours
        dense = ndi.binary_erosion(both, iterations=max(1, n // 160))
        out["colour"] = {"ours": colour_bands(imgs[view].resize((n, n)), dense),
                         "picture": colour_bands(ref_square(Image.open(pic).convert("RGB"), n), dense)}
    return out


def reference_image(name: str, reference: str | None = None):''')
p.write_text(s)
print("ok")
