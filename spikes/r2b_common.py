"""R2b (drape first) helpers: the armhole as a CONE from the shoulder joint through the body's armhole loop, the
shoulder pad as a wedge under the shell, a march along a surface. Spike code.

THE ARMHOLE RULE (a tailor's): the armhole is the body's own armhole loop (D4's armhole: the shoulder point at the
pad's edge, close in round the arm's root at the front / back pitch, down to the underarm) carried out to the garment
along rays from the shoulder joint (a cone with its apex in the joint), never a plane fitted to the loop: the plane
leaves the loop where the toile stands off the body and cut a narrow peak at the top and the sleeve's crown into the
body (R2: no crown, the front stretched 66 % at the shoulder)."""
import numpy as np


class Cone:
    """apex O (the shoulder joint: on the arm's axis A, `back` m in from the shoulder tape's start), the loop's angle
    from the axis as a function of the azimuth round it. sdist(P) > 0 inside the cone (the sleeve side), in metres."""

    def __init__(self, sh, A, loop, back=0.05):
        self.A = A / np.linalg.norm(A)
        self.O = sh - back * self.A
        e1 = np.cross(self.A, [0, 1.0, 0])
        self.e1 = e1 / np.linalg.norm(e1)
        self.e2 = np.cross(self.A, self.e1)
        ps, al = self.polar(loop)
        o = np.argsort(ps)
        self.PS, self.AL = ps[o], al[o]

    def polar(self, P):
        d = np.atleast_2d(P) - self.O
        n = np.linalg.norm(d, axis=1) + 1e-12
        return np.arctan2(d @ self.e2, d @ self.e1), np.arccos(np.clip((d @ self.A) / n, -1, 1))

    def sdist(self, P):
        ps, al = self.polar(P)
        return (np.interp(ps, self.PS, self.AL, period=2 * np.pi) - al) * np.linalg.norm(np.atleast_2d(P) - self.O, axis=1)

    def save(self):
        return {"cone_O": self.O, "cone_A": self.A, "cone_PS": self.PS, "cone_AL": self.AL}

    @classmethod
    def load(cls, Z):
        c = cls.__new__(cls)
        c.O, c.A, c.PS, c.AL = Z["cone_O"], Z["cone_A"], Z["cone_PS"], Z["cone_AL"]
        e1 = np.cross(c.A, [0, 1.0, 0])
        c.e1 = e1 / np.linalg.norm(e1)
        c.e2 = np.cross(c.A, c.e1)
        return c


def smooth01(a):
    a = np.clip(a, 0, 1)
    return a * a * (3 - 2 * a)


def pad_thickness(P, x_sp, y_sh, z_sh, T, inward=0.13, over=0.03, half_w=0.11, drop=0.12):
    """A shoulder pad's thickness at P (folded to the left side): T at the shoulder point, thinning to nothing
    `inward` m toward the neck and `over` m past the shoulder point (it ends at the crown's edge), cos^2 across the
    shoulder (half width `half_w` front and back of the shoulder line y_sh(x)), only on top of the shoulder (within
    `drop` m below the shoulder line z_sh(x))."""
    x = np.abs(P[:, 0])
    u = smooth01((x - (x_sp - inward)) / inward) * smooth01((x_sp + over - x) / over)
    dy = (P[:, 1] - y_sh(x)) / half_w
    v = np.where(np.abs(dy) < 1, np.cos(np.pi / 2 * dy) ** 2, 0.0)
    w = smooth01((P[:, 2] - (z_sh(x) - drop)) / 0.04)
    return T * u * v * w


def march(P, dirs, dist, onto, grad, step=0.003):
    """Points walked `dist` along a surface (onto: project onto it; grad: its normals) from P in the directions
    dirs (projected into the tangent plane each step): a width measured along the surface."""
    P = P.copy()
    n = int(np.ceil(dist / step))
    for _ in range(n):
        g = grad(P)
        d = dirs - np.einsum("ij,ij->i", dirs, g)[:, None] * g
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
        P = onto(P + (dist / n) * d)
    return P
