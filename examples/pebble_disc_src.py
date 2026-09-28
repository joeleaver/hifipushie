"""Generate the pebble_disc terrain spec (examples/pebble_disc.json): a Pebble Beach-inspired 18-hole disc golf course.

    uv run python examples/pebble_disc_src.py            # writes examples/pebble_disc.json
    uv run python examples/terrain_run.py examples/pebble_disc.json

Holes are tee -> (vias) -> basket lines. Each becomes a tee pad site and a basket site (props), a shaped fairway zone
(narrow off the tee, a landing zone, a round green at the basket, edges that wander), a band of trees lining it, a
sight-line intent per leg, and a walking route from its basket to the next tee.
"""
import json
import math
import random
from pathlib import Path

OUT = Path(__file__).parent

# ---- the land: Carmel Bay to the south and west. SW: the point (hole 7) and the chasm (hole 8). South-centre:
# Stillwater bay, irregular, a rocky headland on its east side (hole 17's basket), the lodge above its head.
LAND = [(1000, 800), (1000, 186), (900, 181), (820, 180), (775, 184), (742, 190), (716, 199), (708, 212),
        (716, 228), (729, 246), (724, 270), (700, 292), (668, 306), (640, 310), (612, 302), (590, 281),
        (578, 252), (566, 214), (553, 180), (520, 168), (420, 160), (330, 150),
        (275, 140), (246, 122), (236, 94), (214, 62), (192, 68), (181, 96), (176, 135), (172, 165), (160, 182),
        (120, 190), (80, 200), (58, 240), (72, 300), (66, 420), (86, 560), (78, 700), (92, 800)]

HOLES = [
    # front nine: inland from the lodge, down to the sea, out along the cliffs to the point
    dict(t=(545, 352), v=[(505, 400)], b=(470, 470), note="opener through the pines, gently uphill, dogleg right"),
    dict(t=(452, 478), v=[(400, 470)], b=(335, 420), note="rolling downhill between pine stands"),
    dict(t=(345, 402), v=[(382, 348)], b=(430, 272), note="down toward the sea: the bay opens up"),
    dict(t=(442, 226), b=(346, 184), note="along the shore, the sea a few metres off the left edge: OB"),
    dict(t=(326, 204), b=(276, 166), tee_level=10, par=3, note="short par 3 on the cliff edge, OB sea left"),
    dict(t=(318, 205), v=[(278, 252)], b=(238, 240), note="climb onto the headland plateau"),
    dict(t=(212, 176), b=(210, 112), par=3, note="the tiny par 3 down onto the point"),
    dict(t=(186, 190), b=(106, 242), par=3, note="the carry across the chasm, up to the far clifftop"),
    dict(t=(118, 256), v=[(100, 330)], b=(97, 400), note="clifftop, the cliff edge the whole way on the left: OB sea"),
    dict(t=(100, 418), v=[(98, 480)], b=(106, 552), note="clifftop, basket by the edge"),
    # back nine: an inland loop through the pines on the high ground
    dict(t=(142, 572), v=[(190, 625)], b=(255, 640), note="turn inland, uphill"),
    dict(t=(272, 648), b=(352, 690), par=3, note="par 3 in the pines"),
    dict(t=(368, 700), v=[(430, 690)], b=(500, 705), note="ridge line"),
    dict(t=(515, 695), v=[(610, 700)], b=(690, 648), note="the long one, dogleg right"),
    dict(t=(705, 640), v=[(760, 640)], b=(830, 612), note="rolling"),
    dict(t=(848, 598), b=(872, 452), tee_level=16.5, note="downhill toward the coast"),
    dict(t=(840, 318), b=(733, 222), par=3, note="par 3 out onto the rocky headland"),
    dict(t=(752, 252), v=[(724, 306), (672, 344)], b=(598, 340),
         note="curving along the sea wall round the bay's head to the lodge"),
]
LODGE = (615, 378)
CAR = (650, 452)
BAY = [645, 250]  # Stillwater's water, for the lodge to overlook

PEAKS = {
    "arrowhead": {"at": [230, 242], "h": 28, "radius": 38, "base_radius": 115},
    "west_downs": {"at": [140, 340], "h": 24, "radius": 60, "base_radius": 170},
    "knoll_a": {"at": [560, 560], "h": 30, "radius": 30, "base_radius": 150},
    "knoll_b": {"at": [300, 520], "h": 28, "radius": 25, "base_radius": 130},
    "knoll_c": {"at": [745, 500], "h": 30, "radius": 30, "base_radius": 140},
    "the_point": {"at": [210, 100], "h": 11, "radius": 22, "base_radius": 60},
    "north_rise": {"at": [500, 780], "h": 36, "radius": 150, "base_radius": 350},
}
COVES = {"chasm": {"at": [150, 190], "width": 55, "depth": 110, "beach": False, "apron": 0}}
STORY = ("A disc golf course on a clifftop peninsula above a bay, inspired by Pebble Beach Golf Links on Carmel Bay: "
         "a lodge above a sheltered bay, inland holes rolling through pines down to the sea, a run of clifftop holes "
         "(a tiny par 3 onto a rocky point, a carry across a cliff chasm, holes along the cliff edge with the sea as out "
         "of bounds), then back inland through the pines and a finish out onto the bay's rocky headland and along its "
         "sea wall to the lodge. Wind-shaped cypress on the points, pines inland in stands and lining the fairways, "
         "open mown grass everywhere else.")


