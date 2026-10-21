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

## NEXT (agreed with Joe)
Stop hand-writing the settle: use Blender's cloth sim (bending stiffness per piece, sewing springs, pins, no or little
gravity), which already does stiff interfaced pieces:
1. Simon's band + collar loaded flat, sewn together (collar sewn edge to the band's top, between their notches).
2. Both stiff (interfaced): high bending stiffness; the fold happens at the seam.
3. The band's neck edge sewn / pinned to the neckline on the primitive neck (cylinder + shoulder cone; add simple
   upper fronts later if the open state needs them).
4. Collar folded over at the seam; settle with little or no gravity: its stiffness holds it up.
5. Then OPEN: the top button undone, the band's front ends free / spread (the fronts rolled back), and judge it
   against Joe's trace. Seconds to a minute per look; send Joe each look as a file (front / 3/4 / side).
Rules: renders under /mnt/data/hifipushie/bin/capped (GPU lock); files on /mnt/data/hifipushie/collar_spike/; stage
git by path, never `git add -A`; only the coordinator pushes main.
