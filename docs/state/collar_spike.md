# STATE: collar_spike (a folded shirt collar from the PATTERN's own pieces, on a primitive form) -- 2026-10-21

GOAL (Joe): a quick loop (seconds to a minute per look) that puts a folded shirt collar on a body from the PATTERN's
own band + collar pieces, closed and worn open, so that it matches the concept's open collar (Joe's trace:
/mnt/data/hifipushie/collar_spike/joe_trace.png, the concept is
workspace/garrett_v20/concept_v8_front_apose.png: open neck V ~60 mm below HPS, the collar's leaves stand either side
of the neck, long points ~147 mm apart, 50-61 mm below HPS). Primitive form only (Joe: Garrett isn't needed).
Spike only: no garment rounds, no agents grinding for an hour.

## What Joe settled (don't re-litigate)
- The pattern already has the right SHAPE (Simon's stand + collar from FreeSewing). Don't re-draft or invent the
  collar shape (the drape op, docs/state/drape_band.md, invented it; parked). The problem was always putting the
  pattern ON the body.
- "Can a flat piece make this" is the wrong question: any worn shape flattens to some pattern.
- A collar is NOT floppy cloth: the band and the collar are interfaced, pressed pieces. The settle must treat them as
  stiff (real bending stiffness), not as drapey cloth under gravity.
- The collar's flat fronts / points do NOT sit on the chest. Worn open they are held off the body by the collar's own
  stiffness, the band and the fold.
- The open look comes from the top button undone and the band's ends spreading, with the shirt fronts rolling back
  (C134), not from a neckline shape invented by hand.
- No enterprise / closed-source tools. GarmentCode (MIT) may be tried in another session. Avoid overengineering.

## Where it stands
- /mnt/data/hifipushie/collar_spike/wrap.py '{"tag": .., "open": deg, "grav": .., "stiff": .., "stiff_collar": 0|1}':
  loads Simon's stand + collar pieces from /mnt/data/hifipushie/drape_band1/form_c0.pkl (pieces["pieces"]["stand"
  | "collar"], names: stand leftBottomCf..rightBottomCf = neck edge, leftTopCf..rightTopCf = top; collar
  leftBottomEdge..rightBottomEdge = sewn edge, points at left/rightTopEdge), meshes them, wraps the stand round a
  neck cylinder (neckline = the stand's neck-edge length, 440 mm) over a shoulder cone, hangs the collar down
  outside, and relaxes with a home-made position-based solver (edge lengths, pins, sewing, floors). ~15-40 s / look.
  Renders front / three-quarter / side via hifipushie.render.render_views (clay_studio.exr, part colours).
- Results: CLOSED reads as a folded shirt collar (w3, w9, w12: band blue, collar orange). OPEN is wrong (w13: a hand-made
  open neckline drags the band into a deep V; band strain 100 %+). With fake stiffness (pair-distance constraints)
  and no gravity the collar still lies on the cone and wrinkles (w16): the start pose hangs it onto the body, and the
  pair constraints crumple a curved piece. Collar strain p99 ~22 %.
- spike.py (same folder) = the drape op on the same primitive (c1-c5, o1-o2, v1-v2): parked.

- 2026-10-21 Blender cloth try (bsim.py + bl_cloth.py, same folder; `bsim.py '{"tag":..,"frames":..,"bend":..,"tension":..,"sew":..}'`,
  Blender 5.1 headless, ~10-50 s): flat pieces as the rest shape key, a wrapped start, the band's neck edge pinned,
  sewing springs collar -> band top, self collision, little gravity. Faults found: wrap.py's start was stretched 60 %
  p99 with sliver edges (remeshed: outline at 5 mm + hex fill); the shoulder cone cut through the band at CF (moved
  below the band: pieces then hold still, 0.1 %). With the seam springs on, every run crumpled (b7-b10: strain 22-170 %,
  b10 the collar balled up). Joe: "not sure simulation is the right path"; two tries then regroup -> STOPPED.
- s1 (no sim, frames 1): each flat piece wrapped ISOMETRICALLY onto the surface it makes: the band (nearly straight,
  its neck edge an arc of radius 2.1 m) on a cylinder r 70 mm; the collar's sewn edge is an arc (radius 369 mm, fit
  err 0.7 mm), so the collar is an annular sector and wraps onto its own cone (half-angle 11.6 deg), turned down
  outside the band. 0.0 % strain, reads as a clean closed turned-down collar standing off the neck. Faults: seam gap
  up to 34 mm at CF (the band's top dips toward CF; the collar's sewn edge is 426 mm vs the band's top 445 mm), not open.

## NEXT: regroup with Joe (sim parked)
Proposal on the table: place the pieces geometrically, not dynamically: each piece as the developable surface its own
flat shape makes (cylinder / cone as in s1), then a small static fit (keep every edge length, close the seam, keep off
the body, bend only at the fold) for the seam gap; OPEN = the band's front ends turned down the neckline V and the
collar's cone following its band. Waiting for Joe's call.

Rules: renders under /mnt/data/hifipushie/bin/capped (GPU lock); files on /mnt/data/hifipushie/collar_spike/; stage
git by path, never `git add -A`; only the coordinator pushes main.
