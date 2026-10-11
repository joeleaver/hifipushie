# Driving GNM: the manual (what you see -> which control)

A face that differs from the picture differs in a few big masses and many small ways. This manual turns what you
see, said the way an artist says it, into the GNM control that fixes it: sign, rough size per step, what to hold, and
what the move drags along. It was built and tested on a driving test ("gnmdrive", 2026-10-10: synthetic GNM pairs,
drivers who saw only clay renders, an oracle that knew the least-cost answer). On 14 pairs driven by two fresh groups,
drivers WITHOUT the manual passed 3 / 14, WITH it 7 / 14 (easy 5 / 8, medium 2 / 3, hard 0 / 3). Method, numbers and
dead ends: docs/notes/gnm_atlas.md "## gnmdrive".

Moves are block-in moves (`block_in_step`): `<macro>` FREE (the population's conditional mean; head size kept;
neighbours come along), `<macro>!` HELD (that measure alone, every other macro held), `pc:<GNM region><k>` (GNM's own
regional principal direction, + = the region forward on average), `sculpt:<zone>` / `relief:<zone>` (mm along the
zone's normal / against its surround), `nd:<gap>`, `gnm:<control>`. Sizes are per +1 unit, in mm on GNM's head (an
adult interocular ~62 mm); GNM is linear, so they hold on any head. `gnm_controls(phrase="...")` returns the matching
entries below; `block_in_step(seen="...")` puts them in its reply.

## 0. Before you name anything

- **The order.** Size (halo) -> the vault -> face length / width -> jaw, chin and the line under it -> the muzzle
  (mouth area in profile) -> the nose -> eye placement -> brows -> lips -> eye openings. Big masses first: a lip
  fix under a wrong jaw is wasted.
- **Step size.** A difference you can see at whole-head scale (3-6 mm) needs 1-2 sd of a free macro: one sd moves
  the feature it names 2.5-9 mm (tables below). Then, once the masses are close, 0.5-0.8 steps. Half-sd steps are
  invisible at head scale (1 px ~ 1.1 mm there): judge them in the zoomed crops (eyes ~0.4 mm / px, nose / mouth
  0.35, chin / jaw 0.6, cheeks 0.65) and in the tracing / onion skin, not in the clay row (the eye anchors on the
  start: three drivers thought the "current" row was stale; it wasn't).
- **Several free moves in one step compound** (jaw_width + cheek_fullness + under_chin at 1.5 each landed at ~2.6 sd
  each): give each about 2/3 of what it looks like it needs.
- **After every free move, check the three usual drags:** the nose's projection (lip, brow and eye moves push it 1-2
  mm), the chin's height (head_size, pc:upper_lip_region0, face_length move it), the neck (jaw, chin and under-chin
  moves widen or thin it). Put a drag back with a HELD move (`nose_projection!`, `pc:chin_region0`, `neck_width!`).
- **The tracing: red = target, green = you.** Green INSIDE red = the target is bigger / fuller / further forward
  there. Under the chin, green above / behind red = the target is the fuller one.
- **Uniform 1 mm offsets whose direction flips between crops are framing, not shape** (each crop is framed on its own
  feature): leave them.

## 1. Size and the skull

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| A HALO: your outline a rim outside (inside) the target's all the way round | `head_size` (-/+) | cheekbones 6.0, jaw angles 6.5, skull width 4.7 mm, pupils 3.1 mm | -0.5 is invisible at head scale: 1-1.5 for a 3-5 mm halo. Drags the chin lower (put back `pc:chin_region0` -) and lowers the vault (cranium_height -0.66 sd: put back `cranium_height!` +) |
| Vault taller over the brows, face the same | `cranium_height!` | crown 4.6 mm | free cranium_height widens the skull 5.3 and the jaw 3.7 |
| Skull wider over the ears / temples, face the same | `cranium_width!` | skull width 8.3 mm | free widens the face too (cheekbones 3.5, jaw 4.2): free only when the face is wider as well. A rim seen only in 3/4 is often the EAR (see ears) |
| Back of the skull further back (head longer) | `head_depth!` | occiput 8.4 mm | below ~0.8 nothing shows; free head_depth drags the neck +5 and the nose forward |
| The whole face sits a uniform step ahead of the ear in profile (brow, nose, lips, chin all offset alike) | `head_depth!` (+: occiput back = face relatively forward) | 8.4 mm | not lip / chin / nose projection (they reshape, the offset stays) |
| Forehead stands forward of / behind the nasion (upright and full vs sloping) | `forehead_slope!` (- = forward, upright) | forehead -3.0 mm vs the nasion per +1 | judge it against the NASION, not the outline: free forehead_slope moves the nose tip 2 mm too and drivers read it as "the whole profile slid". `pc:forehead_region1` is NOT a forehead move (moves the whole profile) |
| Ears stand out (front view) / lie flat | `ear_out!` | clean, +1 visible | a "skull rim" in 3/4 behind the cheek is often the ear |
| Ears bigger | `ear_size!` | clean | |

