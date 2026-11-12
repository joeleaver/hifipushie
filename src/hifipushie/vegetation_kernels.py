"""Lineage hashing and the growth kernels: collect, distribute, the pipe model, pose, shed. Part of vegetation (vegetation.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from numba import njit

def _mix(x):
    x = np.asarray(x, np.uint64)
    with np.errstate(over="ignore"):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


def _child(key, i):
    with np.errstate(over="ignore"):
        return _mix(np.asarray(key, np.uint64) * np.uint64(0x9E3779B97F4A7C15) + np.asarray(i, np.uint64) + np.uint64(1))


def _u(key, salt):
    """Uniform [0, 1) from a key."""
    return (_child(key, 1000 + salt) >> np.uint64(11)).astype(np.float64) / float(1 << 53)


# ---------------------------------------------------------------- kernels
@njit(cache=True)
def _collect(parent, qnode, Q, size):
    n = len(parent)
    for i in range(n):
        Q[i] = qnode[i]
        size[i] = 1
    for i in range(n - 1, 0, -1):
        Q[parent[i]] += Q[i]
        size[parent[i]] += size[i]


@njit(cache=True)
def _distribute(parent, main, order, Q, qtip, qlat, lam, v0, v, vtip, vlat):
    """Extended Borchert-Honda: hand the resource out from the root. qlat = the summed light of a node's lateral
    buds; vlat = the resource of them together."""
    n = len(parent)
    den = np.zeros(n)
    for i in range(n):
        o = min(order[i], len(lam) - 1)
        den[i] = lam[o] * qtip[i] + (1.0 - lam[o]) * qlat[i]
    for i in range(1, n):
        p = parent[i]
        o = min(order[p], len(lam) - 1)
        den[p] += (lam[o] if main[i] else 1.0 - lam[o]) * Q[i]
    v[0] = v0
    for i in range(n):
        if i > 0:
            p = parent[i]
            o = min(order[p], len(lam) - 1)
            w = lam[o] if main[i] else 1.0 - lam[o]
            v[i] = v[p] * w * Q[i] / den[p] if den[p] > 1e-12 else 0.0
        o = min(order[i], len(lam) - 1)
        if den[i] > 1e-12:
            vtip[i] = v[i] * lam[o] * qtip[i] / den[i]
            vlat[i] = v[i] * (1.0 - lam[o]) * qlat[i] / den[i]
        else:
            vtip[i] = 0.0
            vlat[i] = 0.0


@njit(cache=True)
def _pipe(parent, mem, tip_area, expo, area):
    n = len(parent)
    kids = np.zeros(n, np.int32)
    for i in range(1, n):
        kids[parent[i]] += 1
    for i in range(n):
        area[i] = mem[i] + (tip_area if kids[i] == 0 else 0.0)
    for i in range(n - 1, 0, -1):
        area[parent[i]] += area[i]
    # area holds the sum of d^n: the radius is its n-th root
    for i in range(n):
        area[i] = area[i] ** (1.0 / expo)


@njit(cache=True)
def _pose(parent, off, pin, pinpos, order, radius, leafy, theta, sag, sag_max, sag_trunk, pos, R, g0, gx, gy):
    """Bend under weight, then forward kinematics. off = each node's internode in its parent's rest frame; theta =
    how far its internode has bent so far (it never bends back: wood sets). The ground (z = g0 + gx x + gy y) holds
    up what sags onto it: a limb rests on it."""
    n = len(parent)
    m = np.zeros(n)
    mx = np.zeros(n)
    my = np.zeros(n)
    for i in range(1, n):
        p = parent[i]
        L = math.sqrt(off[i, 0] ** 2 + off[i, 1] ** 2 + off[i, 2] ** 2)
        w = radius[i] * radius[i] * L * 3.14 + (0.0006 if leafy[i] else 0.0)
        m[i] = w
        mx[i] = w * 0.5 * (pos[i, 0] + pos[p, 0])
        my[i] = w * 0.5 * (pos[i, 1] + pos[p, 1])
    for i in range(n - 1, 0, -1):
        p = parent[i]
        m[p] += m[i]
        mx[p] += mx[i]
        my[p] += my[i]
    for i in range(1, n):
        p = parent[i]
        if m[i] > 0:
            ax = mx[i] / m[i] - pos[p, 0]
            ay = my[i] / m[i] - pos[p, 1]
            arm = math.sqrt(ax * ax + ay * ay)
            k = sag if order[i] > 0 else sag * sag_trunk
            t = k * 5e-7 * m[i] * arm / (radius[i] ** 4 + 1e-12)
            if t > sag_max:
                t = sag_max
            if t > theta[i]:
                theta[i] = t
    d = np.zeros(3)
    for i in range(1, n):
        p = parent[i]
        if pin[i]:
            for a in range(3):
                pos[i, a] = pinpos[i, a]
                for b in range(3):
                    R[i, a, b] = 1.0 if a == b else 0.0
            continue
        for a in range(3):
            d[a] = R[p, a, 0] * off[i, 0] + R[p, a, 1] * off[i, 1] + R[p, a, 2] * off[i, 2]
        # rotate d toward straight down by theta: axis = d x (0, 0, -1)
        kx, ky = -d[1], d[0]
        kn = math.sqrt(kx * kx + ky * ky)
        L = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        t = theta[i] * (kn / L if L > 0 else 0.0)  # (a vertical internode has no lever)
        if order[i] > 0 and kn > 1e-9 and L > 0:
            # the ground stops the bend: an internode that would dip under it turns only as far as resting on it, and
            # what it carries turns with it (a limb sagged onto the ground lies there and its end rises again)
            fl = g0 + gx * (pos[p, 0] + d[0]) + gy * (pos[p, 1] + d[1]) + radius[i]
            sn = (fl - pos[p, 2]) / L
            if sn < 0.95:
                e_min = math.asin(sn) if sn > -1.0 else -1.5708
                e0 = math.asin(max(-1.0, min(1.0, d[2] / L)))
                if e0 - t < e_min:
                    t = e0 - e_min
                    if t < -0.6:
                        t = -0.6
        if kn > 1e-9 and abs(t) > 1e-6:
            kx /= kn
            ky /= kn
            c, s = math.cos(t), math.sin(t)
            # Rodrigues, axis (kx, ky, 0)
            r00 = c + kx * kx * (1 - c)
            r01 = kx * ky * (1 - c)
            r02 = ky * s
            r10 = kx * ky * (1 - c)
            r11 = c + ky * ky * (1 - c)
            r12 = -kx * s
            r20 = -ky * s
            r21 = kx * s
            r22 = c
            for b in range(3):
                a0, a1, a2 = R[p, 0, b], R[p, 1, b], R[p, 2, b]
                R[i, 0, b] = r00 * a0 + r01 * a1 + r02 * a2
                R[i, 1, b] = r10 * a0 + r11 * a1 + r12 * a2
                R[i, 2, b] = r20 * a0 + r21 * a1 + r22 * a2
            x = r00 * d[0] + r01 * d[1] + r02 * d[2]
            y = r10 * d[0] + r11 * d[1] + r12 * d[2]
            z = r20 * d[0] + r21 * d[1] + r22 * d[2]
            d[0], d[1], d[2] = x, y, z
        else:
            for a in range(3):
                for b in range(3):
                    R[i, a, b] = R[p, a, b]
        for a in range(3):
            pos[i, a] = pos[p, a] + d[a]
        if order[i] > 0:
            fl = g0 + gx * pos[i, 0] + gy * pos[i, 1] + radius[i]
            if pos[i, 2] < fl:
                pos[i, 2] = fl


@njit(cache=True)
def _shed(parent, main, born, pin, Q, size, cut, step, thr, age, dead):
    n = len(parent)
    dead[0] = False
    for i in range(1, n):
        if dead[parent[i]]:
            dead[i] = True
        elif cut[i]:
            dead[i] = True
        elif (not main[i]) and (not pin[i]) and step - born[i] >= age and Q[i] < thr[i] * size[i]:
            dead[i] = True
        else:
            dead[i] = False
