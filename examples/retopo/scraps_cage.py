# Scraps (a goat on two thin legs; googly eyes, a gas-mask canister held in his mouth, fur drips, horns sweeping
# back, ears out to the side): the artist's decisions for his low cage. Run by retopo_cage (in scope: c, s, full, az,
# X, Y, Z, np, math, props). The eyes and the canister were rebuilt as primitives (retopo_props) and cut from the
# sculpt: c.body (= s) is the body under them (rays and snaps land on it); rings are sliced off the whole sculpt.
# The spike's frame: centred, feet at z ~ -0.5. 16 round every body ring (k: 0 front, 4 +x, 8 back, 12 -x).
N = 16
A = [az(360 / N * k) for k in range(N)]
EYES = {+1: tuple(props["eyes"][0]["c"]), -1: tuple(props["eyes"][1]["c"])}
EYE_R = props["eyes"][0]["R"]
CAN = props["props"][0]                       # the canister: a cylinder along x (c = centre, R)
CAN_Y, CAN_Z, CAN_R = CAN["c"][1], CAN["c"][2], CAN["R"]

# ---- torso: hips to shoulder tops. The shoulder root is sized to the arm: armpit -0.02 to shoulder top 0.04 (6 cm,
# the arm's own thickness), so a raised arm doesn't neck through a small hole.
TZ = [-0.22, -0.15, -0.08, -0.02, 0.04]
T = [c.hring(z, A, centre=c.centre_of(z, (0, 0.0)), pick=(0, 0.0)) for z in TZ]
for a, b in zip(T, T[1:-1]):
    c.bridge(a, b)
c.bridge(T[3], T[4], skip={3, 4, 11, 12})
armhole = {+1: [T[4][3], T[4][4], T[4][5], T[3][5], T[3][4], T[3][3]],
           -1: [T[4][13], T[4][12], T[4][11], T[3][11], T[3][12], T[3][13]]}
# ---- neck
NZ = [0.08, 0.13]
Nk = [c.hring(z, A, centre=c.centre_of(z, (0, -0.01)), pick=(0, -0.01)) for z in NZ]
c.bridge(T[4], Nk[0]); c.bridge(Nk[0], Nk[1])
# ---- head rings: under the jaw, cheeks, eyes bottom, eyes middle, brow, crown
HZ = [0.20, 0.26, 0.30, 0.345, 0.395, 0.44]
H = [c.hring(z, A, centre=(0.0, 0.0)) for z in HZ]
c.bridge(Nk[1], H[0])
# EYES: 2 x 2 holes in bands H2-H4, columns k1-k3 (and k13-k15); the hole snapped onto the circle where the eyeball
# meets the skin; a lid ring on the eyeball; the rest hidden inside it (pinned)
HC = np.array([0.0, 0.0, 0.33])
eyehole = {+1: [H[2][1], H[2][2], H[2][3], H[3][3], H[4][3], H[4][2], H[4][1], H[3][1]],
           -1: [H[2][15], H[2][14], H[2][13], H[3][13], H[4][13], H[4][14], H[4][15], H[3][15]]}
for sd in (+1, -1):
    ax_ = np.asarray(EYES[sd]) - HC; ax_[2] *= 0.3
    for i, p in zip(eyehole[sd], c.snap_to_sphere(eyehole[sd], EYES[sd], EYE_R + 0.004, ax_, 62)):
        c.put(i, c.closest(p))
# MUZZLE root: an oval round the snout seen from the front; its bottom (behind the canister) is invented
MC, ma, mb = (0.0, 0.27), 0.068, 0.068
c.put(H[2][0], c.front(0.0, 0.338))
c.put(H[1][2], c.front(ma, MC[1])); c.put(H[1][14], c.front(-ma, MC[1]))
for k, th, sd in ((2, -25, 1), (14, -25, -1)):
    t = math.radians(th); c.put(H[0][k], c.front(sd * ma * math.cos(t), MC[1] + mb * math.sin(t)))
CHIN = {0: (0.0, -0.118, 0.17), 1: (0.035, -0.118, 0.18), 15: (-0.035, -0.118, 0.18)}
for k, p in CHIN.items():
    c.put(H[0][k], p); c.pin(H[0][k])
root = [H[0][14], H[0][15], H[0][0], H[0][1], H[0][2], H[1][2], H[2][2], H[2][1], H[2][0], H[2][15], H[2][14], H[1][14]]
# EARS: 2 x 2 holes in bands H2-H4, columns k4-k6 (and k10-k12)
earhole = {+1: [H[2][4], H[2][5], H[2][6], H[3][6], H[4][6], H[4][5], H[4][4], H[3][4]],
           -1: [H[2][12], H[2][11], H[2][10], H[3][10], H[4][10], H[4][11], H[4][12], H[3][12]]}
