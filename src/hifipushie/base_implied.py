"""What a spec with a base implies: its joints (`inject`), its parts, the mouth's interior, the eye's own measures. Part of base (base.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import base
from .base import source, template_joints
from .base_gnm_parts import gnm_eyes, mouth_lips, mouth_mode, mouth_open
from .base_identity import _gnm_data
from .base_measures import _landmark_joints, head_of

def inject(spec: dict) -> dict:
    """The template's joints added to a spec with a "base" where it doesn't give them (its own win)."""
    b = spec.get("base")
    if not b:
        return spec
    if not isinstance(b, dict):
        raise ValueError('base is {"template": "male_stylized", ...}')
    out = dict(spec)
    joints = dict(spec.get("joints") or {})
    tj = template_joints(b)
    for k, j in tj.items():
        joints.setdefault(k, j)
    eb = source(b)["face"].get("eyeball")
    head = head_of({"joints": joints}, b)
    if head is not None:  # the grafted head's own eyes
        eb = {"centre": head["eyes"][0], "r": head["eye_r"]}
        joints.setdefault("eye.L", {"pos": [round(float(x), 4) for x in eb["centre"]], "r": round(eb["r"], 4)})
        # both eyes look at one point (base "look_at", default 2 m ahead at eye height on the centre line): the
        # iris sits where that line leaves the eyeball, joint eye_front.L (its r: the opening's height, a good
        # iris diameter is ~1.1 x that, so the lids cover its top and touch its bottom). A path seated from the
        # eyeball's centre went off in any direction: walleyed
        c = np.array(joints["eye.L"]["pos"], float)
        look = np.array(b.get("look_at") or (np.array([0.0, c[1], c[2]]) + 2.0 * head["forward"]), float)
        gz = (look - c) / np.linalg.norm(look - c)
        joints.setdefault("eye_front.L", {"pos": [round(float(x), 4) for x in c + eb["r"] * gz],
                                          "r": round(head["eye_open"], 4)})
        if b.get("look_at") is not None:  # a point off the centre line (a camera to one side): each eye turns to it
            # on its own (the mirrored .L gaze looked cross-eyed or walleyed at it)
            cr = np.asarray(head["eyes"][1], float)
            gr = (look - cr) / np.linalg.norm(look - cr)
            joints.setdefault("eye_front.R", {"pos": [round(float(x), 4) for x in cr + eb["r"] * gr],
                                              "r": round(head["eye_open"], 4)})
        for k, j in _landmark_joints(head).items():  # face landmarks to address strokes and paint by
            joints.setdefault(k, j)
        # the mouth closed behind the lips (GNM's mouth bag is left out of the field: its walls made the lips sparkle,
        # and without it parted lips showed a hole into the head)
        iu, il = head["lm68"][62], head["lm68"][66]  # inner lip midpoints
        mc = np.array(joints["lm_mouth_corner.L"]["pos"])
        # (a head that follows its body: the fill sized to the head. A child's head is 0.75-0.85 of the size the fill's
        # numbers were set at, and the fill came out through the lips' corners and showed pale inside the nostrils)
        ks = float(head["carry"]["s"]) / 1.1 if head.get("room") else 1.0
        mode = mouth_mode(b, head)
        if mode == "gnm" and mouth_open(b, head):
            pass  # GNM's own mouth, open: its sock closes the cavity in the head's own field (surface); no fill
        elif mode == "kit":  # the face kit's mouth that can open (face shapes): slit, bag, teeth, tongue
            mi = mouth_interior(head, b["head"])
            if float((b.get("head") or {}).get("lip_seal") or 0.0) >= 0.5:
                # a SEALED mouth (lip_seal, field only): the slit and the bag kept (face shapes read them) but held
                # behind the fused lips (sealed_interior)
                mi = sealed_interior(mi, head)
            out["blobs"] = {**(out.get("blobs") or spec.get("blobs") or {}), **mi}
        elif float(np.linalg.norm(iu - il)) > 0.0015:  # parted lips (a fill behind closed ones made them pout)
            blobs = dict(out.get("blobs") or spec.get("blobs") or {})
            blobs.setdefault("mouth_fill", {"at": [round(float(x), 4) for x in 0.5 * (iu + il) + [0, 0.012, 0]],
                                            "size": [round(float(mc[0]) * 0.8, 4), 0.008,
                                                     round(float(np.linalg.norm(iu - il)) * 0.5 + 0.001, 4)],
                                            "blend": 0.003})
            out["blobs"] = blobs
        else:  # closed lips: the cavity behind them filled from 6 mm back (left open, the field had an outside
            # pocket in the head there: the export's topology wrap projected the lips and chin into it)
            blobs = dict(out.get("blobs") or spec.get("blobs") or {})
            seam = 0.5 * (iu + il)
            # (a followed head: lower and flatter. At its full height the fill's top stood in the nostrils' floor, two
            # pale pegs seen from the front under every nose)
            zc, zr = (-0.008, 0.013) if head.get("room") else (-0.004, 0.02)
            blobs.setdefault("mouth_fill", {"at": [round(float(x), 4) for x in seam + np.array([0, 0.036, zc]) * ks],
                                            "size": [round(float(mc[0]) * 0.85, 4), round(0.03 * ks, 4), round(zr * ks, 4)],
                                            "blend": round(0.004 * ks, 4)})
            out["blobs"] = blobs
    elif eb:  # eye.L: the template eyeball's centre, riding the head joint (paint anchors, the eyes part)
        off = np.array(eb["centre"]) - np.array(tj["head"]["pos"])
        joints.setdefault("eye.L", {"pos": [round(float(x), 4) for x in np.array(joints["head"]["pos"]) + off],
                                    "r": eb["r"]})
    if eb and b.get("eyes"):  # eyeballs as their own part, filling the base's sockets
        blobs = dict(out.get("blobs") or spec.get("blobs") or {})
        blobs.setdefault("eye.L", {"at": "eye.L", "size": [round(float(eb["r"]), 4)] * 3, "part": b["eyes"]})
        eg = head.get("eye_gnm") if head is not None else None  # (gnmnative) GNM's own two-sphere eye
        if (b.get("cornea") if b.get("cornea") is not None else bool(eg)) and "eye_front.L" in joints:
            # the cornea's bulge over the iris: a smaller sphere standing proud where the gaze leaves the eyeball;
            # highlights bend over it and the limbus gets a profile. On a GNM head with GNM's own eyeball it is ON by
            # default and it is GNM's corneal sphere for the identity (its eyes_* components: radius ~7.7 mm, apex
            # ~1.6 mm proud on the template). base "cornea": true | false | {"bulge": 0.09 (x the eyeball's radius),
            # "radius": 0.62} (given numbers win; they are also the defaults without GNM's eye)
            co = b["cornea"] if isinstance(b.get("cornea"), dict) else {}
            R = float(eb["r"])
            rc, bulge = float(co.get("radius", 0.62)) * R, float(co.get("bulge", 0.09)) * R
            if eg and "radius" not in co and "bulge" not in co:
                rc, bulge = float(eg["cornea_r"]), float(eg["apex"]) - R
                if co.get("clear") and "depth" not in co:  # the anterior chamber: GNM's iris disc behind its apex
                    co = {**co, "depth": (float(eg["apex"]) - float(eg["iris_depth"])) * 0.0118 / R}
            for sd in (".L",):  # .R is its mirror (an explicit cornea.R blob came out as a second, giant eyeball)
                c = np.array(joints[f"eye{sd}"]["pos"] if f"eye{sd}" in joints else np.array(joints["eye.L"]["pos"]) * [-1, 1, 1], float)
                gz = np.array(joints[f"eye_front{sd}"]["pos"], float) - c
                gz /= np.linalg.norm(gz)
                if co.get("clear"):  # (eyedetail) a clear cornea over a recessed iris: see clear_cornea
                    blobs.update(clear_cornea({**b, "cornea": co}, c, gz, R, rc, bulge, sd))
                    continue
                # one group with its eyeball (joined softly, then unioned as one): as two elements with different
                # blends the scene's chunked evaluation blew the mirrored eye up into a ball twice its size
                grp = {"group": f"eyeball{sd}", "join": round(0.12 * R, 5), "blend": 0.0}
                blobs[f"eye{sd}"] = {**blobs[f"eye{sd}"], **grp}
                blobs.setdefault(f"cornea{sd}", {"at": [round(float(x), 5) for x in c + (R - rc + bulge) * gz],
                                                  "size": [round(rc, 5)] * 3, "part": b["eyes"], **grp})
        out["blobs"] = blobs
    out["joints"] = joints
    return out


def clear_cornea(b: dict, c, gz, R: float, rc: float, bulge: float, sd: str = ".L") -> dict:
    """base.cornea = {"clear": true, "depth": m (0.0028)}: the eye as a game head builds it (MetaHuman's refractive
    cornea, done with geometry). The eyeball's front is cut flat at the iris plane, `depth` behind the cornea's apex
    (the anterior chamber: 2.5-3.2 mm in adults), so the iris is a recessed disc (the plane meets the 12 mm ball ~6 mm
    off its axis: the iris' own size); the cornea is its own part ("<eyes>_cornea": implied_parts) filling the
    chamber, a clear lens (transmission, IOR 1.376) whose front is the bulge. Through it the iris sits behind the
    surface, shifts with the view and takes the catchlight on top: a painted disc on an opaque bulge did neither."""
    co = b["cornea"] if isinstance(b.get("cornea"), dict) else {}
    depth = float(co.get("depth", 0.0028)) * R / 0.0118
    eyes = b["eyes"]
    apex = R + bulge
    d_i = apex - depth  # the iris plane's distance from the ball's centre
    big = base.CORNEA_BIG
    at = lambda k: [round(float(x), 5) for x in c + k * gz]  # noqa: E731
    return {
        f"iris_cut{sd}": {"at": at(d_i + big), "size": [big] * 3, "op": "subtract", "blend": 0.0, "part": eyes},
        f"cornea{sd}": {"at": at(R - rc + bulge), "size": [round(rc, 5)] * 3, "blend": 0.0, "part": f"{eyes}_cornea"},
        # the lens' back: everything behind the plane taken off (a subtract per eye: two "intersect" caps, one per
        # eye, left nothing, each keeping only what's inside it), a hair in front of the iris (coincident faces: the
        # refraction met the iris' own face)
        f"cornea_back{sd}": {"at": at(d_i + 0.00008 - big), "size": [big] * 3, "op": "subtract", "blend": 0.0,
                             "part": f"{eyes}_cornea"},
    }


def implied_parts(spec: dict) -> dict:
    """Parts the base makes that the spec needn't list, with their channels (a listed part's keys win, merged by
    scene / asset): the clear cornea's lens; GNM's own mouth ("teeth" / "teeth_lower": the rows with their gums, "tongue")."""
    b = spec.get("base") or {}
    co = b.get("cornea")
    out = {}
    if isinstance(co, dict) and co.get("clear") and b.get("eyes"):
        out[f"{b['eyes']}_cornea"] = {"color": "#ffffff", "transmission": 1.0, "ior": 1.376, "roughness": 0.02,
                                      "specular": 0.6, "voxel": 0.0003, "rig_bone": None}
    if mouth_mode(b) == "gnm":
        out.update({k: dict(v) for k, v in base.MOUTH_PARTS.items()})
    if b.get("eyes"):   # the eyeballs meshed fine (the scene voxel left the iris / pupil edge and the cornea in visible
        out.setdefault(b["eyes"], {})["voxel"] = base.EYE_PART_VOXEL   # polygon steps in every close-up)
    return out


def part_defs(spec: dict) -> dict:
    """spec["parts"] with the base's implied parts filled in (their keys under the listed ones)."""
    defs = dict(spec.get("parts") or {})
    for k, v in implied_parts(spec).items():
        defs[k] = {**{kk: vv for kk, vv in v.items() if vv is not None}, **(defs.get(k) or {})}
    return defs


