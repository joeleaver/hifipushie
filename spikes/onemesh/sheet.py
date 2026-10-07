"""The template's hand-check sheets: the neutral, loop close-ups (neck bridge, eyes, mouth, ears), the uv layout and
skin weights round the neck, from the asset itself (src/hifipushie/human_mesh.npz).

    uv run python spikes/onemesh/sheet.py <out dir> [prefix]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import wire  # noqa: E402


def main():
    out = Path(sys.argv[1])
    pre = sys.argv[2] if len(sys.argv) > 2 else "om_01"
    z = np.load(Path(__file__).parents[2] / "src/hifipushie/human_mesh.npz")
    V = z["neutral"].astype(float) + z["offset"]
    F, part = z["faces"], z["part"]
    n0, n_ring, n_all, nb0 = (int(x) for x in z["bridge"])
    col = np.tile(np.array([205, 200, 192]), (len(F), 1))
    gn = (z["gnm_id"][F] >= 0).all(1)
    col[gn] = [222, 196, 170]
    col[nb0:] = [150, 190, 235]
    for pid, c in ((1, (200, 120, 120)), (2, (240, 240, 250)), (3, (240, 240, 250)), (4, (250, 245, 225)), (5, (250, 245, 225)), (6, (215, 120, 130))):
        col[part == pid] = c
    skin = part == 0
    top = V[:, 2].max()
    # 1. the neutral, whole and bust
    c = np.array([0, 0, top / 2])
    ims = [wire.view(V, F[skin], c, top * 1.08, az=a, px=900, colors=col[skin], line=0, title=t)
           for a, t in ((0, "the neutral (MakeHuman 25 y, sex 0.5; GNM's mean on it): front"), (90, "its left"), (180, "back"))]
    cb = np.array([0, 0, top - 0.2])
    ims += [wire.view(V, F[skin], cb, 0.62, az=a, el=e, px=900, colors=col[skin], line=1, title=t)
            for a, e, t in ((0, 0, "bust, wire: body (grey) | bridge (blue) | GNM (tan)"), (60, 5, "3/4"), (180, 5, "back"))]
    wire.sheet(ims, 3, out / f"{pre}_neutral.png")
    # 2. the neck bridge
    cn = V[n0:].mean(0) + [0, 0, 0.015]
    ims = [wire.view(V, F[skin], cn, 0.2, az=a, el=e, px=1000, colors=col[skin], title=t) for a, e, t in
           ((0, 0, "neck bridge, front: A 110 -> 82 -> 58 -> C 42"), (45, 5, "3/4 front"), (90, 0, "its left"),
            (135, 10, "3/4 back"), (180, 5, "back"), (0, -45, "from below (throat)"))]
    wire.sheet(ims, 3, out / f"{pre}_neck.png")
    # 3. eyes, mouth, ears
    gi = z["gnm_id"]
    eyeL = V[(z["part"][np.searchsorted(np.arange(len(F)), np.arange(len(F)))] == 2)[:, None].repeat(4, 1).ravel().nonzero()[0] // 4] if False else None
    ce = V[np.unique(F[part == 2])].mean(0)
    cm = V[np.unique(F[part == 4])].mean(0) + [0, -0.03, -0.004]
    ear = V[np.argmax(V[:, 0] * (V[:, 2] > top - 0.2))]
    ims = [wire.view(V, F, ce + [0, -0.02, 0], 0.07, az=0, px=1000, colors=col, title="left eye, front (skin + eyeball)"),
           wire.view(V, F, ce + [0, -0.02, 0], 0.07, az=60, px=1000, colors=col, title="left eye, 3/4"),
           wire.view(V, F[skin], ce + [0, -0.02, 0], 0.07, az=0, px=1000, colors=col[skin], title="left eye, skin only: lid loops"),
           wire.view(V, F, cm, 0.1, az=0, px=1000, colors=col, title="mouth, front (GNM's mean: lips parted)"),
           wire.view(V, F[skin], cm, 0.1, az=50, px=1000, colors=col[skin], title="mouth, 3/4"),
           wire.view(V, F[~skin], cm + [0, 0.03, 0], 0.11, az=35, el=15, px=1000, colors=col[~skin], back=True,
                     title="inside: teeth, gums, tongue, mouth sock, eyeballs (GNM's own)"),
           wire.view(V, F[skin], ear + [-0.01, 0, 0], 0.11, az=90, px=1000, colors=col[skin], title="left ear"),
           wire.view(V, F[skin], ear + [-0.01, 0, 0], 0.11, az=150, el=5, px=1000, colors=col[skin], title="left ear, from behind"),
           wire.view(V, F[skin], np.array([0, 0, top - 0.11]), 0.3, az=0, px=1000, colors=col[skin], title="face")]
    wire.sheet(ims, 3, out / f"{pre}_face_loops.png")
    # 4. uv layout
    px = 2000
    im = Image.new("RGB", (px, px), (250, 250, 250))
    d = ImageDraw.Draw(im)
    uv = z["uv"]
    for k in np.argsort(part != 0):
        q = [(float(u) * px, (1 - float(v)) * px) for u, v in uv[k]]
        d.polygon(q, fill=tuple(int(x) for x in col[k]), outline=(60, 60, 70))
    d.text((10, 10), "one uv layout: MakeHuman's body (left 60%), GNM's head (right 40%); bridge in blue continues GNM's island", fill=(0, 0, 0))
    im.save(out / f"{pre}_uv.png")
    # 5. skin weights round the neck
    bones = [str(b) for b in z["bones"]]
    W = np.zeros((len(V), len(bones)), np.float32)
    np.put_along_axis(W, z["w_idx"].astype(int), z["w"], 1)
    ims = []
    for bn in ("spine02", "spine01", "neck01", "neck02", "neck03", "head", "jaw", "clavicle.L", "shoulder01.L"):
        w = W[:, bones.index(bn)]
        fw = w[F].mean(1)
        cw = (np.array([70, 80, 200])[None] * (1 - fw[:, None]) + np.array([240, 60, 40])[None] * fw[:, None])
        cw = np.where((fw > 0.002)[:, None], cw, 190)
        for a in (0, 90):
            ims.append(wire.view(V, F[skin], cn + [0, 0, 0.06], 0.42, az=a, px=520, colors=cw[skin], line=0,
                                 title=f"{bn} (grey 0, blue low, red 1)"))
    wire.sheet(ims, 6, out / f"{pre}_weights.png")
    print("wrote", [p.name for p in sorted(out.glob(pre + "_*.png"))])


if __name__ == "__main__":
    main()
