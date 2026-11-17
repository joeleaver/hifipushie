"""Artist retopo, step 1: the LOW CAGE, written by the artist (an LLM) as code, from contour rings sliced off the sculpt.

What an artist does with RetopoFlow / Quad Draw, as functions on `Cage` (guide(topic="retopo") is the playbook):
  ring(origin, normal, u, v, dirs)   a contour: slice the sculpt with a plane, take the region round a point, put a
                                     vertex where a ray at each given direction leaves it (star-shaped round its centre)
  hring(z, dirs)                     a horizontal ring (body, neck, head, limbs hanging down)
  ring_even(..., n, pick, start)     a contour resampled EVENLY by length: thin curved sheets (ears) where rays fail
  bridge(a, b, skip)                 quads between two loops of equal length (skip = holes left in the band)
  cap_grid(r, nx, ny, interior)      close a loop of 2(nx+ny) with a grid (crown, pelvis floor, nose pad)
  inset(loop, centre_xz, scale)      a concentric copy of a face loop, pressed on from the front (muzzle, eyes)
  tracks(prev, ring0, down)          smooth (Hermite) vertex tracks from a limb's root hole to its first free ring
  snap_to_sphere(loop, c, R, axis, th)  a loop onto the circle where an eyeball meets the skin (keeps each angle)
  mouth(r1, r2, ...)                 the lip slit, the mouth bag ("sock") and the jaw / mouth_inside / freeze groups
  pin(...) / seam(...) / groups      invented (not pressed) vertices, UV seams, weighted vertex groups
Coordinates: z up, faces -y, left = +x, mirror plane x = 0. Ring directions: az(deg), 0 = front, 90 = +x.

The cage is saved as cage.ply + cage_pinned.json + cage_seams.json + cage_groups.json; then press (Blender:
subdivide, press onto the sculpt along normals, relax) and bake. `c.s` is the sculpt the rings are sliced from (the
whole, closed sculpt); `c.body` the one rays and snaps land on (the body with the rebuilt eyes / props cut out)."""
from __future__ import annotations

import json
import math

import numpy as np

from .artretopo_sculpt import Sculpt

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


def az(deg):
    """horizontal ring direction in the (x, y) plane: 0 = front (-y), 90 = +x side, 180 = back, 270 = -x"""
    r = math.radians(deg)
    return (math.sin(r), -math.cos(r))


