# Driving GNM: the manual (what you see -> which control)

A face that differs from the picture differs in a few big masses and many small ways. This manual turns what you
see, said the way an artist says it, into the GNM control that fixes it: sign, rough size per step, what to hold, and
what the move drags along. It was built and tested on a driving test ("gnmdrive", 2026-10-10: synthetic GNM pairs,
drivers who saw only clay renders, an oracle that knew the least-cost answer). On 14 pairs driven by two fresh groups,
drivers WITHOUT the manual passed 3 / 14, WITH it (v1) 7 / 14; on 14 more pairs 3 / 14 vs (v2) 6 / 14; on 14 fresh
pairs v3 6 / 14: 8 / 42 without, 19 / 42 with. The phrase tables have a ceiling (their best 10 moves pass 27 / 42);
the millimetre measures of section 0a reach further (v4): start there. Method, numbers and dead ends:
docs/notes/gnm_atlas.md "## gnmdrive".

Moves are block-in moves (`block_in_step`): `<macro>` FREE (the population's conditional mean; head size kept;
neighbours come along), `<macro>!` HELD (that measure alone, every other macro held), `pc:<GNM region><k>` (GNM's own
regional principal direction, + = the region forward on average), `sculpt:<zone>` / `relief:<zone>` (mm along the
zone's normal / against its surround), `mm:<measure>` (a measure you can SEE moved by that many mm, every other
measure held in mm: the precise finishing move), `nd:<gap>`, `gnm:<control>`. Sizes are per +1 unit, in mm on GNM's head (an
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
- **Masses with macros and pc: moves, then MEASURE and finish with `mm:` moves.** The sheets say how many mm a
  pixel is: read the gap (pupils, the chin's tip, the forehead against the nasion, the philtrum) and type the mm:
  `{"mm:chin_forward": 2.5}`. Measures: pupils_apart, eyes_forward, eyes_height (over the nose base), brows_over_eyes,
  forehead_forward (vs the nasion), tip_forward, subnasale_forward, upper_lip_forward, lower_lip_forward, chin_forward,
  philtrum_length, chin_length, nose_length, cheekbone_width, jaw_width, chin_width, mouth_width, nose_width,
  skull_width, skull_top, skull_back, neck_width, under_chin. Cost |dc| 0.3-1.2 per mm, the rest of the face held.
- **Several free moves in one step compound** (jaw_width + cheek_fullness + under_chin at 1.5 each landed at ~2.6 sd
  each): give each about 2/3 of what it looks like it needs.
- **After every free move, check the three usual drags:** the nose's projection (lip, brow and eye moves push it 1-2
  mm), the chin's height (head_size, pc:upper_lip_region0, face_length move it), the neck (jaw, chin and under-chin
  moves widen or thin it). Put a drag back with a HELD move (`nose_projection!`, `pc:chin_region0`, `neck_width!`).
- **The tracing: red = target, green = you.** Green INSIDE red = the target is bigger / fuller / further forward
  there. Under the chin the line slopes, so judge it at right angles to the line: if the target's (red) line sits
  further from the jaw bone (lower and further out from the throat), the target is the fuller one (two drivers got
  this backwards: say which line is outside in words before you choose the sign).
- **Uniform 1 mm offsets whose direction flips between crops are framing, not shape** (each crop is framed on its own
  feature): leave them.

## 0a. Drive in millimetres first (v4: the 23 measures)

Tested (gnmdrive2, 42 synthetic pairs): closing the 8 LARGEST of these 23 gaps passes 30 / 42 pairs, the 4 largest
25 / 42, all 23 40 / 42; drivers choosing macros / pc: moves from the phrase tables below passed 19 / 42, and the best
10 moves of that vocabulary (the oracle) 27 / 42. Read with a 1 mm error the 8 largest still pass 26 / 42. So:
1. **Measure, don't guess.** For each measure below, read the gap between the two heads in the view named (px on the
   sheet x the mm per px in its title; front widths are TOTALS, left edge to right edge), in mm, target minus yours.
   With two GNM heads, `gnm_mm.gaps(Va, Vb)` is the ruler. From PICTURES (a block-in's photos, or renders of a
   target): `face_ruler(name)` / `face_ruler.read(head, views)` reads the same 23 gaps off the outlines and iris
   centres, with each row's error (set s6: drivers with it 11 / 14, by eye 3 / 14 on s5). Trust its rows over your
   eye: in the test every row a driver disputed (under_chin, nose_length, the vault) was right.
