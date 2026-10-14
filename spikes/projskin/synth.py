"""synth.py: the SYNTHETIC ground truth for skin_project (a known dressed head photographed by us).
  synth.py shoot <src> <dst>   dst = src's spec (+ freckles, moles, lines: pigment and fine relief to keep) with src's fitted
                               cameras; its "photographs" = the dressed stage (EEVEE, hair on) through each camera under a
                               DIFFERENT light per view, saved as dst's references; and the truth: the same frames unlit
                               (flat albedo, no hair). HEAVY.
  synth.py score <dst> [k=v]   skin_project.make(dst) against the truth: Lab error by region, raw vs de-lit. LIGHT.
"""
import copy, json, os, sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, store, likeness as lk, skin_project as sp

OUT = "/mnt/data/hifipushie/projskin/out"
# three different lights (stage dicts): a soft frontal window from upper left, a hard key from the subject's left side, a top light
LIGHTS = [
    {"lights": [{"dir": [0.45, -0.7, 0.55], "energy": 3.4, "color": [1.0, 0.97, 0.93], "angle": 30},
                {"dir": [-0.3, -0.95, 0.0], "energy": 0.6, "color": [0.95, 0.97, 1.0], "angle": 40, "shadow": False, "specular": 0.0}],
     "world": {"color": [0.8, 0.8, 0.8], "strength": 0.4}, "view": "Standard", "exposure": 0.0},
    {"lights": [{"dir": [0.9, -0.35, 0.25], "energy": 4.2, "color": [1.0, 0.95, 0.88], "angle": 8},
                {"dir": [-0.5, -0.8, 0.2], "energy": 0.5, "color": [0.9, 0.95, 1.0], "angle": 40, "shadow": False, "specular": 0.0}],
     "world": {"color": [0.7, 0.75, 0.85], "strength": 0.3}, "view": "Standard", "exposure": 0.0},
    {"lights": [{"dir": [0.1, -0.3, 0.95], "energy": 3.8, "color": [1.0, 1.0, 0.97], "angle": 20},
                {"dir": [0.6, -0.8, 0.1], "energy": 0.45, "color": [1.0, 0.98, 0.95], "angle": 40, "shadow": False, "specular": 0.0}],
     "world": {"color": [0.85, 0.82, 0.8], "strength": 0.5}, "view": "Standard", "exposure": 0.0},
]


def frames_of(rj):
    import stage
    out = []
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        w, h = cam["size"]
        s = max(w, h)
        crop = [(w - s) / 2, (h - s) / 2, (w + s) / 2, (h + s) / 2]
        out.append((vi, crop, stage.fitted_frame(cam, crop, f"v{vi}")))
    return out


def crop_back(im, cam, crop):
    w, h = cam["size"]
    s = int(max(w, h))
    im = im.resize((s, s), Image.LANCZOS) if im.size[0] != s else im
    return im.crop((int(-crop[0]), int(-crop[1]), int(-crop[0]) + w, int(-crop[1]) + h))


def shoot(src, dst):
    import stage
    spec = copy.deepcopy(store.load(src))
    sk = spec["skin"]
    sk.pop("projection", None)
    sk["features"] = {**(sk.get("features") or {}), "freckles": 0.7, "moles": 0.6}
    sk["wrinkles"] = {"amount": 0.45}
    rj = copy.deepcopy(bi._refs(src))
    d = store._dir(dst)
    (d / "refs").mkdir(parents=True, exist_ok=True)
    rj["blockin"] = {**(rj.get("blockin") or {}), "root": dst}
    bi._save(dst, spec, f"synthetic ground truth from {src}", rj)
    S = max(max(c["size"]) for c in rj["cameras"])
    for vi, crop, fr in frames_of(rj):
        cam = rj["cameras"][vi]
        kc = np.asarray(LIGHTS[vi % 3]["lights"][0]["color"], float)      # a neutral backdrop LIT BY THE KEY (a real one is: the
        bd = sp._srgb(0.34 * kc / kc.max()).tolist()                       # backdrop anchor reads the light's colour off it)
        lit = stage.shoot(dst, [fr], {**LIGHTS[vi % 3], "backdrop": bd}, size=S, hair_on=True)[fr["name"]]
        flat = stage.shoot(dst, [fr], None, size=S, hair_on=False, flat=True)[fr["name"]]
        p = d / "refs" / f"syn_v{vi}.png"
        crop_back(lit, cam, crop).save(p)
        crop_back(flat, cam, crop).save(d / "refs" / f"truth_v{vi}.png")
        rj["views"][vi] = {**rj["views"][vi], "image": str(p)}
        rj["views"][vi].pop("points", None)
        print("view", vi, "->", p)
    bi._save(dst, spec, "synthetic references", rj)
    json.dump(LIGHTS, open(d / "refs" / "lights.json", "w"))


