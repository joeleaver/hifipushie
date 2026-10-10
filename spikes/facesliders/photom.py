"""photom.py: faces6, the MACRO-SCALE PHOTOMETRIC term (stage M): what silhouettes and landmark positions can't see, the
depth of the face's FRONT surfaces (cheek fullness, eye depth, brow ridge, nasolabial depth), read from shading the
way the photo shows it.

Per view (front, 3/4): the face box at ~PX_MM mm per pixel; the photo's GREEN channel, linearised (discounts the
cheeks' and lips' redness); a mask = the detector's skin mask (oval, minus brows, eyes, lips, nostrils, forehead
above the brows + 25 mm) AND the model's skin AND not hair (photo darker than HAIR_K x the skin median) AND the
model's own eye / brow / lip neighbourhood. The model is shaded by the photo's light fitted on its normals / AO / key
visibility (the linear model c0 (1 - aw + aw ao) + max(w.n, 0) lit + min(w.n, 0), likeness.render's light=) times a
SMOOTH ALBEDO (a quadratic in the picture's x / y, log domain: paint can't satisfy the term at the macro scale), the
two fitted alternately. The residual: log(photo) - log(model shade) - log(albedo), low-passed with a Gaussian of
LP_MM, sampled every LP_MM on the mask. Its Jacobian over identity directions by finite differences on the mesh
(vertices move linearly with the identity: VB, like fit5.border_model), light and albedo held.
"""
import os

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from hifipushie import headfit

headfit.N = 170   # (as fit5: all head comps; set before headfit._gnm() is first called)
from hifipushie import base as basemod, humanfit, likeness, likeness_shape as ls, onemesh  # noqa: E402

PX_MM = float(os.environ.get("PX_MM", "0.8"))
LP_MM = float(os.environ.get("LP_MM", "3.0"))
HAIR_K = 0.55
FD_H = float(os.environ.get("FD_H", "0.5"))
SHADOW = os.environ.get("PH_SHADOW", "0") == "1"   # (hard shadows toggle per FD step: off by default)
ALB_RIDGE = float(os.environ.get("ALB_RIDGE", "0.05"))
INNER = float(os.environ.get("PH_INNER", "0.8"))   # the mask: inside the face oval scaled by this about its centre


def vertex_basis(st):
    """(170, n, 3): each mesh vertex's world move per identity unit (0 off GNM's head; faded to the stitch)."""
    g = basemod._gnm_data()
    tpl = st["tpl"]
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    c = st["head"]["carry"]
    R, s = np.asarray(c["R"], float), float(c["s"])
    hg = headfit._gnm()
    jm = hg["JB"].mean(1)
    fade = np.asarray(onemesh.asset()["g_fade"], float)[np.maximum(gid, 0)] * (gid >= 0)
    IB = np.asarray(g["vertex_identity_basis"], float)[hg["comps"]]
    out = s * (IB[:, np.maximum(gid, 0)] - jm[:, None, :]) @ R.T * fade[None, :, None]
    return out.astype(np.float32)


