"""The eye ruler's picture reader on a drawn eye (known lids, corners, iris), with detector points that are off the
way MediaPipe's are (iris centre 1 mm low, lids 1 mm out, corners 1.5 mm wide)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from hifipushie import eye_ruler as er

MM = 0.2          # mm per picture px
SKIN = (205, 160, 135)


def lids(u, a=10.0, b=-12.5, top=2.2, bot=-4.6):
    """Upper / lower margin (mm, v up) of the drawn eye at u (mm toward the outer corner): parabolas between the canthi."""
    t = (u - b) / (a - b)
    k = np.clip(4 * t * (1 - t), 0, None)
    base = -2.5 + 0.6 * t                     # the canthal line: outer corner 0.6 mm higher
    return base + (top + 2.5 - 0.3) * k ** 0.8, base + (bot + 2.5 - 0.3) * k ** 0.9


def draw(r_iris=5.5, pd=60.0, brow=12.0, crease=4.5, caruncle=3.0):
    W, H = 900, 520
    S = 4                                      # supersampling
    im = Image.new("RGB", (W * S, H * S), SKIN)
    d = ImageDraw.Draw(im)
    cy = 300.0
    cs = [(W / 2 - pd / 2 / MM, cy), (W / 2 + pd / 2 / MM, cy)]       # subject's right eye = the picture's left
    P = np.zeros((478, 2))
    P[168], P[152] = (W / 2, cy - 40), (W / 2, cy + 400)
    for s, (cx, _) in enumerate(cs):
        sg = -1 if s == 0 else 1               # picture x of the outer side
        X = lambda u: (cx + sg * u / MM) * S   # noqa: E731
        Y = lambda v: (cy - v / MM) * S        # noqa: E731
        uu = np.linspace(-12.5, 10.0, 240)
        up, lo = lids(uu)
        poly = [(X(u), Y(v)) for u, v in zip(uu, up)] + [(X(u), Y(v)) for u, v in zip(uu[::-1], lo[::-1])]
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).polygon(poly, fill=255)
        ball = Image.new("RGB", im.size, (228, 222, 216))
        bd = ImageDraw.Draw(ball)
        ri = r_iris / MM * S
        bd.ellipse([X(0) - ri, Y(0) - ri, X(0) + ri, Y(0) + ri], fill=(95, 85, 60))
        bd.ellipse([X(0) - ri, Y(0) - ri, X(0) + ri, Y(0) + ri], outline=(40, 32, 22), width=int(0.3 / MM * S))
        bd.ellipse([X(0) - 0.35 * ri, Y(0) - 0.35 * ri, X(0) + 0.35 * ri, Y(0) + 0.35 * ri], fill=(8, 8, 8))
        x0, x1 = sorted((X(-12.5), X(-12.5 + caruncle)))
        bd.rectangle([x0, 0, x1, im.size[1]], fill=(150, 88, 80))     # the caruncle: wet dark red at the inner corner
        im.paste(ball, (0, 0), mask)
        lash = uu > -10.5                      # (no lashes over the inner ~12 %: the caruncle's corner)
        d.line([(X(u), Y(v + 0.45)) for u, v in zip(uu[lash], up[lash])], fill=(60, 38, 28), width=int(0.9 / MM * S))   # lash line
        d.line([(X(u), Y(v - 0.2)) for u, v in zip(uu[lash], lo[lash])], fill=(170, 110, 100), width=int(0.4 / MM * S))  # waterline
        d.line([(X(u), Y(v + crease)) for u, v in zip(uu[20:-10], up[20:-10])], fill=(150, 105, 85), width=int(0.5 / MM * S))
        ub = np.linspace(-13, 14, 60)
        for off in np.linspace(0, 5.0, 40):
            d.line([(X(u), Y(np.interp(u, uu, up) + brow + off + 0.02 * (u + 2) ** 2 * 0)) for u in ub], fill=(70, 52, 40), width=int(0.3 / MM * S))
        # the detector: iris centre 1 mm LOW and its radius 10 % small, lids 1 mm outside, corners 1.5 mm wide
        ic, rim = (468, (469, 470, 471, 472)) if s == 0 else (473, (474, 475, 476, 477))
        c = np.array([cx, cy + 1.0 / MM])
        P[ic] = c
        for i, a in zip(rim, (0, 90, 180, 270)):
            P[i] = c + 0.9 * r_iris / MM * np.array([np.cos(np.radians(a)), np.sin(np.radians(a))])
        us = np.linspace(11.5, -14.0, 9)
        upd, lod = lids(np.clip(us, -12.4, 9.9))
        for i, u, v in zip(er.UPPER[s], us, upd):
            P[i] = (cx + sg * u / MM, cy - (v + 1.0) / MM)
        for i, u, v in zip(er.LOWER[s], us, lod):
            P[i] = (cx + sg * u / MM, cy - (v - 1.0) / MM)
        P[er.UPPER[s][0]] = P[er.LOWER[s][0]] = (cx + sg * 11.5 / MM, cy + 2.2 / MM)
        P[er.UPPER[s][-1]] = P[er.LOWER[s][-1]] = (cx - sg * 14.0 / MM, cy + 2.5 / MM)
        for i, u in zip(er.BROW_LOW[s], np.linspace(12, -11, 5)):
            P[i] = (cx + sg * u / MM, cy - (float(np.interp(u, uu, up)) + brow + 1.0) / MM)
    return im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6)), P


def test_read_drawn_eye():
    im, P = draw()
    for e in er.read(im, P, MM):
        cols = er.COLS
        up, lo = lids(cols)
        assert abs(e["iris"] - 11.0) < 0.35, e["iris"]
        # the iris centre is the circle's, not the detector's (1 mm low): the margins come out in the true frame
        got_up, got_lo = np.array(e["up"]), np.array(e["lo"])
        mid = np.abs(cols) <= 6
        assert np.nanmax(np.abs(got_up[mid] - up[mid])) < 0.45, (got_up, up)
        assert np.nanmax(np.abs(got_lo[mid] - lo[mid])) < 0.6, (got_lo, lo)
        assert abs(e["inner"][0] + 12.5) < 1.3, e["inner"]   # (the blurred tip reads up to 1 mm long)
        assert abs(e["outer"][0] - 10.0) < 0.9, e["outer"]
        assert abs(e["fissure"] - 22.5) < 1.5, e["fissure"]
        assert 1.5 < e["caruncle"] < 4.5, e["caruncle"]
        assert abs(e["mrd1"] - lids(np.array([0.0]))[0][0]) < 0.4
        cr = np.array(e["crease"])[mid]
        assert np.nanmax(np.abs(cr - 4.5)) < 0.9, cr
        br = np.array(e["brow"])[mid]
        assert np.nanmax(np.abs(br - 12.0)) < 1.2, br


def test_limbus_circle_under_a_lid():
    """A disc whose top third is covered: the circle's centre and radius still come from the side arcs."""
    N = 400
    y, x = np.mgrid[0:N, 0:N].astype(float)
    lum = np.full((N, N), 0.85)
    lum[np.hypot(x - 200, y - 190) < 60] = 0.25
    lum[y < 160] = 0.6                              # the lid
    c, r, n = er.limbus_circle(lum, (203.0, 205.0), 52.0, np.array([1.0, 0.0]), np.array([0.0, 1.0]))
    assert n >= 8 and abs(r - 60) < 1.5 and np.linalg.norm(c - [200, 190]) < 1.5, (c, r, n)