def score(dst, **kw):
    spec, rj = store.load(dst), bi._refs(dst)
    d = store._dir(dst)
    out = f"{OUT}/{dst}"
    os.makedirs(out, exist_ok=True)
    r = sp.make(dst, **kw)
    print(r["text"])
    at = sp.atlas(spec["base"])
    VI = list(range(len(rj["views"])))
    meshes = bi._per_view(spec["base"], rj, VI, lambda b: lk.model_mesh(b))
    num, den = np.zeros((len(at["ii"]), 3)), np.zeros(len(at["ii"]))
    for vi in VI:
        s = sp.sample_view(at, meshes[vi], rj["cameras"][vi], np.asarray(Image.open(d / "refs" / f"truth_v{vi}.png").convert("RGB")))
        w = s["vis"] * sp._sstep((s["facing"] - 0.3) / 0.4)
        num += w[:, None] * s["rgb"]
        den += w
    truth = num / np.maximum(den, 1e-6)[:, None]
    direct = r["conf"][at["ii"], at["jj"], 0] / 255.0
    ok = (direct > 0.6) & (den > 0.5)
    regs = sp.region_masks(at)
    res = {}
    Lt = sp.lab(truth)
    print(f"\nsynthetic truth: Lab dE (CIE76) of the recovered albedo against the true one, texels the pictures cover ({int(ok.sum())}):")
    print(f"  {'region':16s} {'raw mean':>9s} {'raw p90':>8s} {'de-lit mean':>12s} {'de-lit p90':>11s}   dL raw / de-lit (mean signed)")
    for k, m in {"ALL": np.ones(len(ok), bool), **regs}.items():
        q = ok & m
        if q.sum() < 300:
            continue
        row = {}
        for nm in ("raw", "albedo"):
            La = sp.lab(sp._lin(r[nm][at["ii"], at["jj"], :3][q] / 255.0))
            de = np.linalg.norm(La - Lt[q], axis=1)
            row[nm] = (float(de.mean()), float(np.percentile(de, 90)), float((La[:, 0] - Lt[q][:, 0]).mean()))
        res[k] = row
        print(f"  {k:16s} {row['raw'][0]:9.2f} {row['raw'][1]:8.2f} {row['albedo'][0]:12.2f} {row['albedo'][1]:11.2f}   {row['raw'][2]:+.1f} / {row['albedo'][2]:+.1f}")
    # broad (4 mm) and fine (< 1.2 mm) error separately
    for nm in ("raw", "albedo"):
        a = np.log(np.maximum(sp._lin(r[nm][at["ii"], at["jj"], :3] / 255.0), 1e-4))
        t = np.log(np.maximum(truth, 1e-4))
        lo_a, lo_t = sp._blur(at, a, ok.astype(float), 4.0), sp._blur(at, t, ok.astype(float), 4.0)
        e_lo = float(np.sqrt(np.mean(((lo_a - lo_t)[ok] @ sp.Y) ** 2)))
        ha, ht = (a - sp._blur(at, a, ok.astype(float), 1.2))[ok] @ sp.Y, (t - sp._blur(at, t, ok.astype(float), 1.2))[ok] @ sp.Y
        print(f"  {nm}: broad (4 mm) log-luminance rms error {e_lo:.3f}; fine band (< 1.2 mm) correlation with the truth {np.corrcoef(ha, ht)[0, 1]:.2f}, strength ratio {ha.std() / max(ht.std(), 1e-9):.2f}")
    for nm in ("raw", "albedo"):   # error maps: dE x 12 as grey
        La = sp.lab(sp._lin(r[nm][at["ii"], at["jj"], :3] / 255.0))
        de = np.where(ok, np.linalg.norm(La - Lt, axis=1), 0)
        Image.fromarray(sp.image(at, np.clip(de * 12, 0, 255).astype(np.uint8))).save(f"{out}/err_{nm}.png")
    Image.fromarray(r["albedo"][..., :3]).save(f"{out}/albedo.png")
    Image.fromarray(r["raw"][..., :3]).save(f"{out}/raw.png")
    Image.fromarray(sp.image(at, (np.clip(sp._srgb(truth), 0, 1) * 255).astype(np.uint8))).save(f"{out}/truth.png")
    Image.fromarray(r["conf"]).save(f"{out}/conf.png")
    Image.fromarray(r["detail"]).save(f"{out}/detail.png")
    json.dump({"score": res, "report": r["report"]}, open(f"{out}/score.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    if sys.argv[1] == "shoot":
        shoot(sys.argv[2], sys.argv[3])
    else:
        kw = dict(a.split("=", 1) for a in sys.argv[3:])
        score(sys.argv[2], **{k: (v == "1" if v in "01" else v) for k, v in kw.items()})