def sealed_interior(mi: dict, head: dict) -> dict:
    """The interior's slit and bag (subtracts) for a SEALED mouth: their cuts reached through the fused lips (the slit
    from in front of them, the bag's box to ~2 mm of their front): a row of holes and pale "fangs" (the teeth through
    them) along the seam in every render of a sealed head with an interior (Garrett gj6 / gj8, 2026-10-09). Kept, for
    the face shapes that read them, but held SEALED_BACK behind the lips' front (the slit's front end, the bag)."""
    out_dir = np.asarray(mouth_lips(head)["out"], float)
    mi = dict(mi)
    for k, v in list(mi.items()):
        if k.endswith("_mouth_slit"):
            v = {**v, "values": {**v["values"], "n1": [-base.SEALED_BACK] * len(np.atleast_1d(v["values"]["n1"]))}}
            mi[k] = v
        elif k.endswith("_mouth_bag"):
            mi[k] = {**v, "at": [round(float(x), 5) for x in np.asarray(v["at"], float) - base.SEALED_BACK * out_dir]}
    return mi


def mouth_interior(head: dict, hd: dict) -> dict:
    """The face kit's mouth interior (kits._interior: slit, bag, teeth and tongue parts) behind a GNM head's lips
    (head["interior"], same keys). GNM's own mouth bag, teeth and tongue are not used: the head's style pushes move
    the lips (6 mm back on the golfer) and left GNM's teeth standing in front of them."""
    from . import kits
    m = mouth_lips(head)
    pts, knots = m["pts"], m["knots"]

    def on_skin(u, dz, o):
        p = np.array([np.interp(u, knots, pts[:, j]) for j in range(3)])
        p = p + m["side"] * ((u * (pts[-1] - m["M"]) @ m["side"]) - (p - m["M"]) @ m["side"])  # x exactly u
        return p + m["up"] * dz + m["out"] * o
    o = kits._Out({}, "base")
    kits._interior({"interior": hd["interior"]}, None, on_skin, np.linspace(0.0, 1.0, 7), kits._frame(m["out"]),
                   m["width"], m["ru"], m["rl"], m["gap"], o, "face")
    return o.blobs


