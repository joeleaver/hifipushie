# Clothes: what goes wrong, and the fix

Read guide(topic="cloth") first. Most faults below are construction faults: fix them in the description, the sheet,
the pattern or the start, never by tuning the solver. Rows marked "automatic" are handled by the tools now; they're
listed so you recognise the symptom if it comes back.

## The wrong garment

| What you see | Why | Fix |
|---|---|---|
| Clean sim, wrong garment (a sweatshirt for a fitted sweater, slacks for jeans, a sack for a tailored coat) | Started from the nearest template and fixed faults one at a time | Describe the garment from the reference first (guide(topic="cloth"), stage 0) and choose kind / block / details from the description |
| Armholes deep into the torso, a boxy body on a fitted knit | A woven or sweatshirt draft; armhole depth never checked against the armpit | `"block": "knit"`, set-in `sleeve`; measure the draft's armhole depth below the armpit (2-4 cm) before any sim |
| Suit trousers read as pyjamas | No crease, a wide cropped leg, no fly | `kind: "suit_trousers"` (crease, slim leg, fly, waistband, darts, belt) |
| Jeans read as smooth dark slacks | Fabric, leg, construction and topstitching tells missing | guide(topic="cloth_design"), "What makes jeans read as jeans" |
| Trousers read high-waisted; the belt sits far above the reference's | The block's top is at the NATURAL waist | `block_options.waist_drop` (men's tailored 0.04-0.08) |

## Pattern and construction

| What you see | Why | Fix |
|---|---|---|
| Puffed sleeve caps, a gathered knotted waist, a collar like a funnel, ruffled cuff joins | Cap ease, seam lengths that don't match, a missing piece, a fall too short for its stand, no placket | `look_pattern`: fix every failing seam and evidence line before simulating. Never tune stiffness to hide them |
| A lapel or collar that will not roll | Wholly interfaced (frozen as placed), or no fold line | Interface a band, add a fold line; stage 3 fails on this |
| `dress` says NOT simulated | Stages 1-3 fail | Read the failures, fix the sheet or pattern; `force=True` only to look at the fault |
| A shirt collar's fall stands up (won't turn); collar or stand crumpled on a thin neck | The stand is taller than the neck between trapezius and jaw, pushed off the chin | `collar_rule` sizes it from the neck (stand = neck height - 13 mm, >= 20 mm); or Simon `collarStandWidth` 0.055 |
| A buttoned collar starts 17-30 mm open | Too little collar ease at the neck's base | Simon `collarEase` 0.115 (13 mm over the neck base) |
| A sleeve sewn in rotated (top notch off the shoulder seam) | The armhole's seam chain started at the front pitch | Start an armhole chain where the sleeve's top meets the shoulder seam |
| Back darts read as open tucks | Straight dart legs end in a poke | `dart_taper` 0.6 (the suit_trousers default) |
| No belt shows on trousers with belt loops | The shirt hangs free over the waistband | Tuck it: the trousers `over: "shirt"` |
| A notched collar is a fat roll round the neck | The collar marked draped | Leave the collar made (the default) |
| The jacket collar hides the shirt collar; the jacket's armhole / underarm seams stand open over the shirt | Drafted from the bare body | `over: "shirt"` drafts it over the shirt; check the draft log says "drafted over shirt" |
| Both lapels unroll into a funnel round the neck | The collar stand was lowered to show more shirt collar | Keep the stand (shirt stand + a few mm); lower the back neck (`neckline` op first) and the notch (`gorge_drop`, `break_y`) |
| Lapels stand off the front (gap over 10 mm) | The roll line's fold is soft | `lapel` op `roll_radius` 0.003, `roll_strength` 1.0 (not `made_folds`) |
| A lapel lies flat as a board | Pressed flat on the forepart | `lapel_options.roll_top` (default 7 mm; over 10 knots the collar end) |
| An open jacket's fronts bow forward to the hem (a tent from the side) | The side panel's hem spring (`contour` +16 mm per edge at the hem = 64 mm of flare a side) | Panel seams straight below the waist (`contour` [["waist", 0], ["hem", 0]]); hip room from `hips_ease` |
| An open jacket hangs CLOSED and stands forward of the body below the chest | Started lapped like a buttoned one; or a stiff front (canvas + hard roll) boards the chest's slope down | A front `open` starts apart (`open_gap`); keep the roll soft (`roll_strength` ~0.3) and the canvas light |
| An open jacket too closed (or open) below the break; the shirt V the wrong width at the button | The button stance (lapel `stand`) | Adjust `stand`; measure each front's edge from centre by height, both sides |
| An open jacket's fronts hang together where the reference's hang apart | The pose: the reference raises its arms further | Judge against the reference in ITS pose (turn the arm joints on a copy and dress that) |
| STRAINED at chest / seat on a heavy body | The draft's ease is relative; the belly isn't in the block | `alterations` (`large_abdomen` is automatic); more ease where strained |
| STRAINED at the waist on a shirt with plenty of ease | The placket's fold rows, not the fit | Automatic (fold rows left out of the fit). Read where the strain is before adding ease |
| A skirt slides down or one side seam gapes | Pieces start far wider than the waist; no hip to hold the band | Keep the fit close (straight / a_line), waist ease 2-3%; `zozo.stitch_stiffness` 8 |
| A waistband open at CB, a V down the back | The made band started open and was held so | Self-closed bands start closed (stage 4 fails a band that doesn't). 2-3% waist ease |
| Trouser hem 5 cm short, the ankle showing, or puddled on the foot | Length cut from the shoe's heights, or the shoe isn't a collider | `length: "break"` + `collide: ["shoes", "soles"]` |
| A shirt's top front button ends 2 cm open, a slit of skin by the band | The made stand's centre-front points started further apart than the fronts can follow | Keep the wear rule's numbers consistent: collar `gap` 0.03, spread 18 / 14 / 65; `worn_top` fronts pinned to the stand |
| An open collar stands 2 cm off the nape; a jacket collar rides over it as a shelf | The stand laid round the neck at its length + `gap` | Small `gap` (0.03); the opening from `collar_spread` |
| An open shirt collar stands up round the neck like a ring | A made stand laid ring-like stays a ring | `collar_spread` (default [18, 14, 65]); more drags button 1 open |
| "a neckband piece (none in the pattern)" on a drafted knit | Old: rib details couldn't make their bands | Automatic: the KB's band details generate them |
| A hem band: "piece 'back' has no point 'cbHem'" | A body cut within 3 cm of the waist names its hem points `cbWaist` / `waist` / `cfWaist` | Give the band's own `generate` entry naming those points |

## The start (stage 4)

| What you see | Why | Fix |
|---|---|---|
| Seams round the armpit (side-back, underarm) end 40-110 mm open | They START 75-160 mm open: one start cylinder at the widest level leaves a suppressed waist's arc in one seam | Not fixed yet (a per-level start). Stitch stiffness makes it worse. Read the start gaps |
| On another body the same jacket's sleeves start down the arm, seams far open, the sim stalls early | The armhole is too high for that body's shoulder line | Bodice `armhole_depth` 0.12-0.14 for a jacket; check `sleeve_down` <= 0.02 |
| `ccd failed` at frame 0, or the fine settle refuses its start, with a triangle 3-4x stretched next to a placket | A roll fold's line ends just past the band's inner row at a shallow angle: a sliver | End the roll a few cm above the fastening |
| A layered start: a piece pushed far out, a sleeve started 11 cm down the arm, `ccd failed` at frame 0 | The padded body folded in a hollow (the neck under an open collar, the pit) | Automatic now (unfolded); if it recurs, suspect the pad (`under_cap`, the under collar) |
| "contact starts overlapping" / "newton stalled ... a prescribed pin driven into geometry that cannot yield" at frame 0 | The start was laid on the padded body but the collider is the under garment's own mesh | Automatic (cleared both ways). If it recurs, look at the job's in.npz against its frame-0 collider |
| Trousers over a shirt fail before the sim ("the fine settle's start is stretched ... at the waist corner") | The waist taped on the bare body | Automatic for garments `over` another; give trousers `under_cap` ~0.003 |
| Trousers start as slabs in front of and behind the legs | Old: one front and one back piece per leg tube | Automatic; read the start seam gaps of every new lower-body design |
| A jacket's collar stands as wings over the shoulders beside the neck | The shirt's open stand stood off the neck and the jacket was built over it | A stand that hugs the neck; `under_fall`, `pad_over` 1.1 (jacket defaults). Measure the ridge beside the neck: 5-12 mm of jacket over what's under it |
| A jacket hangs 2-5 cm high: shirt collar hidden, cuffs short, side seams open | Something holds its top up: a back built over the shirt collar, `worn_envelope` too high, too little hip room | `worn_envelope` 0-10; `hips_ease` |
| One side of a symmetric garment wrong; draft changes don't move it | An input of the sim isn't mirror-symmetric (e.g. a made collar end started on the chest) | Before touching the draft or solver: compare every sim input with its mirror at the start (`check_garment(stages=["place"])`). `mirror_mesh` if the mesh is the suspect |

## Simulation

| What you see | Why | Fix |
|---|---|---|
| CORRUPT fronts / plackets | Overlapping pieces passed through each other while sewing | Automatic (self-collision while sewing; the outer front starts one layer outside) |
| CORRUPT sleeves at the elbow | A straight sleeve round a bent arm overlapped itself at the start | Automatic (the excess placed as a fin; `wrap.no_fin` turns it off) |
| A cuff or collar crumpled into a ball | Rest shape and start disagree on a stiff band | If it persists: `resolution` 0.01, not finer |
| A made piece crumpled, or "made pieces start 300-600% stretched past their rest" | Made pieces constructed twice (coarse and fine) and different | Automatic (`made_from` "fine"); check `made_reshaped` is empty |
| Patch pockets through the cloth they're sewn on (CORRUPT) | Held by tacks only, they slid in the sim | Automatic: seated after the sim |
| A knit's sleeves, armholes and rib bands end 20-50 mm OPEN (holes under the arms, ruffled cuffs) | The knit held to 5% strain; its sleeves laid as cylinders off the arm; ring bands laid at cut length | Automatic: a knit is held to its fabric's limit, sleeves stretched on round the arm, `knitted_rib` laid stretched on. Read the per-seam start gaps on every knit |
| Puffy, inflated look | Draft quality or thick collision buffers | Final quality |
| Fine crinkle all over | Frozen buckles a triangle or two across | Clean-up (`cleanup.smooth`); a stiffer fabric; a Blender sculpt + pull |
| Shrink-wrapped (body forms show through) | Too little ease or a too-light, stretchy fabric | More ease in the pattern; a heavier or stiffer fabric |
| Uniform, evenly spaced folds | One fabric everywhere, a symmetric pose | Different fabrics per garment; interfacing on bands; break symmetry by hand in Blender |
| Shirt rides up / sleeves dragged up the arm | Sewing everything at once lifts the bodice | Automatic (bodice sewn first) |
| A hung coat bunched into a sack | Strong sewing force while hung, or a thick rack collider | Hang it on a hanger (`"hung"`), not one pin |
| A sim runs many times longer than usual | No room in the draft (contact everywhere), or a piece through itself | Cancel; read the place stage; go back to the last working ease; never resubmit unchanged |
| A notched collar's ends crumple or stand off where they meet the lapels | The collar is held as laid while the fronts settle under it | Not solved; `collar_ends: "draped"` is experimental |

## Looks and maps

| What you see | Why | Fix |
|---|---|---|
| Every seam a raised welt with a valley beside it, visible across the room | Pieces wound opposite ways, the solver's free hinge, heavy seam maps | Automatic (shared normals, pressed seams, seam finishes). Measure before tuning: the angle between a seam's two sides' normals against the cloth's own |
| The placket band invisible in clay and at outfit distance | The lap sank between the band's edges; a step spread over one triangle | Automatic (band edge cut and lifted after the sim); closure `finish` box over french for shirts |
| A shirt's placket reads as plain cloth with dots | The band's lift too small; maps drew a hem, outlined slots, rivet buttons | Closure `finish`, `hole`, `button` (guide(topic="cloth_sim"), "Closures and bands") |
| Shirt fronts stand 3-5 mm proud of each other down the placket | The solver holds two layers its contact gap apart | Automatic ("lap ... laid closed") |
| A second, undone-looking button beside a closed one | The sim left that fastening apart and the under button peeked out | Automatic (no button drawn under a closed lap); the report flags `!! closure ... sides N mm apart` |
| A jacket's buttons are small white shirt buttons | Shirt defaults on every kind | Automatic (kind defaults: 20 mm, a darker tone of the cloth) |
| A shirt under a jacket shows as a crumpled surface with no placket or buttons, or faceted like crumpled paper | Drawn as the pressed collider, or tucked without the jacket over it | Draw through `cloth.worn_together`; never draw a tucked garment without the garment over it |
| Skin through an under garment under a rolled lapel | Old: the tuck pushed cloth into the body | Automatic (never closer than 1 mm to the body) |
| Jagged, torn-looking white edges in clay | Workbench stencil shadows of a coarse mesh | Shadows off (`HIFIPUSHIE_CLOTH_SHADOWS=0`) |
| A pale zigzag down a seam in your own render | The seam's two vertex rows drawn unwelded | `look_cloth` welds closed seams; weld in your own renders |
| No notch to see: collar end and lapel flush | The collar end sank into the lapel | `collar_options.end_over` 1.0 (default); judge notches in a close camera |
| A made collar end reads as a narrow strap; a knot where it turns the side neck | Made pieces laid on eased cloth | Lay made pieces at their CUT length / width (defaults); check per-station 3D / pattern length (~1) |
| A detail (buttons, a trim) missing, so a sim is queued | Buttons are built after the sim; the render left them out | No sim: look_cloth / export draw them; your own render must too |
| A number disagrees with the eye | The measure names something else (a "notch" read at the collar's tip) | Measure what you name: the notch = where collar end and lapel top meet; heights below the chin AND from the shoulder line |
| A render that "didn't change" after a fix | It was made before the change (old cache key) | Check both renders in a comparison were made after the change |