c.bridge(H[0], H[1], skip={14, 15, 0, 1})
c.bridge(H[1], H[2], skip={14, 15, 0, 1})
c.bridge(H[2], H[3], skip={1, 2, 13, 14, 4, 5, 10, 11})
c.bridge(H[3], H[4], skip={1, 2, 13, 14, 4, 5, 10, 11})
c.bridge(H[4], H[5])
# crown: 6 x 2 grid closed from inside the head looking up; each horn's root takes two cells at the back-side
up_ = lambda x, y: c.hit((x, y, 0.36), (0, 0, 1))
g = c.cap_grid(H[5], 6, 2, lambda i, j, p: up_(p[0], p[1]))
c.fill(g, 6, 2, holes={(4, 1), (5, 1), (0, 1), (1, 1)})
hornhole = {+1: [g[(4, 1)], g[(5, 1)], g[(6, 1)], g[(6, 2)], g[(5, 2)], g[(4, 2)]],
            -1: [g[(2, 1)], g[(1, 1)], g[(0, 1)], g[(0, 2)], g[(1, 2)], g[(2, 2)]]}


# ---- muzzle: concentric loops to the nose pad; where the canister fills the mouth the loops are invented (pinned)
def muzzle_inset(scale):
    out = []
    for i in root:
        p = np.asarray(c.V[i]); q = np.asarray(MC) + scale * (p[[0, 2]] - np.asarray(MC))
        try:
            h = c.front(q[0], q[1]); ok = h[1] < -0.14 and q[1] > 0.228
        except ValueError:
            ok = False
        if ok:
            out.append(c.add(h))
        else:   # behind the canister: the lips and jaw WRAP it (he bites it): a shell just outside the cylinder
            p0 = np.array([q[0], -0.125 - 0.1 * (1 - scale), max(q[1], 0.2)])
            d = np.array([p0[1] - CAN_Y, p0[2] - CAN_Z]); d = d / (np.linalg.norm(d) + 1e-9)
            out.append(c.add((q[0], CAN_Y + (CAN_R + 0.006) * d[0], CAN_Z + (CAN_R + 0.006) * d[1]))); c.pin(out[-1])
    return out


prev = root; rings_m = []
for sc_ in (0.75, 0.45):
    r = muzzle_inset(sc_); c.bridge(prev, r); prev = r; rings_m.append(r)
r1, r2 = rings_m
LIP = [1, 2, 3]
phi = math.radians(32)                    # the lower lip line sits on the canister's top front edge
for k in LIP:
    x_ = c.V[r2[k]][0]
    c.put(r2[k], (x_, CAN_Y - (CAN_R + 0.004) * math.sin(phi), CAN_Z + (CAN_R + 0.004) * math.cos(phi)))
c.mouth(r1, r2, lip=LIP, jaw_extra=[root[k] for k in (0, 1, 2, 3, 4)] + [H[0][k] for k in (15, 0, 1)])

# ---- eyes: lid ring on the eyeball, then hidden loops inside it
for sd in (+1, -1):
    ax_ = np.asarray(EYES[sd]) - HC; ax_[2] *= 0.3
    prev = eyehole[sd]
    for th, rr in ((52, EYE_R + 0.003), (35, EYE_R - 0.006)):
        prev = c.bridge_new(prev, c.snap_to_sphere(eyehole[sd], EYES[sd], rr, ax_, th), pin=True)
    c.cap8(prev, np.asarray(EYES[sd]) + (EYE_R - 0.012) * ax_ / np.linalg.norm(ax_), pin=True)

# ---- arms: smooth Hermite tracks from the shoulder root to the free arm, then contours to the hoof
for sd in (+1, -1):
    adeg = [30, 90, 150, 210, 270, 330] if sd > 0 else [330, 270, 210, 150, 90, 30]
    prev = armhole[sd]
    rings = [c.hring(z, [az(d) for d in adeg], pick=(cx * sd, cy)) for z, cx, cy in
             ((-0.05, 0.169, 0.006), (-0.10, 0.19, 0.0), (-0.15, 0.21, 0.0), (-0.20, 0.225, 0.0))]
    ring_c = lambda r: np.mean([c.V[i] for i in r], axis=0)
    mids = c.tracks(prev, rings[0], ring_c(rings[1]) - ring_c(rings[0]))
    chain = [prev[4]]
    for r in mids + rings:
        c.bridge(prev, r); prev = r; chain.append(r[4])
    c.seam(armhole[sd]); c.seam(chain, closed=False); c.seam(prev)          # root, inner line (index 4), sole
    c.cap6(prev)

