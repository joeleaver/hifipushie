# Block-in: the step vocabulary (`block_in_step`)

Read guide(topic="block_in") first: the loop, the stage-0 description and the self-review.

4. **One small step** (0.3-0.7 sd; a big mass difference 1-2 sd, see the manual's step sizes):
   `block_in_step(name, {direction: amount}, seen=..., why=...)`. Each step writes
   a NEW model (default: the next number), so every round stays comparable; `seen` and `why` go in the log.
   - FREE `"chin_height": 0.5`: the population's conditional mean per +1 sd: the face stays whole. Try first for
     masses and proportions.
   - HELD `"chin_height!": 0.5`: that one macro, every other macro held (a pseudo-inverse column). For a single
     feature, or to put back a neighbour a free step dragged. Costs more |c| per unit (more unusual faces).
   - GAPS `"nd:radix_width": 1`: vocabulary the macros lacked, filled with data-backed coupled directions (below).
   - `sex`, `eth0..2`: the sampler's sex axis (+1 = female mean -> male mean) and ethnicity contrasts.
   - BASE keys, SET: `head_scale` (base.style.human.head_size: the head's UNIFORM size about the neck, x the body's
     own head; 1 = the body's), `gnm_base`, `dimorphism`, `weight`, `eye_size` (base.head.eyes: the eye AND its
     orbit scaled about the eye centre), `eye_radius` (base.head.eye_radius, m: an OVERRIDE of GNM's eyeball by
     an absolute ball of ours, seated by a search; 0 drops it). THE DEFAULT IS GNM'S OWN EYEBALL: its
     14.6 mm scleral sphere at its eye joint x the head's scale, which GNM's lids are shaped on; block_in_start
     drops a refs model's eye_radius (older heads carry 0.012: on those the lids stand
     ~0.5 mm further off the ball). Do not shrink the ball to fix an iris: the iris is its own quantity:
   - GNM's OTHER identity components, SET: `iris_mm` (the iris' diameter in mm at the model: solves the identity's
     `eyes_000`, GNM's limbus, sd ~0.4 mm of radius; `brow_read` / `eye_ruler`'s IRIS line gives the picture's),
     `id:eyes_001` (the cornea's prominence, sd; only from a profile close-up), `id:teeth_NNN` (GNM's 80 teeth
     components, sd; only from a picture that shows the teeth); expression components SET: `ex:pupils_000` (the
     pupil: -1 = 0.33 of the iris, 0 = 0.5, +1 = 0.67), `ex:tongue_NNN`. They are the same identity / expression
     vectors as the head's 170 + the eye / lower-face regions: every step and solve keeps them.
   - DESIGNED age / soft-tissue ops, SET: `shape:<op>`: faceslide's age sliders in their units (`age_nasolabial`
     +1 = a 2 mm fold, `age_prejowl`, `age_cheek_flat`, `age_lid_fold`, `face_planes`, `face_lean`, `cheek_hollow`
     +1 = 4 mm) and headage's ops without a slider (`eye_bag`, `lip_bow`, `lip_roll` in m, `lips_thin` a share).
     Hand-authored, NOT learnt from people: the reply and the log flag them DESIGNED. Place them by eye, zoomed in
     (focus=cheeks / mouth) under the raking light against the pictures; the cheeks rows (nasolabial_fold,
     cheek_hollow: shading contrast, photo minus clay) should close. E.g. age_nasolabial 0.5 closed a fold's
     gap 22 -> 19 % (front) and 28 -> 20 % (3/4).
   - LOCAL residuals, SET: `local:<faceslide slider>` (base.head.sliders), for what no identity direction draws;
     the reply warns past 2.5 x the slider's population sd beyond GNM (ICT: nose_radix_width 0.09, nose_tip_width
     0.18, nose_dorsum_width 0.12).
   - LIDS, SET: `lid_upper`, `lid_lower` (metres, -0.001 = 1 mm up): by measure, see 7.
   - SCULPT, the GNM way (THE standard fix for a feature no macro reaches, before any local): `"sculpt:<zone>": mm`
     moves a named zone (its mean normal, + out of the face) by the LEAST-COST identity change over all 170 comps with
     every macro HELD (the face's measured proportions stay) and a locality penalty on the skin > 6 mm away;
     `relief:<zone>` moves it against its 5 mm surround (- deepens a groove: alar crease, nasolabial, lid fold).
     Options after `|`: `hold=<zone>+<zone>` (zones kept still), `free=<macro>+..` (macros let go), `loc=<w>`. Zones:
     `gnm_controls(zones=True)`. A narrow bridge: `"sculpt:bridge_walls|hold=dorsum": -1.0` = walls 0.746 ->
     0.590 at |dc| 3.5 (the designed local nose_dorsum_width -0.8 gave 0.670); -2.0 reaches his concept's 0.504. A
     sculpt of 1 mm usually costs |dc| 2.5-4: big next to a macro step, but it moves a real face's |c| (~13), not away.
   - MILLIMETRES: `"mm:<measure>": mm` moves one measure you can see (pupils_apart, eyes_forward, eyes_height,
     brows_over_eyes, forehead_forward, tip_forward, subnasale_forward, upper / lower_lip_forward, chin_forward,
     philtrum_length, chin_length, nose_length, the widths, skull_top / back, under_chin, and the orbit's
     brow_ridge_forward, side_rim_forward, under_eye_forward, brow_hollow: 27) by that many mm with every
     other measure held in mm, the lids kept on the ball and the profile line kept (gnm_mm; |dc| 0.3-1.7 per mm).
     Every forward measure is taken against the NASION. Use it FIRST for anything you can measure (manual
     section 0a): take the largest gaps in population sd first; several mm: moves in one step add up exactly. The
     forward measures are a chain (subnasale -> upper lip -> lower lip -> chin): a link carries what is below it. The
     eyes set further apart is `mm:pupils_apart` (eye_spacing moves only the inner corners; head_size! scales the head).
   - RAW CONTROLS: `"gnm:<control>": amount`: any identity-space control of the atlas (`head_042`, `z:05` a sampler
     latent, `label:sex`, `pc:nose_region3`): see `gnm_controls`.
5. **Keep it only if the whole face reads closer AND no target went out.** The reply has the read (the moved macro,
   before -> after, and the largest coupled moves), the target table's delta (items that went out, came in or moved
   by half a tolerance) and the new sheet. Otherwise step again from the earlier model: that is the revert (the log
   marks the abandoned step). Free moves drag neighbours; the table catches it; put the neighbour back with a held
   step (length -> philtrum, lips -> chin, bridge / eye depth -> narrower eyes, chin height -> chin width).
