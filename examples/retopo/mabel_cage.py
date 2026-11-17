# Mabel (a cow standing on two legs; arms drawn pressed to her sides; a big head with a muzzle, horns and ears):
# the artist's decisions for her low cage. Run by retopo_cage (in scope: c, s, full, az, X, Y, Z, np, math).
# The spike's frame: centred, feet at z ~ -0.5, ~1.0 tall. 16 round every body ring (k: 0 front, 4 +x, 8 back, 12 -x).
N = 16
A = [az(360 / N * k) for k in range(N)]

# ---- torso, hips to shoulder tops. ARMS FUSED to the torso (the concept drew them pressed to her sides): the real
# armpit is put at z 0.01, so the shoulder root is as tall as the arm is thick (~11 cm; at 0.06 the raised arm necked
# through a 6 cm hole). Under it the torso's side carries on, INVENTED (pinned: not pressed onto the fused sculpt).
TZ = [-0.235, -0.17, -0.10, -0.025, 0.01, 0.12]
T = [c.hring(z, A, centre=c.centre_of(z, (0, 0.07)), pick=(0, 0.07)) for z in TZ]
TORSO_SIDE = 0.178          # the torso's half width under the arm (its side at z -0.03 is 0.182)
for sd, ks in ((+1, (3, 4, 5)), (-1, (11, 12, 13))):
    for k in ks:
        p = np.asarray(c.V[T[3][k]]); q = np.asarray(c.V[T[4][k]])
        c.put(T[4][k], (sd * min(abs(q[0]), TORSO_SIDE + (0.0 if k in (4, 12) else -0.012)), q[1] if k in (4, 12) else p[1], q[2]))
        c.pin(T[4][k])
for a, b in zip(T, T[1:-1]):
    c.bridge(a, b)
c.bridge(T[4], T[5], skip={3, 4, 11, 12})          # shoulder holes: the shoulder ball only
armhole = {+1: [T[5][3], T[5][4], T[5][5], T[4][5], T[4][4], T[4][3]],
           -1: [T[5][13], T[5][12], T[5][11], T[4][11], T[4][12], T[4][13]]}

# ---- head rings: neck, below / beside / above the muzzle, brow, crown
HZ = [0.17, 0.24, 0.32, 0.42, 0.445]
H = [c.hring(z, A, centre=(0.0, 0.0)) for z in HZ]
# the MUZZLE's root loop: an oval round the snout seen from the front, pressed onto the face
MC, ma, mb = (0.0, 0.232), 0.125, 0.10
root = [H[0][14], H[0][15], H[0][0], H[0][1], H[0][2], H[1][2], H[2][2], H[2][1], H[2][0], H[2][15], H[2][14], H[1][14]]
ang = {H[0][0]: -90, H[0][1]: -55, H[0][2]: -25, H[1][2]: 0, H[2][2]: 22, H[2][1]: 58, H[2][0]: 90,
       H[2][15]: 122, H[2][14]: 158, H[1][14]: 180, H[0][14]: 205, H[0][15]: 235}
under = lambda x: c.hit((x, -0.10, 0.12), (0, 0, 1))   # the jaw's underside, looking up from just under the chin
for i, th in ang.items():
    t = math.radians(th); x, z = MC[0] + ma * math.cos(t), MC[1] + mb * math.sin(t)
    c.put(i, under(x) if th < -20 or th > 200 else c.front(x, z))
# the EYES: their loops sit on the muzzle's top edge and under the brow
EC = {+1: (0.088, 0.352), -1: (-0.088, 0.352)}
c.put(H[3][1], c.front(0.050, 0.392)); c.put(H[3][2], c.front(0.125, 0.392))
c.put(H[3][15], c.front(-0.050, 0.392)); c.put(H[3][14], c.front(-0.125, 0.392))
eyehole = {+1: [H[2][1], H[2][2], H[3][2], H[3][1]], -1: [H[2][15], H[2][14], H[3][14], H[3][15]]}

# the throat under the overhanging jaw is a deep crease: its row is relaxed across it, not pressed into it
c.pin([T[5][k] for k in (14, 15, 0, 1, 2)])
c.pin([H[0][k] for k in (2, 14)])                   # the jaw's corners, where that crease turns up the cheek
c.bridge(T[5], H[0])
c.bridge(H[0], H[1], skip={14, 15, 0, 1})
c.bridge(H[1], H[2], skip={14, 15, 0, 1})
c.bridge(H[2], H[3], skip={1, 3, 4, 11, 12, 14})    # eyes (1, 14) and ears (3-4, 11-12)
c.bridge(H[3], H[4])
earhole = {+1: [H[2][3], H[2][4], H[2][5], H[3][5], H[3][4], H[3][3]],
           -1: [H[2][13], H[2][12], H[2][11], H[3][11], H[3][12], H[3][13]]}

