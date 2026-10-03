# Clothing construction audit (2026-10-03)

The user asked whether our garment construction has ever been checked against tailoring practice and real artist
workflows, with special attention to collars, cuffs and other small visible details, and added: "the cloth appears
thick". This is that check, for the shirt (FreeSewing Simon) and the overcoat (FreeSewing Carlton), on `main` at
08a0aa2. The ZOZO agent's branch (`worktree-agent-ab37bf6854d9d06f0`, d2de8d5 and later) already fixes some of what
is listed; those items are marked **(zozo2)**.

Renders: `workspace/cloth_renders/audit_*.png`. Reference photos: `workspace/cloth_refs/` (README there). Seam check:
`cloth_check.py` (`report(Bp, kind)`), `tests/test_cloth_check.py`.

## The short answer

The patterns are real (FreeSewing drafts sewn on the seam line, with notches that match), and the shirt's seam table
is nearly right. But the construction around them is a simplification that a tailor would not recognise in several
places, and those places are exactly the small details the eye goes to:

1. **The cloth reads thick because nothing on the mesh can be thinner than about 7 mm.** Real shirting creases are
   2.5-4 mm wide; ours are 6-11 mm. The 1 cm mesh can't make a crest radius under ~7 mm, and every layer is held
   5-17 mm off the one under it, where real layers touch.
2. **The shirt collar is a funnel, not a turned collar.** The fall sits 7.6 mm off the stand and stops 13 mm above the
   neckline seam at the back. A real fall covers the stand and its seam by 6-10 mm.
3. **The coat has no lapels.** The fronts are interfaced whole and rest as placed (flat), so nothing rolls back along
   the roll line. There is no facing, so a rolled lapel would show the wrong side anyway.
4. **Seam-table errors in Carlton:**
   - The sleeve cap was +43.7% (zozo2).
   - The stand was -23.8% (zozo2).
   - The missing belt makes back + tail 83 mm shorter than the front side seam (-20.5% above the waist, -5.6% below):
     still open.
   - The tail top is 98 mm too long because its pleats aren't folded (zozo2 folds them).
5. **The shirt sleeve has no placket.** A closed sleeve tube is sewn round a cuff whose ends overlap by 22 mm, so the
   seam has to open or the cuff has to stretch.

## Part 1: construction against tailoring practice

Each line gives what a tailor does, what we do (file:line), and how visible the difference is (H = high, M = medium,
L = low).

### Shirt (Simon)

