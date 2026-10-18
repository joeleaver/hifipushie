"""teethcount.py <glb> [shape w ...]: per tooth (connected component of the row's mesh) the area seen from the front
(ray toward -y from each front-facing triangle's centroid hits no head triangle), and how many teeth show (>= 2 mm^2 seen)."""
import sys
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from hifipushie import rig_audit as ra
def count(g, a):
    """a: [shape, w, ...]."""
    def posed(m):
        V = m["V"].copy()
        for s, w in zip(a[::2], a[1::2]):
            if s in m["targets"]:
                V += float(w) * m["targets"][s]
        return V
    H = g["meshes"]["head"]; tri = posed(H)[H["F"]]
    lo, hi = np.array([-0.08, -0.2, 1.40]), np.array([0.08, 0.05, 1.52])
    T = tri[((tri > lo) & (tri < hi)).all(2).any(1)]
    d = np.array([0.0, -1.0, 0.0]); e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]; p = np.cross(d, e2); det = (e1 * p).sum(1)
    def blocked(o):
        s = o - T[:, 0]; u = (s * p).sum(1) / det; q = np.cross(s, e1); v = (q @ d) / det; t = (q * e2).sum(1) / det
        return bool(((u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-5) & (np.abs(det) > 1e-14)).any())
    for part in ("teeth", "teeth_lower"):
        m = g["meshes"][part]; V = posed(m); F = m["F"]
        n = len(V); e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        # weld by position (glTF splits vertices at UV seams)
        _, wid = np.unique(np.round(V, 6), axis=0, return_inverse=True); wid = wid.ravel()
        k, lab = connected_components(coo_matrix((np.ones(len(e)), (wid[e[:, 0]], wid[e[:, 1]])), shape=(wid.max() + 1,) * 2), directed=False)
        c = V[F]; fn = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]); area = 0.5 * np.linalg.norm(fn, axis=1)
        proj = 0.5 * np.maximum(-fn[:, 1], 0)  # area projected on the front view (facing -y)
        C = c.mean(1); fl = lab[wid[F[:, 0]]]
        seen = np.zeros(len(F))
        for i in np.where(proj > 0)[0]:
            seen[i] = 0 if blocked(C[i]) else proj[i]
        per = np.bincount(fl, seen * 1e6, minlength=k); tot = np.bincount(fl, proj * 1e6, minlength=k)
        order = np.argsort([C[fl == j, 0].mean() for j in range(k)])
        big = [j for j in order if tot[j] > 5]
        cx = np.round(C[:, 0] * 1000).astype(int); cols = np.bincount(cx - cx.min(), seen * 1e6)
        on = np.where(cols >= 0.3)[0] + cx.min()
        ext = f"seen x {on.min()}..{on.max()} mm ({len(on)} 1-mm columns)" if len(on) else "seen nothing"
        print(f"{a or 'neutral'} {part}: seen {seen.sum()*1e6:.0f} of {proj.sum()*1e6:.0f} mm^2 front area, {ext}")
        mid = (np.abs(C[:, 0]) < 0.004) & (proj > 0)
        zs = C[mid & (seen > 0), 2]
        print(f"   centre +-4 mm: crown z {C[mid, 2].min()*1e3:.1f}..{C[mid, 2].max()*1e3:.1f}, seen " + (f"{zs.min()*1e3:.1f}..{zs.max()*1e3:.1f} = {(zs.max()-zs.min())*1e3:.1f} mm of {(C[mid, 2].max()-C[mid, 2].min())*1e3:.1f}" if len(zs) else "none")); continue
        print(f"{a or 'neutral'} {part}: {len(F)} tris, {k} components, {len(big)} teeth; seen mm^2 (right->left): "
              + " ".join(f"{per[j]:.0f}/{tot[j]:.0f}" for j in big) + f"; teeth showing (>=2 mm^2): {sum(per[j] >= 2 for j in big)}")


if __name__ == "__main__":
    count(ra.read_glb(sys.argv[1]), sys.argv[2:])