def line(h):
    return [h["t"], *h.get("v", []), h["b"]]


def length(h):
    p = line(h)
    return sum(math.dist(a, b) for a, b in zip(p, p[1:]))


def _sample(pts, step=4.0):
    """Points along the polyline every ~step m, with the fraction along it and a smoothed direction."""
    out = []
    total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    s = 0.0
    for a, b in zip(pts, pts[1:]):
        L = math.dist(a, b)
        n = max(1, int(L / step))
        for k in range(n):
            u = k / n
            out.append(((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u), (s + L * u) / total))
        s += L
    out.append((pts[-1], 1.0))
    dirs = []
    for i in range(len(out)):
        p0 = out[max(i - 3, 0)][0]
        p1 = out[min(i + 3, len(out) - 1)][0]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        n = math.hypot(dx, dy) or 1
        dirs.append((dx / n, dy / n))
    return out, dirs


def width(h, u, extra=0.0):
    """Fairway width along the hole: narrow off the tee, a landing zone, narrower toward the basket."""
    if h.get("par") == 3:
        w = 12 + 12 * min(u / 0.5, 1)
    else:
        land = math.exp(-((u - 0.62) / 0.22) ** 2)
        w = 10 + 18 * min(u / 0.25, 1) + 10 * land - 4 * max(0, (u - 0.8) / 0.2)
    return w + extra


def corridor(h, extra=0.0, seed=0):
    """A shaped fairway polygon (or a wider band for the trees lining it), edges wandering a few metres."""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.28) for _ in range(4)]
    pts, dirs = _sample(line(h))
    left, right = [], []
    for (p, u), (dx, dy) in zip(pts, dirs):
        nx, ny = -dy, dx
        s = u * length(h)
        wl = width(h, u, extra) / 2 + 2.5 * math.sin(s / 23 + ph[0]) + 1.5 * math.sin(s / 9 + ph[1])
        wr = width(h, u, extra) / 2 + 2.5 * math.sin(s / 19 + ph[2]) + 1.5 * math.sin(s / 11 + ph[3])
        left.append((p[0] + nx * wl, p[1] + ny * wl))
        right.append((p[0] - nx * wr, p[1] - ny * wr))
    # a round green at the basket (a putting circle): the basket end bulges out
    bx, by = h["b"]
    dx, dy = dirs[-1]
    ang0 = math.atan2(dy, dx)
    r = 12 + extra / 2
    cap = [(bx + r * math.cos(ang0 + math.pi / 2 - k * math.pi / 8), by + r * math.sin(ang0 + math.pi / 2 - k * math.pi / 8))
           for k in range(9)]
    poly = left + cap + right[::-1]
    return [[round(x, 1), round(y, 1)] for x, y in poly]


