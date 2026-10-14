"""orange.py <model> ...: one table: mid-cheek and under-eye patch colours (Lab, hue deg, chroma) of the photo (front view,
lit as shot), the de-lit atlas, the stack's recomposition, our procedural skin (no stack, no projection) and the base tone."""
import copy, sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, likeness as lk, skin, skin_project as sp, store, images
def lch(lin):
    L = sp.lab(np.asarray(lin, float)[None])[0]
    return f"L {L[0]:5.1f} a {L[1]:5.1f} b {L[2]:5.1f} hue {np.degrees(np.arctan2(L[2], L[1])):5.1f} C {np.hypot(L[1], L[2]):4.1f}"
for m in sys.argv[1:]:
    spec = store.load(m); rj = bi._refs(m); at = sp.atlas(spec["base"]); regs = sp.region_masks(at)
    pj = spec["skin"]["projection"]
    alb = sp._lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
    cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0][at["ii"], at["jj"]] / 255.0
    rec_p = store._dir(m) / "skin_layers" / "recomposed.png"
    rec = sp._lin(np.asarray(Image.open(rec_p).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]] if rec_p.exists() else None
    s2 = copy.deepcopy(spec); s2["skin"].pop("stack", None)
    ours = sp.ours_albedo(at, s2, log=lambda s: None)
    vi = bi._front(rj)
    mesh = bi._per_view(spec["base"], rj, [vi], lambda b: lk.model_mesh(b))[vi]
    ph = np.asarray(Image.open(rj["views"][vi]["image"]).convert("RGB"))
    smp = sp.sample_view(at, mesh, rj["cameras"][vi], ph)
    tone = sp._lin(np.asarray(skin.tone_rgb(skin.params(spec)["tone"]), float))
    print(f"\n{m} (tone sRGB {skin.tone_rgb(skin.params(spec)['tone'])}):")
    for nm, q in (("mid-cheek", regs["cheek"]), ("under-eye", regs["under_eye"])):
        q = q & (cf > 0.6) & smp["vis"]
        print(f"  {nm} ({int(q.sum())} texels)")
        print(f"    photo, lit      {lch(np.median(smp['rgb'][q], 0))}")
        print(f"    atlas, de-lit   {lch(np.median(alb[q], 0))}")
        if rec is not None:
            print(f"    stack recomp.   {lch(np.median(rec[q], 0))}")
        print(f"    ours, no stack  {lch(np.median(ours[q], 0))}")
    print(f"  base tone          {lch(tone)}")
