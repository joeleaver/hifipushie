# Clothes: the design sheet (stage 1) in detail

Read guide(topic="cloth") first: describe the garment from the reference, then fill the sheet from that description.

## The body

A garment is drafted to the body it's on (`tailor.measure`: FreeSewing's measurements taken off the surface), so
the model needs a `base` body. A prop for a drape (a table) needs no body.

## The sheet (`design_garment`)

```
design_garment(name, "shirt", design={"kind": "shirt", "from": "simon", "fit": "regular",
               "fabric": "cotton_shirting", "details": {"cuff": "barrel", "hem": "shirttail"}},
               spec={"color": "#8fb3d9", "quality": "draft"})
```

Hard failures: a choice the draft source can't make (the reply names what it can make); a choice that needs another
(a barrel cuff needs a sleeve placket; buttons need a placket).

### Targets: the kind's checklist is the input (C243)

```
design_garment(name, "hoodie", design={"kind": "hoodie", "targets": {"fit": "relaxed", "body_length": "hips",
               "shoulder": "dropped", "collar": "hood", "pockets": "kangaroo", "cuff": "rib", "hem": "rib_band"}})
```
Items (one definition each: cloth_checklist.json `design_targets`; the kind's list and defaults:
`garment_reference(kind=...)` `targets_template`): `body_length` (a body level waist / hips / seat / crotch, or
`{"to", "below": m}`: the FINISHED hem at CB from the hps, a band included), `sleeve_length` (short / elbow /
three_quarter / long, or `{"to", "below"}`: the finished sleeve, cuff included, from the shoulder point), `shoulder`
(set_in / dropped / m past the shoulder point), `fit` + `chest_ease` / `waist_ease` / `hip_ease` (fractions; default
the middle of the fit's band; a block's waist and hips follow its chest), `neckline` (`{"style": crew | round | v |
collar | hood, "width": m seam to seam, "depth": m front drop from the hps}`), `neckband_width` / `cuff_height` /
`hem_band_height` (m, finished), `hem_shape` (`{"shape": straight | curved | shirttail, "rise": m}`), and every
detail as a choice (`collar`, `cuff`, `pockets`, `hem`, ...). Unknown items are refused with the kind's list. What
each sets: a drafted design's block options and ops (length, chest_ease, sleeve length + length_bonus,
drop_shoulder, hem_shape, neckline, the bands' generate heights), a FreeSewing draft's options solved on the draft
(lengthBonus, sleeveLengthBonus, chestEase / waistEase / hipsEase, cuffLength, hemCurve); the solved numbers are kept
in `design.solved`. An option or op the sheet gives itself overrides its target (the reply lists it). Kinds with a
checklist: tee, hoodie, shirt, blouse.

### The contract: strict, self-describing, transactional (C241)

Every key is checked when `design_garment` / `alter_pattern` is called; an unknown one is an ERROR that lists the
valid ones with units, sign and default, e.g. `cloth 'hoodie' ops[2] (sleeve): unknown key "ease"; sleeve
takes: biceps_ease (fraction of the biceps girth (+ = roomier); default 0.15), cap_ease (...), ...`. Nothing is
silently dropped, and a call that fails saves nothing (the reply's `saved v<N>` is the only proof of a save).

- **Which keys go where.** A design drafted from a block (`"from": "draft"` / `"block"`) takes `block_options`, `ops`
  and a detail's `"op"` params. A FreeSewing draft (`simon`, `carlton`, `jaeger`) takes its own options (`pattern.options`,
  a detail's `"options"`) and the pattern words; `ops` / `block_options` on it are refused (they never run there:
  shape its drafted pieces with `alter_pattern`). A detail is `{"type", "options", "op", "generate", "trim"}`.
- **FreeSewing options REPLACE their default, they do not add to it.** Units are FreeSewing's: a percent option is
  a FRACTION (`lengthBonus` default 0.25 = 25 %). `"lengthBonus": 0.05` gives 0.05, i.e. 20 points SHORTER than the
  default, not 5 % longer (shirt t7 cut 17 cm in two probes). The reply lists every option set with what it replaces;
  `guide(topic="design_garment")` errors name each option's type, default and range (`freesewing_options.json`).
- **Units in our drafts.** Lengths in metres; eases are fractions of the girth (0.15 = 15 %); angles in degrees.
  Pattern coordinates: x right (out from a half piece's centre line), **y UP** (+y toward the neck on a bodice, the
  cap on a sleeve): `reshape` / `move` `"by": [0, -0.01]` LOWERS a point 10 mm. `block_options.length_bonus` is
  metres added to the bodice; the sleeve op's `length_bonus` is a fraction of its length.

`garment_reference(kind=...)` -> `lessons`: read them before designing that kind.

## Tailoring numbers (checked in stage 2 where the pieces exist)