## 2. Face length, width, the lower face (incl. the full, heavy, "fluffy" lower face)

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Lower face longer: chin and jaw underside lower, the features above the same | `face_length` free / `pc:chin_region0` (+) | face_length: chin -4.7 mm; pc:chin_region0: chin -3.7, under-chin -4.2 mm (|dc| 0.8) | face_length drags gonial, nose length, philtrum. pc:chin_region0 is the workhorse for "chin bottom lower / higher" |
| The whole lower face broader and heavier (wide jaw, broad chin, full cheeks, full under the chin, thick neck: "fluffy", not lean) | free `jaw_width` +1, `cheek_fullness` +1, `under_chin` -0.6 (or `face_width` +1 if the skull is wider too) | jaw_width +1: jaw angles 8.8, neck 6.4, chin 3.9 mm | 1.5 each overshot 3-4 mm all round (compounding): ~1.0. If only the submental is full, `under_chin` -1 alone. Thick neck after it: `neck_width!` (-) |
| Lean face vs full face (the same, reversed) | `cheek_fullness` (-1..-1.5) first | | the right first move for "full vs lean" (drivers, twice) |
| Jaw wider at the angles only | `jaw_width!` | +8.8 mm at the angles, clean | +0.35 was invisible |
| Lower face wider beside the mouth (not at the angles) | `sculpt:jawline` (+, mm) | +2.9 mm width at mouth level per mm | `jaw_width!` and `cheek_fullness` missed it (drivers) |
| Face wider just below the ears (masseter / parotid bulge) | `sculpt:parotid` (+, mm) | +2.5 mm per mm | jaw_width / face_width didn't reach it |
| Full under the chin / double chin vs a clean jaw-to-neck angle | `under_chin!` (- = full, + = clean) | 4.5 mm per sd, very clean | sign: + = CLEAN. The free one also widens neck and jaw (and thins the neck going +) |
| Thick / thin neck | `neck_width!` | 14 mm per sd | |
| Chin stands forward / back in profile | `pc:chin_region1` (+: pogonion +3.6 mm, |dc| 1.0) or `chin_projection!` (+2.9 mm, lower lip +1.6) | | free chin_projection widens the jaw 2.6 and pulls the nose back |
| Small chin: short AND set back | `pc:chin_region0` (-) + `pc:chin_region1` (-) together | | needed both (driver) |
| Jaw angles higher / lower | `gonial_height` (free: the chin lower too) or `nd:gonial_height|hold_face_length_chin_height` | | |

## 3. The mouth area and the lips (incl. the PROFILE ANGLE)

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The MUZZLE stands forward in profile: nose base, both lips and chin forward TOGETHER (a protrusive profile angle) | `pc:upper_lip_region0` (+) | lips +2.0, subnasale +1.3, chin +1.1 mm; mouth +1.9 mm wider; |dc| 0.8 | right in both signs, every time it was used; +2..+3 for a 4-7 mm gap. Lengthens the face (chin -2.2 mm, face_length +0.6, gonial +0.7 sd per unit) and widens mouth / nose: put back `face_length` or `pc:chin_region0` (-), `mouth_width!` (-) |
| The LIPS pout ahead of the nose-chin line, the nose and chin staying | `lip_projection!` (+) | lower lip +2.15, upper +1.0, chin -0.9 mm; |dc| 2.8 | free lip_projection pulls the nose tip back 2.2 and the chin back 2.0 mm |
| Fuller lips (taller red in front) | `lip_fullness` free (pulls the nose tip back 1.9 mm: often welcome) or `lip_fullness!` | | `lip_fullness!` adds little in profile and drags face_length +0.7 and the chin bottom 1.9 mm: check the jaw after it |
| Thinner lips | `lip_fullness` free (-) | | free pushes the nose forward ~1 mm: put back `nose_projection!` - |
| Longer upper lip: the mouth sits lower under the same nose | `philtrum!` (+) | 2.0 mm per sd, very clean | a 5 mm longer lip is ~2.5 sd: 1.2-1.5 looked like "barely moved". Free philtrum pushes the nose forward |
| Wider mouth | `mouth_width!` (+) | corners 3.1 mm | free widens the jaw 3.4 |
| Lower lip forward of the upper | `relief:mentolabial_sulcus` (+: lower lip +1.2, upper -0.9 per mm) or `lip_projection!` | | `sculpt:lower_vermilion` shifts the whole profile 1.2 mm per mm: avoid |

