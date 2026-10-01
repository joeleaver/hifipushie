"""Images for the decal examples (examples/image_decals_src.py), drawn procedurally so nothing third-party ships:
landscape.jpg (a painted landscape for the framed painting) and logo.png (a disc golf brand stamp with alpha).

    uv run python examples/images/make_images.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent


def _ridge(rng, w, base, amp, rough):
    """A mountain/hill outline: y per x (fractal midpoint noise)."""
    n = 1
    y = np.array([base + rng.uniform(-amp, amp), base + rng.uniform(-amp, amp)])
    a = amp
    while n < w:
        mid = (y[:-1] + y[1:]) / 2 + rng.uniform(-a, a, len(y) - 1)
        out = np.empty(len(y) * 2 - 1)
        out[0::2], out[1::2] = y, mid
        y, n, a = out, len(out), a * rough
    return np.interp(np.arange(w), np.linspace(0, w - 1, len(y)), y)


def landscape(W=1024, H=768, seed=3):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W] / np.array([H, W])[:, None, None]
    img = np.zeros((H, W, 3))
    horizon = 0.56
    # sky: warm near the horizon, blue above
    t = np.clip(yy / horizon, 0, 1)[..., None]
    img[:] = (1 - t) * np.array([0.33, 0.52, 0.80]) + t * np.array([0.98, 0.84, 0.62])
    # sun glow
    d = np.hypot(xx - 0.72, (yy - 0.36) * H / W)
    img += (np.exp(-(d / 0.05) ** 2) * 0.6 + np.exp(-(d / 0.18) ** 2) * 0.18)[..., None] * np.array([1.0, 0.85, 0.5])
    layers = [(0.42, 0.06, 0.55, [0.50, 0.55, 0.72]), (0.47, 0.05, 0.6, [0.36, 0.44, 0.58]),
              (0.53, 0.035, 0.62, [0.22, 0.36, 0.30]), (0.60, 0.03, 0.55, [0.27, 0.45, 0.24])]
    lake = (yy > 0.64) & (yy < 0.80)
    for base, amp, rough, col in layers:
        r = _ridge(rng, W, base, amp, rough) * H
        m = np.arange(H)[:, None] > r[None, :]
        shade = 1 - 0.25 * np.clip((np.arange(H)[:, None] - r[None, :]) / (0.2 * H), 0, 1)
        img[m] = (np.array(col) * shade[..., None])[m]
    # a lake reflecting the sky, ripples across
    rip = 0.04 * np.sin(yy * 260 + np.sin(xx * 40) * 2)
    refl = (1 - 0.6 * (yy - 0.64) / 0.16)[..., None] * np.array([0.55, 0.66, 0.82]) + rip[..., None]
    img[lake] = refl[lake]
    fg = yy >= 0.80
    img[fg] = (np.array([0.35, 0.42, 0.18]) * (1 - 0.3 * (yy - 0.8) / 0.2)[..., None] + 0.03 * rng.standard_normal((H, W, 1)))[fg]
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    # trees on the near shore: dark cones
    for x in rng.uniform(0.03, 0.42, 9):
        h = rng.uniform(0.10, 0.2) * H
        X, Y = x * W, 0.82 * H
        dr.polygon([(X - h * 0.22, Y), (X + h * 0.22, Y), (X, Y - h)], fill=(30, 58, 36))
        dr.line([(X, Y), (X, Y + 8)], fill=(60, 40, 25), width=4)
    # brushwork: short strokes in each spot's own colour, jittered, laid along the land (horizontal-ish)
    a = np.asarray(im).astype(np.float64)
    out = im.copy()
    dr = ImageDraw.Draw(out)
    for _ in range(26000):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        c = a[int(y), int(x)] * rng.uniform(0.9, 1.1) + rng.normal(0, 6, 3)
        ang = rng.normal(0, 0.35) + (0 if y > horizon * H else rng.normal(0, 0.6))
        L = rng.uniform(6, 18)
        dx, dy = np.cos(ang) * L / 2, np.sin(ang) * L / 2
        dr.line([(x - dx, y - dy), (x + dx, y + dy)], fill=tuple(int(v) for v in np.clip(c, 0, 255)),
                width=int(rng.integers(3, 7)))
    return out.filter(ImageFilter.SMOOTH)


def logo(S=1024):
    """A round brand stamp: a ring, a stylised basket and the name round the rim, on transparent."""
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    ink = (196, 32, 40, 255)
    dr.ellipse([20, 20, S - 20, S - 20], outline=ink, width=36)
    dr.ellipse([110, 110, S - 110, S - 110], outline=ink, width=10)
    # a basket: pole, chains, tray
    c = S / 2
    dr.rectangle([c - 14, 300, c + 14, 720], fill=ink)
    dr.ellipse([c - 170, 270, c + 170, 330], outline=ink, width=22)
    for k in range(-4, 5):
        dr.line([(c + k * 38, 300), (c + k * 14, 560)], fill=ink, width=9)
    dr.rectangle([c - 150, 560, c + 150, 640], fill=ink)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 84)
    dr.text((c, 790), "PEBBLE", font=font, fill=ink, anchor="mm")
    font2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
    dr.text((c, 200), "DISC GOLF", font=font2, fill=ink, anchor="mm")
    return im


if __name__ == "__main__":
    landscape().save(HERE / "landscape.jpg", quality=88)
    logo().save(HERE / "logo.png", optimize=True)
    for f in ("landscape.jpg", "logo.png"):
        print(f, (HERE / f).stat().st_size // 1024, "KB")
