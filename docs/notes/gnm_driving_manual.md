# Driving GNM: the manual (gnmdrive, 2026-10-10)

What you see between two faces, in an artist's words, and the GNM control that fixes it: sign, rough size, what to
hold, what it drags along. Built from a driving test: synthetic GNM pairs (A, and B = A with one to three regions
changed the way people differ), drivers who saw only clay renders, an oracle that knows the least-cost answer, and the
misses between them. Numbers are per +1 unit, measured on GNM's head (linear: the same on any head). mm in GNM's
template size (interocular ~62 mm). Notes, method, scores: docs/notes/gnm_atlas.md "## gnmdrive".

Moves are block-in moves (block_in_step): `<macro>` FREE (the population's conditional mean, size kept: neighbours
come along), `<macro>!` HELD (that measure alone, every other macro held), `pc:<region><k>` (GNM's own regional
principal direction), `sculpt:<zone>` / `relief:<zone>` (mm), `nd:<gap>`, `gnm:<control>`.

## 0. Reading the sheet before you name anything

- **Size first.** Steps are bigger than you think. A visible 3-6 mm difference needs 1-2 sd of a free macro (one sd
  moves the feature it names 2.5-9 mm, see the tables), not 0.3-0.5. Half-sd steps are invisible at whole-head scale
  (1 px ~ 1.1 mm there): judge small steps in the zoomed crops (eyes ~0.4 mm / px, nose / mouth ~0.35, chin / jaw 0.6).
- **The tracing: red = target, green = you.** Where green sits INSIDE red, the target is bigger / fuller / further
  forward there. Under the chin: green above or behind red = the target is the fuller one (a driver got this backwards).