| Detail | Practice |
|---|---|
| Shirt collar | Stand 30-35 mm at CB, 25-30 at CF, but never taller than the neck allows: neck height (trapezius to jaw) - 13 mm, at least 20 (`collar_rule`). The fall covers the stand and its seam by 6-10 mm at CB (fall = stand + 12). Points 65-80 mm. Roll a few mm above the collar/stand seam. Buttoned girth ~13 mm over the neck's base (Simon `collarEase` 0.115) |
| Jacket collar over a shirt | Stand at CB = the shirt's stand + a few mm (20 mm shirt band -> 24 mm). The shirt collar shows 10-20 mm above it at CB. Lower the back neck, not the stand |
| Jacket length and sleeve | Hem covers the seat. Sleeve ends 10-15 mm short of the shirt cuff |
| Armhole depth | Underarm 2-4 cm under the armpit for a fitted knit or shirt, a jacket ~3 cm. Block option `armhole_depth` = the share of waist-to-armpit the armhole drops below the armpit (+ half the biceps ease): 0.12-0.14 is ~3 cm on a jacket; the bodice default 0.02 and the knit block's 0 sit near the armpit |
| Barrel cuff | 60-70 mm tall. Closed girth = wrist + 25-40 mm. Overlap 20-25 mm. Needs a placket opening 120-150 mm |
| Sleeve cap ease | Shirt 0-3%, coat and jacket 3-6%, knit about 0 |
| Other seams | Within 1.5% unless designed to ease. Notches within 6 mm |
| Waistband | 30-40 mm finished. Closed = waist + 0-30 mm. Ends lap 25-40 mm |
| Rib neckband | 80-92% of the neckline's length |
| Rib bands | Hem band 50-80 mm, 80-90% of the edge it is sewn to |
| Hems | Shirttail 5-6 mm, straight 10-25, skirt and trouser blind hem 30-50, coat 40-50, knit 20-25 |
| Buttons | Shirt 10-12 mm, 70-110 mm apart. Coat 20-25 mm. The buttonhole side laps over |
| Notched lapel | A roll line, a facing, fronts interfaced but free to roll |
| Lapped vent | One CB extension (35-50 mm) laps the other, tacked at the top, never sewn full length |
| Ease (chest) | Woven fitted 5-8%, shirt 10-20%, jacket 8-15% over a shirt, coat 15-30% over a jacket; knits 0 or negative. Skirt / trouser waist 0-3% |

## Settings that decide how it is worn and built

Design-sheet keys go in `design`; garment keys in `spec` (`design_garment(..., spec={...})`).

**Stale options.** `design_garment` merges the sheet key by key, so an option set rounds ago is still there
(`block_options.darts: true` did nothing on a hip-length bodice, then made fish-eye darts under a princess line).
Read the sheet back in the reply; give `false`, null, or `replace=True` to clear.

## Knits (a sweater, a sweatshirt, a tee)

## What makes jeans read as jeans, not slacks

## Shirts: how they are worn

A shirt is worn the way its kind is (garment_kb.json `kinds.shirt.wear`): without a tie (`"tie"` false, default) ONLY
the collar button is undone. Every front button stays closed, the first high on the chest; the V comes from the
collar spreading and the fronts above the first button rolling softly back. `"tie": true` closes the collar too. The
garment's own `closures` entries still win. Simon's `extraTopButton` must stay false (an extra top button with
nothing fastened draws as a hole on the open collar).

An open collar is laid SPREAD (`collar_spread` [out, down, from] deg, default [18, 14, 65], or false): the stand
hugs the back and sides of the neck, and from about the neck's side forward it swings out and tips down so the
points lie on the collarbones. Keep the stand's `gap` small (0.03): every cm of gap is 1.6 mm of radius off the
neck. More spread (40 / 20) drags the fronts' top corners apart and button 1 opens.

Collar proportions come from the wearer's neck (`"collar_rule": "simon"`): stand = neck height (trapezius to jaw)
less 13 mm, within 20-35 mm; fall at CB = stand + 12 mm; points 70 mm. A stand taller than the neck is pushed off the
chin and its fall won't turn. The garment's own pattern options still win.

## Layers: a garment over another

A garment worn over another is DRAFTED over it, as a tailor measures for a jacket over a shirt: its neck is the
under garment's neckline plus the collar's thickness round, its armhole lowered by the under garment's thickness in
the armpit (the draft log says "drafted over <garment>"). Body girths stay the bare body's: give the design's ease
for what goes under it. Proportions are still yours: the outer collar's stand at CB is the under collar's stand less
what should show; the outer sleeve ends 10-15 mm short of the under cuff (`length_bonus` about -0.03 over a shirt
that reaches the hand).

**Don't lower a jacket's collar stand to show more shirt collar**: the lapel's roll line comes down from the stand,
and with a lower stand the collar's turn pulls the lapels up into a funnel round the neck. Lower the jacket's back
NECK instead and set its notch lower: `{"op": "neckline", "widen": 0.012, "back": 0.035}` FIRST in the ops, lapel
`gorge_drop` ~0.12 and `break_y` ~0.46 (judge it). The jacket collar lies low and flat round the back of the neck
outside the shirt collar, the shirt collar showing above it at the back and sides.

A tucked shirt: the TROUSERS are `over` the shirt (drafted from the waist taped over the tucked shirt + the layer
gap; `under_cap` ~0.003). Worn free, the shirt hangs over the belt.