class View:
    def __init__(self, view, cam, mesh, P_photo):
        self.cam = cam
        self.img = Image.open(view["image"]).convert("RGB")
        P = np.asarray(P_photo, float)[:, :2]
        lo, hi = P[likeness.OVAL].min(0), P[likeness.OVAL].max(0)
        c = 0.5 * (lo + hi)
        side = 1.15 * float(np.max(hi - lo))
        self.box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
        mmpx = likeness._mm_per_px(cam, mesh["L"][27:48])
        self.px = int(round(side * mmpx / PX_MM))
        self.k = self.px / side
        crop = self.img.crop(tuple(int(round(v)) for v in self.box)).resize((self.px, self.px), Image.LANCZOS)
        a = np.asarray(crop, float) / 255.0
        a = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
        self.Y = a[..., 1]                   # green: discounts redness (cheeks, lips)
        to_px = lambda Q: (np.asarray(Q, float) - [self.box[0], self.box[1]]) * self.k  # noqa: E731
        side_ = likeness.Side(P, None)
        sm = ls.skin_mask(side_, (self.px, self.px), to_px, self.k / mmpx)
        med = np.median(self.Y[sm]) if sm.any() else np.median(self.Y)
        self.mask0 = sm & (self.Y > HAIR_K * med)
        if INNER < 1:   # the face's middle only: the oval's outer band (grazing normals, hair shadow, the jaw's edge)
            # pulled the first fits' jaw wide and square (f6_14: width_jaw +9 mm) while the outline said otherwise
            from PIL import ImageDraw
            O = to_px(P[likeness.OVAL])
            cO = O.mean(0)
            im_ = Image.new("L", (self.px, self.px), 0)
            ImageDraw.Draw(im_).polygon([tuple(p) for p in cO + INNER * (O - cO)], fill=1)
            self.mask0 &= np.asarray(im_, bool)
        yy, xx = np.mgrid[0:self.px, 0:self.px]
        self.XY = np.stack([xx / self.px - 0.5, yy / self.px - 0.5], -1)
        self.sig = max(LP_MM / PX_MM, 1.0)
        st_ = max(int(round(LP_MM / PX_MM)), 1)
        self.grid = (slice(st_ // 2, None, st_), slice(st_ // 2, None, st_))
        self.light, self.alb = None, np.zeros(6)

    def _passes(self, mesh, light):
        im, k, ps = likeness.render(mesh, self.cam, self.box, px=self.px, brows=False, passes=True, ao=True,
                                    shadow=(True if SHADOW else False), light=light)
        return ps

    def _shade(self, ps, light):
        c0, w, _, aw = light
        dn = ps["nrm"] @ np.asarray(w, float)
        return c0 * (1 - aw + aw * ps["ao"]) + np.maximum(dn, 0) * ps["lit"] + np.minimum(dn, 0)

    def _poly(self):
        x, y = self.XY[..., 0], self.XY[..., 1]
        return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], -1)

    def fit_light(self, mesh, iters=3):
        """the photo's light (c0, w, aw) and the smooth albedo, alternately, on the current mesh."""
        _, _, ps = likeness.render(mesh, self.cam, self.box, px=self.px, brows=False, passes=True)
        m = self.mask0 & (ps["part"] == 0)
        c0, w, _ = ls.fit_light(self.Y, ps["nrm"], m)
        light = (c0, np.asarray(w, float), 1.0, 0.8)
        # the albedo: no constant (the light's level is c0: with one the two drifted together, c0 -> 0, |w| -> 4 and
        # the shape ran away, |c| 21), a ridge so it only takes what no light / shape can (ALB_RIDGE)
        Pl = self._poly()[..., 1:]
        self.alb = np.zeros(Pl.shape[-1])
        med = float(np.median(self.Y[m]))
        u = np.asarray(w, float) / max(np.linalg.norm(w), 1e-9)
        for _ in range(iters):
            ps = self._passes(mesh, light)
            m = self.mask0 & (ps["part"] == 0)
            Ya = self.Y / np.exp(Pl @ self.alb)
            dn = ps["nrm"] @ u
            X = np.c_[np.ones(m.sum()), ps["ao"][m], (np.maximum(dn, 0) * ps["lit"])[m], np.minimum(dn, 0)[m]]
            sol = np.linalg.lstsq(X, Ya[m], rcond=None)[0]
            A, Bao, C = sol[:3]
            c0n = max(float(A + Bao), 0.25 * med)
            light = (c0n, u * max(float(C), 0.0), 1.0, float(np.clip(Bao / c0n, 0, 1)))
            S = np.maximum(self._shade(self._passes(mesh, light), light), 1e-4)
            r = np.log(np.maximum(self.Y, 1e-4)) - np.log(S)
            A_ = Pl[m]
            self.alb = np.linalg.solve(A_.T @ A_ + ALB_RIDGE * len(A_) * np.eye(A_.shape[1]), A_.T @ (r[m] - r[m].mean()))
        self.light = light
        return light

    def residual(self, mesh):
        """the low-passed log residual on the grid samples of the mask (and the mask used)."""
        ps = self._passes(mesh, self.light)
        m = self.mask0 & (ps["part"] == 0)
        S = np.maximum(self._shade(ps, self.light), 1e-4)
        r = np.log(np.maximum(self.Y, 1e-4)) - np.log(S) - self._poly()[..., 1:] @ self.alb
        r = r - np.mean(r[m]) if m.any() else r   # (level: the light's)
        num = gaussian_filter(np.where(m, r, 0.0), self.sig)
        den = gaussian_filter(m.astype(float), self.sig)
        R = np.where(m & (den > 0.4), num / np.maximum(den, 1e-6), np.nan)
        return R[self.grid].ravel(), R


def mesh_moved(mesh, dV):
    out = dict(mesh)
    out["V"] = mesh["V"] + dV
    out.pop("_ao", None)
    out.pop("_occ", None)
    return out


def jacobian(views, mesh, VB, dirs, h=FD_H):
    """(r0 (n,), J (n, k), keep): the stacked residual over views and its FD Jacobian over the given identity
    directions (each (170,)); rows NaN in any evaluation are dropped."""
    r0 = np.concatenate([v.residual(mesh)[0] for v in views])
    cols = []
    for d in dirs:
        dV = np.tensordot(np.asarray(d, np.float32), VB, 1)
        m2 = mesh_moved(mesh, h * dV)
        cols.append((np.concatenate([v.residual(m2)[0] for v in views]) - r0) / h)
    J = np.stack(cols, 1)
    keep = np.isfinite(r0) & np.isfinite(J).all(1)
    return r0[keep], J[keep], keep