# ---- pelvis (thin legs): the torso closes with a FLOOR; each leg comes out of a hole in it sized to the leg (a
# half-hip loop as the root of a 5 cm leg swung the whole crotch with it). The crotch between the holes is the hips'.
down_ = lambda x, y: c.hit((x, y, -0.15), (0, 0, -1))
pf = c.cap_grid(T[0], 4, 4, lambda i, j, p: down_(p[0], p[1]))
c.fill(pf, 4, 4, holes={(3, 1), (3, 2), (0, 1), (0, 2)})
leghole = {+1: [pf[(3, 1)], pf[(4, 1)], pf[(4, 2)], pf[(4, 3)], pf[(3, 3)], pf[(3, 2)]],
           -1: [pf[(1, 1)], pf[(0, 1)], pf[(0, 2)], pf[(0, 3)], pf[(1, 3)], pf[(1, 2)]]}
for sd in (+1, -1):
    prev = leghole[sd]; dirs = None; chain = [prev[0]]
    for z, cx, cy in ((-0.27, 0.089, 0.0), (-0.31, 0.084, 0.012), (-0.35, 0.09, 0.01), (-0.39, 0.1, 0.004), (-0.43, 0.108, -0.003),
                      (-0.47, 0.112, -0.007), (-0.495, 0.115, -0.011)):
        if dirs is None:
            dirs = c.dirs_from(leghole[sd], (cx * sd, cy))
        r = c.hring(z, dirs, pick=(cx * sd, cy)); c.bridge(prev, r); prev = r; chain.append(r[0])
    c.seam(leghole[sd]); c.seam(chain, closed=False); c.seam(prev)          # root, inner line, sole
    c.cap6(prev)

# ---- ears: 8-rings out to the tips in planes x = const, resampled evenly (crescent sections break centre rays)
for sd in (+1, -1):
    prev = earhole[sd]
    chain = [prev[1]]
    for x in (0.15, 0.185, 0.215, 0.24):
        r = c.ring_even((x * sd, 0, 0), X, Y, Z, 8, (0.035, 0.345), (-1, -1), ccw=True); c.bridge(prev, r); prev = r; chain.append(r[1])
    c.seam(earhole[sd]); c.seam(chain, closed=False)
    box = ((0.22, -0.05, 0.26), (0.30, 0.12, 0.42)) if sd > 0 else ((-0.30, -0.05, 0.26), (-0.22, 0.12, 0.42))
    c.close_to(prev, c.extreme(box[0], box[1], (sd, 0, 0)))                # the ear closes to its real tip

# ---- horns: up off the crown, then back: rings in planes y = const; the root's front edge becomes the horn's top;
# the root's directions EVENED round the tube (3 on top / 3 below = a crease)
for sd in (+1, -1):
    base = np.mean([c.V[i][:2] for i in hornhole[sd]], axis=0)
    raw = [(np.asarray(c.V[i])[0] - base[0], -(np.asarray(c.V[i])[1] - base[1])) for i in hornhole[sd]]
    a0 = math.atan2(raw[0][1], raw[0][0]); turn = 1 if raw[0][0] * raw[1][1] - raw[0][1] * raw[1][0] > 0 else -1
    dirs = [(math.cos(a0 + turn * 2 * math.pi * k / 6), math.sin(a0 + turn * 2 * math.pi * k / 6)) for k in range(6)]
    prev = hornhole[sd]
    for y, cx, cz in ((0.10, 0.078, 0.459), (0.14, 0.088, 0.47), (0.18, 0.098, 0.467), (0.215, 0.104, 0.459)):
        r = c.ring((0, y, 0), Y, X, Z, dirs, pick2d=(cx * sd, cz)); c.bridge(prev, r); prev = r
    c.seam(hornhole[sd])
    box = ((0.06, 0.20, 0.40), (0.16, 0.30, 0.50)) if sd > 0 else ((-0.16, 0.20, 0.40), (-0.06, 0.30, 0.50))
    tip = c.add(c.extreme(box[0], box[1], (0, 1, 0)))                       # the horn closes where it really ends
    c.quad(prev[0], prev[1], prev[2], tip); c.quad(prev[2], prev[3], prev[4], tip); c.quad(prev[4], prev[5], prev[0], tip)

# the body's own seam: down the back from the crown to the pelvis floor; the eye holes; the neck (head = own island)
c.seam([g[(3, 2)], H[5][8], H[4][8], H[3][8], H[2][8], H[1][8], H[0][8], Nk[1][8], Nk[0][8]] + [t[8] for t in reversed(T)]
       + [pf[(2, 4)], pf[(2, 3)], pf[(2, 2)]], closed=False)
for sd in (+1, -1):
    c.seam(eyehole[sd])
c.seam(Nk[1])
