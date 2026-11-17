"""Hard surface from the point cloud: the PART format (what the fitters return and blender_hardsurf_build meshes).

Every part is one object with its own artist UV seams; coordinates are the framed sculpt's (z up, front -y, metres).
TYPES (required keys):
- lathe   origin, axis, profile [[t, r], ...] from the axis round the outside back to the axis (t along the axis)
          optional: seg (32), support (True: support loops at corners > 40 deg), eps (0.003), cap (True), phase (deg)
- tube    paths [[[x,y,z], ...], ...] (one or more), r; optional: seg (12), closed, smooth (Catmull-Rom), step (0.02)
- loft    rings [[[x,y,z] * n], ...] (equal n, from hardsurf_fit.sweep_rings); optional: caps (True)
- rbox    c, size [x,y,z]; optional: rot [deg x,y,z], bevel (0.01), bseg (3)
- plate   pts2d [[x,y], ...] (local XY outline), c, thick; optional: rot, bevel
- plate3d pts3d [[x,y,z], ...] (a roughly planar outline), thick; optional: bevel, bseg
- torus   c, axis, R, r; optional: seg (32), rseg (10)
- radial  origin, axis, count, r, size [axial, tangential, radial]; optional: arms [[axial_offset, twist_deg, phase]],
          bevel, bseg: rounded boxes repeated round an axis (tyre lugs, bolt studs, rivets, gear teeth, flutes)
Common optional keys: bone, rough (0.6), metal (0), nmap (normal-map strength 0..1: 0 = the sculpt's lumps stay out),
extr / reach (normal-bake cage), bake_offset [dx,dy,dz] (= where it was measured minus where it is placed: the artist
MOVED it; it bakes in place, then goes back), clean (0..1: pull its colour toward its median; metals default 0.45),
mirror ("x": a mirrored copy, mirror_name, mirror_bone)."""
from __future__ import annotations

TYPES = {
    "lathe": ("origin", "axis", "profile"), "tube": ("paths", "r"), "loft": ("rings",), "rbox": ("c", "size"),
    "plate": ("pts2d", "c", "thick"), "plate3d": ("pts3d", "thick"), "torus": ("c", "axis", "R", "r"),
    "radial": ("origin", "axis", "count", "r", "size"),
}


def validate(p: dict) -> dict:
    if "name" not in p or "type" not in p:
        raise ValueError(f"a part needs a name and a type: {str(p)[:120]}")
    if p["type"] not in TYPES:
        raise ValueError(f"part {p['name']}: unknown type {p['type']} (one of {sorted(TYPES)})")
    miss = [k for k in TYPES[p["type"]] if k not in p]
    if miss:
        raise ValueError(f"part {p['name']} ({p['type']}) misses {miss}")
    if p["type"] == "lathe" and len(p["profile"]) < 3:
        raise ValueError(f"part {p['name']}: a profile needs 3+ points")
    if p["type"] == "loft" and len({len(r) for r in p["rings"]}) != 1:
        raise ValueError(f"part {p['name']}: loft rings must all have the same count")
    for k in ("rough", "metal", "nmap", "clean"):
        if k in p and not 0 <= float(p[k]) <= 1:
            raise ValueError(f"part {p['name']}: {k} must be 0..1")
    return p