6. **The table after every step** (five groups: head shape, jaw and chin, eye placement, nose, mouth: likeness items
   read the same way on the picture and on the model through its fitted camera, with tolerances). `flag` items are
   shown, not counted (jaw_angle_height reads the detector's guess at the jaw contour, not the gonion; alar_width and mouth_over_alar read MediaPipe's alar points, which sit on the cheek past the alae: judge the alae by eye in focus=nose). A SIZE line
   appears when the long lengths are all off the same way: that is a uniform scale (the camera's distance or the head's
   size), not shape: refit the camera (`block_in_step(..., cameras=[i])`) or set `head_scale`, never chase it with
   head_size / eye_spacing identity steps.
## Coupling you will meet (free directions)

| step | drags |
|---|---|
| face_length | the philtrum (gets longer before the chin does) |
| philtrum (free) | the chin (shorter) |
| lip_projection | the chin's height |
| chin_height (free) | chin width |
| bridge_height, eye_depth | interocular distance (eyes narrower) |
| orbital_rim (nd) | a heavy brow and deep eyes come with it (the male pattern): hold them or the face reads older |

## Filling a vocabulary gap

When no direction expresses a difference you see: write a reader for it on GNM heads, measure it over ~2000 sampled
heads, and look at R2 (is it linear in the identity?), its sd (does the population vary it?) and its couplings. Add
it as a coupled direction (conditional mean within sex). R2 high and sd visible: a new direction (`nd:` table in
`blockin_data.npz`). Low R2 or a tiny sd: a real capability gap: a small LOCAL residual is
justified. A coupling against what you see (a defined orbital rim pulling in a heavy brow) means the look lives
elsewhere (lids, skin) or needs a held variant (`nd:orbital_rim|hold_brow_ridge_eye_depth`).

Filled so far: gonial_height, orbital_rim, lower_orbit (also humanmacro macros), radix_width (R2 0.90, sd ~0.6 mm:
GNM barely varies it; ICT adds ~0.13 mm beyond GNM: a near-invisible gap, `local:nose_radix_width`), tip_width (R2
0.94, sd 1.3 mm: comes with wide alae, full forward lips and a low bridge; `nd:tip_width|held` keeps those), and held
variants `orbital_rim|hold_brow_ridge_eye_depth`, `gonial_height|hold_face_length_chin_height`.

## What goes wrong

- Big steps (> 1 sd): one move then explains three differences and you can't tell which one was right.
- Chasing a uniform size with identity steps (head_size!, eye_spacing!): the table's SIZE line; check camera and
  head_scale first.
- Judging on the outline overlay alone: the outline is the easy part. The planes inside it (cheeks, muzzle, orbit)
  are what makes the person; squint.
- Fixing eyes with identity: lids are pose (lid_read).
- A painted or stylised picture's light is not one light, and its camera may fit badly (the clay turns differently
  from the painting): judge shape on the photographic views first; refit that view's camera.

## GNM's controls (the atlas: gnm_controls)

Every way to move GNM's head, measured: 170 identity comps + eyes 3 + teeth 80, the region
principal directions (pc:), 100 symmetric eye-region and 150 lower-face expression comps + tongue / pupil, the joints,
the identity sampler's 64 latents (+ 16 principal latent directions) and its labels (sex, 4 ethnicities), the
expression sampler's 20 class prototypes, and our block-in moves. For each: where it acts (50 named zones: alar_crease,
vermilion borders, jowls, lid_fold, bridge_walls ...), mm per unit of prior cost, how local it is, the macros it drags,
its face-ID effect, the nearest block-in move, and its sheet (in the workspace's gnm_atlas renders:
-2 | 0 | +2 front / 3/4 / profile in hair-cap clay + the move's map; index.html lists them all).
What it taught (use it when choosing a step):
- GNM's identity comps are WHOLE-FACE: median specificity 1.5 (the moved zone vs the face's rms), at any index; no
  single comp is "the alar crease". A local feature is a COMBINATION: that is what sculpt solves for.
- Per unit of prior cost the most identity-laden moves are the ORBIT / BRIDGE complex (bridge_height, eye_depth,
  orbital_rim, brow_ridge, nose_projection: face-ID 0.15-0.19 per sd): steps there change who it is fastest.
- Per mm moved, the fine comps (120-169: 0.04 mm per unit) are 5x as identity-laden as the first ten.
- The identity sampler's latent space is a GENERATOR, not a fitting space: our people and GNM's own N(0, I) heads
  are not on its 64-d manifold (residual > |c|); its labels are clean whole-face directions (label:sex, label:white
  narrows and steepens the bridge, label:asian / black widen it).
- The expression sampler's 20 class prototypes are data-backed whole-face expressions (eyes and mouth together: happy
  squints the eyes): the vocabulary for a picture's expression.