- **A halo (your outline a rim outside the target's all the way round) is HEAD SIZE**: `head_size` -1 sd shrinks the
  whole outline ~3-6 mm (cheekbones -6.0, jaw angles -6.5, skull width -4.7 mm, pupils -3.1 mm). -0.5 is not visible
  at head scale; for a 3-5 mm halo use -1 to -1.5. If only the VAULT (top / temples / back) is a rim out and the face
  matches: `cranium_height!` (-1: top -4.6 mm), `cranium_width!` (-1: skull width -8.3 mm), `head_depth!` (-1: back
  of the skull +8.4 mm forward, face unchanged). These are the held forms: the free ones change the face too.
- **The whole face sits a uniform step ahead / behind the ear and skull in profile** (brow, nose, lips, chin all
  offset the same): not a feature. `head_depth!` (+1 = the back of the skull 8.4 mm further back = the face relatively
  forward against the ear) or `head_depth` free (+1: skull back -7.2 mm, nose tip +2.9 mm). Do not answer it with
  lip_projection / chin_projection / nose_projection (they reshape, the offset stays).
- **Uniform 1 mm offsets whose direction flips between close-ups are framing, not shape**: leave them.

## 1. Head and skull

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Vault taller over the brows, face the same | `cranium_height!` | top +4.6 mm, |dc| 3.2 | free `cranium_height` also widens the skull +5.3 and jaw +3.7 |
| Skull wider over the ears / temples | `cranium_width!` | skull width +8.3 mm, |dc| 3.4 | free `cranium_width` widens the face too (+3.5 cheekbones, +4.2 jaw): use free only when the face is wider as well |
| Head longer front to back (back of the skull) | `head_depth!` | back +8.4 mm | free head_depth drags the neck +5 and the nose forward |
| Forehead slopes back / upright | `forehead_slope` (+ = slopes back) | small (nose tip +2, nasion +1.3) | drivers saw "no change" at 0.6-1.2 in profile: the forehead's line barely moves per sd; use pc:forehead_region1 (+: brow / nasion forward +1.6, skull top +2) for a fuller brow-forehead |
| Everything bigger / smaller (halo) | `head_size` | see 0 | free head_size moves the pupils apart (+3.1 mm) and lowers the vault (cranium_height -0.66 sd) |

## 2. Eyes (placement, prominence, opening)

GNM's eyeballs are a fixed size (29 mm): "bigger eyes" is the OPENING (lids) or the BALL standing forward or the
eyes set wider. Tell them apart in the eyes crop (front + profile) before choosing.

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Pupils further apart (the whole eye unit, balls too; onion skin shows doubled irises side by side) | `head_size` (+) | pupils +3.1 mm, but also the face +6 mm wider | `eye_spacing` does NOT move the eyeballs (pupils 0.0 mm): it moves the inner corners (lids). After head_size, put the face back with `face_width!` / `cheekbone_width!` / `jaw_width!` (-) if the face isn't wider |
| Inner corners closer / further (lids, not balls) | `eye_spacing!` | inner canthi only | free eye_spacing drags the bridge down (-0.59 sd) and pushes the eyes forward |
| Eyes prominent, standing forward of the brow (more white in profile, little lid cover) | `eye_depth` FREE (-) | eyeballs +4.2 mm forward of the nasion (the nasion -2.8 back, nose tip -3.5) | NOT `eye_depth!` (|dc| 6.2: moves radix / glabella 4 mm, the upper face, not the eyes). Free eye_depth also lowers the bridge: if the target's bridge is high, follow with `sculpt:radix` (+) |
| Deep-set eyes under a heavy brow | `eye_depth` (+) or `brow_ridge` (+) free | eye_depth +1: balls -4.2 mm; brow_ridge +1: balls -3.6, brow +1.9 forward | both bring the nose forward (+2.8-3.5 mm tip) and the bridge up: put back with `nose_projection!` (-) if the nose was right |
| Eye openings taller / rounder | `eye_height` (+) | the lid gap; small in mm | free eye_height narrows the jaw a little (-1.5 mm); held version is clean but costs |dc| 2.3 |
| Eye openings longer corner to corner | `eye_width` (+) | lids only | free drags eye_height +0.65, lower_orbit -0.6 |
| Under-eye full / puffy, no lower rim (the ball sits forward of the cheek) vs a defined lower rim | `nd:lower_orbit` / `lower_orbit` (- = flatter / fuller under the eye) | ~0.5 mm per sd at the rim | small per sd: 2-3 sd for a visible change |
| Outer corners up / down | `eye_tilt` | free drags cheekbones +2.4 mm | held is clean (|dc| 2.0) |
| Lid crease / fold deeper | eye step (block-in) d_line; `relief:lid_fold` does NOT deepen it (raises it) | GNM's valley ceiling ~1.6 mm (gnmcrease) | a crisp slit is outside GNM: record, don't fight |

## 3. Brows

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Brows sit lower / higher over the eyes | `brow_height` free | brow +2.7 mm up | free drags the eyes forward (+2.3 mm) and the nose back: if those were right, `brow_height!` (+1.8 mm, clean, |dc| 1.9) |
| Heavy brow ridge + deep eyes + brows low (the whole "heavy brow" look) | `brow_ridge` free (+) | brow +1.9 mm forward, balls -3.6 | brings the nose forward +2.8: put back `nose_projection` (-0.5..-0.7) |
| Brow / glabella forward but the eyes NOT deeper (prominent eyes under a strong brow) | `brow_ridge!` (+) then `eye_depth` free (-) | brow_ridge! +1 = brow +2.8 mm | brow_ridge! alone barely reads (drivers): pair it with the eye move |
| Defined socket rim | `orbital_rim` free | balls -3.4 mm, like brow_ridge | orbital_rim! moves the lid fold zone (2.4 mm): lid / crease, not the rim |
| The middle of the brow (glabella) and bridge forward together | `pc:middle_brow_region1` (+) | nasion +2.6, tip +2.7 mm, |dc| 1.0 | the cheapest strong move for the brow-bridge complex (face-ID 0.15 / unit) |

## 4. Nose

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The whole nose stands further out, bridge to tip ("a strong nose") | `pc:nose_region0` (+) | tip +4.0, nasion +2.3, subnasale +2.4 mm; |dc| 0.95 | the oracle's first choice for nose differences; also lengthens the skull back (-3.9). Free `bridge_height` is similar (tip +4.0, nasion +2.5) but sinks the eyes 3.6 mm |
| High bridge only (radix / upper dorsum), tip right | `sculpt:radix` (+, mm) | nasion +1.1 per mm, |dc| 1.2 | `bridge_height!` is a TRAP (|dc| 7.5, moves the lips and chin 3 mm) |
| Tip projects more, bridge right | `nose_projection` free (+) | tip +3.6 mm, nasion +2.1 | free drags upturn -0.78 sd and the eyes back; held `nose_projection!` costs |dc| 5.1 and lifts the tip 2.2 mm: prefer free + `sculpt:radix` (-) to put the bridge back |
| Tip rotated up (more nostril) / drooping | `nose_upturn` | free: tip -2.5 mm back as it turns up | held `nose_upturn!` (|dc| 3.9) lifts the tip 2.3 mm but pushes lips / chin forward 1-1.6 mm. Garrett's accepted fix: `nose_upturn!` +1.4 with `nose_projection!` -0.4 |
| Longer / shorter nose (tip lower) | `nose_length` free | tip / subnasale lower; also face longer | `nose_length!` lifts the eyes and brows 1.9 mm instead (the nose's top moves): a driver saw "no gain" |
| Wider nose at the wings | `nose_width!` (+) | alae +3.3 mm, clean (|dc| 2.25) | free nose_width widens mouth / jaw / face (+4.3 jaw): only when the whole lower face is broader |
| Broad, round tip (lobule) | `nd:tip_width|held` | | the free nd:tip_width also flattens the bridge |
| Narrow / pinched nose, projecting with the tip down | `pc:nose_region2` (+) | width -1.8, tip +1.4 mm | narrows the jaw too |
| Shorter nose with a longer upper lip | `pc:nose_region1` (-) | subnasale up | |

## 5. Mouth and lips (incl. the PROFILE ANGLE)

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The MUZZLE stands forward in profile: nose base, both lips and chin forward together (a protrusive profile angle), mouth a bit wider | `pc:upper_lip_region0` (+) | lips +2.0, subnasale +1.3, pogonion +1.1 mm, mouth +1.9 wider; |dc| 0.8 | the oracle's first choice for mouth differences (+2..+3 on s1's protrusive mouths); found by a driver only on a third try. lip_projection and nose_projection do NOT do it |
| Lips pout ahead of the nose-chin line (the chin and nose stay) | `lip_projection!` (+) | lower lip +2.15, upper +1.0, chin -0.9 mm; |dc| 2.8 | free lip_projection pulls the nose tip back 2.2 mm and the chin back 2.0 (the population's "full lips, small nose" coupling) |
| Fuller lips (taller red, front view) | `lip_fullness` free if the nose may come back with it, else `lip_fullness!` | | `lip_fullness!` moves the chin bottom 1.9 mm up and under the chin: check the jaw after it; free pulls the nose tip back 1.9 mm |
| Wider mouth | `mouth_width!` (+) | corners +3.1 mm | free widens the jaw (+3.4) and shortens the head back |
| Longer upper lip (nose to mouth) | `philtrum` free / `philtrum!` | | philtrum! moves the chin bottom 1.2 mm too |
| Lower lip forward of the upper (or behind) | `relief:mentolabial_sulcus` (+: lower lip +1.2, upper -0.9 per mm) or `lip_projection!` | | `sculpt:lower_vermilion` (|dc| 2.8) shifts the whole profile 1.2 mm: avoid |

## 6. Chin, jaw, neck (incl. the full / "fluffy" lower face)

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| The whole lower face broader and heavier: wide jaw, broad chin, full cheeks, full under the chin, thick neck ("fluffy", not lean) | free `jaw_width` + `cheek_fullness` (+) and `under_chin` (-), 1-1.5 each; or `face_width` +1.5 | jaw_width +1: jaw angles +8.8, neck +6.4, chin +3.9 mm | face_width free also widens the skull +5.8: put the vault back with `cranium_width!` (-). Wanted: one move (the regional mode jaw_full0, docs/notes/gnm_atlas.md "## gnmdrive") |
| Jaw wider at the angles only | `jaw_width!` (+) | +8.8 mm at the angles, clean | |
| Face wider just below the ears (masseter / parotid bulge) | `sculpt:parotid` (+, mm) | +2.5 mm jaw-angle width per mm, |dc| 1.2 | jaw_width / face_width didn't reach it (driver D) |
| Full under the chin / double chin | `under_chin` (-): free also widens neck and jaw; `under_chin!` (-) only the submental | under_chin! +1 = 4.5 mm cleaner angle | sign: + = CLEAN angle, - = FULL |
| Chin bottom lower (taller chin) | `chin_height` free / `pc:chin_region0` (+: chin -3.7, under-chin -4.2 mm, |dc| 0.8) | chin_height! = -2.7 mm but moves the eyes / mouth up 1.2 | `chin_height!` at +1 was "no visible change" for a driver: the chin bottom moves but so does everything above it |
| Lower face longer overall | `face_length` free (+1: chin -4.7 mm) | drags gonial, chin, nose length, philtrum | |
| Chin stands forward in profile | `pc:chin_region1` (+: pogonion +3.6, |dc| 1.0) or `chin_projection!` (+2.9, lower lip +1.6) | | free chin_projection widens the jaw +2.6 and pulls the nose back |
| Jaw angles higher / lower | `gonial_height` free (chin lower too) or `nd:gonial_height|hold_face_length_chin_height` | | |
| Thicker neck | `neck_width!` (+14 mm per sd) | | the neck is a big lever for the face-error metric but rarely what a face reads by |

## 7. Cheeks

| You see | Use | Size per +1 | Watch |
|---|---|---|---|
| Full, chunky cheeks with a wider lower face | `cheek_fullness` free (+) | jaw +4.8, cheekbones +2.8 mm | it is a lower-face width move as much as a cheek move |
| The cheek's front plane stands forward in 3/4 but the face isn't wider in front | not found yet: `sculpt:cheeks` +2 mm and `cheek_fullness!` read as nothing in two cases | | record it in the log |
| Wider cheekbones only | `cheekbone_width!` | +5.3 mm, clean | free also widens jaw +5.5 and skull +4.1 |

## Ambiguous phrases (look alike, need different controls)

- "Mouth forward": the MUZZLE (nose base + lips + chin together: `pc:upper_lip_region0`) vs the LIPS ahead of nose
  and chin (`lip_projection!`) vs the WHOLE FACE ahead of the ear (`head_depth!`). Check the subnasale and the chin:
  both forward = muzzle; both still = lips; the brow forward too = whole face.
- "Bigger eyes": pupils apart (`head_size`) vs eyeballs forward (`eye_depth` -, free) vs taller opening (`eye_height`)
  vs longer opening (`eye_width`). Look at the onion skin: doubled irises = placement; same irises, different lids = opening.
- "Chin lower" vs "fuller under the chin": the chin's bottom point (`chin_height`, `pc:chin_region0`) vs the
  submental line (`under_chin` -).
- "Head too big" vs "skull too wide" vs "face too far forward": halo all round (`head_size`) vs the vault only
  (`cranium_*!`) vs a uniform profile offset (`head_depth!`).
- "Nose further out": the whole nose (`pc:nose_region0`) vs bridge only (`sculpt:radix`) vs tip only (`nose_projection`).
- "Heavy brow": with deep eyes (`brow_ridge` free) vs with prominent eyes (`brow_ridge!` + `eye_depth` -).
- "Wide face": the face and skull (`face_width` free) vs the lower face only (`jaw_width`, `cheek_fullness`) vs the
  masseter bulge (`sculpt:parotid`).

## Traps (held moves that move the wrong place; couplings.py)

`bridge_height!` (|dc| 7.5: lips / chin 3 mm, marionette), `eye_depth!` (6.2: radix / glabella / forehead),
`nose_projection!` (5.1), `brow_ridge!` (4.5), `face_length!` (moves the jowls / under-chin), `lip_fullness!` (moves the
chin bottom 1.9 mm), `philtrum!` (chin 1.2 mm), `nose_length!` (moves the eyes and brows up, not the tip down).
Sculpts that shift the whole face instead of the zone: `sculpt:dorsum`, `sculpt:lower_vermilion`, `sculpt:chin`,
`sculpt:pogonion` (the profile moves 0.5-1.2 mm per mm asked: macros are held, so the zone moves by translating).

## What the vocabulary can't reach (measured)

Even the oracle (the least-cost moves, knowing the answer) closes only ~30-50 % of a person's regional difference in
six moves: a nose that differs between two people differs in 6-8 independent ways. Go for the masses that read
(size, the muzzle, the nose's projection, the jaw's width, the eye placement) and stop.
