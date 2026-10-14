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

- **kind:** shirt, blouse, tee, hoodie, jacket, coat, trousers, jeans, suit_trousers, shorts, skirt, dress, flat. It
  sets the fit's ease bands, the default details, the sleeve cap's ease band and the sewing order. `jeans` and
  `suit_trousers` draft themselves (`{"kind": "jeans", "fit": "straight"}` is five-pocket jeans: yoke, scoop and
  patch pockets, fly, band, mid rise). A crew-neck SWEATER is kind `hoodie` with `"block": "knit"`, details collar
  `rib_neckband`, cuff `rib`, hem `rib_band`, pockets `none`, plus garment key `worn_top: true` (see "Knits").
- **from:** what drafts it. `simon` (shirt, FreeSewing), `carlton` (overcoat, FreeSewing), `skirt_block` (our own
  skirt draft). Or a `block` + `ops` (guide(topic="cloth_blocks")). Or leave both out and give own `pieces` +
  `seams` on the garment (name each piece's `"role"`).
- **fit:** the kind's fits (shirt slim / regular / relaxed, skirt straight / a_line / full). Stage 2 checks the
  pattern's ease per girth against its band.
- **fabric:** a fabric with physical numbers (weight, thickness, woven or knit, bending length): cotton_shirting,
  oxford, linen, cotton_twill, denim, wool_suiting, wool_coating, jersey, rib_knit, french_terry. Different fabrics
  must bend differently: one preset on every garment reads generic. ZOZO gets the fabric's real numbers: density
  from the KB's gsm, flexural rigidity B = w g c^3 from its bending length c (`garment_design.kb_physical`; the
  construction stage prints "ZOZO gets (kb): ..."). A fabric with no KB bending length (rib_knit, or a bare preset
  name like "shirting") falls back to the solver preset and stage 3 WARNS. To change a fabric, correct its numbers
  in garment_kb.json `fabrics`; a one-off garment can give `"fabric": {"preset": ..., "physical": {"density",
  "bend"}}`, which wins.
- **details:** one choice per detail, or `{"type": choice, "options": {raw draft options}}`. Anything left out takes
  the kind's default, and the reply says so. `garment_reference(detail="collar")` lists the choices with what each
  is made of, its seams, fold lines, interfacing, dimensions and checks.
- **method:** `"simulate"` (sew and simulate everything) or `"settle"` (construct, settle lightly, detail:
  guide(topic="cloth_sim")).
- **pattern:** draft words passed through (`ease`, `length`, `sleeve_length`, `options`, `measurements`).

Hard failures: a choice the draft source can't make (the reply names what it can make); a choice that needs another
(a barrel cuff needs a sleeve placket; buttons need a placket).

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