## 4. The nose

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The whole nose stands further out, bridge to tip ("a strong nose") | `pc:nose_region0` (+) | tip +4.0, nasion +2.3, subnasale +2.4 mm; |dc| 0.95 | the best nose move (oracle and drivers): 0.4-0.6 for 1.5-2 mm, 1.7 for ~7 mm at the tip |
| Narrow, pinched nose that projects, the tip pointing down | `pc:nose_region2` (+) | width -1.8, tip +1.4 mm | narrows the jaw too (put back `jaw_width!` +) |
| Wider / narrower at the wings | `nose_width!` | alae 3.3 mm, clean | free nose_width widens mouth, jaw and face (+4.3 jaw) |
| Wings flare wider (the alae themselves) | `sculpt:alae` (- = narrower, mm) | 1.6 mm width per mm | |
| Tip projects more, the bridge right | `nose_projection` free (+) | tip +3.6, nasion +2.1 mm | drags upturn -0.78 sd and the eyes back; `nose_projection!` costs |dc| 5.1 and lifts the tip 2.2 mm |
| High bridge at the radix only | `sculpt:radix` (+, mm) | nasion +1.1 mm per mm | `bridge_height!` is a TRAP (|dc| 7.5: moves lips and chin 3 mm) |
| Narrow, steep-sided bridge (walls) | `sculpt:bridge_walls|hold=dorsum` (-, mm) | Garrett: -1 mm took the walls 0.75 -> 0.59 | no macro reads dorsum width; `nd:tip_width|held` "did nothing visible" for a pinched tip (driver) |
| Tip turned up (more nostril) / drooping | `nose_upturn` | free: the tip 2.5 mm back as it turns | `nose_upturn!` (|dc| 3.9) lifts the tip 2.3 mm and pushes lips / chin forward 1-1.6. Garrett's accepted fix: nose_upturn! +1.4 with nose_projection! -0.4 |
| Longer nose (tip and base lower) | `nose_length` free (+3.5 mm eyes-to-nose-base per sd) | | face longer too |
| The eyes AND brows sit lower (higher) over the same nose base | `nose_length!` (+: they rise; -: they drop) | eyes +1.9, nose base -1.5 mm per +1 | (driver find: the irises doubled one above the other in the onion skin) |
| Broad, round tip | `nd:tip_width|held` | | the free one flattens the bridge |

## 5. Eyes

GNM's eyeballs are a FIXED size (29 mm). "Bigger eyes" is one of four things: tell them apart in the eyes crop and
the onion skin before choosing.

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Pupils further apart (the onion skin shows irises doubled side by side) | `head_size` (+) | pupils +3.1 mm (and the face 6 mm wider) | `eye_spacing` does NOT move the eyeballs (pupils 0.0 mm): only the inner corners. After head_size, put the face back (`face_width!` / `cheekbone_width!` / `jaw_width!` -) |
| Inner corners closer / further (lids) | `eye_spacing!` | | free drags the bridge down |
| Eyes prominent, standing forward of the brow (more white in profile) | `eye_depth` FREE (-) | eyeballs +4.2 mm forward of the nasion (nasion -2.8, tip -3.5) | NOT `eye_depth!` (|dc| 6.2: moves the radix / glabella 4 mm). Put the nose back after |
| Deep-set eyes under a heavy brow | `brow_ridge` free (+) or `eye_depth` (+) | balls -3.6 / -4.2 mm | both push the nose forward 2.8-3.5 mm: `pc:nose_region0` (-) or `nose_projection` (-) after |
| Eye openings taller / rounder (irises in the same place) | `eye_height` (+) / `eye_height!` | | |
| Narrow, hooded openings | `eye_height` (-) | | brows pressing on the lid is `brow_height` (-), a different move |
| Openings longer corner to corner | `eye_width` (+) | | drags eye_height +0.65 |
| Outer corners up / down | `eye_tilt!` | clean | free drags the cheekbones 2.4 mm |
| Under-eye: hollow vs full (the lower lid vs the cheek in profile) | `lower_orbit!` (- = fuller, flatter under the eye) | 1.1 mm per sd, clean | weak: puffy BAGS and dark hollow SOCKETS were not fixed by lower_orbit either way (+2 bulged the cheek, -2 widened the eyes). Record them: likely skin / shading, or out of GNM's identity |
| Lid crease / fold deeper | the eye step (lid_read match) | GNM's valley ceiling ~1.6 mm | `relief:lid_fold` raises the crease instead of deepening it; a crisp slit is outside GNM (gnmcrease) |

