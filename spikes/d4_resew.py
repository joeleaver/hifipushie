"""D4: the armhole RE-SEWN by arc from the shoulder point, and the check that found why.

D3's network (n2j / run cnet.pkl) has each armhole's sewn pairs offset: the front's top 54 mm (shoulder down) sewn to the
UNDER sleeve, the back's shoulder corner to the top sleeve's front pitch, so by union every junction of the armhole is
ONE node: front.L 125 (shoulder) and 103 (fsArmhole), side 1672 / 1686, back 1918 / 1939, three top-sleeve and three
under-sleeve points (13 vertices). The armhole closes into petals hanging from one point; links stay exact (E1 passed).

bad_groups(c): sewn groups holding two points of ONE piece far apart in the flat that are not sewn to each other (joined
only through other pieces): a seam table that closes a piece on itself by mistake.
resew_armholes(c, landmark): the body's armhole (front from the shoulder, side, back back to the shoulder) and the
sleeve's cap (top sleeve from its crown toward its front pitch, under sleeve, back to the crown) paired node for node by
arc fraction; every other seam as it was; roots and merged links rebuilt as chain_net does (d1_where.relink)."""
import copy

import numpy as np


def _uf(n, pairs):
    p = np.arange(n)

    def f(x):
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x
    for a, b in pairs:
        ra, rb = f(a), f(b)
        if ra != rb:
            p[max(ra, rb)] = min(ra, rb)
    return np.array([f(x) for x in range(n)])


def bad_groups(c, root=None, tol=0.010):
    root = c.root if root is None else root
    direct = {(int(min(a, b)), int(max(a, b))) for a, b in c.sew}
    out = []
    for r in np.unique(root):
        g = np.where(root == r)[0]
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                a, b = g[i], g[j]
                if c.piece[a] == c.piece[b] and (int(a), int(b)) not in direct and \
                        np.linalg.norm(c.uv[a] - c.uv[b]) > tol:
                    out.append((int(r), c.names[c.piece[a]], int(a), int(b),
                                round(float(np.linalg.norm(c.uv[a] - c.uv[b])) * 1e3, 1)))
    return out


def _path(c, piece, v0, v1, through):
    """The outline of `piece` from v0 to v1, the way that passes more of `through`."""
    ol = [int(x) for x in c.outlines[piece]]
    i0, i1, n = ol.index(v0), ol.index(v1), len(ol)
    fw = [ol[(i0 + k) % n] for k in range((i1 - i0) % n + 1)]
    bw = [ol[(i0 - k) % n] for k in range((i0 - i1) % n + 1)]
    return fw if len(set(fw) & through) >= len(set(bw) & through) else bw


def _run_of(c, piece, verts):
    """verts (one contiguous stretch of piece's outline) in outline order."""
    ol = [int(x) for x in c.outlines[piece]]
    ks = sorted(ol.index(v) for v in verts)
    n = len(ol)
    gaps = [(ks[(i + 1) % len(ks)] - ks[i]) % n for i in range(len(ks))]
    j = int(np.argmax(gaps))
    return [ol[ks[(j + 1 + t) % len(ks)]] for t in range(len(ks))]


def _nodes(seq, r0):
    out = []
    for v in seq:
        if not out or r0[v] != r0[out[-1]]:
            out.append(v)
    if len(out) > 1 and r0[out[0]] == r0[out[-1]]:
        out = out[:-1]
    return out


def _arc(c, seq):
    st = np.linalg.norm(np.diff(c.uv[seq], axis=0), axis=1)
    st[c.piece[seq[1:]] != c.piece[seq[:-1]]] = 0
    a = np.r_[0, np.cumsum(st)]
    return a / a[-1], float(a[-1])