2. **Take the largest gaps first, in population sd** (gap / the sd in the table), not in mm: 3 mm of lower lip (sd
   1.6) outranks 8 mm of neck (sd 12.6).
3. **Type the gap**: `{"mm:<measure>": gap}`. Each move holds the other 22 in mm, so several mm: moves in one step add
   up exactly; no put-backs are needed between them.
4. **Then the phrase tables** (sections 1-7) for what the measures do not describe: lip fullness, cheek fullness and
   planes, eye openings, the brow's shape, the nose's width at the bridge, ears, jowls.

Set s5 (14 fresh pairs, the same manual): drivers reading the gaps BY EYE passed 3 / 14, drivers given a ruler (the
gaps as numbers, +-1 mm) 7 / 14 (10 / 14 for the ruler's 8 largest gaps applied blindly; the phrase oracle 8 / 14).
The eye is the weak link, not the control. What the drivers found:
- **Readable by eye** (within ~2 mm): the front totals (skull, cheekbone, jaw, chin, mouth, nose width, skull top),
  `under_chin`, `chin_length`, `chin_forward`, the lip links IN THE MOUTH CROP, `pupils_apart` in the eyes crop,
  `brows_over_eyes`. A very large gap is under-read by about a third (a 15 mm chin took +10 then +5).
- **Not readable by eye**: `subnasale_forward`, `eyes_forward`, `forehead_forward` (the sheets are framed on the
  face, so "the muzzle is back" and "the upper face is forward" look the same, and the nasion they are measured from
  moves too); a small `tip_forward` vs the whole muzzle; any gap under 1.5 mm. For those use a ruler, or the phrase
  moves `pc:upper_lip_region0` (muzzle) and `pc:nose_region0` (whole nose), which a driver CAN judge on the outline.
- **Missed by eye at head scale, found at once by the ruler**: chin length (7-9 mm, twice), nose width (12 mm), mouth
  width (7 mm), eye spacing + prominence (9 and 10 mm, seen only as "big sockets"), the sign of `under_chin` (three
  drivers read the tracing backwards). Measure the front totals in the feature crops, never at head scale.
- **What mm: moves drag** (they hold the 23 measures, not everything): the ears (`ear_out` 0.5-1.2 sd with any large
  width / muzzle move: put back with `ear_out!`, clean; `mm:skull_width` carries the ears with it, so look before
  adding it), lip fullness (about +1 sd with big nose / mouth moves), `mm:tip_forward` turns the tip (nose_upturn
  ~0.4 sd per mm: pair with `nose_upturn!`), `mm:eyes_height` at 4+ mm tilts the eyes and angles the brows,
  `mm:brows_over_eyes` at 8+ mm leaves a V-frown, `mm:eyes_forward` moves the nasion and brow as much as the eye,
  `mm:forehead_forward` leaves the brow ridge behind (add `brow_ridge!`).
- **Lip fullness after mm: moves: free `lip_fullness` in 0.5-0.8 steps with the muzzle put back** (read the drag on
  the profile). `lip_fullness!` looked clean to the drivers and RAISED the face error all four times it was kept in
  s5 (0.4-1.4 mm rms: it moves the chin's bottom and the face length): do not use it.
- **By region** (pass rates, ruler drivers on s5 vs phrase-manual drivers on s2-s4): eyes 3/3 vs 3/9, cheeks 2/2 vs
  2/6, brows 2/3 vs 4/9, jaw 2/3 vs 4/9, chin 1/2 vs 1/6; but nose 0/3 vs 6/9 and mouth 0/4 vs 5/12. So: mm: moves
  for placement, widths, lengths and the jaw / chin / skull masses; `pc:nose_region0` / `pc:nose_region2` for the
  nose and `pc:upper_lip_region0` for the muzzle (their differences are 1-3 mm profile shapes, under a ruler's error),
  then mm: moves to finish them.
- **A ruler cannot confirm its own move** (after you type a gap it reads 0 whatever the truth): keep / reject on the
  renders. Its large gaps (> 1 sd) were right every time; its small profile gaps (tip, philtrum, lip links under
  ~2.5 mm, with a +-1 mm reading error) were wrong by the renders on 5 of the 14 pairs.

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| mm measure: irises doubled side by side (overlay), eyes set wider | `mm:pupils_apart` | 1 mm; population sd 3.1 mm | read in front; a 2-3 mm offset looks like "longer eyes" at head scale: check the eyes crop |
| mm measure: eyeballs stand forward of the nasion in profile | `mm:eyes_forward` | 1 mm; sd 4.0 | |
| mm measure: eyes sit higher above the nose base, longer mid-face | `mm:eyes_height` | 1 mm; sd 3.5 | irises doubled one above the other |
| mm measure: brow to eye distance, lid space | `mm:brows_over_eyes` | 1 mm; sd 2.7 | which overlay copy is the target's is hard to tell: compare the two clay rows before you choose the sign |
| mm measure: forehead ahead of the nasion in profile | `mm:forehead_forward` | 1 mm; sd 3.0 | |
| mm measure: nose tip out from the nose base | `mm:tip_forward` | 1 mm; sd 2.5 | the bridge is held: a whole nose further out is `pc:nose_region0` |
| mm measure: nose base forward of the eyes, carries lips and chin (the whole muzzle step) | `mm:subnasale_forward` | 1 mm; sd 3.8 | top of the forward CHAIN: subnasale -> upper lip -> lower lip -> chin, each measured against the one above, so a link carries everything below it |
| mm measure: upper lip forward of the nose base, carries lower lip and chin | `mm:upper_lip_forward` | 1 mm; sd 2.5 | chain |
| mm measure: lower lip forward of the upper lip, carries the chin | `mm:lower_lip_forward` | 1 mm; sd 1.6 | chain: the lower lip ALONE +2 = `mm:lower_lip_forward` +2 with `mm:chin_forward` -2 |
| mm measure: pogonion forward of the lower lip | `mm:chin_forward` | 1 mm; sd 3.5 | bottom of the chain: moves the chin alone |
| mm measure: mouth lower under the nose, longer upper lip skin | `mm:philtrum_length` | 1 mm; sd 2.1 | |
| mm measure: chin bottom lower under the lower lip, taller chin | `mm:chin_length` | 1 mm; sd 4.1 | |
| mm measure: nose base lower under the nasion, longer nose | `mm:nose_length` | 1 mm; sd 3.3 | |
| mm measure: width across the cheekbones (total) | `mm:cheekbone_width` | 1 mm; sd 8.0 | |
| mm measure: width of the jaw line at mouth level (total) | `mm:jaw_width` | 1 mm; sd 10.7 | the largest lower-face gap on every heavy / lean jaw pair: 20-35 mm between a lean and a heavy face |
| mm measure: breadth of the chin (total) | `mm:chin_width` | 1 mm; sd 5.7 | |
| mm measure: mouth corner to corner (total) | `mm:mouth_width` | 1 mm; sd 4.0 | |
| mm measure: nose wing to wing (total) | `mm:nose_width` | 1 mm; sd 4.2 | |
| mm measure: skull width above the ears (total) | `mm:skull_width` | 1 mm; sd 8.2 | the face is held: this is the "vault wider, face the same" move |
| mm measure: crown height over the nasion | `mm:skull_top` | 1 mm; sd 4.2 | |
| mm measure: occiput behind the nasion, longer head in profile | `mm:skull_back` | 1 mm; sd 10.3 | |
| mm measure: neck thickness in front view (total) | `mm:neck_width` | 1 mm; sd 12.6 | cheap and big: last |
| mm measure: the line under the chin below the chin's bottom (submental fullness) | `mm:under_chin` | 1 mm; sd 4.6 | + = fuller, hangs lower |

## 1. Size and the skull

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| A HALO: your outline a rim outside (inside) the target's all the way round | `head_size` (-/+) | cheekbones 6.0, jaw angles 6.5, skull width 4.7 mm, pupils 3.1 mm | -0.5 is invisible at head scale: 1-1.5 for a 3-5 mm halo. Drags the chin lower (put back `pc:chin_region0` -) and lowers the vault (cranium_height -0.66 sd: put back `cranium_height!` +) |
| Vault taller over the brows, face the same | `cranium_height!` | crown 4.6 mm | free cranium_height widens the skull 5.3 and the jaw 3.7 |
| Skull wider over the ears / temples, face the same | `cranium_width!` | skull width 8.3 mm | free widens the face too (cheekbones 3.5, jaw 4.2): free only when the face is wider as well. A rim seen only in 3/4 is often the EAR (see ears) |
| Back of the skull further back (head longer) | `head_depth!` | occiput 8.4 mm | below ~0.8 nothing shows; free head_depth drags the neck +5 and the nose forward |
| The whole face sits a uniform step ahead of the ear in profile (brow, nose, lips, chin all offset alike) | `head_depth!` (+: occiput back = face relatively forward) | 8.4 mm | not lip / chin / nose projection (they reshape, the offset stays) |
| Forehead stands forward of / behind the nasion (upright and full vs sloping) | `mm:forehead_forward` (mm) or `forehead_slope!` (- = forward, upright) | forehead -3.0 mm vs the nasion per +1 (by eye at the upper forehead less: a 9 mm gap took -2.5) | judge it against the NASION, not the outline: free forehead_slope moves the nose tip 2 mm too and drivers read it as "the whole profile slid". `pc:forehead_region1` is NOT a forehead move (moves the whole profile) |
| Ears stand out (front view) / lie flat | `ear_out!` | clean, +1 visible | a "skull rim" in 3/4 behind the cheek is often the ear |
| Ears bigger | `ear_size!` | clean | |

## 2. Face length, width, the lower face (incl. the full, heavy, "fluffy" lower face)

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Lower face longer: chin and jaw underside lower, the features above the same | `face_length` free / `pc:chin_region0` (+) | face_length: chin -4.7 mm; pc:chin_region0: chin -3.7, under-chin -4.2 mm (|dc| 0.8) | face_length drags gonial, nose length, philtrum. pc:chin_region0 is the workhorse for "chin bottom lower / higher" |
| The whole lower face broader and heavier (wide jaw, broad chin, full cheeks, full under the chin, thick neck: "fluffy", not lean) | free `jaw_width` +1, `cheek_fullness` +1, `under_chin` -0.6 (or `face_width` +1 if the skull is wider too); a fat face with jowls and a double chin: `gnm:head_000` -2 (a driver's biggest single win) | jaw_width +1: jaw angles 8.8, neck 6.4, chin 3.9 mm | ~1.0 each for a moderate gap (1.5 each overshot 3-4 mm), 1.5 each for a very large one (worked on m3_01). If only the submental is full, `under_chin` -1 alone. Thick neck after it: `neck_width!` (-) |
| Lean face vs full face (the same, reversed) | `cheek_fullness` (-1..-1.5) first | | the right first move for "full vs lean" (drivers, twice) |
| Jaw wider at the angles only | `jaw_width!` | +8.8 mm at the angles, clean | +0.35 was invisible |
| Lower face wider beside the mouth (not at the angles) | `sculpt:jawline` (+, mm) | +2.9 mm width at mouth level per mm | `jaw_width!` and `cheek_fullness` missed it (drivers) |
| Face wider just below the ears (masseter / parotid bulge) | `sculpt:parotid` (+, mm) | +2.5 mm per mm | jaw_width / face_width didn't reach it; -0.8 was invisible: 2 mm or more |
| Full under the chin / double chin vs a clean jaw-to-neck angle | `under_chin!` (- = full, + = clean) | 4.5 mm per sd, very clean | sign: + = CLEAN. The free one also widens neck and jaw (and thins the neck going +) |
| Thick / thin neck | `neck_width!` | 14 mm per sd | |
| Chin stands forward / back in profile | `mm:chin_forward` (mm, vs the lower lip) or `pc:chin_region1` (+: pogonion +3.6 mm in the head, ~1.4 mm against the lips, |dc| 1.0) or `chin_projection!` (+2.9 mm, lower lip +1.6) | | pc:chin_region1 by eye: 0.6 barely moved, 1.8 gave ~2.5 mm: measure and use mm:chin_forward. | free chin_projection widens the jaw 2.6 and pulls the nose back |
| Small chin: short AND set back | `pc:chin_region0` (-) + `pc:chin_region1` (-) together | | needed both (driver) |
| Jaw angles higher / lower | `gonial_height` (free: the chin lower too) or `nd:gonial_height|hold_face_length_chin_height` | | |

## 3. The mouth area and the lips (incl. the PROFILE ANGLE)

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The MUZZLE stands forward in profile: nose base, both lips and chin forward TOGETHER (a protrusive profile angle) | `pc:upper_lip_region0` (+) | lips +2.0, subnasale +1.3, chin +1.1 mm; mouth +1.9 mm wider; |dc| 0.8 | right in both signs, every time it was used; +2..+3 for a 4-7 mm gap. Lengthens the face (chin -2.2 mm, face_length +0.6, gonial +0.7 sd per unit) and widens mouth / nose: put back `face_length` or `pc:chin_region0` (-), `mouth_width!` (-) |
| The LIPS pout ahead of the nose-chin line, the nose and chin staying | `lip_projection!` (+) | lower lip +2.15, upper +1.0, chin -0.9 mm; |dc| 2.8 | free lip_projection pulls the nose tip back 2.2 and the chin back 2.0 mm |
| Fuller lips (taller red in front) | `lip_fullness` free (pulls the nose tip back 1.9 mm: often welcome); not `lip_fullness!` (s5: raised the face error every time) | | free also drags lip_projection +0.68 (lips and chin ~1.5 mm forward): put the muzzle back with `pc:upper_lip_region0` (-). | `lip_fullness!` adds little in profile and drags face_length +0.7 and the chin bottom 1.9 mm: check the jaw after it |
| Thinner lips | `lip_fullness` free (-) | | free pushes the WHOLE nose forward ~1.7 mm per sd, bridge to tip, and carries lips and chin back (lip_projection -0.7 per sd): put the nose back with `pc:nose_region0` (-0.4 per -1.0 of lip_fullness; `nose_projection!` is a trap), and halve the step once the profile is on |
| Longer upper lip: the mouth sits lower under the same nose | `mm:philtrum_length` (mm) or `philtrum!` (+) | 2.0 mm per sd, very clean | a "doubled lip seam" in the onion skin can be the lip's shape, not its height: philtrum! +1.5 didn't fix one | a 5 mm longer lip is ~2.5 sd: 1.2-1.5 looked like "barely moved". Free philtrum pushes the nose forward |
| Wider mouth | `mm:mouth_width` (mm, total) or `mouth_width!` (+) | 3.1 mm corner to corner (total) per sd | free widens the jaw 3.4 |
| Lower lip forward of the upper | `relief:mentolabial_sulcus` (+: lower lip +1.2, upper -0.9 per mm) or `lip_projection!` | | `sculpt:lower_vermilion` shifts the whole profile 1.2 mm per mm: avoid |

## 4. The nose

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The whole nose stands further out, bridge to tip ("a strong nose") | `pc:nose_region0` (+) | tip +4.0, nasion +2.3, subnasale +2.4 mm; |dc| 0.95 | the best nose move (oracle and drivers): 0.4-0.6 for 1.5-2 mm, 1.7 for ~7 mm at the tip |
| Narrow, pinched nose that projects, the tip pointing down | `pc:nose_region2` (+) | width -1.8, tip +1.4 mm | narrows the jaw too (put back `jaw_width!` +) |
| Wider / narrower at the wings | `nose_width!` | alae 3.3 mm, clean | free nose_width widens mouth, jaw and face (+4.3 jaw) |
| Wings flare wider (the alae themselves) | `sculpt:alae` (- = narrower, mm) | 1.6 mm width per mm | |
| Tip projects more (less), the bridge right | `mm:tip_forward` (mm: the tip against the nose base, the bridge held) or `nose_projection` free (+) | tip +3.6, nasion +2.1 mm | free nose_projection (-) drops the bridge with the tip: mm:tip_forward is the clean one. | drags upturn -0.78 sd and the eyes back; `nose_projection!` costs |dc| 5.1 and lifts the tip 2.2 mm |
| The dorsum proud / scooped between nasion and tip (a convex or a dished bridge), the tip right | `bridge_hump` free with `mm:tip_forward` to put the tip back (hump +0.9 with tip -2 mm), or `bridge_hump!` | | two s5 drivers, both kept; free bridge_hump alone drags the tip 2 mm forward |
| High bridge at the radix only | `sculpt:radix` (+, mm) | nasion +1.1 mm per mm | `bridge_height!` is a TRAP (|dc| 7.5: moves lips and chin 3 mm) |
| Narrow, steep-sided bridge (walls) | `sculpt:bridge_walls|hold=dorsum` (-, mm) | Garrett: -1 mm took the walls 0.75 -> 0.59 | no macro reads dorsum width; `nd:tip_width|held` "did nothing visible" for a pinched tip (driver) |
| Tip turned up (more nostril) / drooping | `nose_upturn` | free: the tip 2.5 mm back as it turns | `nose_upturn!` (|dc| 3.9) lifts the tip 2.3 mm and pushes lips / chin forward 1-1.6. Garrett's accepted fix: nose_upturn! +1.4 with nose_projection! -0.4 |
| Longer nose (tip and base lower) | `nose_length` free (+3.5 mm eyes-to-nose-base per sd) | | face longer too |
| The eyes AND brows sit lower (higher) over the same nose base | `mm:eyes_height` (mm) or `nose_length!` (+: they rise; -: they drop) | eyes +1.9, nose base -1.5 mm per +1 | nose_length! drags face_length +0.6 per sd (the head longer): pair it with `face_length` (-). | (driver find: the irises doubled one above the other in the onion skin) |
| Broad, round tip | `nd:tip_width|held` | | the free one flattens the bridge |

## 5. Eyes

GNM's eyeballs are a FIXED size (29 mm). "Bigger eyes" is one of four things: tell them apart in the eyes crop and
the onion skin before choosing.

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Pupils further apart (the onion skin shows irises doubled side by side) | `mm:pupils_apart` (mm: the eyes alone, |dc| 0.61 per mm) | head_size moves them 3.1 mm per sd but the face 6 mm wider: too blunt when the outline already matches (two drivers) | `eye_spacing` does NOT move the eyeballs (pupils 0.0 mm): only the inner corners. After head_size, put the face back (`face_width!` / `cheekbone_width!` / `jaw_width!` -) |
| Inner corners closer / further (lids) | `eye_spacing!` | | free drags the bridge down |
| Eyes prominent, standing forward of the brow (more white in profile) | `mm:eyes_forward` (mm) or `eye_depth` FREE (-) | eyeballs +4.2 mm forward of the nasion (nasion -2.8, tip -3.5) | NOT `eye_depth!` (|dc| 6.2: moves the radix / glabella 4 mm). Put the nose back after |
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
| Brows sit lower / higher over the eyes | `brow_height` free (2.7 mm), then `brow_height!` or `mm:brows_over_eyes` to finish | brow_height! reads about HALF its 2.65 mm by eye (0.7 invisible, 1.5 for ~2 mm) | free at 2 drags lip_projection +0.85, the bridge -1.1 sd and pushes the forehead and nose ~2 mm forward; free at 2 drags lip_projection +0.85 and the bridge -1.1 sd, and the eyes forward |
| Heavy brow: ridge forward, eyes deep, brows low together | `brow_ridge` free (+) | brow +1.9 mm forward | brings the nose forward 2.8 mm (put back) and lowers the brows a little |
| Ridge / glabella forward with PROMINENT eyes | `brow_ridge!` (+) then `eye_depth` free (-) | brow_ridge! +2.8 mm | brow_ridge! overshoots at the nasion: 0.5-0.7 |
| Glabella and bridge forward together | `pc:middle_brow_region1` (+) | nasion +2.6, tip +2.7 mm | |
| Brows more arched / the tails dropping | no clean control (brow_height moves the arch 1.4 mm per sd with the rest; `sculpt:brows` 0.6 mm per mm) | | record it |

## 7. Cheeks

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Full, chunky cheeks AND a wider lower face | `cheek_fullness` free | jaw +4.8, cheekbones +2.8 mm | it is a lower-face width move: it reaches the jaw, not the cheek beside the mouth, and drags under_chin +-0.7 |
| The cheek's front plane stands forward / back in 3/4, the front width right | `relief:cheeks` (+ forward, mm; 1.3 mm per mm) or `sculpt:cheeks` (-2.5 worked on a too-full cheek) | |dc| 2.4 per mm | relief:cheeks drags cheek_fullness ~0.9 sd per mm (the jowl widens; -1.5 thinned the lower cheek): not for a bone point. |
| The cheekbone / the apple under the eye stands proud in 3/4 (fullness HIGH on the cheek, not on the jowl) | `sculpt:malar` (mm) | | +4 matched an upper-cheek bulge, -1.5 a cheekbone proud in 3/4 (two drivers) | `pc:left_ / right_cheek_region*` are NOT cheek moves (they narrow and shorten the whole lower face) |
| Wider cheekbones only | `cheekbone_width!` | +5.3 mm, clean | free widens the jaw 5.5 and skull 4.1 |

## Phrases that look alike (and need different controls)

- "Mouth forward": the MUZZLE (nose base + lips + chin together: `pc:upper_lip_region0`) vs the LIPS ahead of nose and
  chin (`lip_projection!`) vs the WHOLE FACE ahead of the ear (`head_depth!`). Check the subnasale and the chin:
  both forward = muzzle; both still = lips; brow forward too = whole face.
- "Bigger eyes": pupils apart (`mm:pupils_apart`) vs balls forward (`eye_depth` -) vs taller opening (`eye_height`) vs
  longer opening (`eye_width`). Onion skin: doubled irises side by side = placement; same irises = the lids.
- "Eyes lower on the face": the eye unit over the nose (`nose_length!` -) vs brows pressing down (`brow_height` -).
- "Chin lower": the chin's bottom (`pc:chin_region0`, `face_length`) vs the line under it (`under_chin!` -).
- "Head too big": all round (`head_size`) vs the vault only (`cranium_*!`) vs a uniform profile offset
  (`head_depth!`) vs the ears (`ear_out!`).
- "Nose further out": the whole nose (`pc:nose_region0`) vs the radix (`sculpt:radix`) vs the tip (`mm:tip_forward`).
- "Cheek proud in 3/4": the plane (`relief:cheeks`) vs the bone / apple under the eye (`sculpt:malar`) vs the lower face
  (`cheek_fullness`).
- "Lips sit lower": the philtrum (`mm:philtrum_length`) vs the lip's shape (no move: record it).
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
any driver: puffy lower-lid bags, dark hollow sockets, brow arch / brow shape (straight vs angled), a crisp lid
crease, a narrow dorsum other than through sculpt:bridge_walls, a bulge at the nape in 3/4.