def spec():
    zones = {
        "land": {"polygon": [list(p) for p in LAND]},
        "cliff_coast": {"polygon": [[0, 0], [300, 0], [300, 130], [230, 200], [190, 300], [170, 520], [200, 660], [0, 660]]},
        "headland17": {"near": [728, 225], "radius": 40},
        "inland": {"all": ["land", {"not": {"near": "sea", "radius": 70}}]},
    }
    fw, lining = [], []
    for i, h in enumerate(HOLES, 1):
        zones[f"fairway{i}"] = {"polygon": corridor(h, seed=i)}
        zones[f"lining{i}"] = {"polygon": corridor(h, extra=46, seed=100 + i)}
        fw.append(f"fairway{i}")
        lining.append(f"lining{i}")
    zones["fairways"] = {"any": fw}
    zones["linings"] = {"any": lining}
    zones["clubhouse"] = {"any": [{"near": "lodge", "radius": 45}, {"near": "car_park", "radius": 40}]}
    sites = {"lodge": {"at": list(LODGE), "radius": 22, "overlooks": BAY, "shoulder": 12, "prop": "lodge",
                       "facing": BAY},
             "car_park": {"at": list(CAR), "radius": 24, "shoulder": 12, "toward": "south", "fall": 0.03}}
    intent = {}
    for i, h in enumerate(HOLES, 1):
        sites[f"t{i}"] = {"at": list(h["t"]), "radius": 3, "shoulder": 4, "prop": "tee_pad",
                          "facing": list(line(h)[1]) if h.get("v") else f"b{i}"}
        if "tee_level" in h:  # a raised tee box, so the basket shows over the rise in front
            sites[f"t{i}"]["level"] = h["tee_level"]
        sites[f"b{i}"] = {"at": list(h["b"]), "radius": 4, "shoulder": 5, "prop": "disc_basket", "facing": f"t{i}"}
        legs = line(h)
        for k, (a, b) in enumerate(zip(legs, legs[1:])):
            frm = f"t{i}" if k == 0 else list(a)
            tgt = {"at": f"b{i}", "height": 1.3} if k == len(legs) - 2 else {"at": list(b), "height": 1.0}
            intent[f"hole{i}_leg{k + 1}"] = {"from": frm, "see": [tgt]}
    routes = {"to_first_tee": {"from": "car_park", "to": "t1", "via": ["lodge"]},
              "home": {"from": "b18", "to": "lodge"}}
    for i in range(1, 18):
        routes[f"walk{i}"] = {"from": f"b{i}", "to": f"t{i + 1}"}
    for r in routes.values():
        r.update({"width": 2, "max_grade": 0.22, "max_fill": 3})
    for k in ("walk6", "walk7", "walk8"):  # clifftop paths down to the point and up from it: stepped
        routes[k]["max_grade"] = 0.33
    return {
        "story": STORY,
        "world": {"kind": "coast", "compression": "auto", "base": 13},
        "units": "m",
        "extent": [[0, 0], [1000, 800]],
        "cell": 2,
        "tilt": {"down": 160, "grade": 0.025},
        "zones": zones,
        "peaks": PEAKS,
        "sea": {"level": 0, "land": "land", "wander": 0.05, "depth": 20, "shore": "beach",
                "cliffs": {"height": [6, 10], "only": ["cliff_coast", "headland17"], "platform": 12, "geos": 0,
                           "stacks": {"count": 3, "at": "the_point"}},
                "beaches": {"stillwater_beach": {"at": [640, 312], "length": 70},
                            "sea_wall": {"at": [712, 290], "length": 70}},
                "coves": COVES},
        "sites": sites,
        "routes": routes,
        "cover": {
            "rough": {"type": "meadow", "in": "land", "density": 0.8, "color": "#6f8d3e"},
            "fairway": {"type": "grass", "in": "fairways", "density": 1.0, "color": "#4f9d34"},
            "pines_lining": {"type": "conifer", "trees": "pine", "in": {"all": ["linings", "inland"]},
                             "density": 0.16, "avoid": ["fairways", "routes", "sites", "clubhouse"],
                             "breakup": {"scale": 40, "amount": 0.8}},
            "pine_stands": {"type": "conifer", "trees": "pine", "in": "inland", "density": 0.3,
                            "avoid": ["fairways", "routes", "sites", "clubhouse"],
                            "breakup": {"scale": 120, "amount": 1.6}},
            "specimen_pines": {"type": "conifer", "trees": "pine", "in": "inland", "count": 45,
                               "avoid": ["fairways", "routes", "sites", "clubhouse"]},
            "cypress": {"type": "conifer", "trees": "cypress",
                        "in": {"all": [{"near": "sea", "radius": 45}, {"any": ["cliff_coast", "headland17"]}]},
                        "count": 45, "slope": [0, 35], "avoid": ["fairways", "routes", "sites"], "color": "#1f3322"},
            "cliff_rock": {"type": "rock", "in": "cliffs"},
            "sand": {"type": "sand", "in": {"any": [{"all": ["beach", {"near": "sea", "radius": 6},
                                                             {"not": {"near": [716, 285], "radius": 45}}]},
                                                    {"near": [640, 312], "radius": 35}]}},
            "sea_wall_rocks": {"type": "rock", "in": {"all": [{"near": "sea", "radius": 7},
                                                              {"near": [716, 285], "radius": 50}]},
                               "slope": [0, 90], "color": "#6b6660"},
            "shore_rocks": {"type": "rock", "in": {"all": [{"near": "sea", "radius": 3}, {"not": {"near": [640, 312],
                                                                                             "radius": 45}}]},
                            "slope": [0, 90], "breakup": {"scale": 12, "amount": 0.8}},
            "boulders": {"type": "rock", "in": "cliff_foot"},
        },
        "intent": intent,
        "export": {"size": 1025, "engine": "unity"},
        "erosion": {"strength": 0.25},
        "rock": {"buttresses": 0.3},
        "notes": "Generated by examples/pebble_disc_src.py. Holes: " + "; ".join(
            f"{i}: {round(length(h))} m, {h['note']}" for i, h in enumerate(HOLES, 1)),
    }


def sketch():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1000, 800), (70, 110, 160))
    d = ImageDraw.Draw(im)
    f = lambda p: (p[0], 800 - p[1])
    d.polygon([f(p) for p in LAND], fill=(140, 170, 110))
    for i, h in enumerate(HOLES, 1):
        d.polygon([f(p) for p in corridor(h, extra=46, seed=100 + i)], outline=(30, 80, 30))
        d.polygon([f(p) for p in corridor(h, seed=i)], fill=(90, 190, 70))
        d.line([f(p) for p in line(h)], fill=(255, 255, 255), width=1)
        d.text(f((h["t"][0] + 5, h["t"][1] + 5)), str(i), fill=(0, 0, 0))
    im.save(OUT / "sketch.png")


if __name__ == "__main__":
    (OUT / "pebble_disc.json").write_text(json.dumps(spec(), indent=1))
    for i, h in enumerate(HOLES, 1):
        print(i, round(length(h)), h["note"])
    print("total", round(sum(length(h) for h in HOLES)))
