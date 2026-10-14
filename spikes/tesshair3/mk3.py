"""mk3.py <dst> <head model> <style.json | '{json}'> [from=<model: hairline + look>] [seed=3]: dst = the head model's
spec wearing a tied STYLE (groom.tied, hair_flow.style) and nothing else: the hairline and look are taken from `from`
(default th_T66: Tess's traced hairline; "none" = the head's default hairline and look). Only writes th_* models.
Prints the lock counts; plot=1 also draws the locks' lines from four sides ($TOUT/locks_<dst>.png: no Blender)."""
import copy, json, os, shutil, sys, time
import numpy as np
from hifipushie import hair, store

dst, head, st = sys.argv[1:4]
kw = dict(a.split("=", 1) for a in sys.argv[4:])
assert dst.startswith("th_"), dst
tied = json.loads(st) if st.lstrip().startswith("{") else json.load(open(st))
sp = copy.deepcopy(store.load(head))
src = kw.get("from", "th_T66")
groom = {"tied": tied, "seed": int(kw.get("seed", 3))}
h = {"style": "strands", "groom": groom}
if src != "none":
    hs = hair.carry(src)
    groom["hairline"] = hs["groom"]["hairline"]
    groom["fit"] = hs["groom"]["fit"]
    h["look"] = hs.get("look") or {}
    sp.setdefault("parts", {})["hair"] = copy.deepcopy((store.load(src).get("parts") or {}).get("hair") or {})
elif kw.get("look"):
    h["look"] = copy.deepcopy(store.load(kw["look"])["hair"].get("look") or {})
    sp.setdefault("parts", {})["hair"] = copy.deepcopy((store.load(kw["look"]).get("parts") or {}).get("hair") or {})
sp["hair"] = h
d = store.HOME / dst
d.mkdir(exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
if (store.HOME / head / "human_refs.json").exists():
    shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
t = time.time()
r = hair.groom(dst, replace=True, note=f"tesshair3: tied style on {head}")
print(str(r)[:600], f"{time.time() - t:.0f} s")

if kw.get("plot"):
    from PIL import Image, ImageDraw
    sp = store.load(dst)
    sc = hair.scalp(dst, sp)
    L = sp["hair"]["locks"]
    A, E = np.meshgrid(np.arange(0, 360, 5.0), np.arange(-60, 90, 5.0))
    H = sc.point(A.ravel(), E.ravel(), 0.0) - sc.C
    views = {"front": ([1, 0, 0], [0, 0, 1], [0, -1, 0]), "left": ([0, 1, 0], [0, 0, 1], [1, 0, 0]),
             "back": ([-1, 0, 0], [0, 0, 1], [0, 1, 0]), "top": ([1, 0, 0], [0, 1, 0], [0, 0, 1]),
             "right": ([0, -1, 0], [0, 0, 1], [-1, 0, 0])}
    N, k = 520, 520 / 0.46
    im = Image.new("RGB", (N * 5, N), "white")
    dr = ImageDraw.Draw(im)
    for vi, (vn, (ex, ey, ez)) in enumerate(views.items()):
        ex, ey, ez = (np.asarray(v, float) for v in (ex, ey, ez))
        px = lambda P: np.stack([vi * N + N / 2 + (P @ ex) * k, N * 0.32 - (P @ ey) * k], 1)  # noqa: E731
        for q in px(H[H @ ez > 0]):
            dr.ellipse([q[0] - 2, q[1] - 2, q[0] + 2, q[1] + 2], fill="#e2c4ac")
        for n, lk in L.items():
            P = hair.lock_world(sc, lk, lk["pts"]) - sc.C
            c = "#c22" if lk.get("hairs") else "#247" if lk.get("free") else "#421"
            Q = px(P)
            for j in range(len(P) - 1):
                if P[j] @ ez > -0.01 and P[j + 1] @ ez > -0.01:
                    dr.line([tuple(Q[j]), tuple(Q[j + 1])], fill=c, width=2)
        dr.text((vi * N + 8, 6), vn, fill="black")
    im.save(f"{os.environ['TOUT']}/locks_{dst}.png")
    print("plot", f"{os.environ['TOUT']}/locks_{dst}.png")
