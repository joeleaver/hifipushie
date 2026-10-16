"""rvpack_cloth.py <job dir>  (env MODEL = the model; COATV / COATSHEEN / PATCH / PROPS as below)
<job dir> <garments> <tag> <region=x,y,z,zoom,views> ...: rv_renders.py's look_cloth close-ups, but
cloth.render only PACKS each render (job.json + data + maps) into <job dir>/r_<tag>_<region>/ for NICO-TOP
(spikes/offload/job_clothjobs.py); fin/rvunpack.sh puts the PNGs back as out/rv_<tag>_<region>.png."""
import json, os, shutil, sys
from pathlib import Path
import numpy as np
from hifipushie import cloth, server
jobdir, gs, tag = Path(sys.argv[1]), sys.argv[2].split(","), sys.argv[3]
MODEL = os.environ["MODEL"]  # the model packed (required)


class Packed(Exception):
    pass


CUR = {}


def pack(objects, prefix, views=("front",), resolution=700, box=None, aspect=0.62, textured=False, suns=None, shadows=None):
    d = jobdir / f"r_{tag}_{CUR['reg']}"
    d.mkdir(parents=True, exist_ok=True)
    data, objs = {}, []
    for o in list(objects) + PROPS:
        data[o["name"] + "_V"] = np.asarray(o["V"], np.float64); data[o["name"] + "_F"] = np.asarray(o["F"])
        for k, s_ in (("C", "_C"), ("uv", "_UV"), ("uv_corner", "_UVC")):
            if o.get(k) is not None:
                data[o["name"] + s_] = np.asarray(o[k], np.float32)
        oo = {k: v for k, v in o.items() if k in ("name", "color", "thickness", "offset", "maps", "roughness", "sheen")}  # s13: "sheen" was dropped here, so no rvpack2 render ever carried a sheen (b02s0 == b02dc22)
        if oo.get("maps"):
            oo["maps"] = dict(oo["maps"])
            for k, v in oo["maps"].items():
                if isinstance(v, str) and os.path.exists(v):
                    nm = f"{o['name'].replace(':', '_')}_{k}{Path(v).suffix}"
                    shutil.copy(v, d / nm); oo["maps"][k] = nm
        objs.append(oo)
    np.savez(d / "data.npz", **data)
    job = {"mode": "render", "data": "data.npz", "objects": objs, "out_prefix": "out", "views": list(views),
           "resolution": resolution, "aspect": aspect, "textured": bool(textured), "suns": suns,
           "box": [list(map(float, box[0])), list(map(float, box[1]))] if box is not None else None,
           "shadows": bool(shadows) if shadows is not None else os.environ.get("HIFIPUSHIE_CLOTH_SHADOWS", "1") != "0"}
    (d / "job.json").write_text(json.dumps(job))
    raise Packed(str(d))


cloth.render = pack
# look_cloth draws only the body and the garments' "collide" parts (shoes): the props worn OVER the clothes (lanyard,
# clip, badge, laces) were missing from every b01 render. They go in as their own objects, coloured by their part,
# built BEFORE any COATV patch (the build is keyed on the stored spec).
PROPS = []
if os.environ.get("PROPS", "lanyard,clip,badge,badge_card,laces"):
    from hifipushie import store as _s0
    _sp = _s0.load(MODEL)
    # (thin props are sub-voxel in the whole-figure build (lanyard 36 verts, badge none): close-up box builds,
    # ~2 mm voxels at the chest, ~1 mm at the feet)
    _Z = []
    for _box, _res in ((((-0.25, -0.3, 0.9), (0.25, 0.15, 1.55)), 330), (((-0.3, -0.3, -0.02), (0.3, 0.25, 0.16)), 300)):
        _b = _s0.build(MODEL, resolution=_res, box=(np.array(_box[0]), np.array(_box[1])))
        _Z.append(dict(np.load(_b["mesh"])))  # (box builds share one closeup file: read it now)
    for _p in os.environ.get("PROPS", "lanyard,clip,badge,badge_card,laces").split(","):
        _z = next((z for z in _Z if _p in [str(n) for n in z["part_names"]]), None)
        _names = [str(n) for n in _z["part_names"]] if _z is not None else []
        if _p not in _names:
            print("WARNING: prop part", _p, "not in the build"); continue
        _k = _names.index(_p); _vm = _z["part"] == _k
        _idx = -np.ones(len(_vm), int); _idx[_vm] = np.arange(_vm.sum())
        _f = _z["faces"][_vm[_z["faces"]].all(1)]
        PROPS.append({"name": "prop_" + _p, "V": _z["verts"][_vm], "F": _idx[_f],
                      "color": (_sp.get("parts", {}).get(_p) or {}).get("color", "#888888"),
                      "roughness": (_sp.get("parts", {}).get(_p) or {}).get("roughness", 0.6)})
    print("props", [(o["name"], len(o["V"])) for o in PROPS])