| Key | Where | What it does, and when |
|---|---|---|
| `tie` | garment / sheet | false (default): a shirt worn with only its collar button open; true: closed to the top |
| `closures` `[{"name", "state"}]` | garment | How an opening is worn: `{"name": "front", "state": "open"}` hangs a jacket open (buttons stay on); laid over the design's entry by name |
| `collar_spread` | garment | An open shirt collar's spread [out, down, from] deg (default [18, 14, 65]); false keeps it a ring |
| closure `finish`, `topstitch`, `hole`, `button` | closure entry | How the placket / faced edge, buttonholes and buttons look (guide(topic="cloth_sim"), "Closures and bands") |
| `block_options.leg` | sheet (trousers) | skinny, slim, tapered, straight, wide: the leg's cut from the leg's own girths |
| `block_options.length` | sheet (trousers) | `"break"` (suit trousers' default): 30 mm over the floor, back 12 mm longer, the hem resting on the shoe with one soft break |
| `block_options.waist_drop` | sheet (trousers) | m under the natural waist where the top sits (men's tailored 0.04-0.08) |
| `block_options.hips_ease` | sheet (jackets) | Room over the hips (a heavier body ~0.14). Only acts with `"fitted": true`. Never get hip room from hem flare |
| `block_options.length_bonus` | sheet | Length added to the bodice (m). A jacket covers the seat |
| `block_options.armhole_depth` | sheet | Lowers the armhole (share of waist-to-armpit): see the tailoring table |
| `block_options.front_balance` | sheet | Raises the front's neck and shoulder. Pulled the sleeves up when tried: leave 0 |
| `block_options` | sheet | Merged over the kind's own draft options key by key |
| `lapel` op `roll_radius`, `roll_strength` | sheet ops | The roll line's fold. 0.003 / 1.0 holds the lapel on the front (gap 9-11 mm; default 0.006 / 0.5: 12-15) |
| `lapel` op `gorge_drop`, `break_y`; `neckline` op `back` | sheet ops | Where the notch sits and how low the back neck is: how much shirt collar shows. `neckline` goes FIRST in the ops |
| `over` | garment | Worn over another garment: drafted over it, placed and simulated on it pressed. A shirt tucked into trousers = the TROUSERS `over` the shirt (only then does the belt show) |
| `under_cap` | garment (outer) | How far the under garment's loose cloth may stand off the body (0.008; jackets over shirts 0.004; trousers over a shirt ~0.003) |
| `under_fall` | garment (outer) | How far over the pressed cloth the under garment's collar fall lies under this garment (0.004 for jackets / coats) |
| `pad_over` | garment (outer) | How far up a body normal the under garment still pads, x its own distance to the body (1.1 jackets / coats, 1.5 otherwise) |
| `collar_ends` | garment | A notched collar past the neck's side: "made" (default) or "draped" (EXPERIMENTAL, not usable yet) |
| `support` | garment | Pads on the body, not cloth: `[{"kind": "shoulder_pad", "thickness": 0.012}, "sleeve_head"]`. Without them a jacket's shoulders slope soft |
| `worn_top` | garment / kind | true for shirts, jackets and coats (the kind's default): fronts and backs built on the form. Set it for knits with a seam-laid neckband |
| `press_lay` | garment | How far a pressed lapel starts off its front (0.003; 0.005 where an open shirt collar's points lie under the lapels) |
| `worn_envelope` | garment | Smoothing rounds of the surface a worn top is laid on (0 = the padded body; up to ~10 where the under garment's open collar makes steps; more rides the jacket up) |
| `made`, `made_folds` | garment / sheet | Override made / draped per piece; `made_folds` didn't pay on lapels. Leave them off |
| `collide` | garment | Model parts the cloth rests on besides the body: `["shoes", "soles"]` so a trouser hem lands on the shoe |
| `interfaced` | garment | Whole pieces or bands: `{"piece": "front.L", "near": ["break", "lapelPoint"], "within": 0.1}` is a jacket's chest canvas |
| `zozo.stitch_stiffness` | garment | 1 default. 8 closes trouser / skirt seams ZOZO leaves 3-15 mm open, at ~3x the time. Does NOT fix seams that start far apart |
| `fine_settle` | garment | false skips the fine settle (a garment whose fine start fails the start check) |
| `mirror_mesh` | garment | Opt-in: .R pieces meshed as the exact mirror of .L (when the mesh is the suspect in an asymmetry) |

**Stale options.** `design_garment` merges the sheet key by key, so an option set rounds ago is still there
(`block_options.darts: true` did nothing on a hip-length bodice, then made fish-eye darts under a princess line).
Read the sheet back in the reply; give `false`, null, or `replace=True` to clear.

## Knits (a sweater, a sweatshirt, a tee)

`"block": "knit"` (0-2% ease, no darts, a looser neck, a cap without ease) + `{"op": "sleeve"}`. The rib details
make their own bands (`draft.generate`: the neckband laid up from the neckline, `wrap: seam`, 3 mm out; cuffs round
each arm following the sleeve's wrist; the hem band from CB on the torso, aligned on the front's centre). Override
one band with a garment `generate` entry of the same `band` name, or a detail's `{"type": "rib", "generate":
{"height": 0.06}}`.
- `worn_top: true`: the body pieces are laid on the form, so the seam-laid neckband starts round the neck (on a loose
  tube it starts 2x stretched). The armhole then sits at the true armpit: lengthen the sleeve,
  `{"op": "sleeve", "length_bonus": 0.06}` (a share of shoulder-to-wrist).
- Fabric: one per garment. A knit sweater is `jersey` (a sweatshirt `french_terry`); `rib_knit` has no KB bending
  length and falls back to the solver preset (stage 3 warns). The rib bands' stretch comes from their `ratio`.
- `block_options.hips_ease` only acts with `"fitted": true`; unfitted, the knit hangs straight from the chest.
- Length: `block_options.length` in metres below the HPS at CB. Measure the target as where the BAND's lower edge
  sits on the reference, less the band's height. A body cut within 3 cm of the waist names its hem points
  `cbWaist` / `waist` / `cfWaist`, not `cbHem` / `hem` / `cfHem`: a hem band's chain must name those (give the
  band's own `generate` entry), else "piece 'back' has no point 'cbHem'".
- A hem band laid from the seam (`wrap: seam`) starts 135% stretched: keep the torso + align wrap. Its closing seam
  starts ~30 cm open at the back (stage 4 WARN): the declared rib stretch lets the solver close it.
- A sweatshirt (kind hoodie, french_terry, drop shoulder, deep armhole, boxy) is a different garment from a fitted
  knit sweater (jersey / rib knit, set-in sleeve near the armpit, close body): the description decides which.
- Not built: knit surface texture (gauge, rib texture). The knit reads from drape, bands and silhouette.

## What makes jeans read as jeans, not slacks

| Tell | Made by | How |
|---|---|---|
| Heavy, stiff denim: broad folds behind and in front of the knee, a stack at the hem | Fabric + sim | denim at its KB numbers (395 g/m2, bending length 26 mm); a hem resting on the shoe (`collide`), length "floor". A longer cut to stack at 2 cm went CORRUPT: not yet |
| Fuller straight leg below the knee | Pattern | `block_options` `knee` / `hem` (half girths, m), e.g. 0.20 / 0.19 |
| Back yoke, scoop pockets, patch pockets, fly, band, belt loops | Construction (kind `jeans`) | Automatic; patch pockets seated after the sim |
| Contrast topstitching (double rows on felled seams, fly J, pocket edges, hem) | Detail maps | `detail.thread` golden (#b8843a); the kind's `felled` seams draw two rows |
| Arcuate back-pocket stitching, rivets, coin pocket, button | Detail maps / trims | NOT built |
| Indigo wear and fades (whiskers, knees, seam edges, hem) | Paint | NOT built for cloth |

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

`"over": "<garment>"` wears this garment over another of the model (dress that one first). The one underneath is
frozen and pressed close to the body where it is loose (`under_cap`), and is what this garment is placed on and
collides with. After the sim the report lists the tailoring tells: the under collar showing above this collar at CB
(10-20 mm), the under cuff past this sleeve (10-15 mm), lapels lying on the fronts, this collar hugging the one
under it, no crossings between the layers. The export leaves out what this garment hides of the one underneath.

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
