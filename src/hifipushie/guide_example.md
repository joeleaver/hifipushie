# Two whole specs to start from

Each is a complete model: `put_model(name, <the spec>)` builds it as it stands, `look(name)` shows it. Read one
before writing your own, then change it with `edit_model` (one joint, one size at a time) rather than rewriting it.
Metres; Z up; the creature faces -Y; ".L" names are mirrored to ".R", so only the centre line and the left side are
written. Every key a joint, a bone or a blob takes is in guide(topic="spec"); every blob shape in kit_reference.

## A creature: a fox (17 joints, 13 bones, 8 blobs)

What to read in it: the SKELETON comes first (pelvis, chest, neck, head, then each leg as a chain of joints with its
own radii: a joint's `r` is the limb's thickness there). Bones join joints as round cones and may be flattened
(`flat`). Blobs are the masses the cones cannot make: the ribcage and the haunches, the skull, the ears as `blade`s
with `cup`. Proportions live in the joint positions, so a longer leg is two edited joints, not a new model.

```json
{
 "symmetry": true,
 "blend": 0.03,
 "joints": {
  "pelvis": {"pos": [0, 0.17, 0.36], "r": 0.085},
  "chest": {"pos": [0, -0.12, 0.38], "r": 0.105},
  "neck": {"pos": [0, -0.22, 0.48], "r": 0.065},
  "head": {"pos": [0, -0.28, 0.58], "r": 0.075},
  "snout": {"pos": [0, -0.44, 0.535], "r": 0.022},
  "shoulder.L": {"pos": [0.07, -0.13, 0.33], "r": 0.05},
  "elbow.L": {"pos": [0.07, -0.11, 0.19], "r": 0.034},
  "fwrist.L": {"pos": [0.07, -0.13, 0.05], "r": 0.024},
  "fpaw.L": {"pos": [0.07, -0.17, 0.022], "r": 0.026},
  "hip.L": {"pos": [0.07, 0.17, 0.34], "r": 0.065},
  "knee.L": {"pos": [0.075, 0.09, 0.2], "r": 0.04},
  "hock.L": {"pos": [0.07, 0.2, 0.1], "r": 0.026},
  "hpaw.L": {"pos": [0.07, 0.16, 0.022], "r": 0.026},
  "tail0": {"pos": [0, 0.25, 0.37], "r": 0.035},
  "tail1": {"pos": [0, 0.4, 0.3], "r": 0.075},
  "tail2": {"pos": [0, 0.56, 0.24], "r": 0.06},
  "tail3": {"pos": [0, 0.67, 0.25], "r": 0.015}
 },
 "bones": {
  "spine": {"a": "pelvis", "b": "chest"},
  "neck": {"a": "chest", "b": "neck"},
  "head": {"a": "neck", "b": "head"},
  "muzzle": {"a": "head", "b": "snout", "r_a": 0.05},
  "upperarm.L": {"a": "shoulder.L", "b": "elbow.L"},
  "forearm.L": {"a": "elbow.L", "b": "fwrist.L", "blend": 0.01},
  "fpaw.L": {"a": "fwrist.L", "b": "fpaw.L", "blend": 0.01},
  "thigh.L": {"a": "hip.L", "b": "knee.L"},
  "shin.L": {"a": "knee.L", "b": "hock.L", "blend": 0.01},
  "hindfoot.L": {"a": "hock.L", "b": "hpaw.L", "blend": 0.01},
  "tail_a": {"a": "tail0", "b": "tail1"},
  "tail_b": {"a": "tail1", "b": "tail2"},
  "tail_c": {"a": "tail2", "b": "tail3"}
 },
 "blobs": {
  "skull": {"at": "head", "size": [0.085, 0.08, 0.075]},
  "cheek.L": {"at": "head", "offset": [0.06, 0.0, -0.035], "size": [0.05, 0.045, 0.04]},
  "ear.L": {"at": "head", "offset": [0.05, 0.02, 0.09], "size": [0.035, 0.012, 0.07], "rot": [0, 20, 0], "blend": 0.015},
  "ruff": {"at": "chest", "offset": [0, -0.06, -0.02], "size": [0.085, 0.08, 0.1]},
  "haunch.L": {"at": "hip.L", "offset": [0.005, 0, -0.02], "size": [0.055, 0.09, 0.09]},
  "eye_socket.L": {"at": "head", "offset": [0.045, -0.07, 0.015], "size": [0.022, 0.022, 0.02], "op": "subtract", "blend": 0.01},
  "eye.L": {"at": "head", "offset": [0.043, -0.066, 0.015], "size": [0.017, 0.017, 0.017], "layer": 1, "blend": 0.004},
  "nose": {"at": "snout", "offset": [0, -0.005, 0.008], "size": [0.02, 0.016, 0.015], "layer": 1, "blend": 0.008}
 }
}
```

## A prop: a chair (5 joints, 3 bones, 3 blobs)

What to read in it: a prop is the same spec with HARD shapes. `blend` is 4 mm, a glue line, not a creature's 3 cm;
the legs and posts are bones with `"ends": "flat"`; the seat and rails are `box` blobs with a small `round` (a
worn edge). One `part` carries the material. Left legs mirror to the right. For a room of furniture, repeated
pieces and walls see guide(topic="props") (prefabs, instances, arrays).

```json
{
 "symmetry": true,
 "blend": 0.004,
 "parts": {"wood": {"color": "#8a6644"}},
 "joints": {
  "front_top.L": {"pos": [0.19, -0.19, 0.44], "r": 0.02},
  "front_foot.L": {"pos": [0.2, -0.2, 0.0], "r": 0.017},
  "back_seat.L": {"pos": [0.19, 0.19, 0.44], "r": 0.02},
  "back_foot.L": {"pos": [0.2, 0.22, 0.0], "r": 0.017},
  "back_top.L": {"pos": [0.18, 0.24, 0.92], "r": 0.016}
 },
 "bones": {
  "front_leg.L": {"a": "front_top.L", "b": "front_foot.L", "ends": "flat", "part": "wood"},
  "back_leg.L": {"a": "back_seat.L", "b": "back_foot.L", "ends": "flat", "part": "wood"},
  "back_post.L": {"a": "back_seat.L", "b": "back_top.L", "ends": "flat", "part": "wood"}
 },
 "blobs": {
  "seat": {"shape": "box", "at": [0, 0, 0.455], "size": [0.22, 0.22, 0.018], "round": 0.006, "part": "wood"},
  "top_rail": {"shape": "box", "at": [0, 0.238, 0.88], "size": [0.19, 0.012, 0.04], "round": 0.005, "part": "wood"},
  "slat": {"shape": "box", "at": [0, 0.225, 0.66], "size": [0.19, 0.01, 0.03], "round": 0.004, "part": "wood"}
 }
}
```