| Detail | Tailoring practice | Ours | Visible |
|---|---|---|---|
| Grain | Every piece cut on grain. Collar, cuffs and plackets are on grain too. Woven cloth is stiff along warp and weft and soft on the bias, and that anisotropy shapes hems and sleeve drape. | `pattern.py` sets `grain` 90 on every piece. No solver uses it: Blender springs, Newton and ZOZO are all isotropic here. | M |
| Seam allowance | Sewn on the seam line; the allowance is pressed and felled. | Pieces are the FreeSewing **seam line** (`pattern.from_freesewing`, path "seam"), sewn by sampling both sides at equal fractions (`cloth.py:244`). Correct, as in MD. The allowance appears only as a 0.6 mm normal-map ridge (`DETAIL` `cloth.py:2470`). | L |
| Sleeve cap ease | A shirt cap carries 0-1.5 cm of ease, set flat before the side seam is closed, then flat-felled. Notches: front single, back double, cap top on the shoulder seam. | Cap 548.9 vs armhole 550.2 mm (-0.2%). Notches land within 0.5 mm (front 0.274 / 0.274, back 0.659 / 0.660) and the cap top is 3 mm off the shoulder seam. Good. The ease is spread evenly along the whole seam (fraction sampling), not concentrated over the cap between the notches. That is harmless for a shirt but wrong for a coat. | L |
| Back yoke | Two layers (outer + inner yoke, "burrito" method), usually with box or side pleats at the back below it. | One layer. The back is sewn flat to the yoke (458.3 / 458.3 mm, no pleat: Simon's defaults). | L |
| Front plackets | The buttonhole side has a folded placket 32-38 mm wide: 2-3 layers, interfaced, edge-stitched 2-3 mm from both folds. The button side is turned under twice. | `turn` (`pattern.py:242`) **cuts the placket fold off**: one layer plus an interfacing band 16-20 mm wide (`cloth_designs.json` `interfaced`). Fronts start a layer (`LAYER` 4 mm, `cloth.py:797`) apart and end **8.6 mm** apart (median) where they overlap. Real: ~1 mm. | H (the front edge reads padded) |
| Buttons | 7 front buttons, 86 mm apart, 11 mm (18 ligne). Buttonholes on the left front, vertical on the placket, horizontal on the stand and cuffs, button + 3 mm long. | Spacing 86-87 mm and 11 mm buttons: correct. Left over right: correct. Every buttonhole is vertical (`cloth.py:2556`), so the cuff's is turned 90 degrees. The stand and top buttons aren't stitched, so the shirt is worn open-necked by default without saying so. | L/M |
| Collar stand | 30-35 mm at CB, tapering to ~25 mm at CF. Interfaced. Its ends extend past CF to the placket edges. | 29.6 mm at CB and CF, no taper. Interfaced whole. The ends are correct. | L |
| Collar (fall) | The fall at CB is the stand height + 8-12 mm, so it covers the stand and the neckline seam. The roll is a few mm above the collar/stand seam. Upper and under collar plus interfacing: ~1 mm edges. Points 65-80 mm, lying on the shirt. Spread 90-140 mm with a tie, more open-necked. | The draft's fall is 36.6 mm at CB on a 29.6 mm stand: only +7 mm (FreeSewing's default, at the low end). Placement `fold: [0.006, 0.01]` (`cloth_designs.json:15`, `cloth.py:1186`): rise 6 mm, then a U **10 mm across**. That U eats 15.7 mm of the fall, so measured on the sim the fall ends **13 mm above the neckline seam** and lies **7.6 mm off the stand** (p90 12.6). The made collar rests as placed (`made_pieces` `cloth.py:1454`), so the solver keeps that U as the collar's shape. Points 55.7 mm (short). One point lies **28.5 mm off the shirt** (the other 3.1). Spread 174 mm. | **H**: the "hood/funnel" read in every render (`audit_collar.png`) |
| Cuff | Barrel cuff 60-70 mm tall. Closed girth = wrist + 25-40 mm. Overlap 20-25 mm. The sleeve enters through a **placket opening** (120-150 mm slit on the little-finger side, bound underlap, overlap placket), with 2-3 pleats folded toward the placket. Interfaced, edge-stitched. | 57 mm tall, closed 183 mm on a 149 mm wrist (+34 mm), overlap 22 mm: OK. **No placket**: Simon drafts `sleevePlacketUnderlap/Overlap` and a `placketCut` line (x = -64 mm, 142 mm long), but the design table doesn't use them. The sleeve tube is closed to the wrist and sewn to the cuff's whole 205 mm edge. The overlapping 22 mm of cuff has nowhere to come from, so it shows as -1.8% on the seam check and as a twisted, ruffled join. The 2 x 14 mm pleats are folded away as gaps, with no fold direction. The made cuff was 17-30% too big from the push off the wrist (zozo2: elliptic spiral, rests before the push). | **H** at the wrist |
| Hem | Shirttail hem, narrow double-turned 5-6 mm, edge-stitched. | Every free edge gets a 20 mm "hem" in the maps (`DETAIL` hem 0.02), including the collar's outer edge, the cuff edges and the placket edge. Those are bagged seams or folds, not hems. A 20 mm band on a 36 mm collar reads as a stripe. | M |
| Topstitching | Collar, stand and cuffs edge-stitched 1.5-6 mm from the edge (dress shirt 1.5-3 mm). Side and armhole seams flat-felled: two rows 6 mm apart on one side only. | One dashed row 6 mm in from **every** edge of every piece, so a seam shows a row on each side, 12 mm apart. No flat-fell. | M (close-ups) |
| Interfacing | Fused, on the collar, stand, cuffs and buttonhole placket. Bending ~5-20x the shell. Collar stays in the points. | `stiff` 40 for bending (`cloth.py:52`, Blender `bending_stiffness_max`, `blender_cloth.py:102`); `interfacing_bend` 40, stretch 6 (`cloth_job.py:80`). High but plausible for collars. No stays: the points curl up (one is 28 mm off the shirt). | M |
| Pressing | Collar roll, cuff fold, placket edges, hems and pleats pressed: crisp 1-2 mm edges. | Nothing is pressed. Fold lines exist only as placement plus rest (the collar U). There are no fold angles or strengths and no "press" of a two-layer edge. | **H** (part of "thick") |
| Sewing order | Yoke to back, fronts to yoke, collar to stand, stand to neckline, sleeves set flat, side + underarm in one pass, cuffs, hem, buttons. | `cloth_job.stages`: the bodice alone first, then everything, then pose, settle (gravity). The order doesn't matter much in a simulator. Buttons are stitched from the start (MD's guide: sew closed before fastening). | L |

