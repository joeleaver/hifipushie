"""styles.py <style|all> [plot|look|cycles|export] [views=a,b] [size=n] [k=v strands dials]: the loose-hair test set.
Each style is its own model hu_s_<style> (a copy of its test head with the groom on it).
  plot    lock spines over the collider, front / side / back (no Blender, seconds)
  look    hair.look in EEVEE -> $HR/hu_<style>_strands.png
  cycles  the same in Cycles (waits for the heavy slot)
  export  export_hair with all tiers + check sheet -> $OUT/<style>/"""
import json, os, shutil, sys, time
import numpy as np
from hifipushie import hair, store, hair_loose

HR, OUT = os.environ["HR"], os.environ["OUT"]
BROWN = {"gap": "#1c110c", "lit": "#5c3b28", "sheen": "#8a6044", "vary": 0.45, "root": 0.1}
BLACK = {"gap": "#050404", "lit": "#17120f", "sheen": "#4a4038", "vary": 0.3, "root": 0.05}
BLOND = {"gap": "#4a3520", "lit": "#b08a55", "sheen": "#dcc08c", "vary": 0.4, "root": 0.25}
DARKB = {"gap": "#0d0806", "lit": "#2e1e15", "sheen": "#5e4636", "vary": 0.35, "root": 0.08}
HL = {"front": 0.72, "temples": 0.004, "sideburns": 0.02, "nape": 0.0}
STYLES = {
    "wavy": ("hu_w30", {"parting": {"side": "left", "offset": 0.025}, "hairline": HL,
                        "loose": {"length": 0.3, "body": 0.024, "lift": 0.008, "stiff": 0.3, "uneven": 0.5}},
             {"wave": 0.014, "wavelength": 0.09, "curl": 0.25, "clump": 0.55, "loose": 0.45, "frizz": 0.3,
              "flyaway": 0.3, "tips": 0.6, "under_length": 0.08}, BROWN),
    "bob": ("hu_w30", {"parting": {"side": "none"}, "hairline": HL,
                       "loose": {"length": 0.3, "level": -0.105, "body": 0.02, "stiff": 0.25, "uneven": 0.15,
                                 "ends": 0.6, "back": 0.25, "messy": 0.05,
                                 "fringe": {"length": 0.07, "span": 48, "depth": 0.05, "level": -0.004, "stiff": 0.3}}},
            {"wave": 0.002, "wavelength": 0.12, "clump": 0.4, "loose": 0.15, "frizz": 0.12, "flyaway": 0.02,
             "tips": 0.15, "taper": 0.3, "under_length": 0.06}, DARKB),
    "long": ("hu_w26a", {"parting": {"side": "centre"}, "hairline": HL,
                         "loose": {"length": 0.52, "body": 0.022, "stiff": 0.2, "uneven": 0.3, "messy": 0.05}},
             {"wave": 0.003, "wavelength": 0.16, "clump": 0.45, "loose": 0.2, "frizz": 0.15, "flyaway": 0.12,
              "tips": 0.5, "under_length": 0.08}, BLACK),
    "tousled": ("hu_m30", {"parting": {"side": "none"}, "hairline": {**HL, "front": 0.78},
                           "loose": {"length": {"front": 0.06, "top": 0.065, "sides": 0.035, "back": 0.04, "nape": 0.02},
                                     "body": 0.006, "lift": 0.004, "stiff": 0.75, "out": 0.45, "messy": 0.7,
                                     "uneven": 0.8, "back": 0.3, "spacing": 0.02}},
                {"wave": 0.006, "wavelength": 0.05, "curl": 0.3, "clump": 0.7, "clump_size": 0.006, "loose": 0.6,
                 "frizz": 0.4, "flyaway": 0.3, "tips": 0.8, "under_length": 0.03}, DARKB),
    "afro": ("hu_w28d", {"parting": {"side": "none"}, "hairline": {**HL, "front": 0.78},
                         "loose": {"length": 0.085, "body": 0.0, "lift": 0.0, "stiff": 1.0, "out": 1.0, "messy": 0.15,
                                   "uneven": 0.25, "spacing": 0.02}},
             {"wave": 0.03, "wavelength": 0.012, "curl": 1.0, "random": 1.0, "clump": 0.5, "clump_size": 0.005,
              "loose": 0.5, "frizz": 0.8, "flyaway": 0.5, "tips": 0.5, "under_length": 0.02, "count": 40000}, BLACK),
    "curls": ("hu_w28d", {"parting": {"side": "left", "offset": 0.02}, "hairline": {**HL, "front": 0.78},
                          "loose": {"length": 0.22, "body": 0.035, "lift": 0.012, "stiff": 0.45, "out": 0.25,
                                    "messy": 0.25, "uneven": 0.5}},
              {"wave": 0.03, "wavelength": 0.028, "curl": 1.0, "random": 1.0, "clump": 0.85, "clump_size": 0.012,
               "clump_shape": 0.1, "loose": 0.3, "frizz": 0.5, "flyaway": 0.35, "tips": 0.4, "under_length": 0.04},
              BLACK),
    "short": ("hu_m35a", {"parting": {"side": "left", "offset": 0.035}, "hairline": {**HL, "front": 0.78},
                          "loose": {"length": {"front": 0.045, "top": 0.04, "sides": 0.012, "back": 0.012, "nape": 0.006},
                                    "body": 0.003, "lift": 0.003, "stiff": 0.6, "out": 0.15, "messy": 0.12,
                                    "uneven": 0.3, "spacing": 0.018}},
              {"wave": 0.001, "clump": 0.5, "clump_size": 0.005, "loose": 0.25, "frizz": 0.2, "flyaway": 0.1,
               "tips": 0.5, "under_length": 0.012, "taper": 0.4}, BLACK),
    "child": ("hu_g7", {"parting": {"side": "none"}, "hairline": {**HL, "front": 0.76},
                        "loose": {"length": 0.24, "body": 0.012, "lift": 0.004, "stiff": 0.2, "uneven": 0.5,
                                  "back": 0.2, "fringe": {"length": 0.05, "span": 42, "depth": 0.04}}},
              {"wave": 0.005, "wavelength": 0.1, "clump": 0.35, "clump_size": 0.005, "loose": 0.5, "frizz": 0.45,
               "flyaway": 0.5, "tips": 0.8, "thickness": 0.75, "under_length": 0.05}, BLOND),
}


