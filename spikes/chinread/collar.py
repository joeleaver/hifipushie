"""collar.py: a GARMENT laid into a dressed benchmark picture in true depth order (the cloth-edge read's validation): a
collar as a vertical cylinder round the neck (radius 72 mm about the neck's axis, its top edge `top` mm above the chin's
lowest point), drawn wherever it stands in FRONT of the model's own surface (or of the backdrop). The chin (33 mm in front
of it) and the jaw's angles (above it) stay bare; the jaw's body and the chin's underside run down into it, as into a high
collar or a hood; with the head tilted down the whole chin stands in front of it.
  dress(img, head, cam, top=8) -> the picture with the garment, the garment's mask
  python collar.py <truth model> <view> <out.png> [top mm]   a look (+ the cloth reads on it)"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from hifipushie import face_ruler as fr, humanfit


def dress(img, head, cam, top=8.0, radius=0.072, colour=(132, 134, 140), seed=0):
    L = np.asarray(head["L"], float)
    _, ps = fr.clay(head, cam, passes=True)
    zb = ps["zb"]
    H, W = zb.shape
    w, h = cam["size"]
    Rc = humanfit._cam_rot(cam)
    k = H / float(h)
    u, v = np.meshgrid((np.arange(W) + 0.5) / k, (np.arange(H) + 0.5) / k)
    d = np.stack([(u - w / 2) / cam["f"], (v - h / 2) / cam["f"], np.ones_like(u)], -1)          # camera-frame ray, z = 1
    o = np.asarray(cam["centre"], float) - np.asarray(cam["t"], float) @ Rc                      # the camera's eye, world
    dw = d @ Rc                                                                                  # world direction per unit depth
    ax = np.array([0.0, float(L[[2, 14], 1].mean()) + 0.010])
    ztop = float(L[8, 2]) + top * 1e-3
    px, py = o[0] - ax[0], o[1] - ax[1]
    a = dw[..., 0] ** 2 + dw[..., 1] ** 2
    b = 2 * (px * dw[..., 0] + py * dw[..., 1])
    c = px ** 2 + py ** 2 - radius ** 2
    disc = b ** 2 - 4 * a * c
    s = np.where(disc > 0, (-b - np.sqrt(np.maximum(disc, 0))) / np.maximum(2 * a, 1e-12), np.inf)
    z = o[2] + s * dw[..., 2]
    m = (disc > 0) & (s > 0) & (z < ztop) & (s < zb - 0.001)
    if m.shape != (img.size[1], img.size[0]):
        m = np.asarray(Image.fromarray(m).resize(img.size, Image.NEAREST))
    rng = np.random.default_rng(seed)
    tex = np.asarray(colour, float)[None, None] * (1.0 + 0.2 * ndi.gaussian_filter(rng.standard_normal(m.shape), 3.0)[..., None])
    yy = np.linspace(1.05, 0.9, m.shape[0])[:, None, None]
    al = ndi.gaussian_filter(m.astype(float), 0.7)[..., None]
    out = np.asarray(img.convert("RGB"), float) * (1 - al) + np.clip(tex * yy, 0, 255) * al
    return Image.fromarray(out.astype(np.uint8)), m


def picture(T, vi):
    """A truth model's own dressed picture of view vi (mkhead's, or solvereads')."""
    import os
    from hifipushie import blockin as bi
    f = bi._refs(T)["views"][vi]["image"]
    if not os.path.basename(f).startswith(("cz_", "sx_")):
        f = f"/mnt/data/hifipushie/solvereads/synth/{T[:-2]}_{vi}.png"
    return Image.open(f).convert("RGB")


if __name__ == "__main__":
    from PIL import ImageDraw
    from hifipushie import blockin as bi, store
    T, vi, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    cam = bi._refs(T)["cameras"][vi]
    head = fr.model_head(store.load(T))
    im, m = dress(picture(T, vi), head, cam, top=float(sys.argv[4]) if len(sys.argv) > 4 else 8.0)
    v = {"img": im, "cam": cam, "kind": fr.kind_of(abs(fr.view_yaw(cam))), "style": "photo", "chin": {"cloth": True}}
    _, ps = fr.clay(head, cam, passes=True)
    ob = fr._cloth_obs(head, v, ps)
    o = np.array([x["o"] for x in ob])
    print(T, vi, "cloth reads", len(o), (f"bias {o.mean():+.2f} rms {np.sqrt((o ** 2).mean()):.2f}" if len(o) else ""))
    a = np.asarray(im, float)
    pm = v.get("_parse")
    if pm:
        a[..., 2] = np.clip(a[..., 2] + 70 * (pm["cloth"] > 0.5), 0, 255)
        a[..., 0] = np.clip(a[..., 0] + 50 * (pm["skin"] > 0.5), 0, 255)
    im2 = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(im2)
    for x in ob:
        d.line([tuple(x["p"]), tuple(x["q"])], fill=(255, 255, 0), width=2)
        d.ellipse([x["p"][0] - 3, x["p"][1] - 3, x["p"][0] + 3, x["p"][1] + 3], fill=(0, 220, 0))
        d.ellipse([x["q"][0] - 2, x["q"][1] - 2, x["q"][0] + 2, x["q"][1] + 2], fill=(255, 0, 0))
    W = Image.new("RGB", (im.size[0] * 2, im.size[1]))
    W.paste(im, (0, 0)); W.paste(im2, (im.size[0], 0))
    W.resize((W.size[0] * 2 // 3, W.size[1] * 2 // 3)).save(out)
    print(out)