def eye_native(spec: dict) -> dict | None:
    """GNM's own eye on a spec's built head (gnm_head's "eye_gnm", world metres: "limbus", "cornea_r", "apex",
    "iris_r", "iris_depth", "pupil_r", "pupil" = the pupil over the iris disc), or None: no GNM head, or
    base.head.eye_radius overrides the ball."""
    b = spec.get("base") or {}
    hd = b.get("head")
    if not isinstance(hd, dict) or hd.get("eye_radius") or hd.get("source", "gnm") != "gnm":
        return None
    if (b.get("body") or {}).get("source") == "human":
        from . import onemesh_head
        ht = onemesh_head.head_rest(b)
    else:
        ht = head_of({"joints": inject(spec)["joints"]}, b)
    return None if ht is None else ht.get("eye_gnm")


def drawn_iris(spec: dict, r_ball: float | None = None, legacy: float = 0.51 * 0.985) -> float:
    """The drawn iris' RADIUS (m): skin.eyes.iris_size / 2 when set; else GNM's limbus for the identity (its
    `eyes_000` component; eye_native); else (our own ball) `legacy` x the ball's radius."""
    drawn = ((spec.get("skin") or {}).get("eyes") or {}) if isinstance((spec.get("skin") or {}).get("eyes"), dict) else {}
    if drawn.get("iris_size"):
        return 0.5 * float(drawn["iris_size"])
    eg = eye_native(spec)
    if eg:
        return float(eg["limbus"])
    return legacy * float(r_ball if r_ball is not None else 0.012)


