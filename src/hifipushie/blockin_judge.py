"""The block-in's JUDGING sheet (promoted from spikes/reruns/jsheet.py; block_in_look(judge=True)): a clay head reads
younger and softer than the person, so a head is judged wearing the pictures. Per reference view: photo | 50 % blend |
the head with the pictures projected as its skin | the clay under the photo's light.

The spike shot this in Blender through a scratch stage; here it is the block-in's own software render, so the sheet
costs a look, not a scene sync. The pictures go on through their fitted cameras, the front last (most trusted, as in
the spike), so a turned view shows the front picture on the turned head: where it smears or doubles, the geometry is
wrong there. Picture pixels are for judging only: nothing here reaches the model."""
import numpy as np
from PIL import Image, ImageDraw

from . import blockin as bi, humanfit, likeness as lk, likeness_read as lr, store

SOURCE_PX = 1000   # a picture's own depth map (visibility), long side


def _source(mesh: dict, cam: dict, view: dict) -> dict:
    """A picture and its camera's depth map."""
    w, h = cam["size"]
    _, k, ps = lk.render(mesh, cam, (0.0, 0.0, float(w), float(h)), px=min(max(w, h), SOURCE_PX), passes=True)
    return {"photo": np.asarray(Image.open(view["image"]).convert("RGB"), float), "cam": cam, "k": k, "zb": ps["zb"],
            "R": humanfit._cam_rot(cam)}


def _lay(img: np.ndarray, X: np.ndarray, n: np.ndarray, ii: np.ndarray, jj: np.ndarray, s: dict) -> None:
    """The picture s laid on img at the surface points X (world, normals n) its camera sees."""
    cam, zs = s["cam"], s["zb"]
    w, h = cam["size"]
    Xs = (X - np.asarray(cam["centre"], float)) @ s["R"].T + np.asarray(cam["t"], float)
    u, v = cam["f"] * Xs[:, 0] / Xs[:, 2] + w / 2, cam["f"] * Xs[:, 1] / Xs[:, 2] + h / 2
    a, b = np.round(v * s["k"] - 0.5).astype(int), np.round(u * s["k"] - 0.5).astype(int)
    ok = (a >= 0) & (a < zs.shape[0]) & (b >= 0) & (b < zs.shape[1]) & (u >= 0) & (u < w - 1) & (v >= 0) & (v < h - 1)
    vis = np.zeros(len(X), bool)
    vis[ok] = Xs[ok, 2] < zs[a[ok], b[ok]] + lr.PROJECT_TOL
    to_cam = -(Xs / np.linalg.norm(Xs, axis=1, keepdims=True)) @ s["R"]
    vis &= (n * to_cam).sum(1) > lr.PROJECT_GRAZE
    x0, y0 = np.floor(u[vis]).astype(int), np.floor(v[vis]).astype(int)
    fx, fy = (u[vis] - x0)[:, None], (v[vis] - y0)[:, None]
    ph = s["photo"]
    img[ii[vis], jj[vis]] = (ph[y0, x0] * (1 - fx) * (1 - fy) + ph[y0, x0 + 1] * fx * (1 - fy)
                             + ph[y0 + 1, x0] * (1 - fx) * fy + ph[y0 + 1, x0 + 1] * fx * fy)


def _skinned(mesh: dict, cam: dict, box: tuple, sources: list, px: int) -> tuple:
    """(the head with the pictures as its skin, the same head's clay) through cam, cropped to box."""
    im, k, ps = lk.render(mesh, cam, box, px=px, passes=True)
    zb = ps["zb"]
    on = np.isfinite(zb)
    ii, jj = np.nonzero(on)
    z = zb[ii, jj]
    u, v = box[0] + (jj + 0.5) / k, box[1] + (ii + 0.5) / k
    w, h = cam["size"]
    Xc = np.c_[(u - w / 2) / cam["f"] * z, (v - h / 2) / cam["f"] * z, z]
    Rc = humanfit._cam_rot(cam)
    X = (Xc - np.asarray(cam["t"], float)) @ Rc + np.asarray(cam["centre"], float)
    n = ps["nrm"][ii, jj] @ Rc
    clay = np.asarray(im.convert("RGB"), float)
    img = clay * 0.45 + 40.0                     # (skin no picture sees: dim clay)
    img[~on] = 200.0
    for s in sources:
        _lay(img, X, n, ii, jj, s)
    return Image.fromarray(img.astype(np.uint8)), im.convert("RGB")


def sheet(name: str, out: str, views: list | None = None, T: int = 420) -> dict:
    """The judging sheet of block-in model name. -> {"out", "views"}."""
    rj = bi._refs(name)
    base = store.load(name)["base"]
    VI = list(range(len(rj["views"]))) if views is None else [int(v) for v in views]
    every = range(len(rj["views"]))
    meshes = bi._per_view(base, rj, every, lambda b: bi.presented_mesh(b, rj=rj))
    boxes = (rj.get("blockin") or {}).get("boxes") or bi._boxes(base, rj)
    front = bi._front(rj)
    order = [i for i in every if i != front] + [front]
    cols = ("photo", "50% blend (photo + projected)", "the pictures projected as skin", "clay")
    S = Image.new("RGB", (T * len(cols), 18 + (T + 4) * len(VI)), "white")
    dr = ImageDraw.Draw(S)
    for j, lab in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    for r, vi in enumerate(VI):
        cam, box = rj["cameras"][vi], tuple(float(x) for x in boxes[vi])
        mesh = meshes[vi]
        src = [_source(mesh, rj["cameras"][i], rj["views"][i]) for i in order]
        skin, clay = _skinned(mesh, cam, box, src, T)
        ph = Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((T, T), Image.LANCZOS)
        skin, clay = skin.resize((T, T)), clay.resize((T, T))
        for j, im in enumerate((ph, Image.blend(ph, skin, 0.5), skin, clay)):
            S.paste(im, (j * T, 18 + r * (T + 4)))
    S.save(out)
    return {"out": out, "views": VI}