def resew_armholes(c, landmark, log=print):
    nm = c.names
    arm = {}
    for side in ("L", "R"):
        f, s, b, st, su = (f"{k}.{side}" for k in ("front", "side", "back", "sleeve_top", "sleeve_under"))
        arm[side] = (f, s, b, st, su)
    body_p = {nm.index(x) for v in arm.values() for x in v[:3]}
    slv_p = {nm.index(x) for v in arm.values() for x in v[3:]}
    is_arm = np.array([(c.piece[a] in body_p and c.piece[b] in slv_p) or (c.piece[b] in body_p and c.piece[a] in slv_p)
                       for a, b in c.sew])
    keep = c.sew[~is_arm]
    r0 = _uf(c.n, keep)
    new, rep = [], {}
    for side, (f, s, b, st, su) in arm.items():
        old = c.sew[is_arm & np.isin(c.piece[c.sew[:, 0]], [nm.index(x) for x in arm[side]])]
        ends = {int(x) for x in old.ravel()}
        body = _path(c, f, landmark(f"{f}:shoulder"), landmark(f"{f}:fsArmhole"), ends) + \
            _path(c, s, landmark(f"{s}:fsArmhole"), landmark(f"{s}:bsArmholeHollow"), ends) + \
            _path(c, b, landmark(f"{b}:armholeHollow"), landmark(f"{b}:s3ArmholeSplit"), ends)
        top = _run_of(c, st, [v for v in ends if c.piece[v] == nm.index(st)])
        und = _run_of(c, su, [v for v in ends if c.piece[v] == nm.index(su)])
        crown = top[int(np.argmin(np.linalg.norm(c.uv[top] - c.uv[landmark(f"{st}:top")], axis=1)))]
        fp = landmark(f"{st}:frontPitchPoint")
        k = top.index(crown)
        a_, b_ = top[k:], top[:k + 1][::-1]  # (crown -> each end)
        fwd = a_ if np.linalg.norm(c.uv[a_[min(3, len(a_) - 1)]] - c.uv[fp]) < \
            np.linalg.norm(c.uv[b_[min(3, len(b_) - 1)]] - c.uv[fp]) else b_
        back = b_ if fwd is a_ else a_
        e = fwd[-1]  # (the fore seam's top on the top sleeve: the under sleeve starts at its partner)
        part = {int(y) for x, y in keep if x == e} | {int(x) for x, y in keep if y == e}
        if part & {und[-1]}:
            und = und[::-1]
        cap = fwd + und + back[::-1]
        B, C = _nodes(body, r0), _nodes(cap, r0)
        fb, lb = _arc(c, np.array(B + [B[0]]))
        fc, lc = _arc(c, np.array(C + [C[0]]))
        fb, fc = fb[:-1], fc[:-1]
        # pair node for node by arc fraction (monotone; equal counts: one to one)
        if len(B) == len(C):
            pairs = list(zip(B, C))
        else:
            j = np.clip(np.searchsorted(fc, fb), 0, len(C) - 1)
            pairs = list(zip(B, [C[x] for x in j]))
        new += pairs
        rep[side] = {"body_nodes": len(B), "cap_nodes": len(C), "body_mm": round(lb * 1e3, 1),
                     "cap_mm": round(lc * 1e3, 1), "ease_pct": round((lc / lb - 1) * 100, 1),
                     "B": [int(x) for x in B], "C": [int(x) for x in C], "fore": int(e), "hind": int(back[-1])}
        log(f"resew armhole.{side}: { {k: v for k, v in rep[side].items() if k not in ('B', 'C')} }")
    sew = np.r_[keep, np.array(new, np.int64)]
    u = copy.copy(c)
    u.sew = sew
    u.root = _uf(c.n, sew)
    a, b_ = u.root[c.chain_v[:, 0]], u.root[c.chain_v[:, 1]]
    i, j = np.minimum(a, b_), np.maximum(a, b_)
    uk, inv = np.unique(i.astype(np.int64) * c.n + j, return_inverse=True)
    L = np.asarray(c.chain_L, float)
    s_, k_ = np.zeros(len(uk)), np.zeros(len(uk))
    np.add.at(s_, inv, L)
    np.add.at(k_, inv, 1)
    hi, lo = np.zeros(len(uk)), np.full(len(uk), np.inf)
    np.maximum.at(hi, inv, L)
    np.minimum.at(lo, inv, L)
    u.link_i, u.link_j = (uk // c.n).astype(np.int64), (uk % c.n).astype(np.int64)
    u.link_L, u.link_cut, u.link_of_chain = s_ / k_, np.stack([lo, hi], 1), inv
    return u, rep