# crown: a 6 x 2 grid; each horn comes out of two of its cells
g = c.cap_grid(H[4], 6, 2, lambda i, j, p: c.top(p[0], p[1]))
c.fill(g, 6, 2, holes={(5, 0), (5, 1), (0, 0), (0, 1)})
hornhole = {+1: [g[(5, 0)], g[(6, 0)], g[(6, 1)], g[(6, 2)], g[(5, 2)], g[(5, 1)]],
            -1: [g[(1, 0)], g[(0, 0)], g[(0, 1)], g[(0, 2)], g[(1, 2)], g[(1, 1)]]}

# ---- muzzle: concentric loops forward to the nose pad; the mouth: the 0.5 loop's bottom arc lies on her lip crease
prev = root; rings_m = []
for sc_ in (0.78, 0.5):
    r = c.inset(root, MC, sc_); c.bridge(prev, r); prev = r; rings_m.append(r)
r1, r2 = rings_m
# the lip line: the 0.5 loop's bottom arc sits on the muzzle's front (z ~0.19-0.23, a smile); her real crease is a
# straight notch under the overhanging upper lip at z ~0.175: move the arc and its corners onto it
for k in (0, 1, 2, 3, 4):
    c.put(r2[k], c.crease(c.V[r2[k]][0], 0.15, 0.20))
c.mouth(r1, r2, lip=[1, 2, 3])

# ---- eyes: two concentric loops, closed by one quad
for sd in (+1, -1):
    prev = eyehole[sd]
    for sc_ in (0.62, 0.3):
        r = c.inset(eyehole[sd], EC[sd], sc_); c.bridge(prev, r); prev = r
    c.quad(*prev)

# ---- arms: out of the shoulder hole; smooth tracks from the root to the free arm, then contours to the hoof.
# Tracks starting on the invented torso side (the armpit half) leave sideways and stay invented.
for sd in (+1, -1):
    centre0 = (0.261 * sd, -0.02)
    adeg = [30, 90, 150, 210, 270, 330] if sd > 0 else [330, 270, 210, 150, 90, 30]
    prev = armhole[sd]
    rings = [c.hring(z, [az(d) for d in adeg], pick=centre0) for z in (-0.05, -0.10, -0.15, -0.19)]
    ring_c = lambda r: np.mean([c.V[i] for i in r], axis=0)
    mids = c.tracks(prev, rings[0], ring_c(rings[1]) - ring_c(rings[0]), pinned_out=(sd, 0.0, 0.0))
    c.seam(armhole[sd]); chain = [prev[4]]
    for r in mids + rings:
        c.bridge(prev, r); prev = r; chain.append(r[4])
    c.seam(chain, closed=False); c.seam(prev)       # root, inner line, sole
    c.cap6(prev)

# ---- legs (wide and stubby): the hip loop splits through a crotch vertex; contours down to the hoof
C = c.add(c.bottom(0.0, 0.066))
c.pin(C, T[0][8])                                   # the crotch: a deep crease, relaxed across
half = N // 2
legloop = {+1: [T[0][k] for k in range(0, half + 1)] + [C], -1: [T[0][k % N] for k in range(half, N + 1)] + [C]}
for sd in (+1, -1):
    centre = (0.106 * sd, 0.067)
    dirs = c.dirs_from(legloop[sd], centre); prev = legloop[sd]; c.seam(legloop[sd]); chain = [prev[-1]]
    for z in (-0.29, -0.35, -0.41, -0.46, -0.49):
        r = c.hring(z, dirs, pick=centre); c.bridge(prev, r); prev = r; chain.append(r[-1])
    c.seam(chain, closed=False); c.seam(prev)
    gl = c.cap_grid(prev, 3, 2, lambda i, j, p: c.bottom(p[0], p[1]))
    c.fill(gl, 3, 2)

# ---- ears: contours outwards in planes x = const
for sd in (+1, -1):
    dirs = [(-1, -1), (0, -1), (1, -1), (1, 1), (0, 1), (-1, 1)]
    prev = earhole[sd]; c.seam(earhole[sd]); chain = [prev[1]]
    for x in (0.165, 0.20, 0.235):
        r = c.ring((x * sd, 0, 0), X, Y, Z, dirs, pick2d=(0.007, 0.377)); c.bridge(prev, r); prev = r; chain.append(r[1])
    c.seam(chain, closed=False)
    c.cap6(prev)

# ---- horns: contours up from the crown
for sd in (+1, -1):
    centre = (0.104 * sd, -0.004)
    dirs = c.dirs_from(hornhole[sd], centre); prev = hornhole[sd]; c.seam(hornhole[sd])
    for z in (0.465, 0.485):
        r = c.hring(z, dirs, pick=centre); c.bridge(prev, r); prev = r
    c.cap6(prev)

c.seam([g[(3, 2)]] + [h[8] for h in reversed(H)] + [t[8] for t in reversed(T)], closed=False)   # down the back
c.seam(T[5])                                                                                    # the head + neck island