def test_frames_point_outward():
    fr = er.frames((100.0, 50.0), (300.0, 54.0))
    assert fr[0]["ex"][0] < 0 < fr[1]["ex"][0] and fr[0]["ey"][1] > 0.99



def test_crease_path_and_picture(tmp_path, monkeypatch):
    """The fold line as paint: the picture's path from a read, and its alpha picture (a line where the path is)."""
    from PIL import Image as _I
    from hifipushie import images, skin_swatch
    m = {"crease_dark": 0.2, "up": [0, 1.3, 2.0, 2.1, 1.8, 0.9, -0.9], "crease": [5.2, 4.5, 4.5, 4.7, 4.8, 5.0, 5.5]}
    p = er.crease_path(m)
    assert len(p) == 7 and abs(p[3][1] - 6.8) < 1e-6 and p[0][0] == -9.0
    assert er.crease_path({**m, "crease_dark": 0.02}) is None
    monkeypatch.setattr(images, "store_dir", lambda: tmp_path)
    f = skin_swatch.crease_image(p, 0.5)
    a = np.asarray(_I.open(f))[..., 3]
    ys, xs = np.nonzero(a > 60)
    # canvas 40 x 30 mm at 32 px / mm, centre (0, 3): the pupil column's line at v ~6.8 -> row 480 - 3.8 * 32
    col = a[:, 640]
    assert abs(int(np.argmax(col)) - (480 - 3.8 * 32)) < 8 and xs.min() > 320 and xs.max() < 960


if __name__ == "__main__":
    test_read_drawn_eye()
    test_limbus_circle_under_a_lid()
    test_frames_point_outward()
    print("ok")