def limbus_identity(spec: dict, iris_mm: float) -> dict:
    """The identity's `eyes_000` (GNM's limbus component, sd 1: ~0.4 mm of limbus radius on its 14.6 mm ball) that
    makes the built head's limbus DIAMETER iris_mm (mm, world), the other eye components kept: {"eyes_000": value,
    "from_mm", "sd"}. Linear in the component; raises past 3 sd (no eye in GNM's population has that iris)."""
    eg = eye_native(spec)
    if eg is None:
        raise ValueError("limbus_identity: the head has no GNM eyeball (base.head.eye_radius overrides it: drop that key)")
    g = _gnm_data()
    names = [str(n) for n in g["identity_names"]]
    i = names.index("eyes_000")
    T = g["template_vertex_positions"].astype(float)
    cur = float(((spec["base"]["head"].get("identity") or {}) if isinstance(spec["base"]["head"].get("identity"), dict) else {}).get("eyes_000", 0.0))
    lim = lambda v: gnm_eyes(T + v * g["vertex_identity_basis"][i], g)[0]["limbus"]  # noqa: E731
    l0 = lim(cur)
    k = float(eg["limbus"]) / l0  # world over GNM's frame (the head's scale x the eye piece's)
    want = 0.0005 * float(iris_mm) / k
    v = cur
    for _ in range(6):  # (nearly linear: 0.37-0.50 mm per sd; a few secant steps)
        lv = lim(v)
        v = float(np.clip(v + (want - lv) / max(lim(v + 0.25) - lv, 1e-7) * 0.25, -6.0, 6.0))
    if abs(v) > 3.0:
        raise ValueError(f"limbus_identity: an iris of {iris_mm:.2f} mm needs eyes_000 {v:+.2f} (past 3 sd; the model draws "
                         f"{2000 * eg['limbus']:.2f} mm): check the read, or set skin.eyes.iris_size for a drawn iris")
    return {"eyes_000": round(v, 4), "from_mm": round(2000 * float(eg["limbus"]), 3), "sd": round(v - cur, 3)}