## 6. Brows

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Brows sit lower / higher over the eyes | `brow_height` free (2.7 mm), then `brow_height!` to finish (2.65 mm, clean) | | free at 2 drags lip_projection +0.85 and the bridge -1.1 sd, and the eyes forward |
| Heavy brow: ridge forward, eyes deep, brows low together | `brow_ridge` free (+) | brow +1.9 mm forward | brings the nose forward 2.8 mm (put back) and lowers the brows a little |
| Ridge / glabella forward with PROMINENT eyes | `brow_ridge!` (+) then `eye_depth` free (-) | brow_ridge! +2.8 mm | brow_ridge! overshoots at the nasion: 0.5-0.7 |
| Glabella and bridge forward together | `pc:middle_brow_region1` (+) | nasion +2.6, tip +2.7 mm | |
| Brows more arched / the tails dropping | no clean control (brow_height moves the arch 1.4 mm per sd with the rest; `sculpt:brows` 0.6 mm per mm) | | record it |

## 7. Cheeks

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Full, chunky cheeks AND a wider lower face | `cheek_fullness` free | jaw +4.8, cheekbones +2.8 mm | it is a lower-face width move: it reaches the jaw, not the cheek beside the mouth, and drags under_chin +-0.7 |
| The cheek's front plane stands forward / back in 3/4, the front width right | `relief:cheeks` (+ forward, mm; 1.3 mm per mm, very clean) or `sculpt:cheeks` (-2.5 worked on a too-full cheek) | |dc| 2.4 per mm | `pc:left_ / right_cheek_region*` are NOT cheek moves (they narrow and shorten the whole lower face) |
| Wider cheekbones only | `cheekbone_width!` | +5.3 mm, clean | free widens the jaw 5.5 and skull 4.1 |

## Phrases that look alike (and need different controls)

- "Mouth forward": the MUZZLE (nose base + lips + chin together: `pc:upper_lip_region0`) vs the LIPS ahead of nose and
  chin (`lip_projection!`) vs the WHOLE FACE ahead of the ear (`head_depth!`). Check the subnasale and the chin:
  both forward = muzzle; both still = lips; brow forward too = whole face.
- "Bigger eyes": pupils apart (`head_size`) vs balls forward (`eye_depth` -) vs taller opening (`eye_height`) vs
  longer opening (`eye_width`). Onion skin: doubled irises side by side = placement; same irises = the lids.
- "Eyes lower on the face": the eye unit over the nose (`nose_length!` -) vs brows pressing down (`brow_height` -).
- "Chin lower": the chin's bottom (`pc:chin_region0`, `face_length`) vs the line under it (`under_chin!` -).
- "Head too big": all round (`head_size`) vs the vault only (`cranium_*!`) vs a uniform profile offset
  (`head_depth!`) vs the ears (`ear_out!`).
- "Nose further out": the whole nose (`pc:nose_region0`) vs the radix (`sculpt:radix`) vs the tip (`nose_projection`).
- "Heavy brow": with deep eyes (`brow_ridge` free) vs with prominent eyes (`brow_ridge!` + `eye_depth` -).
- "Wide face": face and skull (`face_width`) vs the jaw angles (`jaw_width!`) vs beside the mouth (`sculpt:jawline`) vs
  the masseter (`sculpt:parotid`) vs the cheek plane in 3/4 (`relief:cheeks`).
- "Forehead forward": the forehead vs the nasion (`forehead_slope!` -) vs the brow ridge (`brow_ridge`) vs the whole
  face (`head_depth!`).

## Traps (held moves and sculpts that move the wrong place)

`bridge_height!` (|dc| 7.5: lips / chin 3 mm, marionette), `eye_depth!` (6.2: radix / glabella / forehead),
`nose_projection!` (5.1), `brow_ridge!` (4.5), `face_length!` (moves the jowls / under-chin), `lip_fullness!` (chin
bottom 1.9 mm, face_length), `philtrum!` is fine (2 mm per sd, clean) but needs big steps. `pc:forehead_region1` and
free `forehead_slope` slide the whole profile. Sculpts that translate the face instead of moving the zone:
`sculpt:dorsum`, `sculpt:lower_vermilion`, `sculpt:chin`, `sculpt:pogonion` (the profile moves 0.5-1.2 mm per mm).
`pc:left_* / pc:right_*` move one side (and the cheek ones the whole lower face).

## What GNM's vocabulary can't reach (measured)

Even the oracle (the least-cost moves, knowing the answer) closes only ~30-50 % of a person's regional difference in
six moves: two people's noses differ in 6-8 independent ways. Go for the masses that read (size, the muzzle, the
nose's projection, the jaw's width, the eye placement, the chin's height) and stop. Not found in GNM's identity by
any driver: puffy lower-lid bags, dark hollow sockets, brow arch, a crisp lid crease, a narrow dorsum other than
through sculpt:bridge_walls.