### Coat (Carlton)

| Detail | Tailoring practice | Ours | Visible |
|---|---|---|---|
| Sleeve cap ease | A two-piece sleeve: cap ease 3-6% (2.5-4 cm), eased over the cap between the pitch notches, little under the arm. Sleeve head roll + shoulder pad. | **+43.7%** (867 vs 603 mm). The hindarm part of the under sleeve was counted into the cap (zozo2 fixed). Ease spread evenly by fraction, not over the cap. No sleeve head, no pad. | **H** (puffed caps, splayed sleeves) |
| Back to tail (waist) | Carlton: back + **belt** + tail. The belt (`carlton.belt`, width = 15% of hps-to-waist = 82 mm) closes the gap: the back ends bw/2 above the waist and the tail is waistToHem - bw/2 long. | Belt left out. The back's side seam is 157.7 vs the front's 198.3 mm (-20.5%) and the tail is 724.5 vs 767.5 (-5.6%): 83 mm in total = the belt width. The sim spreads the mismatch along the whole side seam. The tail top is 340.9 mm on a 242.9 mm back waist: +98 mm (the pleats aren't folded; zozo2 folds them, leaving ~ -4.5%). | **H** (gathered, knotted back waist in zz15) |
| Tail centre back | The ref photos (Met 1973.65.1, the same style) show the tail's CB as a pleat/vent: one edge laps over the other, basted at the top, pressed. FreeSewing: "fold under to align" cbMid to fold2Mid, i.e. each tail's CB strip folded under 36 mm. In a standard overcoat vent, one side's extension (35-50 mm) laps over the other's, and the top is stayed with a diagonal tack through both layers (and the lining). | `tail.L:cbTop>cbBottom` is sewn to `tail.R` full length (`cloth_designs.json`). There is no vent and no fold, and the 36 mm strips lie in the plane. The "crossings at the back vent" in every backend are this extra cloth plus the gathered waist. Measured gap tail.L to tail.R: median 15.9 mm. | M/H |
| Lapel and roll line | The front edge from the break point (top button) to the gorge is turned back along the roll line, taped. A facing is cut to the front's lapel shape, so the turned lapel shows the right side. The collar is sewn from the gorge round the back. Notch at collarTip. | No roll: the fronts are interfaced **whole** and are "made pieces" resting **as placed** (job `made`: front.L, front.R), flat on the torso cylinder. The lapel can't roll. No facing (the cutlist has `frontFacing`). The stand was sewn CF to CF (-23.8%; zozo2 stops it at the roll line). Collar 17.1 mm off its stand. | **H** (the coat reads as a closed-neck tube) |
| Buttons (double-breasted) | 3 x 2 at 108 mm across, 97 mm apart. Coat buttons 20-25 mm. Horizontal buttonholes. Jigger button inside. | Pairs stitched CF to CF: correct. Buttons are drawn **11 mm** (`cloth.py:2544`, the shirt's size) with vertical holes. | M |
| Lining, facings, hems | A lined overcoat. Facings 70-90 mm at the front and lapel. Hems turned 40-50 mm, sleeve hems 30-40 mm, blind-stitched (invisible outside). | Shell only (the design says so). Without a lining the open front shows the seam allowances' absence and single-layer inside. Hem detail 20 mm. | M |
| Interfacing | Fused front (body + lapel), roll line taped, felt undercollar, chest piece, pad. | Whole fronts, stand and collar at stiff 20 (wool). With rest = placed, this is what blocks the lapel. | H (via the lapel) |
| Fabric | Wool coating ~450 g/m², bending 0.1-0.3 gf cm²/cm. | 2e-5 N m = 0.2 (zozo2 recalibrated; 6e-5 before). | — |

### Why "the cloth appears thick" (measured)

Fold widths at the same physical scale (`audit_folds_shirt.png`, `audit_coat_hanger.png`). The profiles are taken
across the dominant fold direction (structure tensor), high-passed at 40 mm (coat 120 mm); FWHM of light crests and
dark creases. Medians, in mm:

| | crease width | crest width | fold spacing |
|---|---|---|---|
| ref oxford shirt, sleeve | 2.6 | 3.1 | 8.6 |
| ref oxford shirt, front | 3.2 | 3.5 | 10.7 |
| ref chambray shirt, torso | 4.2 | 4.3 | 12.1 |
| ref white shirt, sleeve (soft light) | 4.5 | 11.2 | 16.0 |
| **ours shirt zz16, sleeve** | **6.1** | **10.9** | **21.0** |
| **ours shirt zz16, torso** | **10.9** | **15.2** | **30.5** |
| ours shirt hung (1 cm) | 17.3 | 22.3 | 36.5 |
| ref wool coat tails (brown / grey) | 20.9 / 10.3 | 29.9 / 15.9 | 44.2 / 38.2 |
| **ours coat zz15, tail** | **28.7** | **28.8** | **96.5** |

Mesh crest radius on the sims (1/max normal curvature at local maxima, away from borders):

| | p10 | p50 | tightest |
|---|---|---|---|
| shirt | 11.3 mm | 21.3 mm | 7.0 mm |
| hung shirt | 13.5 mm | 26.4 mm | 8.0 mm |
| coat | 7.9 mm | 17.3 mm | 5.3 mm |

The edges are 10.1 mm, so **no crest under ~7 mm exists anywhere**. Physics agrees that it should. Shirting's bending
length (B / w)^(1/3) is about 12 mm and coating's about 16 mm, so gravity drape folds are that soft. But wrinkles,
creases at bends and pressed edges are 1-4 mm, and they are what reads as "thin cotton".

Layer gaps (median, where one layer lies over another):

| | ours | real (two cloth thicknesses) |
|---|---|---|
| shirt collar over stand | 7.6 mm | ~1 mm |
| shirt fronts | 8.6 mm | ~1 mm |
| coat collar over stand | 17.1 mm | 3-4 mm |
| coat fronts | 5.7 mm | 3-4 mm |
| coat tails | 15.9 mm | 3-4 mm |

Causes: placement layers (`LAYER` 4 mm, collar U 8-10 mm), made pieces resting as placed (the U becomes the shape),
ZOZO's contact gap + offset (1 + 2 mm), no pressing.

Taubin clean-up widens crests further. The cleaned surface wasn't measured here: the cached results are the raw sim
(`<key>.npz` V).

So "thick" is three things, in order:
1. 1 cm resolution: MD's guide says 5 mm or less for finals.
2. Layers held apart.
3. No pressed edges or creases.

The Solidify thickness in renders is not one of them: 0.4-2 mm, as real.

## Part 2: our pipeline against a real MD/CLO artist workflow

Sources, summarised in our words:
- the Marvelous Designer Creator's Field Guide 2024 (`s3.marvelousdesigner.com/newmdweb/case/20240626/MD+User+Guide+2024.pdf`), which covers fold angles, fold arrangement, strengthen/freeze/solidify, press, seam taping, bond, steam, particle distance and collision thickness;
- the MD manual pages already in `cloth_guide.md`;
- [Threads: professional shirt collars](https://www.threadsmagazine.com/project-guides/fit-and-sew-tops/creating-professional-looking-shirt-collars);
- [CLO: buckling ratio](https://support.clo3d.com/hc/en-us/articles/115002797808-Adjust-Buckling-Ratio) and [buckling stiffness](https://support.clo3d.com/hc/en-us/articles/115002685527-Adjust-Buckling-Stiffness);
- [Fabric measurement for virtual prototyping (Manchester)](https://pure.manchester.ac.uk/ws/portalfiles/portal/160056173/3DBP_Measurement_of_fabric_properties.pdf);
- [Hanbok silk virtual drape study (KES vs CLO Fabric Kit)](https://link.springer.com/article/10.1186/s40691-024-00388-6);
- FreeSewing's [Carlita instructions](https://freesewing.eu/docs/designs/carlita/instructions/): the belt joins back and tail, the tail's back seam is sewn in two parts with the pleat part basted and pressed, the roll line is taped. Carlton's own instructions are unwritten.

| MD/CLO practice | Ours | Gap |
|---|---|---|
| Arrangement points on bounding cylinders; symmetric pairs. | Same idea (`place`, isometric cylinders, cones for bands). | none |
| Particle distance 20 mm while blocking, **5 mm or less** final; collision thickness 2.5 mm default, lowered on the final. | 20 mm blocking, **10 mm** final (Blender's per-edge bending softened finer meshes; ZOZO 1 cm on a pod). Layer offsets 4-10 mm, ZOZO gap + offset 3 mm. | **5 mm finals** on visible pieces (collar, cuffs, plackets at least); layer offsets ≤ 1-2 mm at final. |
| Fold Angle + Fold Strength on internal lines and seams (0-360 deg, 180 flat): collar roll, cuff fold, lapel roll, placket folds, pleats. Fold Arrangement to pre-fold collars and cuffs. | Only the collar is pre-folded by placement (`wrap.fold`), and its U radius is 4-5 mm. No fold angle on lines, no per-line rest angle. | A **fold-line primitive**: a polyline in the pattern with a target dihedral angle and strength. It's a rest-angle constraint on the edges along it (ZOZO: bend rest per hinge; Blender: shape-key rest). Use it for the collar roll, lapel roll, placket edges, cuff edges, hem turns, pleats. |
| Bond (interfacing as its own preset layer on a piece or an internal shape), Seam Taping (fusible tape along a seam: roll lines, front edges), Strengthen (temporary starch while folding), Solidify (keep a shape), Freeze. | Interfacing = a bending multiplier per vertex (whole piece or band). "Made pieces" rest as placed (= permanent Solidify). | Interfacing should stiffen **without** freezing the placed shape. The coat fronts must be free to roll. Add taping (stiff edges along a line). Starch/freeze as stage options. |
| Press tool: two layers sewn at an edge are switched to a "turned" seam type and flattened (collars, cuffs, facings). | Nothing. Bagged edges don't exist: collar, cuff and placket are single layers. | A turned-edge seam: either two layers sewn at the edge with zero gap, or a single layer with a pressed fold-line edge plus a map-level edge. |
| Layers on overlapping pieces (outer over inner), layer clone for padded pieces. | `wrap.out` per piece. | OK |
| Fabric presets from measurements (CLO Fabric Kit / FAB / KES: weft, warp and bias stretch; bending weft, warp and bias; buckling ratio and stiffness; density; thickness; friction). | Isotropic presets. Bending calibrated to KES numbers (zozo2). No buckling, no bias. | Anisotropy from `grain` (warp/weft stiffer than bias), and a buckling ratio. Collar undercollars and cuffs bend differently along and across. |
| Pose from neutral: simulate in A-pose, then record along the avatar's animation to the final pose. | `pose` stage (straight arms -> bent), `lower` for hangers. | OK |
| Steam (local shrink/stretch). | None. | Low priority. |
| Topstitch, buttons and buttonholes as trims with orientation; puckering along seams. | Maps: one generic topstitch row on every edge, vertical buttonholes, 11 mm buttons everywhere. | Per-edge stitch spec (distance, rows, which side), buttonhole orientation, button size per design. |
| Simulation quality steps: fast for blocking, complete for final, then a sculpt clean-up. | coarse -> fine -> Taubin. | Clean-up widens crests. Keep smoothing off pressed lines and creases. |

## Part 3: references and numeric targets

`workspace/cloth_refs/README.md` lists the photos:
- the Met overcoats (CC0);
- Unsplash/Pexels mirrors (CC0);
- one CC BY-SA 2.0 collar photo.

Scales are from buttons (11 mm) and placket widths on shirts, and from button size and back width on the coats. They
are good to ~15%.

| Check | Reference / practice | Ours (zz15, zz16) | Target for the report |
|---|---|---|---|
| Crease width (FWHM), shirting | 2.6-4.5 mm | 6.1 sleeve, 10.9 torso | **≤ 5 mm** median on worn sleeves/torso |
| Fold spacing, shirting (wrinkled regions) | 8.6-16 mm | 21-31 mm | **8-18 mm** |
| Mesh crest radius, shirting | ~1-4 mm wrinkles, ~10 mm drape | p10 11.3, min 7.0 | p10 **≤ 4 mm** (needs ≤ 5 mm triangles) |
| Crease width, wool coating | 10-21 mm | 28.7 | **≤ 20 mm** |
| Fold spacing, wool tail on hanger | 38-44 mm | 96.5 | **30-60 mm** |
| Layer gap (collar/stand, fronts) | ~1 mm shirt, 3-4 mm coat | 7.6 / 8.6 mm; coat 17.1 / 5.7 | median **≤ 2 mm** shirt, **≤ 4 mm** coat |
| Collar fall covers stand at CB | fall edge 6-10 mm below the neckline seam | 13 mm above it | **≥ +6 mm** below |
| Collar points on the shirt | touching | 3.1 / 28.5 mm off | both **≤ 3 mm** |
| Collar point spread, open-necked / buttoned | 120-180 / 90-140 mm | 174 open | in band for the state |
| Stand height CB / CF | 30-35 / 25-30 mm | 29.6 / 29.6 | in band |
| Cuff height; closed girth − wrist | 60-70 mm; +25-40 mm | 57 mm; +34 mm | in band |
| Cuff seam (sleeve edge vs cuff edge minus overlap) | sleeve wrist = cuff length − overlap (placket open) | closed tube vs 205 mm | seam check within band |
| Sleeve angle on a hanger, sideways from vertical | 2-7 deg (shirt), 2-4 deg (coat) | 23.7 shirt, 7-11 coat | **≤ 8 deg** |
| Sleeve cap ease | shirt 0-3%, coat 3-6% | -0.2%, +43.7% | `cloth_check` bands |
| Every other seam | ±1.5% unless designed | coat side −20.5%, −5.6%; tail top +40% | `cloth_check` bands |
| Notches | aligned within ~3 mm | shirt ≤ 3 mm; coat tail fold4 13 mm | **≤ 6 mm** (`NOTCH_MM`) |
| Hem swing (coat on hanger) | hem level within ~±15 mm across the front | not measured reliably here (the tail bunches) | add as a report line |

## Ranked fix list (what matters most visually first)

| # | Fix | Why | Effort |
|---|---|---|---|
| 1 | **Coat lapels:** interfacing stiffens but doesn't freeze the fronts (no "made" rest for fronts); a roll-line fold (break point → `rollLineEnd`, fold 180 → ~20 deg, strong); a facing piece (`carlton.frontFacing`) sewn along the front edge so the lapel shows its right side; stand/collar from the roll line (zozo2 did the stand). | The coat reads as a closed tube without them. | M-L (2-3 days: facing + fold-line rest) |
| 2 | **Fold-line primitive** (rest dihedral per edge along a pattern line, with strength), used for: collar roll (rise ~3 mm, U ≤ 2 mm), cuff edges, placket folds, hems, pleats, the lapel. Replaces the collar's 10 mm U. | Collar funnel, the thick edges, unpressed everything. MD's main tool for collars and cuffs. | M (1-2 days; ZOZO has per-hinge rest angles via bend rest) |
| 3 | **Layer offsets to ≤ 1-2 mm at the final:** LAYER 4 mm, collar U 10/8 mm, ZOZO contact gap + offset, cuff layer. Check with the gap numbers above. | Every overlapping edge reads padded. | S-M (needs ZOZO's min gap at 5 mm) |
| 4 | **5 mm final mesh** on visible pieces (or at least collar, cuffs, plackets, sleeves). MD finals are ≤ 5 mm. Pair it with fold-detail normal maps if the sim can't afford it. | Crest radius floor ~7 mm at 1 cm: the "thick" read. | M (pod time; ZOZO 1 cm already 164 s on a 4090: 5 mm ~4x) |
| 5 | **Carlton belt:** add `carlton.belt` between back and tail (or close the 82 mm another way), so the side seams match. Also the tail CB as a lapped pleat/vent: not sewn full length, each CB strip folded under 36 mm (fold line), basted at the top. | The knotted, gathered back waist and the "crossings at the vent". | S-M |
| 6 | **Shirt sleeve placket:** cut `placketCut`, add `sleevePlacketUnderlap/Overlap` pieces (or a bound slit), sew the open wrist edge to the cuff minus its overlap, fold the pleats toward the placket. | Ruffled, twisted cuff joins. | S-M |
| 7 | **Collar fall length:** check the draft's fall vs stand (≥ stand + 8 mm at CB) and raise `collarHeight`/stand options if not. Add collar stays (stiff strips in the points) or point tacks. | The stand shows at the back; points flip up. | S |
| 8 | **Seam check in the report** (`cloth_check.report` at draft time; fail the draft on ease/notch errors). | Caught the cap, stand and belt errors in seconds; they went unseen for days. | S (done as a module; wire into `cloth.report`) |
| 9 | **Detail maps per design:** buttons 20-25 mm on coats; buttonholes horizontal on cuffs, stands and coats; edge-stitch distance per edge (shirt 1.5-3 mm); flat-fell rows on one side only; hem depth per edge type (shirttail 6 mm, coat 40-50 mm, none on bagged collar/cuff/placket edges). | Close-ups. | S |
| 10 | **Grain anisotropy + buckling** in fabric presets (warp/weft vs bias stretch and bending). | Hem swing, sleeve drape, collar roll on the bias. | M (ZOZO uses uv to orient anisotropy) |
| 11 | **Sleeve angle on hangers ≤ 8 deg** (arms_down further, or a hang stage long enough). | Sleeves splay 24 deg on the hung shirt. | S |
| 12 | Ease over the cap between the notches, not evenly along the whole armhole (weighted sampling per segment between notches); back shoulder ease. | Correct drape at the sleeve head; only visible on coats. | S |
| 13 | Two-layer yoke, bagged collar/cuffs (upper + under), coat lining. | Mostly hidden; the lining shows inside an open coat. | M |

## Seam check output (main, 08a0aa2)

Run `uv run python -c` with `cloth_check.report(cloth.pieces(g, body.m["mm"]), "shirt"|"overcoat")`:

- **Shirt:**
  - cap -0.2% (flagged: under the 0-3% band; harmless);
  - sleeve-to-cuff -1.8% (the missing placket);
  - collar-to-stand -2.4% (collar 9 mm shorter than the stand's top between its CF notches; slight stretch on the
    collar).
  - Everything else 0.0%; notches aligned.
- **Coat:**
  - back to tail -28.7%, notch off 13 mm (the unfolded pleats);
  - side seams -20.5% / -5.6% (the belt);
  - cap +43.7%;
  - stand -23.8%;
  - collar to stand +4.5%.