def model(style, regrow=True):
    head, gr, st, look = STYLES[style]
    name = f"hu_s_{style}"
    d, src = store._dir(name), store._dir(head)
    if not (d / "scene.blend").exists():
        shutil.copytree(src, d, dirs_exist_ok=True)
        for f in d.glob("hair_stage*.blend"):
            f.unlink()
    spec = store.load(name)
    h = {"style": "strands", "groom": {**gr, "seed": 3}, "strands": dict(st), "look": dict(look)}
    for a in sys.argv[3:]:
        k, v = a.split("=", 1)
        if k.startswith("loose."):
            h["groom"]["loose"][k[6:]] = json.loads(v)
        elif k not in ("views", "size", "count", "tiers"):
            h["strands"][k] = json.loads(v)
    if spec.get("hair", {}).get("groom") != h["groom"] or regrow:
        spec["hair"] = {**h, "locks": (spec.get("hair") or {}).get("locks") or {}}
        store.save(name, spec, "hair4 style")
        t = time.time()
        r = hair.groom(name, replace=True)
        print(style, "groomed", r["grown"], round(time.time() - t, 1), "s", flush=True)
    else:
        spec["hair"] = {**spec["hair"], "strands": h["strands"], "look": h["look"]}
        store.save(name, spec, "hair4 style dials")
    return name


def plot(style):
    from PIL import Image, ImageDraw
    name = model(style)
    spec = store.load(name)
    sc = hair.scalp(name, spec)
    col = hair_loose.collider(name, spec, sc)
    locks = hair.resolve(spec, sc)
    S, W = 900, 420
    img = Image.new("RGB", (W * 3, S), (235, 235, 235))
    dr = ImageDraw.Draw(img)
    views = [((1, 0, 0), "front"), ((0, 1, 0), "side"), ((-1, 0, 0), "back")]
    lo, st = col.lo, col.step
    for vi, (ax, lab) in enumerate(views):
        ins = col.phi < 0
        sil = ins.any(1) if lab != "side" else ins.any(0)  # (x, z) or (y, z)
        hcoord = lo[0] if lab != "side" else lo[1]
        for ih, iz in zip(*np.nonzero(sil)):
            hx, z = hcoord + ih * st - (sc.C[0] if lab != "side" else sc.C[1]), lo[2] + iz * st - sc.C[2]
            if lab == "back":
                hx = -hx
            x, y = vi * W + W / 2 + hx * 1000, 230 - z * 1000
            dr.point((x, y), fill=(200, 170, 150))
        for lk in locks:
            P = np.asarray(lk["pts"]) - sc.C
            hx = P[:, 0] if lab != "side" else P[:, 1]
            if lab == "back":
                hx = -hx
            depth = P[:, 1].mean() if lab != "side" else -P[:, 0].mean()
            if lab == "front" and depth > 0.03 or lab == "back" and depth < -0.03:
                c = (150, 150, 190)
            else:
                c = (60, 30, 20) if not lk["name"].startswith("lf") else (20, 60, 160)
            dr.line([(vi * W + W / 2 + a * 1000, 230 - b * 1000) for a, b in zip(hx, P[:, 2])], fill=c, width=1)
        dr.text((vi * W + 6, 6), f"{style} {lab}  {len(locks)} locks", fill=(0, 0, 0))
    img.save(f"{HR}/hu_plot_{style}.png")
    print("plot", f"{HR}/hu_plot_{style}.png", flush=True)


def kw():
    d = {"views": ("bust_front", "bust_three_quarter", "bust_side", "bust_back", "close_front"), "size": 480}
    for a in sys.argv[3:]:
        k, v = a.split("=", 1)
        if k == "views": d["views"] = tuple(v.split(","))
        elif k == "size": d["size"] = int(v)
        elif k == "count": d["count"] = int(v)
    return d


def look(style, engine="eevee"):
    name = model(style, regrow=False)
    t = time.time()
    out = f"{HR}/hu_{style}_strands{'_cycles' if engine == 'cycles' else ''}.png"
    sheet, sec, fr = hair.look(name, clay=False, engine=engine, save=out, **kw())
    print(style, engine, sec, "s", out, "bare", hair.look.mass_share, [l for l in fr if "strands" in l][:1], flush=True)


def export(style):
    name = model(style, regrow=False)
    tiers = ["hero", "main", "npc", "far"]
    for a in sys.argv[3:]:
        if a.startswith("tiers="):
            tiers = a[6:].split(",")
    out = f"{OUT}/{style}"
    t = time.time()
    r = hair.export_hair(name, out, tiers=tiers)
    print(style, "export", round(time.time() - t), "s", flush=True)
    chk = hair.check_tiers(name, r, save=f"{HR}/hu_{style}_tiers.png")
    print(hair.tiers_text(chk), flush=True)


if __name__ == "__main__":
    which = list(STYLES) if sys.argv[1] == "all" else sys.argv[1].split(",")
    mode = sys.argv[2] if len(sys.argv) > 2 else "plot"
    for s in which:
        {"plot": plot, "look": look, "cycles": lambda s: look(s, "cycles"), "export": export}[mode](s)
