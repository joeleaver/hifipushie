"""shots.py <model> <tag> [folds=<json file | json | ''>] [views=front,eyes,mouth,q3] [lights=photo,rake,top] [size=640]
The model's DRESSED head stage (skin_read.stage: bare skin + eyes; EEVEE) from set views under set lights, one sheet
(rows = lights, columns = views). folds= replaces skin.folds for the shot ('' = none). Importable: frames_of, LIGHTS,
shoot_all (the sf_* sheets use them)."""
import json, os, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont

G = os.environ.get("G", ".") + "/out"
RAKE = {"lights": [{"dir": [0.96, -0.25, 0.12], "energy": 4.0, "color": [1.0, 0.98, 0.96], "angle": 6}],
        "world": {"color": [0.5, 0.5, 0.52], "strength": 0.12}, "view": "Standard", "exposure": 0.0}
TOP = {"lights": [{"dir": [0.0, -0.3, 0.95], "energy": 4.0, "color": [1.0, 0.98, 0.96], "angle": 6}],
       "world": {"color": [0.5, 0.5, 0.52], "strength": 0.12}, "view": "Standard", "exposure": 0.0}
OTHER = {"lights": [{"dir": [-0.55, -0.6, 0.58], "energy": 3.2, "color": [1.0, 0.96, 0.9], "angle": 20},
                    {"dir": [0.7, -0.5, 0.2], "energy": 0.8, "color": [0.85, 0.92, 1.0], "angle": 40, "shadow": False, "specular": 0.0}],
         "world": {"color": [0.55, 0.6, 0.7], "strength": 0.45}, "view": "Standard", "exposure": 0.0}


def font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def frame(name, centre, width, az=0.0, el=0.0, dist=0.7):
    """A view of `width` m round `centre` from azimuth az (deg; 0 = the front, + = from the figure's left) and
    elevation el."""
    a, e = np.radians(az), np.radians(el)
    out = np.array([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)])       # from the centre to the camera
    eye = np.asarray(centre, float) + dist * out
    right = np.array([np.cos(a), np.sin(a), 0.0])
    up = np.cross(right, -out)
    up = up / np.linalg.norm(up) * (1 if up[2] >= 0 else -1)
    return {"name": name, "eye": eye.tolist(), "dir": out.tolist(), "up": up.tolist(), "fov": float(np.degrees(2 * np.arctan(width / 2 / dist))),
            "shift": [0.0, 0.0], "center": list(map(float, centre)), "near": 0.01, "scale": None, "axes": None}


def joints(spec):
    from hifipushie.spec import expand_mirror
    return {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}


def frames_of(spec, names):
    J = joints(spec)
    eyes = 0.5 * (J["eye.L"] + J["eye.R"])
    mouth = 0.5 * (J["lm_mouth_corner.L"] + J["lm_mouth_corner.R"])
    face = 0.5 * (eyes + mouth) + [0, 0, 0.012]
    V = {"front": (face, 0.24, 0, 0), "eyes": (eyes + [0, 0, -0.004], 0.11, 0, 0), "mouth": (mouth + [0, 0, 0.008], 0.10, 0, 0),
         "eyeL": (J["eye.L"] + [0, 0, -0.004], 0.06, 0, 0), "eyeR": (J["eye.R"] + [0, 0, -0.004], 0.06, 0, 0),
         "q3": (face, 0.24, 40, 5), "q3r": (face, 0.24, -40, 5), "eyes_q3": (eyes + [0, 0, -0.004], 0.11, 35, 0),
         "mouth_q3": (mouth + [0, 0, 0.008], 0.10, 35, 0), "side": (face + [0, 0.03, 0], 0.26, 90, 0), "low": (face, 0.24, 25, -25),
         "high": (face, 0.24, -30, 25)}
    return [frame(n, *V[n]) for n in names]


def lights(name, spec_name=None):
    from hifipushie import skin_read as sr
    return {"photo": sr.LIGHT, "rake": RAKE, "top": TOP, "other": OTHER}[name]


def shoot_all(model, spec, view_names, light_names, size=640, log=print):
    """{(light, view): RGB uint8 array (composited on mid grey)}."""
    from hifipushie import skin_read as sr, resources
    out = {}
    with resources.heavy(f"skinfolds shots {model}", gb=6, log=log):
        sn = sr.stage(model, spec, log=log)
        fr = frames_of(spec, view_names)
        for ln in light_names:
            got = sr.shoot(sn, fr, lights(ln), size=size)
            for f in fr:
                a = got[f["name"]].astype(float) / 255.0
                bg = np.array([0.42, 0.42, 0.44])
                out[(ln, f["name"])] = np.round(255 * (a[..., :3] * a[..., 3:] + bg * (1 - a[..., 3:]))).astype(np.uint8)
    return out


def sheet(cells, rows, cols, title, path, size=None):
    """cells: {(row, col): array}; one labelled sheet."""
    size = size or next(iter(cells.values())).shape[0]
    pad, top, left = 6, 54, 0
    W = len(cols) * (size + pad) + pad
    H = top + len(rows) * (size + pad + 30)
    img = Image.new("RGB", (W, H), (18, 18, 20))
    d = ImageDraw.Draw(img)
    d.text((pad, 8), title, fill=(240, 240, 240), font=font(26))
    for r, rn in enumerate(rows):
        y = top + r * (size + pad + 30)
        for c, cn in enumerate(cols):
            x = pad + c * (size + pad)
            d.text((x + 4, y), f"{cn}  |  {rn}", fill=(255, 220, 120), font=font(22))
            if (rn, cn) in cells:
                img.paste(Image.fromarray(cells[(rn, cn)]).resize((size, size), Image.LANCZOS), (x, y + 30))
    img.save(path)
    return path


if __name__ == "__main__":
    from hifipushie import store
    model, tag = sys.argv[1:3]
    kw = dict(a.split("=", 1) for a in sys.argv[3:])
    spec = store.load(model)
    if "folds" in kw:
        sk = {k: v for k, v in (spec.get("skin") or {}).items() if k != "folds"}
        if kw["folds"]:
            sk["folds"] = json.load(open(kw["folds"])) if os.path.exists(kw["folds"]) else json.loads(kw["folds"])
        spec["skin"] = sk
    if "relief" in kw:
        spec["skin"]["fold_relief"] = kw["relief"]
    vn = kw.get("views", "front,eyes,mouth,q3").split(",")
    ln = kw.get("lights", "photo,rake,top").split(",")
    t = time.time()
    cells = shoot_all(model, spec, vn, ln, size=int(kw.get("size", 640)))
    p = sheet(cells, ln, vn, f"{model} {tag}: dressed stage (EEVEE); folds {json.dumps((spec.get('skin') or {}).get('folds'))[:150]}", f"{G}/shots_{model}_{tag}.png")
    print(p, f"{time.time() - t:.0f} s")