class Cage:
    def __init__(self, sculpt: Sculpt, body: Sculpt | None = None):
        self.s, self.body = sculpt, body or sculpt
        self.V, self.F, self.names, self.pinned = [], [], {}, set()
        self.seams, self.groups = set(), {}

    # ---- vertices
    def add(self, p):
        self.V.append(np.asarray(p, float)); return len(self.V) - 1

    def put(self, i, p):
        self.V[i] = np.asarray(p, float)

    def pin(self, *ids):
        """invented vertices: kept where you put them (not pressed onto the sculpt; subdivision interpolates them)"""
        for i in ids:
            self.pinned.update(i if isinstance(i, (list, tuple, set)) else [i])

    # ---- rays and snaps (on the body)
    def hit(self, origin, d, last=False):
        return self.body.hit(origin, d, last)

    def front(self, x, z):
        return self.body.front(x, z)

    def top(self, x, y):
        return self.body.top(x, y)

    def bottom(self, x, y):
        return self.body.bottom(x, y)

    def crease(self, x, z_lo, z_hi):
        return self.body.crease(x, z_lo, z_hi)

    def closest(self, p):
        return self.body.closest([p])[0]

    def extreme(self, lo_box, hi_box, direction):
        """where a horn / ear really ends: the WHOLE sculpt's furthest vertex along direction inside the box"""
        return self.s.extreme(lo_box, hi_box, direction)

    def centre_of(self, z, pick=(0.0, 0.0)):
        return self.body.centre_of(z, pick)

    # ---- contours
    def _region(self, origin, normal, u, v, pick2d):
        polys = self.s.slice(origin, normal, u, v)
        if not polys:
            raise ValueError(f"empty slice at {tuple(np.round(origin, 4))} normal {normal}")
        return min(polys, key=lambda p: (0 if p.contains(pick2d) else 1, p.distance(pick2d)))

    def ring(self, origin, normal, u, v, dirs, centre2d=None, pick2d=(0.0, 0.0), name=None):
        """dirs: 2D directions in the plane's (u, v). Returns the new vertex indices."""
        poly = self._region(origin, normal, u, v, pick2d)
        c = np.asarray(centre2d if centre2d is not None else poly.centroid, float)
        o, u, v = np.asarray(origin, float), np.asarray(u, float), np.asarray(v, float)
        out = []
        for d in dirs:
            p = poly.ray_exit(c, d)
            if p is None:
                raise ValueError(f"ray {tuple(np.round(d, 3))} from {tuple(np.round(c, 4))} misses the contour at "
                                 f"{tuple(np.round(origin, 4))}: is the centre inside this region?")
            out.append(self.add(o + p[0] * u + p[1] * v))
        if name:
            self.names[name] = out
        return out

    def hring(self, z, dirs, centre=None, pick=(0.0, 0.0), name=None):
        return self.ring((0, 0, z), Z, X, Y, dirs, centre, pick, name)

    def ring_even(self, origin, normal, u, v, n, pick2d, start_dir, ccw=True):
        """a contour resampled evenly by length, from where it lies furthest along start_dir, counter-clockwise in
        (u, v): thin curved sheets (ears) whose sections are crescents (rays from a centre fail there)"""
        poly = self._region(origin, normal, u, v, pick2d)
        o, u, v = np.asarray(origin, float), np.asarray(u, float), np.asarray(v, float)
        return [self.add(o + q[0] * u + q[1] * v) for q in poly.even(n, start_dir, ccw)]

    def ring_clip(self, origin, normal, u, v, n, keep_side, pick2d, start_dir, ccw=True, pin_inner=True):
        """the part of a contour beyond a line in the plane (keep_side = ((x, y) on the line, the outward normal)),
        resampled evenly by length from where it lies furthest along start_dir: a limb FUSED to the body (a wing pressed
        to the flank, an arm glued to the side) gets its own cross-section; its cut edge is its invented inner side
        (those vertices pinned when pin_inner)"""
        from .artretopo_poly import Poly, clip
        poly = self._region(origin, normal, u, v, pick2d)
        (cx, cy), nn = keep_side
        piece = clip(poly.exterior, (cx, cy), nn)
        if len(piece) < 3:
            raise ValueError(f"ring_clip: nothing of the contour at {tuple(np.round(origin, 4))} lies beyond the line")
        o, u, v = np.asarray(origin, float), np.asarray(u, float), np.asarray(v, float)
        nn = np.asarray(nn, float) / np.linalg.norm(nn); out = []
        for q in Poly(piece).even(n, start_dir, ccw):
            out.append(self.add(o + q[0] * u + q[1] * v))
            if pin_inner and abs((q - np.array([cx, cy])) @ nn) < 0.004:
                self.pinned.add(out[-1])
        return out

    def dirs_from(self, loop, centre_xy, axes=(0, 1)):
        """directions from a centre to a loop's vertices: the next ring down a limb keeps the hole's directions"""
        return [np.asarray(self.V[i])[list(axes)] - np.asarray(centre_xy) for i in loop]

    # ---- faces
    def quad(self, *q):
        self.F.append(list(q))

    def bridge(self, a, b, skip=()):
        n = len(a)
        if n != len(b):
            raise ValueError(f"bridge: loops of {n} and {len(b)} vertices")
        for i in range(n):
            if i in skip:
                continue
            j = (i + 1) % n
            self.F.append([a[i], a[j], b[j], b[i]])

    def bridge_new(self, prev, pts, pin=False):
        """new vertices at pts, bridged to prev; returns them"""
        r = [self.add(p) for p in pts]
        if pin:
            self.pinned.update(r)
        self.bridge(prev, r)
        return r

    def cap_grid(self, r, nx, ny, interior):
        """close loop r (2(nx+ny) long, r[0] at the middle of row 0) with an nx x ny grid; interior(i, j, guess)
        -> the inner vertex's point (guess = between rows 0 and ny). Returns {(i, j): vertex}"""
        walk = ([(i, 0) for i in range(nx)] + [(nx, j) for j in range(ny)] + [(i, ny) for i in range(nx, 0, -1)]
                + [(0, j) for j in range(ny, 0, -1)])
        k0 = walk.index((nx // 2, 0)); walk = walk[k0:] + walk[:k0]
        if len(walk) != len(r):
            raise ValueError(f"cap_grid {nx} x {ny} needs a loop of {len(walk)}, got {len(r)}")
        g = {ij: r[k] for k, ij in enumerate(walk)}
        for i in range(1, nx):
            for j in range(1, ny):
                p = ((ny - j) * np.asarray(self.V[g[(i, 0)]]) + j * np.asarray(self.V[g[(i, ny)]])) / ny
                g[(i, j)] = self.add(interior(i, j, p))
        return g

    def fill(self, g, nx, ny, holes=()):
        for i in range(nx):
            for j in range(ny):
                if (i, j) not in holes:
                    self.quad(g[(i, j)], g[(i + 1, j)], g[(i + 1, j + 1)], g[(i, j + 1)])

    def cap6(self, r):
        self.quad(r[0], r[1], r[2], r[3]); self.quad(r[3], r[4], r[5], r[0])

    def cap8(self, r, centre_pt, pin=False):
        m = self.add(centre_pt)
        if pin:
            self.pinned.add(m)
        self.quad(r[0], r[1], m, r[7]); self.quad(r[1], r[2], r[3], m)
        self.quad(m, r[3], r[4], r[5]); self.quad(r[7], m, r[5], r[6])

    def close_to(self, r, tip_pt):
        """close an even loop to one point (a horn / ear tip: the sculpt's extreme vertex there)"""
        t = self.add(tip_pt)
        for k in range(0, len(r), 2):
            self.quad(r[k], r[k + 1], r[(k + 2) % len(r)], t)
        return t

    def close_small(self, r, tip_pt, toward=None, shrink=0.45, back=0.004):
        """close a 4-vertex tube end at its real tip: a small ring at the tip (the ring shrunk round its centre) and one
        quad (four quads fanned to a point fold onto each other)"""
        tip = np.asarray(tip_pt, float); ctr = np.mean([self.V[i] for i in r], axis=0)
        d = np.asarray(toward if toward is not None else tip - ctr, float); d = d / np.linalg.norm(d)
        end = [self.add(tip + shrink * (np.asarray(self.V[i]) - ctr) - d * back) for i in r]
        self.bridge(r, end); self.quad(*end)
        return end

    def extreme_cone(self, origin, direction, deg=12.0, min_dist=0.03, box=None):
        """a toe's (a claw's, a finger's) real tip: the whole sculpt's furthest vertex along `direction` from `origin`
        inside a cone of `deg` round it (box: (lo, hi) to keep to one foot)"""
        V = self.s.m.V; o = np.asarray(origin, float); g = np.asarray(direction, float); g = g / np.linalg.norm(g)
        rel = V - o; dist = np.linalg.norm(rel, axis=1)
        sel = (rel @ g > np.cos(np.radians(deg)) * dist) & (dist > min_dist)
        if box is not None:
            sel &= np.all((V >= np.asarray(box[0])) & (V <= np.asarray(box[1])), axis=1)
        if not sel.any():
            raise ValueError(f"nothing of the sculpt in a {deg} deg cone from {tuple(np.round(o, 3))} along {tuple(np.round(g, 3))}")
        return V[sel][np.argmax(rel[sel] @ g)]

    def split(self, path, offset=(0.0, 0.0, 0.0015), above=None):
        """split the cage along a path of vertices (a beak's or a muzzle's opening): each inner vertex gets a copy moved
        by `offset`; the faces on the upper side (their centre above `above`, default the path's mean height) take the
        copies; both lines pinned. Returns {vertex: its upper copy}"""
        z = np.mean([self.V[i][2] for i in path]) if above is None else above
        up = {}
        for i in path:
            up[i] = self.add(np.asarray(self.V[i]) + np.asarray(offset, float)); self.pinned.update([i, up[i]])
        ps = set(path)
        for k, f in enumerate(self.F):
            if ps & set(f) and np.mean([self.V[i][2] for i in f]) > z:
                self.F[k] = [up.get(i, i) for i in f]
        return up

    def bag(self, mouth, rings=((0.75, 0.045, 0.016), (0.5, 0.075, 0.022))):
        """a mouth bag behind any opening loop `mouth` (corner, lower edge ..., corner, upper edge ...; even length):
        ellipse rings ((shrink, depth, height) each) and a (len/2 - 2) x 2 cap; all pinned. Returns (rings, cap grid)"""
        from .artretopo_mouth import sock
        mc = np.mean([self.V[i] for i in mouth], axis=0); ring = mouth; out = []
        for shrink, depth, height in rings:
            ring = self.bridge_new(ring, sock(self, mouth, mc, shrink, depth, height), pin=True); out.append(ring)
        half = len(mouth) // 2; nx = half - 2; m = half // 2         # cap_grid starts at the lower edge's middle
        g = self.cap_grid(ring[m:] + ring[:m], nx, 2, lambda i, j, p: p)
        self.fill(g, nx, 2); self.pinned.update(g.values())
        return out, g

    # ---- face loops
    def inset(self, loop, centre_xz, scale):
        """a smaller copy of a face loop, pressed onto the surface from the front (concentric loops)"""
        out = []
        for i in loop:
            p = np.asarray(self.V[i]); q = np.asarray(centre_xz) + scale * (p[[0, 2]] - np.asarray(centre_xz))
            out.append(self.add(self.front(q[0], q[1])))
        return out

    def snap_to_sphere(self, loop, centre, R, axis, theta_deg):
        """points for a loop on the circle theta degrees from the sphere's axis, each vertex keeping its own angle
        round the axis (order and flow kept): eyelid rings round an eyeball"""
        centre, axis = np.asarray(centre, float), np.asarray(axis, float) / np.linalg.norm(axis)
        e1 = np.cross(axis, [0, 0, 1.0]); e1 /= np.linalg.norm(e1); e2 = np.cross(axis, e1)
        th = math.radians(theta_deg); out = []
        for i in loop:
            d = np.asarray(self.V[i]) - centre; phi = math.atan2(d @ e2, d @ e1)
            out.append(centre + R * (math.cos(th) * axis + math.sin(th) * (math.cos(phi) * e1 + math.sin(phi) * e2)))
        return out

    def tracks(self, prev, ring0, down, pinned_out=None, n=2):
        """n rings on smooth vertex tracks (cubic Hermite) from a root hole `prev` to the limb's first free ring
        `ring0`: each leaves the body along the sculpt's normal and arrives along the limb (`down`). A track starting
        on a pinned (invented) vertex leaves along pinned_out (if given) and stays invented."""
        down = np.asarray(down, float); down = down / np.linalg.norm(down)
        mids = [[] for _ in range(n)]
        for a_, b_ in zip(prev, ring0):
            P0, P1 = np.asarray(self.V[a_]), np.asarray(self.V[b_])
            inv = a_ in self.pinned and pinned_out is not None
            n0 = np.asarray(pinned_out, float) if inv else self.body.normal_at(P0)
            L = np.linalg.norm(P1 - P0); T0, T1 = n0 * L, down * L
            for m_, k in zip(mids, range(1, n + 1)):
                t = k / (n + 1)
                h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
                m_.append(self.add(h00 * P0 + h10 * T0 + h01 * P1 + h11 * T1))
                if inv:
                    self.pinned.add(m_[-1])
        return mids

    # ---- the mouth (artretopo_mouth has the reasons)
    def mouth(self, r1, r2, lip=(1, 2, 3), **kw):
        from .artretopo_mouth import build
        return build(self, r1, r2, list(lip), **kw)

    # ---- seams, output
    def seam(self, loop, closed=True):
        """mark the edges along a chain (or loop) of cage vertices as a UV seam"""
        n = len(loop)
        for k in range(n if closed else n - 1):
            a, b = loop[k], loop[(k + 1) % n]; self.seams.add((min(a, b), max(a, b)))

    def save(self, path):
        """cage.ply + _pinned / _seams / _groups json (unused vertices dropped, indices remapped)"""
        path = str(path)
        used = sorted({i for q in self.F for i in q}); remap = {o: n for n, o in enumerate(used)}
        V = np.array([self.V[i] for i in used]); F = [[remap[i] for i in q] for q in self.F]
        with open(path, "w") as f:
            f.write(f"ply\nformat ascii 1.0\nelement vertex {len(V)}\nproperty float x\nproperty float y\nproperty float z\n"
                    f"element face {len(F)}\nproperty list uchar int vertex_indices\nend_header\n")
            for p in V:
                f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
            for q in F:
                f.write(f"{len(q)} " + " ".join(map(str, q)) + "\n")
        json.dump(sorted(remap[i] for i in self.pinned if i in remap), open(path.replace(".ply", "_pinned.json"), "w"))
        json.dump(sorted([remap[a], remap[b]] for a, b in self.seams if a in remap and b in remap),
                  open(path.replace(".ply", "_seams.json"), "w"))
        json.dump({k: ({str(remap[i]): w for i, w in v.items() if i in remap} if isinstance(v, dict)
                       else sorted(remap[i] for i in v if i in remap)) for k, v in self.groups.items()},
                  open(path.replace(".ply", "_groups.json"), "w"))
        return V, F