if os.environ.get("COLOR"):  # a colour variant: the sweater's colour overridden for this pack only (spec untouched)
    from hifipushie import store
    _load = store.load

    def load(name, *a, **k):
        sp = _load(name, *a, **k)
        if name == MODEL:
            sp["cloth"]["sweater"]["color"] = os.environ["COLOR"]
        return sp
    store.load = load
if os.environ.get("COATV"):  # the coat design of spec version COATV rest of the spec current
    from hifipushie import store as _st
    _ld = _st.load
    def _load2(name, *a, **k):
        sp = _ld(name, *a, **k)
        if name == MODEL:
            sp["cloth"]["coat"] = _st.version_spec(MODEL, int(os.environ["COATV"]))["cloth"]["coat"]
        return sp
    _st.load = _load2
if os.environ.get("COATSHEEN"):  # b02 (session 12; session 13: AFTER COATV, which replaced the whole coat and dropped this, so b02s0 == b02dc22 pixel for pixel): the coat's sheen overridden for this pack only (puffy A/B)
    from hifipushie import store as _st2
    _ld2 = _st2.load
    def _load3(name, *a, **k):
        sp = _ld2(name, *a, **k)
        if name == MODEL:
            sp["cloth"]["coat"]["sheen"] = float(os.environ["COATSHEEN"])
        return sp
    _st2.load = _load3
if os.environ.get("PATCH"):  # session 13: dotted-path overrides of dt_tess for this pack only, applied LAST (after COATV /
    # COATSHEEN), e.g. PATCH='{"cloth.coat.sheen": 0, "cloth.sweater.detail.knit.depth": 0.00075}'; each one printed
    import json as _js
    from hifipushie import store as _st3
    _ld3 = _st3.load
    _patch = _js.loads(os.environ["PATCH"])
    def _load4(name, *a, **k):
        sp = _ld3(name, *a, **k)
        if name == MODEL:
            for path, val in _patch.items():
                d = sp
                *head, last = path.split(".")
                for h in head:
                    d = d.setdefault(h, {})
                d[last] = val
        return sp
    _st3.load = _load4
    _chk = _st3.load(MODEL)
    for path, val in _patch.items():
        d = _chk
        for h in path.split("."):
            d = d[h]
        assert d == val, (path, d, val)
        print("PATCH applied", path, "=", d, flush=True)
for spec in sys.argv[4:]:
    reg, rest = spec.split("=")
    x, y, z, zoom, views = rest.split(",", 4)
    CUR["reg"] = reg
    # game-distance views (docs/notes/gates.md): g<metres><f|t>, e.g. g1f = 1 m front, g3t = 3 m three-quarter;
    # a 1920x1080 frame, vertical fov 59 deg, the camera at ~1.6 m eye height looking at the chest (1 m) / mid (3 m)
    def _v(t):
        if not t.startswith("g"):
            return t
        d, f = float(t[1:-1]), t[-1]
        at = [0.0, -0.1, 1.1 if d < 2 else 0.9]
        h = 1.6 - at[2]
        dx, dy = (-0.65, -0.72) if f == "t" else (0.0, -1.0)
        n = (dx * dx + dy * dy) ** 0.5
        flat = (d * d - h * h) ** 0.5
        return {"name": t, "dir": [dx / n * flat / d, dy / n * flat / d, h / d], "dist": d, "fov": 59.0, "at": at,
                "res": [1920, 1080]}
    vlist = [_v(t) for t in views.split("+")]
    try:
        server.look_cloth(MODEL, garments=gs, views=vlist, strain=False, focus=[float(x), float(y), float(z)],
                          zoom=float(zoom), textured=True, size=640, save="/tmp/unused.png")
    except Packed as e:
        print("packed", e)
    else:
        print("WARNING: nothing packed for", reg, "(look_cloth didn't call cloth.render)")
