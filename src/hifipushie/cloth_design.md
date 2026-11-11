# Clothes: the design sheet (stage 1) in detail

Read guide(topic="cloth") first: describe the garment from the reference, then fill the sheet from that description.

## The body

A garment is drafted to the body it's on (`tailor.measure`: FreeSewing's measurements taken off the surface), so
the model needs a `base` body. A prop for a drape (a table) needs no body.

Hard failures: a choice the draft source can't make (the reply names what it can make); a choice that needs another
(a barrel cuff needs a sleeve placket; buttons need a placket).

### Targets: the kind's checklist is the input (C243)

### The contract: strict, self-describing, transactional (C241)

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
