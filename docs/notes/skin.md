# hifipushie notes: skin

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- Skin (2026-10-05, "skin" agent; the user: humans read "flat, plastic-like"; textures "for humans of all sexes, ages,
  and genders", incl. cosmetics, scars, tattoos, wrinkles, freckles; renders `workspace/skin_renders/sk_*`, references
  `workspace/skin_refs/` (24 CC photos, README + refs.json with skin-only boxes; never in the repo)). Guide:
  `guide(topic="skin")` = `skin_guide.md` (the artists' stages with sources); tools `skin`, `look_skin`, `skin_reference`.
  - Diagnosis (`skin_measure.py`: CIE Lab contrast per octave of feature size inside skin-only boxes, zone colour,
    highlight share / blob size / breakup, micro contrast; same code on renders and photos; a*/b* hardly see the light, so
    they read albedo). Flat colour + one roughness vs 13 photographed faces: lightness contrast at 0.35-1.4 mm 0.04-0.08 vs
    0.8-1.3; a* contrast at 1.4-11 mm 0.04-0.11 vs 0.4-0.6; no highlight at all vs 5-13% of a patch; cheek a* +0.3 vs
    +1..7. Ranked: no fine relief / highlight breakup, one albedo colour, no visible specular, no scattering colour, flat
    painted lips/brows.
  - `skin.py`: `spec["skin"]` (tone, age, variation, detail, oil, thin, sun, zones, lips, features, wrinkles, hair, scars,
    tattoos, makeup, shading) expands into ORDINARY paint layers "skin:<x>" laid under the model's own (`paint.layers`),
    plus the skin part's base (`part_base`: tone colour, roughness, specular 0.36 = F0 0.028, subsurface by tone, a coat
    lobe scaled by `oil` on the same bump, sheen; `scene.sync` merges it under the part's own keys). `spec.geometry`
    strips it. Tone = pigments, not a colour: melanosome fraction of the epidermis x haemoglobin fraction of the dermis ->
    spectral reflectance (Jacques' numbers, Kubelka-Munk dermis, Wyman CIE fits) -> sRGB (`tone_rgb(tone, melanin=,
    blood=, oxygenation=, epidermis=, yellow=, grey=)`); every layer is "this skin with more/less of a pigment", so
    cheeks, lips, palms, scars are right on any tone. Calibrated by eye to F1 #cda590 .. F6 #55331c (the raw model went
    orange at high melanin: a 130/cm flat term on melanin and a small back-scatter term fixed hue and floor).
  - Zones (`skin.zone`, paint generator `{"zone": name | {"name", "grow"}}`, expanded in `paint.layers` before anything
    else sees them): FACE (spots at lm_* landmarks in interocular units), LINES (tapered polylines: nasolabial, brow,
    lash lines), OUTLINES (lips), UNIONS (beard, nose, t_zone), BODY (shoulder, elbow/knee on the extensor side, hand,
    palm = hand x facing the palm normal from the finger chains, knuckles, fingertips, nails, forearm, sole). ".L"/".R"
    or both. A missing joint says which.
  - New general paint pieces: generator `spot` (soft ellipsoids / tapered polylines at joints, native per pixel), `tile`
    (a tiling grey image triplanar, `vary` = a second copy at 1.618x mixed by a 7 cm noise, `rotate`; native image nodes:
    mip-mapped), layer `mix` (multiply/screen/overlay/soft_light), entry op `"vertex": true` (measure this entry per
    vertex), a breakup-only entry.
  - THE LIMIT that shaped it: a renderer's shader holds a few dozen layers. EEVEE compiles a material into one GPU
    shader: the first 96-layer skin took > 5 min and 10 GB before I killed it (stage 1's 42 layers: 60 s). Cycles ran out
    of SVM stack ("out of SVM stack space": black skin, no exception) from exposed Value/RGB leaf nodes (every leaf is
    computed first and held: 96 colours x 3 slots), then from the Bump node (it compiles its height subgraph three
    times; one mask of ~20 tapered lines alone overflowed). So: (1) layers marked `_pre` (broad, soft: zones, mottling,
    lips, roughness patches, flush/tan, shadows under hair, foundation/blush...) are composited per VERTEX in Python
    (`paint.precomposite`, linear colour) into five measured scalars the material starts from (`prog["pre"]`); (2) what
    needs detail finer than the mesh is built ONLY from tiling swatches, images and a few line spots, never procedural
    noise/Voronoi (`skin_swatch.py`: depth swatches pores / lines / coarse / lips with the 0.5-3 mm grain folded in; mark
    swatches stubble / freckles / wrinkles / hairs; `brow_image` = a drawn picture of ~900 tapered hairs laid as a decal
    from the brow landmarks: noise strokes read as a smudge); (3) zone masks confining fine layers are measured per
    vertex (`"vertex": true`); (4) skin layers expose no named nodes, unexposed colours are socket constants; (5) one
    layer carries relief + cavity tint + roughness (one mask instance). Heavy test character (63 layers, 26 fine): EEVEE
    compile 130 s -> 75 s, 6-7 s a frame; export bakes (no Bump in emission passes) compile.
    Also: node LINKING is quadratic in tree size (1000 nodes 10 s, 2000 65 s, 3000 168 s in a bare Blender): every mask
    is now its own node group (`_Nodes.group/subtree/instance`, groups named `hpm:<part>:<n>`, dropped on rebuild; pull
    reads `hp:` nodes inside them). Round trip on a copy of dg_fix2: renders mean 0.18/255 apart (every object was
    re-meshed), both pulls empty, spec unchanged.
  - Features (`skin_features.py`, each a number or {"amount", "where": [zones], "mask": [...], ...}): freckles, moles
    (scattered or `at`), age_spots (default age x sun), blemishes, veins (default from age / thin), flush, sunburn, tan
    (`mask` for tan lines); wrinkles default from age (folds / crow's feet / under-eye as tapered lines, forehead / neck /
    lip lines / cheek lines from the wrinkles swatch, crepe from the coarse one); hair: brows, lashes (lash lines only),
    stubble (cool shadow pre + dots), body; scars cut / surgical (stitch dots) / keloid / burn / pockmarks with age 0..1
    and no pores on scar tissue; tattoos (`tattoo_image`: the picture blurred by years in its own mm, black toward
    blue-green, colours faded; multiplied into the skin under its relief). Make-up (`skin_makeup.py`): foundation (also
    hides 75% x coverage of the fine pigment layers, which composite after the pre base), concealer, contour, blush,
    highlight, eyeshadow, eyeliner + wing, mascara, brows, lipstick, nails; each with a finish (roughness / specular /
    metallic).
  - Eyes (`skin.eyes`, on where the base has eyeballs; `_eyes`): a painted picture per eyeball (`skin_swatch.eye_image`:
    radial iris fibres, collarette, limbal ring, soft pupil, a sclera pinker toward its edge with forking vessels) laid
    as a decal on the eyes part, wet (roughness 0.04), a shadow under the upper lid; caruncle and waterline on the skin.
    Flat iris/pupil paint on `eye_front` read as toy eyes at bust distance. No cornea bulge, no lash geometry yet.
  - Shaved / cropped heads (`hair.scalp`: amount, color, hairline): the hair's shadow under the scalp skin (pre) + cut
    hairs from the stubble swatch, inside ONE ellipsoid bigger than the skull whose exit from the skull is the hairline,
    nape and the line over the ears. The head joint is at brow height and the cranium ~1.5 interoculars round it
    (interocular = pupil distance, 6-9 cm on these heads): the first version's spots, sized by guess, ended just inside
    the skull and nothing showed, though the mask read 1 at test points (which were inside the head). Test masks at
    points found on the surface (a ray through `sdf.field_at`), not at joint + offset.
  - Wrinkle swatch: three families of wandering lines (main, a branch family crossing them at a slight angle, fine),
    each line's depth from noise much longer along the line than across (`_smooth_noise(cells, cells_u)`), so creases run
    on for centimetres, fade at their ends and fork. Isotropic depth noise chopped them into dashes ("scratches").
  - `skin_look.py` (`look_skin`): cropped stage models `workspace/_skin_<model>_<head|arm>` (bare skin + eyes, ~1 mm),
    re-synced when the spec or the skin code changes, EEVEE under fixed lights (studio / soft / back) or `engine=
    "cycles"`; views bust, face, three_quarter, side, cheek, eye, mouth, forehead, ear, hand, palm, forearm; `layer=`
    shows one mask; prints the face's measurements beside the photographs' with hints.
  - MakeHuman: the female macro targets are in assets.json (48 files) and `base.body.sex` is the continuous gender
    slider (1 male default: byte-identical; 0 female). GNM heads have no age/sex controls of their own (seeded
    identities): see headfit below.
  - Heads follow the body (2026-10-05, `headfit.py`, renders sk_07 / sk_08; the main session: every head was the same
    adult face). MakeHuman's topology is fixed, so `makehuman_lm68.json` (made once by `spikes/headfit/make_table.py`:
    the two neutral heads aligned by eye centres, similarity ICP on the face, a local ICP per feature, nearest
    vertices, pairs forced symmetric; checked in a picture) names its vertices at GNM's 68 landmarks + 4 cranium
    points. For a body, the landmarks' MOVE from MakeHuman's reference head (25 years, sex 0.5) to the body's own, in
    interocular units round the eye midpoint, is added to the seeded GNM head's landmarks (delta transfer: the
    table's millimetres of mismatch cancel, the seed's individuality stays) and solved in 120 identity components
    (ridge, components past +-2.6 sigma fixed and the rest re-solved), eye centres held. Head scale = the body's
    interocular / the fitted GNM's (0.74 for a 7-year-old, ~0.92 adults; the old default 1.4 made every head a
    doll's). OFF unless asked: `base.head.follow_body: true` or a strength 0..1.5 (the main session: existing
    characters with seed-only heads, s0urc3's Garrett, must not change; without the key the built base is
    bit-identical to main's, checked by checksum on three bodies and in `tests/test_headfit.py`); the `skin` tool
    hints at it and the skin guide's stage 0 recommends it for new characters. 60-70% of the asked move is made.
    What it took: lids and lips weighted 0.3 / 0.5 / 0.15 (in full, the child's lips twisted and lid margins tore);
    the neck and bib HELD (90 skin vertices under the chin: no landmark sees them, and left free the fit flared the
    bib up to the graft plane = the stand-up collar round old bodies' necks; with them held the head's neck matches
    the body's within a few mm); the graft plane follows the chin; a monotone neck taper. `tests/test_headfit.py`.
    Honest read: the child and the men read as their age; the old woman reads as an old man (GNM's space and a
    bald head), the adult woman androgynous.
  - Heads by age / sex / weight, second pass (2026-10-05, renders sk_10 grid, sk_h_*; supersedes the solve described
    above): MakeHuman isn't needed at runtime. `head_axes.npz` (spikes/headfit/make_axes.py) samples how the table's
    points (68 landmarks, 4 cranium points, ~350 dense pairs over face / cranium / neck) MOVE from MakeHuman's
    reference head (25 y, sex 0.5, weight 0.5) across ages x sex and with weight (`headfit.shape_delta`). The move is
    made in two steps: GNM identity components by ridge (60-70% of it), then the residual as a Gaussian RBF warp of
    the head (`head["warp"]`: jaw / chin width, brow ridge, neck girth; lids and lips take little of either). The seed
    first loses its OWN component along the sex / age / weight directions (`_body_axes`: a heavy-jawed seed left a
    woman a man). Keys, all opt-in (without them the base is bit-identical): `base.head.follow_body` (true |
    strength: age, sex, weight and scale from the MakeHuman body), `base.head.like` {"age", "sex" 0 female .. 1 male,
    "weight"} (set apart from the body, or on any body incl. the stylised template), `base.head.features`
    {brow_ridge, jaw, chin, nose, lips, cheeks, eyes, cranium: -1.5..1.5} (one part of the sex / child move on its
    own). `headfit.report(base)`: asked move, share reached by identity / after the warp, largest local stretch.
  - `skin.sex` (0 female .. 1 male, unset = neither; `params` -> `fem` / `masc`): sex-linked DEFAULTS, each still
    settable: finer thinner brows, darker lash lines, finer pores (detail x 0.78), lips with 25% more blood for a
    woman; heavier brows and coarser skin for a man. Stubble stays `hair.stubble` (off unless asked).
  - Eyes, second pass: `base.cornea` (a smaller sphere proud of the eyeball where the gaze leaves it, ONE group with
    its eyeball: as two elements with different blends the scene's chunked evaluation blew the mirrored eye up to
    twice its size, in the scene only, the clay look was fine); look lights take `"window"` (the highlight from a
    rectangular area light, the sun keeps diffuse + shadow) and `"specular": 0` on fills: one window catchlight, not
    two discs; a tear line on the eyeball where the lower lid meets it (paint `near: ["base"]` works).
    `look_skin`'s stage key now includes base.py / headfit.py: a stale stage hid two fixes for an hour.
    Not done: lash cards, re-measuring against the 24 photos, export fixes, grooms; nostrils show a pale thing
    behind them on followed heads.
  - Mirrored decals (the user on sk_07: "the left eyebrow is backwards"): a mirrored image decal kept the picture
    reading the same way round (right for text), so the other brow's hairs ran toward the nose. Image key
    `mirror_image: true` reflects the whole frame (`images.mirrored`: right = the reflected right, planar decals);
    the brows set it. Lashes, lip lines and wrinkles are zone masks / tiling swatches, not mirrored pictures; eyes
    are one decal per side; tattoos and text stay unmirrored. `look_skin` view "brows"; sk_09; tests in
    test_images (`test_mirror_image`) and test_skin (`test_brows_mirror`).
  - Heads as MakeHuman FIELDS (2026-10-05, "skin2" agent, branch worktree-agent-acd58d9aa9f53c1da; renders sk_20_*,
    sk_2w_*, sk_21_*; replaces the identity solve + RBF warp for age / sex / weight, which reached "93%" of 426 sampled
    points and still made a woman a soft man). Diagnosis by rendering MakeHuman's OWN heads beside ours: MakeHuman's f32
    reads female, its f78 an old woman; ours didn't, because (1) only the DELTA from MakeHuman's neutral was added to a
    GNM seed, and GNM's mean head is itself wider-jawed and heavier than MakeHuman's neutral (mean vs reference rms
    0.14 interoculars: more than the whole female move, 0.11); (2) a seed's individuality at spread 0.7 is as large
    as the sex move and reads male on a bald head; stripping the seed along a linear sex axis (landmark- or
    dense-fitted) does not change that. Now `spikes/headfit/make_field.py` registers GNM's mean head onto MakeHuman's
    reference head once (pairs RBF as a first guess, 4 rounds of closest point on MakeHuman's triangles facing the same
    way for the OUTER skin, each displacement smoothed over GNM's mesh by Laplacian least squares; lids' insides, mouth
    sock, ears ride; lips weighted 0.2; eyeballs / teeth carried by the skin beside them) and stores, per GNM vertex,
    `ref` (GNM mean -> MakeHuman reference) and the moves to every age x sex and weight (`head_fields.npz`, 2.6 MB,
    float16, interoculars; no MakeHuman pack at runtime). `headfit.field_vertices(desc)` -> `base.gnm_head` adds it
    x the head's interocular (head["field"] = a small descriptor, not the array: head dicts are cache keys).
    `follow` = seed stripped (`_body_axes`: the fields fitted in GNM's components) + field; `features` alone still go
    through the identity solve + warp and get NO field. New opt-in keys: `base.head.dimorphism` (default 0.8: the
    sex difference pushed past MakeHuman's own, half as far on the male side: a man at 0.8 read as a brute),
    `base.head.toward` (share of the absolute move, 1). Abs transfer through the 426 pairs alone made a lumpy skull;
    identity-space-only abs made a pouting boy. base.VERSION 76. `headfit.solved_points(h)` for tests.
    READ: woman 32 and teen girl read female bald; the old woman reads as an old woman or an ambiguous elder (was: a
    man); child fine; use `spread` <= ~0.45 for women and children (0.7 masculinises). The head's `scale` now comes
    out ~0.88 child / 0.97 adult (the field carries the size ratio).
  - Skin realism pass 2 (same agent): the "dried mud" was the `lines` / `coarse` swatches' Voronoi NET (every cell
    outlined at one depth) + crepe laid at 2-4 mm with a dark tint. Now `skin_swatch._glyphics`: families of nearly
    parallel furrows crossing at an angle with whole-number line counts (tiles), each fading in and out. Wrinkle
    swatch: rounded troughs 2-3 mm wide with rolls between (a 0.7 mm V = a scratch), forehead tint 0.2 -> 0.08; crepe
    relief 0.16 mm, tint 0.1, off forehead / chin; coat 0.04 + 0.16 oil -> 0.015 + 0.07 oil at roughness 0.34 (the
    varnish), base roughness +0.03, pores 0.21 -> 0.34 mm relief with less tint. Elder woman, measured: lightness
    contrast 0.7 / 1.4 / 2.8 / 5.6 mm 0.54 / 0.49 / 0.56 / 0.58 -> 0.38 / 0.47 / 0.57 / 0.61 (photos 1.26 / 0.83 / 0.78 /
    1.2), highlight 10% blobs 4.8 mm breakup 1.69 -> 5% / 4.6 / 1.33, micro 0.019 -> 0.010 (photos 0.05): it reads
    less like mud and MORE airbrushed by the numbers: fine relief is still 2-3x under the photographs. Dark woman:
    micro 0.033, highlight 15% in 11 mm blobs: still oily.
  - Whole humans by age, first honest line-up (the user: "we haven't seen any whole face-and-body children or
    babies"; `spikes/headfit/lineup.py`, sk_21_ages_lineup_clay.png + sk_21_ages_lineup_measures.txt; clay, no skin
    yet, the sheet's columns are mis-cropped). `base.body.age` goes to 1 through put_model; the pack has baby / child
    targets. MEASURED (ours | MakeHuman's own head | reference charts): stature 60 / 74 / 103 / 131 cm at 1 / 3 / 7 / 11
    (refs 75 / 95 / 122 / 144: MakeHuman's children are 10-20% short; pass `height`); heads in the height 4.87 / 5.51 /
    6.52 / 7.29 (MakeHuman's own 4.59 / 5.20 / 6.16 / 6.89; refs 4 / 5 / 6 / 6.75; adults 7.7-8.3 vs 7.5): heads are
    too SMALL at every age, MakeHuman's own by ~12% at 1 year, ours a further ~6% (partly lm_chin vs MakeHuman's
    chin_z: not untangled); hip joint / stature 0.43 at 1 (crotch ref 0.36: legs too long); interocular 37.8 mm at 1.
    FAILS seen: the baby's nose is torn open (a ragged hole at the nostrils: the field at age 1 turns the nostril
    walls inside out); the toddler has a long thin neck (graft) and an adult-ish torso; every face is the same stern
    seed; no fat rolls; rig / hands / skin zones on a baby NOT checked.
  - Whole children and babies (2026-10-05/06, "humans3" agent, branch `humans3`; renders sk_30_* (clay line-up),
    measures sk_30_ages_lineup_measures.txt; references `workspace/skin_refs/ages/` (README = spikes/humans/
    REFERENCES.md): WHO stature + head circumference, Snyder 1977 children's anthropometry from NIST AnthroKids,
    compiled by `spikes/humans/make_growth.py` into `growth.json`). The sk_21 line-up failed; by MEASUREMENT the
    causes were not the ones guessed:
    - Heads were NOT too small. The "reference" heads-in-height (4 / 5 / 6 / 6.75) were artists' chart numbers from
      memory; measured children (WHO stature / Snyder vertex-to-chin) are 4.6 at 1 y, 5.4 at 3, 6.4 at 7, 7.1-7.3 at
      11, 8.0 adult. MakeHuman's proportions were within 2-3% of that at every age. Its SIZES were wrong: baby ->
      child (10 y, not 11) -> young (25 y) blended in straight lines of age gave 60 / 74 / 103 / 149 cm at 1 / 3 / 7 /
      16 (medians 75 / 96 / 122 / 173 for boys), and a 20-year-old was a third child. `makehuman.grows`: under 25 (and
      unless `base.body.growth: false`) the age slider is SOLVED so the shape's heads-in-height = `anthro.heads(age,
      sex)`, then the body is scaled to `anthro.stature(age, sex)` x (MakeHuman's adult / WHO's at 19: 0.98 / 0.975,
      so 19-24 = the 25-year-old). From 25 nothing changes (bit-identical). `height` still overrides the size.
      After: stature, heads, head height, sitting height, trochanter height, hand length within 0-5% of the
      references from 1 to 19 y, both sexes. Off: MakeHuman's women have narrow shoulders (joint breadth 0.85 of
      the taped biacromial; men 0.94-0.97), small feet (0.84-0.89) and slim waists (0.85); under 1 year the shape
      stays a one-year-old's (heads 4.7 vs ~4.4 at 6 months).
    - `anthro.py`: `stature`, `head_height`, `heads`, `head_circumference`, `reference(age, sex)` (Snyder's segment
      means scaled to WHO's stature), `measure(P, J, chin_z)` (the same measures off a body mesh; girths = hulls of
      level slices cut at the shoulder joints, so toddlers' waists read small) and `table`.
    - The toddler's "long thin neck", the baby "cropped below the chest": the graft's neck tube. A followed head
      brought GNM's adult neck, and `_neck_tube` took the loop `loops[-1]` when no loop cleared the plane (a baby's
      chin lies on its chest): `_stitch` then cut the shoulders and arms off with the head. Now a head that follows
      its body fully (`follow_body` true, no `like`, toward 1; `headfit.follow` sets `own_neck`; `base.head.neck:
      "tube"` opts out) keeps the body's own neck: no cut, no tube (`src` = every template vertex: the hand-made
      weights reach the whole neck), the head's points above the plane eased onto the body's own head along their
      normals over `OWN_REACH` 3.5 cm x scale, the two point sets cross-faded as before. The GNM field head is the
      body's own head within 2.5 mm mean (p95 6-9 mm; chin landmark 5-8 mm higher than the table's: definition).
    - The "torn nose" at age 1 / the pale thing in followed heads' nostrils / flecks at the lip corners: the
      mouth fill (`base.inject`) was sized in absolute metres for a head of scale ~1.1; in a child's head (0.74-0.84)
      it came out through the nostrils and lips. Scaled by the head's scale for followed heads.
    - The stern thin mouth: `mouth_gap: 0` (the least-change lip closing + zip) presses the lips into a line. With
      the key left out the lips are GNM's own, a hair parted and full: `humans.spec` leaves it out. (Face shapes
      still need `mouth_gap` >= 0.002 + `interior`.)
    - "Breasts" on the toddler / child: mostly clay shading of MakeHuman's modelled nipples and the sk_21 strip's
      crop (arms cut off, so the torso read narrow-shouldered); MakeHuman's female child (10 y) does have a waist
      (waist / hip girth 0.70 vs a woman's 0.69, a toddler's 0.86). `base.body.nipples: 0` moves the skin round each
      nipple (found as the smallest mesh rings near the breast bone's tail) onto a quadratic sheet fitted through the
      ring outside it. Relaxing those vertices puckered the pole; a centre found by "most forward" landed on the
      belly, by "most proud of its ring" 2.5 cm off (the pole then stayed and the body's field creased in a star).
    - `humans.py` + tool `human(name, age, sex, weight, muscle, height, seed, outfit, tone, skin, head)`: a whole
      DRESSED person as an ordinary spec (body with growth, followed head, eyes + cornea, outfit, skin) and its
      measures against the references in the reply. Outfits (`humans.outfit`): tee_shorts, onesie (under 2),
      underwear, none: plain shell parts whose region boxes / sleeve cones / neck hole are placed from the body's
      joints, crotch and chin. The garment option (`close` / `hang` / tube) made studs at the nipples' rings, ruffs
      in the armpits and a line at the tube's top on small bodies: not used. Children get muscle 0.35, nipples 0.
      `tests/test_humans.py` (references, proportions 1-22 y both sexes, adults / opt-out unchanged, dressed by
      default, own neck). `spikes/humans/lineup.py [clay|skin]`.
    - Never render or send a child's figure unclothed: the tool dresses by default; diagnosis used numbers and
      scratch-only clay.
    - The head tables (head_axes / head_fields) were sampled along MakeHuman's OWN straight-line ages, so a head
      following a grown body is looked up at `makehuman.table_age(body)` (the age whose old slider has this shape:
      a grown 11-year-old -> ~13); `like.age` under 25 is converted the same way when the pack is there.
      spikes/headfit/make_axes.py / make_field.py pass `"growth": false`. base.VERSION 85.
    - STATE AT THE STOP (usage limit, 2026-10-06; branch `humans3`, last commit = this note): tests green at commit
      0f967b6 + the table_age fix (test_humans, test_headfit alone, test_skin, test_images, test_bodywarp; the last
      seq1 run's test results are in the worktree's `scratchpad/seq1.log`, read it first). NOT YET REPORTED to main
      and NOT JUDGED: the final clay line-up `workspace/skin_renders/sk_30_ages_lineup.png` + `_measures.txt` (14
      dressed figures, front + side, at true height, faces under). The copy I last looked at still showed the OLD
      composition (one face per person, 12 + 2 rows) and nipples as RINGS on the adults' tees although the script
      (`spikes/humans/lineup.py`, face row = front + three-quarter, two rows) and the smoothing (r 0.04 H, blend
      0.9 r) had changed: check whether the file was really rewritten (COMPOSE=1 re-lays the sheet from the
      panels in the session scratchpad `humans3/lineup/` without rebuilding) before believing it.
      My read of the previous render: babies, toddlers, 7s, 11s read as their ages and sizes (72-74 / 93-94 / 118-119 /
      140-141 cm), whole, arms on, no long necks, no torn noses. Still failing: tees are skin-tight shells (adults'
      muscles, navels and nipple rings print through: they read as body paint, not cloth); all faces are near one
      face (seeds at spread 0.35-0.5 after the seed loses its sex / age part: raise spread per person or add
      `features`); eyes read half shut at line-up size; a hatch of fine marks on the throat where head and body
      point sets cross-fade (own neck: try a wider band than +-SEAM); faint ring where a nipple was; shorts' box hem.
    - NEXT, in order: (1) verify + judge sk_30, SendMessage to "main" with branch, commit, tests, sheet path, the
      measured table and a blunt read; (2) looser cloth without the garment option's studs (a patch over each
      nipple pole, or fix `base.garment` closing at dense poles), varied faces, open eyes; (3) skin on
      (`lineup.py skin`: needs scene syncs, heavy), per-person front / three-quarter / side rows, face close-ups
      (look_skin stages take the base: check they handle own_neck and the onesie); (4) rig, hands, skin zones on a
      baby (rig_template reads `src`: now every vertex has one; rig.humanoid Neck / Head on a neckless toddler
      unchecked; retopo.graft_head / export topology "wrap" with own_neck UNTESTED and likely needs the no-cut
      path); (5) the `human` tool in guide.md / the skill; (6) priority 2 list from the task (elder woman, fine
      relief, oiliness, lashes, export of one human).
    - Scratch (worktree `scratchpad/`, untracked): run.sh (env), one.py <age> <sex> <outfit> [zoom] (one clay human),
      face.py (face variants), t4.py (bodies vs references table), t5.py (GNM head vs the body's own), quick.py (a
      PIL clay view of a mesh without Blender), seq1.sh (line-up then tests).
  - Chests, clothes with volume, faces, the throat (2026-10-06, "humans4" agent, branch
    `worktree-agent-ab7ea373ab4099300`; sheet sk_40_ages_lineup.png + _measures.txt; the user on sk_30, arrows at the
    woman's chest: "What is going on with this poor woman's boobs?"). Scratch in the worktree's untracked
    `scratchpad/`: run.sh, d1.py / d3.py (bare adult chest views + bust numbers; scratch only), g1.py (one clothed
    clay human, ZOOM=2.4 for a torso close-up), f1.py (face rows for a list of people), n1-n3.py (throat field
    probes), z1.py (a close look at a joint), tile.py.
    - THE CHEST, by measure (`anthro.measure` -> `bust_projection`: how far the fullest level of the chest's front
      stands ahead of the breast bone; ~10-20 mm flat, 30-40 an A/B cup, 50-60 C/D): (1) `base.body.nipples: 0`
      smoothed a patch 4% of the stature wide (6.4 cm on a woman) onto a sheet fitted through the ring outside it:
      it scooped a crater out of each breast = the dented ring. (2) MakeHuman's own female at average cup stands
      18 mm ahead of the breast bone, a small pointed AA cup, and our loader read only the macro targets: its
      breast modifiers were never fetched. (3) The tee was a shell of the skin (see below). Now the pack has
      targets/breast (228 files, CC0, in assets.json; `makehuman._bust`): `base.body.bust` / `firmness` 0..1
      (female x age x muscle x weight x cup x firmness, as MakeHuman blends them; no target at average / average, so
      a body without the keys is bit-identical), `nipples` = MakeHuman's nipple-point / nipple-size targets scaled
      by the body's size (an adult's millimetres turned a baby's chest inside out), then `_smooth_nipples` over 1.2%
      of the stature (wide, 4%, only under 11 years: MakeHuman models a mound under a child's nipple).
      `humans.bust_default`: bust 0.7 growing in from 11 to 17, firmness 0.65 at 30 -> 0.4 at 75, +0.2 dressed (a
      bra). Woman 30: 32 mm; children and men 0-2 mm. base.VERSION must be bumped when makehuman.py changes a body
      (the build cache is keyed on it, not on makehuman's code: a stale build hid two fixes).
    - CLOTHES: `humans.outfit` now uses `parts.<p>.garment` (close + hang + a torso tube; legs tubes for shorts),
      lengths scaled by stature / 1.7. What had made it unusable on these bodies: (1) the garment's field was
      EXACTLY 0 between 6 cm and the mesh's largest face size from the cloth (`_imls`'s far value, max(d - hmax, 0)),
      so the region's box showed as slabs in the air before a loose tee: garment point sets carry `far_fit` (the
      plane fit, capped at half the nearest vertex's distance; the body's own field is untouched); (2) the "studs
      at the nipples" were the nipples (flattened now); (3) notches in the hem at the side: the torso's region box
      was as wide as the shoulder joints and a woman's hips are wider (`tee_hips` box, `breadth()` = the torso's
      half breadth with the arms left out), and the shorts lay outside the tee (thinner shorts, tube_ease 12 mm);
      (4) tube key `"arms": "taper"` (what counts as arm narrows toward the wrist) and `"band"` (the hand-over's
      length, scaled). Onesie: close 60 + a nappy (a layer-1 blob round the seat). Underwear: close 12 / 6.
    - FACES (`humans.face(age, sex, seed)`): per-seed `features` (nose, lips, cheeks, chin, jaw, brow_ridge, eyes)
      leaning with age and sex, spread 0.45 (women, children) .. 0.6, lids opened by `pose` (lid_upper -2.6 mm:
      eye height 0.19-0.23 of the pupils' distance, was 0.15 = half shut), a trace of a smile, `mouth_gap` 0.001
      (lips together; parted, the fill behind showed as ragged teeth).
    - THE THROAT (own-neck graft, `base.surface`): three things were tangled. (1) Fine level lines down the whole
      neck = MakeHuman's neck rings of long thin quads with the IMLS kernel at the MEAN edge length: now the
      longest edge at each vertex (own-neck bodies only). (2) A ragged slot with shards under a child's jaw: there
      the body's and the head's skins are different surfaces 5-10 mm apart inside the overlap, each with a
      few-mm kernel, so the sheets ended in free edges: each point's kernel is now as wide as the gap (they blend
      into one closed skin). (3) The head is eased onto the body's TRIANGLES (closest point facing the same way,
      `rig_template.from_surface`) with trust falling off smoothly by distance and facing. Tried and dropped: a
      step onto the body's IMLS field (tore a ring round the neck), snapping the overlap's points sideways onto the
      body with its normals (a ribbed band). The mouth fill of a followed head is lower and flatter.
    - NOT the cause, for the record: the IMLS and `soften` do not flatten the chest (the tool sets no soften).
    - Read of sk_40 (clay, 14 dressed figures): the clothes read as cloth (tees hang from the bust and belly, no
      navel / muscles / nipples; the woman's chest is a normal chest under a tee, 33 mm; teen girl 28, woman 75
      11 (MakeHuman's old shape hangs low), children and men -6..+4). Still wrong: shorts are puffed tubes, a level
      crease across the bust where the tube takes over, one boat neckline for everyone, no sleeves' drape; babies'
      mouths are lumpy and grim, children still stern; the woman of 75 still reads as an old man; a faint line
      across the 11-year-old girl's throat; nostril interiors are lit pale dishes in clay.
    - `look_skin`'s head stage is BARE skin: for a body under 18 it is cut just under the neck (never a child's bare
      chest or shoulders).
    - Tests: test_humans (+ test_bust, test_faces_differ), test_headfit, test_skin, test_images, test_bodywarp pass.
    - NEXT, in the coordinator's order: (4) skin on (`lineup.py skin`: scene syncs, heavy, one at a time),
      per-person front / three-quarter / side rows, face close-ups; rig, hands, skin zones, export topology on baby
      proportions (retopo.graft_head / topology "wrap" with own_neck UNTESTED); (5) fine relief vs the photographs,
      the dark woman's oiliness, lashes, nostril interior (a dark paint zone inside the nostrils), one human
      exported. Also open from this round: baby / child mouths (try `features.lips` lower and no smile pose under
      3), the elder woman (longer `dimorphism`, or hair), shorts as a real garment, a neckline per outfit, the
      `human` tool in guide.md / the skill.
  - Open: EEVEE shows no light through ears/nostrils (Principled subsurface + thickness set, nothing visible); the
    shadow edge's colour is unmeasured against a matched light; real lashes and long brow hairs want geometry; nipples
    / areolae have no landmarks; freckle swatch repeats at 6 cm if a zone is large; a Cycles LOOK still fails on a heavy
    skin (Bump x3); per-vertex pre layers need a body voxel <= ~1.5 mm to hold 3 mm mottling (look_skin's stages do).
    `tests/test_skin.py`.


- Skin 2 (2026-10-09, "skin2" agent, branch `worktree-agent-a19d53ef6fe103feb`; sheets `workspace/skin_renders/sk2_*`;
  scratch DURABLE in /mnt/data/hifipushie/skin2/: run.sh, gshot.sh <tag> <patch> (dressed Garrett through the photo's
  camera + likeloop's light; HEAD=<head model>), g3q.sh (3/4 beside the desk painting), lk.py (look_skin views), cp.py
  (copy a model + patch; drops other branches' brow keys), t_dens.py (density / curvature on the head mesh),
  t_bd.py (map vs density per vertex), stub_lineup.sh, frk_lineup.sh, mk_looks.sh, grid.py / sheet_g.py / tsheet.py;
  20 more CC refs ref_25..44 in workspace/skin_refs: grey / designer / patchy / 1-day stubble, makeup looks, freckles).
  - `skin_marks.py`: UNIQUE mark maps instead of tiled swatches (the user: stubble "not dots alone", freckles with "no
    visible repeat"). The skin part's field meshed in a box round the head (`head_mesh`, cached `_images/mk_mesh_*`),
    marks scattered by area x a density field from landmarks (+ the field's mean curvature at 1 cm, `head_curvature`),
    drawn into one image per feature through each mark's local Jacobian, laid as a sphere-wrap image decal (centre deep
    in the head behind the mouth, `sphere`). Channels: stubble r dark hairs / g white hairs / b shadow; freckles r all
    (darkness = value) / g dark ones / b moles. Opaque PNG (the image store bleeds colour under alpha 0).
  - Stubble (`hair.stubble`: style clean / five_oclock / short / designer / heavy / patchy + length, density, grey,
    patchy, trim, cheeks, cheek_line, neckline; engine "tile" = the old path): hairs as cut strokes along the growth
    direction (down; out from the philtrum; toward the throat under the chin), finer / shorter / lighter where sparse;
    untrimmed edges taper over ~2 cm with 6% stragglers past them (Joe: "edges too hard, don't follow the face
    shapes"); the top boundary sags under the cheekbone, the neckline hangs from the jaw's landmark chain, convex
    cheek front and nasolabial bulge thinner. Shadow = the EXPECTED dark-root density from a 12x dense sample,
    normalised by the samples' own coverage (blurred drawn roots fell off short of every edge: a pale band over the
    lip; a plain sum doubled where the mesh has two skins). Cast warm grey-brown for grown hair (Garrett's photo: Lab
    ~45/4/13 at 0.8 coverage), cool for a fresh shave.
  - DEAD ENDS / bugs found: the map centre in the mouth mapped tongue/teeth over the whole face through huge Jacobians
    (white discs of shadow); nose / mouth insides along the same rays as the cheeks printed through (fixed by
    `outward`: facing out + outermost skin along the ray by a coarse z-buffer); look_skin's stage didn't re-sync on
    skin_marks.py changes (added to its code hash).
  - Landmark-drawn lines that ignore the surface: lm_mouth_corner sits ~6 mm outside the vermilion's corner on GNM
    heads (skin:lip_seam now ends at verm_u00/u16; g4_garrett's own over_lip_seam paint drew the "slit"); the
    nasolabial / marionette fold lines are now gated by paint "cavity" and a near-grey tint (a red-brown landmark line
    beside facesliders' geometric fold read as streaks); lm_eye_inner / outer sit a few mm past the lids' corners (told
    eyedetail; the caruncle spot still uses it).
  - Make-up (`skin_makeup.py` rewritten): look natural / everyday / evening, placement per side from that side's own
    landmarks seated on the head mesh (`_Seat`: frontmost skin along +y, or nearest round the eye); liner = the lash
    line's zone thickening outward; wing = a drawn flick (`wing_image`) laid from the front at the outer lash line,
    shortened for the receding temple; shadow lid / crease / outer V; contour in the cheek hollow; blush apples /
    lifted / draped; bronzer, highlight, lip liner / overline, balm. Freckles: `features.freckles` {amount, size, clump,
    dark, zones} on the face map; body zones from the swatch with vary on.
  - Tess (approved by Joe, "her skin looks good"): tone fitzpatrick 1, blood 0.25, undertone +0.15; flush 0.3 on cheeks;
    freckles (after the freckle engine changed) {"amount": 0.08, "dark": 0.1}, no moles (map moles are real ones);
    zones nose_red 0.75, midface_red 0.8, under_eye 2.0, eyelids 1.4; lips blood 1.0 melanin 2.8.
    Garrett: stubble {style short, length 0.002, grey 0.35, cheeks 0.75, shadow 1.0, color #3a342f}.
  - Blind reads (fresh general-purpose agents, sheets sk2_05..09 vs refs; the coordinator relays the top 5): round 1
    and 2 drove: stubble = cool blue-grey sub-skin shadow + short upright hairs with skin between (a warm shadow read
    as brown felt, a greyed one as olive "dirty wash", a bluer one as lilac); grey hairs mid-grey (near-white ones
    LIGHTENED Garrett's beard: "ash"); freckles = ~120/cm2 specks ~0.4 mm, few bigger, round, red-brown (1.3 mm lobed
    ones read as splats); crisp lip borders (per-vertex lips need the mouth refine in look_skin, soft <= 0.5 mm);
    perioral redness (else a green band under the lower lip), lower-lip sheen. When a fix seems not to land, first
    check the render is current (stage key + code hash) - here it was, the faults were real.
  - Eyeliner wing, four tries: tube through points seated on the temple (blobs / pieces); a picture laid from the
    front (lands on the lid fold above a deep-set eye: a shard), once mirrored (floated off the other, asymmetric lid);
    a geodesic surface sticker from the lash line (its frame turned on the margin's upward normal, the wing never
    left the corner); WORKS: a chain of small spots from the outer third of the lash line along the lower lash line's
    angle, each spot deep (4 mm) along the forward axis so it reaches the turning skin, per side.
  - Open: base-skin pores / T-zone shine at front distance (blind read 3's #2); blush reads as a soft patch; evening
    red lip flat; the lineup head om_new_man_30 shows its inner shell through the face (z-fighting patches).
  - HANDOVER (skin2 -> next agent, 2026-10-09 late; branch worktree-agent-a19d53ef6fe103feb at 81e32ab+, main has it up
    to be0bc76 + later merges: check `git log main..`). The final blind read (4th) still flagged, and the coordinator saw
    on sk2_05: the evening wing reads as a thorn flicking up off the outer corner; the evening crease shows a pale
    floating arc above the lid (likely makeup_highlight's brow-bone spots or the eyeshadow crease layer's light colour
    against the darker lid: check with look_skin layer=...); lip borders still soft / a halo; no visible sub-skin stubble
    shadow at distance (5 o'clock ~ clean, salt & pepper ~ clean); patchy reads as stains; freckles uniform.
    The coordinator's rule for the next round: GATE BY MEASURE against the refs, not by eye:
    (1) stubble: mean L/a/b of the beard zone minus a clean cheek, ours vs ref_30 (1 day; ref_25 is grey), ref_29
        (designer), ref_28 (salt & pepper); boxes on the refs by hand or with spikes/garrett4/skinm.py's detector
        (`fskinm.py` in scratch measures any photo vs any render with skinm's zone boxes, scaled by interocular); tune
        STUBBLE_STYLES shadow / the cast in skin_features._stubble_map until the deltas match;
    (2) lip border: 10-90% edge width in mm at the cupid's bow and mid lower lip, ours vs ref_36 / ref_38 / Tess's
        photo, and no pale ring (L just outside the border <= the skin's): suspects lip_border (pale rim, grow 1.6),
        the per-vertex lips (look_skin refines the mouth to 0.5 mm; dressed stages don't), lipstick outline soft;
    (3) wing: root distance from the lash line 0, angle = lower lash line extended; measure on the eye view (the
        lm_lid_lower_out -> lm_eye_outer direction projected; the spot chain is in skin_makeup "if wing > 0");
    (4) remove the floating pale arc. Then one more fresh blind read (prompt: copy from this session's: sheets sk2_05..09,
        refs ref_25..41, scores 1-5 per column, 3 defects each, top-5 fixes, < 900 words).
    Re-render with /mnt/data/hifipushie/skin2/round5.sh-style scripts (stub_lineup.sh, frk_lineup.sh, mk_looks.sh
    sk2_t13e <tag>, gshot.sh + g3q.sh for Garrett with HEAD=sk2_g6, grid.py / tsheet.py / sheet_g.py / compose*.py for
    the sheets); one look_skin stage takes 1-3 min (it re-meshes on every code change).
    Tests: tests/test_skin_marks.py (zones from landmarks, deterministic maps, styles, fade band never darker than
    full, freckles don't repeat), test_skin.test_makeup_looks.
- skin3 (2026-10-09/10, "skin3" agent, branch worktree-agent-adc9408fe374b85f8; sheets
  `workspace/skin_renders/sk3_01..05`; scratch /mnt/data/hifipushie/skin3/: skin2's scripts retargeted (run.sh, cp.py
  now KEEPS brow tilt/fall/lift/apart, lk.py, gshot.sh/g3q.sh, grid/tsheet/sheet_g) + the measures below, st1/lu.sh
  (stubble copies of om_new_man_30), mkq/rmk.sh (Tess copies sk3_t13e = ts_h13 + t5.json in each look + measures),
  round6.sh, sheets.sh). Every fix GATED BY MEASURE; renders like with like (each picture resampled by its own
  detector interocular = 62 mm).
  Measures (scratch): stub_m.py (beard = chin + jaw + upper-lip boxes minus the cheek boxes, Lab, at 0.3 mm/px, + the
  1 mm-scale L texture "fine"; hand boxes for ref_28-31), lip_m.py (lip border 10-90 % width + pale ring at face
  scale), lipz_m.py (same on look_skin's mouth close-up, 0.078 mm/px), wing_m.py (canthus projected with the eye
  view's camera: gap from lash line to wing, wing lower edge angle vs the lower lash line), arc_e.py (lid band:
  brightest 1.5-7 mm above the lash line minus the crease minimum up to 10 mm), frk_m.py (freckle specks per cm2 in
  boxes bridge / upper / mid / outer cheek / forehead / chin, + spread of the specks' dL, a, b, size, flatness).
  Baselines: clean-faced refs (ref_02/19/34/35/42) give beard-zone minus cheek ~ dL -13 +-8 (shading), da -3, db +1:
  the refs' stubble increment = their delta minus that. Our renders: increment = delta minus sl_none (-1.9/-5.4/-4.5).
  (1) STUBBLE. Finding: the stubble shadow was a PER-VERTEX (pre) layer: a smooth wash; the stubs (0.1 mm) alone gave
      a 1 mm-scale texture of +0.4 (5 o'clock) .. +2.8 (heavy) over bare skin vs +2.4 .. +3.1 on ref_28/29/30. Now:
      skin_marks.stubble_map draws each dark hair's SHAFT UNDER THE SKIN (a soft dash ~1.3 mm long behind the exit
      point, fading with depth, ~0.2 mm wide) into the shadow channel, which carries it as grain
      (B = smooth * (SUB_GAP 0.4 + 0.6 * clip(2 * dashes))), the shadow layer is per pixel (no longer _pre; shader
      budget test 36 -> 37) with SHADOW_GAIN 1.6 (was 0.85), its cast darker (CAST_DEPTH 0.6) and greyer (CAST_SAT 0.15);
      grey hairs cut the smooth shadow by (1-grey)**0.6 (was linear). VERSION 19 (+ SUB_* in the map's key).
      Increments now (L / a / b, fine): clean -6.2/-1.1/-2.0 +1.0; 5 o'clock -9.5/-1.8/-3.0 +1.8 (ref_30 1-day -5.3/-3.2/
      -5.8 +3.1: darker than ref_30, between it and ref_31's dark shadow); short -10.3, +2.1; designer -13.2/-2.1/-3.5
      +2.8 (ref_29 -13.1/-8/-14, +4); heavy -14.9 +3.2; salt & pepper (grey .45) -7.7/-1.7/-2.8 +1.1 (ref_28 -9.2, +2.4).
      L and texture now in the refs' range at distance; CHROMA is still short: a/b fall 1.5-3.5 where the refs fall 3-14
      (a greyer cast barely moved it: CAST_SAT 0.45 -> 0.15 gave ~0.3; suspect the subsurface (1 mm x 2 mm radius)
      re-reddening the zone; not pursued).
      Patchy: beard_density's random 14 mm noise blobs on the cheeks read as stains; patchy > 0.25 now grows where a beard
      comes in first (moustache along the upper lip, soul patch, the chin's underside / the jaw's front edge), cheeks and
      connectors bare, a 5 mm noise thinning inside the patches (fewer hairs, not blotches); the old noise stays at
      <= 0.3 for every style. Reads as a young man's moustache + chin growth, no stains (ref_33).
      Garrett (gpatch.json = the approved stubble; skin2's dressed-shot pipeline, HEAD=sk2_g6): g15 vs skin2's g14,
      beard - cheek dL -21.2 vs -19.6, fine 2.49 vs 1.70 (grainier, darker by 1.6). NOTE: on the cmp's photo crop the
      same measure gives dL -7.7: our Garrett's beard zone is far darker relative to his cheek than his photo's, before
      and after this round (approved values kept; flag for Joe).
  (2) LIP BORDER: no change needed by measure. 10-90 % width at face scale: ours 1.1-1.5 mm (everyday/evening), refs
      ref_36 1.7-2.5, ref_38 1.6-2.1, ref_13 0.9-1.5, ref_09 0.9-1.8, Tess's photo 1.4-2.3; close-up 1.3-1.9 mm. Pale
      ring: the lit render shows +3..+6 L under the LOWER lip (natural/everyday), but on the albedo (look_skin flat)
      it is -2.6..+0.3: shading (no shadow under the lower lip on these heads), not paint.
  (3) WING: skin2's chain started on the upper lid 3 mm above the corner (gap 2.0 mm from the lash line, edge +30 deg
      off the lash line: the thorn). Now skin_makeup.wing_root finds the canthus on the head mesh (the most lateral
      front skin within 1.5 mm of the eyeball; lm_eye_outer sat 2.7 mm outside it on one head, 1.5 mm inside on Tess),
      the wing = a FILLED triangle: lower edge from the canthus along the lower lash line's outer third extended
      (C - lm_lid_lower_out), upper edge back to the upper lash line's outer third, a fan of 9 tapering spot chains
      (5 left skin slivers; spots <= 40 % of their radius apart: no beads at the tip). Measured: gap 0 (0.47 with the
      strict L < 20 liner threshold: lashes cross the path), edge angle 7 deg off the lash line (skin2: 15-30).
  (4) PALE ARC: found by look_skin flat (albedo; layer= can't show pre layers): the lid colour covered only the lowest
      ~1.3 mm of the lid and the crease colour was a thin line 6 mm up, the bare lid between = the pale arc; plus the
      shimmer finish (specular .55, roughness .32) made the lid's convex top a silvery band. Now the lid colour covers
      lash line -> crease (points 0.3-0.5 ch, radii 0.42-0.72 chm), the crease colour is wider and blurred (0.04 io),
      shimmer = specular .38, roughness .42. arc_e lid band: 26.1 (skin2's evening) -> 8.6, below the same head with no
      eyeshadow (10.2, the lid's own shading). Also: foundation's brow subtraction and makeup_brows used the landmark brow
      zone, a bare trapezoid above Tess's lowered brows; they follow the moved brow's picture now (ctx["brow_area"]).
  (5) FRECKLES: spread already in the refs' range (specks' sd L 1.7-2.8 vs 1.2-3.1, sd a .5-.7 vs .5-1.9, sd b 1.0-1.4 vs
      .6-1.6, size and flatness alike); the PROFILE was off: a sun cut at N.sun 0.05 left 0.01 of the peak on the outer
      cheek (refs 0.1-0.9) and the cheek gaussian was narrow. Now lit = ramp(N.sun, -0.3, 0.55), cheek gaussian wider:
      dense = bridge 1.0, upper cheek .83, mid .52, outer .08, forehead .46, chin .08 (refs: peak bridge/upper cheek in
      5/5, outer .11-.92). Outer cheek still at the refs' low end.
  Tess: sk3_04 approved (skin2's td3) vs now: unchanged but for the freckles' layout. Tests: test_skin_marks
  test_patchy_is_missing_hair_and_freckles_fade_out; the fade-band test compares the shadow blurred 1.5 mm (it has grain).
  5th blind read (skin2's prompt, sheets sk3_01..05, scratch /tmp/claude-1000/blindread5): stubble clean 2, 5 o'clock
  3, short 3, designer 2, heavy 2, patchy 3, salt & pepper 1; freckles 3/3/3/3, moles 2; makeup natural 3, everyday 2,
  evening 1; Garrett before 2 / now 2; Tess approved 3 / now 3 (identical). Its points, against the measures:
  - AGREES with measure / new: salt & pepper shows no white (grey_color #aaa39a at .85 over L~53 skin is only ~+14 L:
    ref_28's white hairs are the brightest thing on the jaw) -> next: brighter, more opaque white hairs; designer /
    heavy read as a light-tan decal with a hard cheek line and a ruled neckline (trim 1 / 0.25 edges) -> soften and
    darken; "clean" already reads as 1-day (dL -6.2, dots) -> the clean style's shave shadow should lose the resolvable
    dots (draw no stubs / dashes for length < 0.1 mm); evening eyeshadow reads as a grey-brown "bruise" cloud in 3/4,
    no outer V; Garrett "now" = sparse dark hairs over peach skin, no grey cast (consistent with the dL -21 vs the
    photo's -7.7 above: his stubble is too dark and too brown; the approved values are Joe's, ask before changing).
  - CONTRADICTS the measures (left as measured): freckle layout "even, not sun-driven" (frk_m: bridge 1.0 / upper
    cheek .83 / mid .52 / outer .08 = the refs' shape); lip "halo past the edge" (albedo ring <= +0.3, widths at or
    below every ref's); the wing "detached, no taper from the lash line" (gap 0, edge 7 deg off the lash line; it IS a
    sharp vector edge: soften its outline, soft 0.3 -> ~0.6, is a fair next step).
  Not this thread's but repeated in every read: no pores / micro-texture or tonal variation in the base skin (redness
  at nostrils and folds, darker under-eyes) on Tess and Garrett.
- skin3 round 2 (2026-10-10; coordinator: Joe never locked Garrett's values, "way better, but the edges are too hard
  and don't follow the face": match his photo; then white hairs, designer/heavy edges, clean, evening bruise, pores).
  Sheets `skin_renders/sk3_11..15` (stubble, freckles, looks, Tess, Garrett). New scratch: ph.py (the photo cropped
  to shot.py's frame: out/photo_front_big.png, pixel-aligned with <tag>_front_big.png; shot.py now also writes it),
  cov_m.py (beard coverage photo vs render: MODE=chroma maps beard as lost chroma (the photo is an upscaled ~300 px
  concept: its fine texture is noise, so texture coverage (MODE=texture) fails on it), regions cheek-at-nose-wing /
  beside mouth / moustache / neck + edge steepness), hue_e.py (lid colour vs the product, FROM=3.5 past the lashes),
  g16-19.json + g0.json (Garrett patches; g0 = no stubble: the shading baseline), round7-9.sh, sheets2.sh.
  GARRETT: his beard-minus-cheek dL -21 was mostly SHADING: the same render with no stubble (g0) gives -11.0 (the
  photo's own -7.6 includes its flatter light). Stubble's own increment: approved g15 -10.2 L; g16 -5.4; g17 -2.1;
  g18 -0.6 (too faint by eye); chosen g19 (grey .55, cheeks .9, cheek_line .12, neckline .3, shadow .3, colour
  #3a342f): -3.1 L / -1.1 a / -1.5 b, the box under the nose gone (code: the moustache-to-cheek transition 9 mm ->
  ~2 cm untrimmed, kl in beard_density.region), up the cheeks and down the neck, soft. NOT written into anyone's
  spec: recommended values = /mnt/data/hifipushie/skin3/g19.json. His photo's grey cast (da -5.5) is still stronger
  than ours (-1.1 over g0): our cast doesn't carry chroma (see round 1's chroma note); his render's cheek is L 72 vs
  the photo's 58 (base skin / light, not this thread).
  1) Salt & pepper: white hairs #d9d4cb at .95 (was #aaa39a .85, ~+14 L): texture over bare 0.84 -> 1.6 (ref_28 +2.4),
     dL increment -6.8.
  2) Designer / heavy edges: the boundaries' half-width io*(0.06 + 0.26*(1-trim)) (was 0.015 + 0.3): a trimmed line
     fades over ~4 mm instead of ~1 mm (exact, from the formula; the face-view texture measure can't see the cheek
     line). By eye the decal edge is softer; the hairs still read light tan in the key light (hair colour/specular
     untouched: next).
  3) Clean: style shadow .4 -> .22, stubs' darkness scaled by length / 0.3 mm (floor .15): increment -6.2 -> -3.3 L,
     texture +1.0 -> +0.4 (no resolvable dots).
  4) Evening: product #8c5e46 / crease #6a4030 / outer #3e2418 (was #7a5a4e / #45302a / #241815: near-neutral darks
     greyed the lid below the bare skin's chroma = "bruise"). Lid (3.5-9 mm above the lashes, lit): Lab 46.7/11.1/15.9,
     chroma 19.4 vs bare 18.3 (was 14.4: greyer than skin), hue 55 deg vs the product's 53 (was 56 vs 47 with a greyer
     product); darkening fades 20 -> 3 L over 8-12 mm (one band = the liner at 2 mm). Lid band 6.2 (bare 9.5). Wing
     angle 0.3 deg off the lash line.
  5) PORES / colour variation: NOT achieved by measure. Tess, L detail at 0.35 / 0.7 / 1.4 mm: photo .39/.43/.47, ours
     .18/.16/.16 before, .18/.16/.16 after pores 0.45 -> 0.65 opacity, darker cavity tint, 0.3 mm deep, bigger pits
     (0.12-0.28 mm, skin_swatch VERSION 16) and fine mottling .2/.16 -> .32/.26. The close-up shows more pores; the
     face view (0.25 mm/px) doesn't move: the pores are sub-pixel and the mottle layers are per VERTEX (_pre noise), so
     nothing per pixel lives at 1-3 mm. Next: a per-pixel unique mottle / pore map like the freckle map (skin_marks
     sphere map: blotches 1-3 mm, pore clusters on nose and medial cheeks, redness at nostrils / folds) — the tests
     forbid procedural noise per pixel, a baked map is allowed. Garrett's photo can't gate pores (upscaled concept).
  6th blind read (same prompt, sheets sk3_11..15, /tmp/claude-1000/blindread6): stubble clean 3, 5 o'clock 2, short 2,
  designer 2, heavy 2, patchy 2, salt & pepper 2; freckles 3/3/2.5/2.5, moles 2; looks 3/2/1.5; Garrett "now" (g19)
  reads CLEAN-SHAVEN from the front and in 3/4 (worse than g15 "before", "closer in kind"); Tess a modest improvement,
  but the upper lip / chin pore specks "read as dirt". Read honestly:
  - Garrett g19 overshot: gating on the photo's total beard-minus-cheek dL (-7.6) was wrong, his render's shading alone
    is -11 (g0). The right gate is the increment over g0 against the photo's increment over ITS bare skin, which the
    concept doesn't have; by eye the photo sits between g16 and g15 (grey haze, flecks on the chin, nothing above the
    cheek line: cheek_line .12 put dots beside the nose). Next: g16's shadow .45, cheek_line 0, grey .5, keep the
    soft transition; gate by a blind A/B vs the photo, not dL.
  - Salt & pepper white hairs now "uniform bright chalk scratches": too white/opaque; real grey is translucent, slightly
    yellow, densest on chin/jaw: #d9d4cb .95 -> ~#c8c0b2 .8 and more grey on the chin than the cheeks.
  - Designer / heavy: this reader wants a CRISP trimmed line again (ref_29) but a grainy, see-through field: the decal
    complaint is the solid tan pad, not the edge. Revert soft to ~2 mm for trim 1 and fix the hairs' colour / coverage.
  - Repeated across reads, unfixed: hairs with no root darkening in close-ups; freckles flat discs, even confetti (the
    measures disagree on layout); wing "detached" (measures: gap 0, 0.3 deg); lips flat fill, no lower-lip highlight.
  - The ranked #1 again: base skin (pores, T-zone sheen, colour zones). Round 2 showed it needs a per-pixel map.
  HANDOVER (skin3 -> next agent, 2026-10-10): branch worktree-agent-adc9408fe374b85f8 (main has round 1 up to cc5e94d;
  round 2 = 2fa2528 + this note). Scripts and gates in /mnt/data/hifipushie/skin3 (see the round 1 / 2 entries;
  sheets2.sh builds sk3_11..15). Priorities from the reads + measures: (1) base skin as a per-pixel unique map (mottle
  1-3 mm, pore clusters nose/medial cheek, redness nostrils/folds, under-eye cool, T-zone roughness) gated by
  fskinm's bands vs Tess's photo (.39/.43/.47 at 0.35/0.7/1.4 mm; ours .18/.16/.16); (2) Garrett per the note above;
  (3) grey hairs translucent; (4) trimmed lines crisp, beard field grainy not a pad; (5) evening/everyday shadow along
  the crease (the everyday lid still has a sooty band mid-lid). Tess's natural look must stay as sk3_14 "now" or better.
- skin4 (2026-10-10, "skin4" agent, branch worktree-agent-a2deeee2ab87a2d79; sheets `skin_renders/sk4_01..04` (01/02 =
  round 1, 03/04 = round 2; blind letters, keys in /mnt/data/hifipushie/skin4/out/sheets_key*.json: Tess A = new,
  B = before; Garrett r1 X g25 / Y g15 / Z g19, r2 X g26 / Y g15 / Z g25). Scratch /mnt/data/hifipushie/skin4/: run.sh
  (this worktree), run_main.sh (main's src: before renders), base0.sh <tag> (Tess = ts_h13 + t5.json as sk4_t0: look_skin
  face/cheek/mouth + fskinm vs her photo), lk2.py (face at 2x, Lanczos to 768: a camera's sharpness), refbands.py (skinm's
  L/a bands on any photos), zvar.py (zone colour variance: std of Lab per skinm box after a 1.5 mm high-pass), genmap.py,
  exp.py + nm.py (export_asset of the head stage, baked normal / colour on vs off), gshot.sh / g3q.sh (HEAD=sk2_g6),
  g20..26.json, sheets.py / sheets2.py.
  (1) BASE SKIN MAP. skin_marks.base_map: a unique map on the head's own surface (the freckle map's sphere wrap, 0.08 mm
      a pixel, ~4000 x 2400, ~1 min, cached by key + BASE_VERSION). Built per PIXEL from 3D noise at each pixel's surface
      point (R interpolated over the head mesh's outward vertices, `_pixel_points`), so scales are true mm anywhere:
      r = relief (pores as pits from a KD-tree of pores scattered by zone: PORE_ZONES nose 240/cm2 r .16 mm, medial
      cheek 170 / .13, forehead 120 / .09, chin 150 / .11, rest 60 / .07, few off the face's front, none on lips, few on
      lids; a 0.8 mm cell net of skin lines; a 0.6-1.2 mm undulation), g = blood (0.5 even; 2.5 / 1.3 / 0.8 mm fbm,
      stronger mid-face, threads beside the alae, calm round the mouth: blotches there read as a beard shadow on a
      woman), b = melanin (3.5 / 1.4 mm). Fades to even toward the map's edges (no seam) and, for relief, where the
      wrap's ray grazes the surface (nose sides: one pixel spans a strip there, streaks); colour only half-fades there.
      Layers (skin._build, faces only, per pixel): mottle_map_red (g up), mottle_map_pigment (b up), mottle_map_light
      (g or b down, one layer: the complexion's mean kept; pigment one way only tanned Tess), micro_map (height, NOT
      _detail: baked into the export's unique normal map). Strength x sqrt(variation) / sqrt(detail): tuned on Tess
      (.6 / .45); linear, Garrett's 1.3 / 1.8 read as sandpaper. Tiling micro_pores' cavity tint 0.65 -> 0.3 on faces
      with the map (its dark dots were the "dirt"). Shader budget test 37 -> 41 (4 layers). skin.VERSION 5.
      Measures (Tess, face view 0.254 mm/px, before -> after): L bands 0.35 / 0.7 / 1.4 mm .18/.155/.16 -> .23/.27/.30
      (photo .39/.43/.47); a .15/.09/.10 -> .18/.17/.19 (photo .18/.10/.15); zone colours within 1 L of before; zone
      variance (< 3 mm, mean over 6 boxes) L .78 -> 1.07 (photo 1.07), a .37 -> .62 (photo .45), b .42 -> .52 (.48).
      FINDINGS: (a) the 0.35 mm band is capped by the renderer: EEVEE's 1.5 px filter + mipmaps; the same scene at 2x
      then Lanczos gives .33/.34/.34. (b) Real CC photos (ref_19/34/35/42/07) read L .3-1.0 and a .16-.6 at these bands:
      Tess's photo is a smooth one; matching it is a floor, not a ceiling. (c) Relief barely moves L under the soft
      light (relief 0 vs .15 mm: +.02) but dominates under a key light (Garrett's shot): tune relief on a key-lit view.
      (d) The first "lost sheen" scare was the albedo mottle hiding the highlight's gradient, not the specular; and
      look_skin's stage cache is keyed on spec + code, not env vars: env toggles need a code change to resync.
      (e) The map's cache key does not see code edits: bump BASE_VERSION on every change (I lost 8 iterations to it).
      EXPORT: head stage at 2048 (0.31 mm/texel) bakes it: base colour changes on 77 % of texels; normal map tilt from
      the relief rms 0.7 deg, p99 3.3 deg (earlier depth; now lower on Tess). Pores (sub-texel) don't survive at 2048;
      the tiling detail maps still ship them. 4096 OOM-killed at the 12 G cap: CAP=20G.
  (2) GARRETT stubble, A/B by eye vs his concept (front through the photo camera) and the blind reads: g20 (skin3's
      g16-like: shadow .45, cheek_line 0, grey .5) and g24 (.7) too faint; g25 (.9, length 2.5 mm, grey .55) rank 3 of 3;
      g26 (shadow 1.0, grey .55, length 2.5 mm, cheeks .9, cheek_line 0, neckline .3, #3a342f) ranked 1st in the round 2
      read (2.5 vs g15's 2.0: "Y's density, X's softness"). Recommended = /mnt/data/hifipushie/skin4/g26.json, not
      written into any spec.
  (3) GREY HAIRS: share weighted to the chin (0.6 + 0.8 x a chin gaussian, normalised so the overall share = grey),
      colour #c8c0b2 at .8 (was #d9d4cb .95). skin_marks.VERSION 22. Read: no longer chalky but now hardly visible: "small
      bright slightly shiny specks over a grey-blue shadow of the dark roots" is what's missing (the cast has no chroma:
      skin3's round 1 note).
  Blind reads (fresh agents, sheet + refs ref_19/34/25/28): round 1 (sk4_01/02): Tess new 2.5 vs before 3 ("uniform
  dark speckle from scalp to chin = dirt", "pale band beside the nose's wing", blotchy cheek); Garrett g25 2, g15 2.5,
  g19 1.5. Fixed: pores off the face's front, finest mottle (0.5-0.7 mm) dropped, colour -15 %, half-fade at grazing.
  Round 2 (sk4_03/04): Tess new 2.5 vs before 2 (before = "plastic, waxy, pockmark decal"; new = closer to her photo,
  but "grey-brown haze, sallow"); the nose-side seam is in BOTH (not the map's: lighting / zones); Garrett g26 1st.
  HANDOVER (skin4 -> next): (1) pores still read as dark dots: drop the tiling micro_pores' colour on faces (shading
  only, 0.3 -> 0) and test; then a key-lit Tess view for relief; (2) colour zoning per the reads (pink nose tip /
  nostrils / chin, cooler under-eye, less peach; Garrett olive-ruddy, darker lower face) - the zone layers exist,
  their strength reads low; (3) lips read as lipstick decals on both heads (flat fill, hard border) in every read;
  (4) grey stubble: bright specular tips + a chroma'd grey-blue root shadow; (5) the nose-side seam on Tess.

## Very fair skin (2026-10-10, "jw2" agent)
- The tone model could not make very fair skin: melanin 0 stopped at ITA 52 deg (L* 71, b* 16.2: Chardon / Del Bino's
  "light"; "very light" is ITA > 55, about L* 70, b* 12), undertone -1 only traded b* for a darker L*. The floor was
  the epidermis's melanosome fraction (MELANIN[0] 1.3%) and the fixed carotene baseline. Now (skin.melanosomes,
  FAIR_TO 0.14 = F2): below F2 the melanosome fraction falls geometrically to MELANIN_FAIR 0.5% and the carotene
  baseline to 0.4x; F2 and darker unchanged to the last digit. melanin 0: ITA 60, F1 59, F2 47, F3 37, F4 18, F5 -14,
  F6 -50 (the bins the literature gives per type). Marks that ADD pigment (melanin x > 1: freckles, moles, age spots)
  count on the unlowered curve: on the first version Tess's freckles nearly vanished (ts_t28 look_skin before / after).
  test_skin::test_tone checks the bins, F3 unchanged and freckle contrast on F1.
- A fair face read "tan" dressed for three reasons, only one of them the albedo: the stage's high key light put the
  sides / jaw in warm subsurface shadow (a frontal soft key fixed most of it), and the photo had a slight COOL cast
  (sclera R/B 0.93): corrected for it, a fair forehead's R/B matched the render's (1.52) within noise. The rendered
  hue followed the albedo's (render cheek hue 46 vs albedo 47 deg): the shader adds no orange.

## Lips (gnmdetail2, 2026-10-10; scratch /mnt/data/hifipushie/gnmdetail2: albedo.py (the stage's albedo splatted through
## the front camera, lip reads on it), liplayers.py (layers painting at the lip probes), liptone.py, reflips.py, sweep.sh)
- The LOWER LIP was painted too red and too dark: lips_lower (blood 7, melanin 0.9 x, thinner epidermis) read +7 a* and
  -6 L against the upper lip in the albedo (Tess: albedo lower da 14.1 / dL -19.6, upper 9.6 / -14.8). Photos
  (skin_refs, 13 faces + Tess; rd.lips da / dL of each lip against the skin beside it): the lower lip's a* contrast is
  the upper's +1 (median; spread -9..+16) and it reads lighter by ~16 L, of which the light from above gives ~13 on
  our heads (grey clay under the same light). Now skin.LOWER_LIP = melanin 0.72 x the lips', blood 3.8, the lips'
  epidermis, oxygenation 0.66 (skin VERSION 6): Tess albedo lower da 10.2 / dL -13.9; dressed lo_mid da 16.6 -> 11.7
  (photo 9.1), dL -9.4 -> -3.8 (photo +0.4). Across tones (liptone.py, Fitzpatrick 1-6) the lower lip is 5-8 L lighter
  than the upper and da -2..+4: on dark skin lighter and pinker than the upper (ref_03 / ref_04 have that). Before /
  after on F4 hu_m30 and F6 hu_w28d (look_skin mouth + face, out/ls_hu_*.jpg): subtle, less hot-pink on F4.
- The PALE HALO under the lower lip (+3..+5 L just outside the border, dressed) is SHADING, not paint: the albedo has
  none (lip_border's rim measures <= +0.3 L 0.5-3 mm out); the clay under the same light shows the skin under the
  lower border lit +5..+8 over the skin 2 mm further down (the lower lip's underside / the labiomental turn faces up
  on these heads). Left as found; skin2 found the same (look_skin flat: -2.6..+0.3).
- Tools: albedo reads need the skin's own base colour (skin.part_base), not the part default grey.
- Garrett (b2_G15, dressed, sheet human_renders/g2_09): lower lip da 11.5 -> 9.1, dL +0.8 -> +5.6 (lighter, less
  orange; his photo's lower lip is pale pink, lighter than the upper): reads closer; maybe a touch pale on him.

## skinread (2026-10-11, "skinread" agent, branch worktree-agent-a7223453932fa0a32; Joe: "Can we have the reference photos
## inform the dressing more than they do?" ... "project the reference, then drive the procedural params from the reference:
## albedo, location of stubble, makeup, extras around eyes and mouth, etc." Scratch DURABLE in /mnt/data/hifipushie/skinread:
## run.sh <script> (capped, this worktree's src, main's workspace), fd.sh (one read + fit against a truth, cached frames),
## fv.sh / fvall.sh (the fold cases), out/; scripts in spikes/skinread; sheets human_renders/sr_*)
STATE / NEXT (skinread, 2026-10-12): BUILT and wired (skin_read.py, skin_folds.py, MCP skin_from_reference, guide, tests). PASS: zone tints, lip colour, freckles (incl. absence), beard zones (order), brow density + placement, the broad folds (nasolabial, tear trough, mentolabial, marionette: 10-11 of 12 hits, 0 of 13 false on a smooth head, readable at 1.1 mm a pixel), "ours has more" 12 of 12. FAIL / OFF: sclera anchor, the tone's lightness, iris colour on photographs, fine-line fields, the lid crease on Tess's photographs; the null under a warm light drifts 1.6 a* / 3.4 b* and lays two false mouth folds on a stubbled head. Applied to copies sr_garrett / sr_tess (sheets sr_01 / sr_02): better hue, beard, lips, brows, freckles; NOT yet the person (Garrett orange and bag-less in the render, Tess a little tanned, lips flat). NEXT: an exposure anchor, folds as GEOMETRY from the same read, a step detector, the lid crease from the lash line ("What to do next").

Scope addition (Joe, 2026-10-11, through the coordinator), a first-class part of the task: "these reference hints are where
we will pick up aging cues that gnm can't model, garrets baggy eyes, garret and tesses eyelid folds, the extras around the
mouth. we need a system to look for them and parameters and layers for such things."

### The instrument (src/hifipushie/skin_read.py)
- Per fitted reference view: P = the picture cropped to the block-in's box (512 px), R = OUR dressed head (its own
  stage `_sr_<model>`: skin_look's head crop, bare skin + eyes, no hair) through the same camera under the picture's own
  fitted light (blockin.photo_lighting on a "Standard" view transform, exposure 0: linear ratios), and A = our albedo at
  every pixel's SURFACE POINT (likeness.render's depth pass -> world points), evaluated in Python. The picture's albedo is
  T = A x P / R (the ratio image). Stage sync 20-45 s, a shot 7 s, masks at 390k points 20 s.
- The Python albedo (`Albedo`: the paint layers' masks through paint.layer_mask on a surface.Points of the pixels, the
  "_pre" layers composited first, then the rest, linear colour, as the scene does) against Blender's flat render through
  the same camera on Tess: mean difference 0.02 / 0.01 / 0.01 Lab, rms 2.0 / 0.34 / 0.38 (pixel-level fine detail). Masks
  are cached per mask definition, so a change of colours and strengths costs 0.09 s at 160k points: this is the fit's
  forward model. The ruler mesh's silhouette and the stage's agree to IoU 0.9995 (same world frame: no registration step).
- Trust per pixel: the model's skin facing its camera (cos 0.35 .. 0.7), the picture's parser (faceparse, MediaPipe
  multiclass) saying skin and not hair, neither picture nor render clipped, the ratio within 4x of the view's median.
- Views are weighed by how WHITE their light is against ours (the log chroma of P / R along the normal: `light_spread`;
  weight 1 / (1 + (spread / 0.06)^2)): a painter's warm lamp + blue room would otherwise be read as skin zones.

### Anchors: what failed
- SCLERA as the exposure / white-balance anchor FAILS on photographs (Tess): the picture's sclera reads 0.45-0.9 x ours
  against the skin (view by view: 0.449 / 0.52 / 0.897 in red) and its colour differs view to view (r/b 1.12, 0.89,
  0.86); anchored on it her plain skin came out at L 93. Real scleras sit under lid and lash shadow and are never paper
  white. Left in as anchor="sclera", never chosen by "auto".
- A plain NEUTRAL BACKDROP (the parser's background, Lab chroma < 7, even) gives the white balance only. Holding the
  plain skin's LIGHTNESS to ours while fitting the tone then FAILS: the target is "the truth, brightened", which the
  pigment model cannot make with the true parameters, and the solve bent every darkening layer to compensate (under-eye
  0, eyelids 0, lower_cool at its bound, beard 0). FIX: the exposure is a free factor of the solve (held to 1 with sigma
  0.5 in log): the tone comes from the skin's chromaticity. chi2 on the synthetic case 1271 -> 29 (was 2682 -> 1085).
- No anchor (a painted backdrop): the tone is NOT READ; all else is read against the face's own plain skin.

### The colour fit (skin_read.fit)
- One bounded least squares over the read's regions (the skin's zones, the two lips, the beard's six zones): model =
  the Python albedo's region means for a candidate spec["skin"], target = ours + the read's d (weighted median of the
  per-pixel Lab difference). Sigma 6 / 0.8 / 0.8 Lab (lightness carries the shading we do not model: see the lids
  below) + each region's spread across views; a weak pull to the start (least change); restarts (the trust-region solve
  stops on its step tolerance in this curved, bounded problem) and a start a little inside the bounds (a parameter
  starting ON a bound never left it: flush, periorbital and a prototype beard all stayed at 0 in the first runs).
- Parameters: tone melanin / blood / undertone (only with an anchor), zones forehead_yellow / midface_red / nose_red /
  perioral_red / lower_cool, features.flush, zones under_eye / eyelids / periorbital, lips blood / melanin and the
  lower lip's own, and the beard as SIX SCALES on the stubble layers' opacity (one per beard zone; a prototype
  "short" beard when the face has none and skin.sex is not female), turned into hair.stubble.zones + density afterwards.
- NEW GENERAL CONTROLS (no per-subject layers): `skin.zones.perioral_red` (the layer existed, its strength could not be
  set), `skin.zones.periorbital` (the socket's darker, browner skin; default 0: off), `skin.lips.lower` {blood, melanin}
  (x the lips'), `skin.hair.stubble.zones` {moustache, chin, soul_patch, jaw, cheeks, neck: 0..1.5}
  (skin_marks.beard_zones: a soft partition of the beard area; all 1 = the old map, same cache key), `skin.folds` (below).
- Brows: colour = ours x (picture's / ours) at the band's darkest third, density from the band's mean darkness;
  placement / thickness by blockin_brows.fit (already there). Freckles: dark specks per cm2 (blobs of the 0.35-1.3 mm
  band 3.5 % darker than their surround, 0.4-12 mm2) on cheeks / nose / forehead, picture against our render, scaled by
  what the freckle layer adds to the same count on our albedo. Iris: picture / ours against the sclera beside it.
- PARAMETERS ARE NOT UNIQUE where layers overlap (mid-face red vs flush; under_eye vs eyelids vs periorbital; melanin
  vs undertone under a free exposure): judge the fit by the ALBEDO it gives, region by region, not by each number.

### Folds: what the shape model does not make (src/hifipushie/skin_folds.py; the checklist in skin_read.fold_read)
- CHECKLIST (general, from the head's own landmarks, in interocular units; FOLDS table): nasolabial, marionette,
  mouth_corner, mentolabial, tear_trough (its roll = the eye bag), lid_fold (the upper lid's crease as a line),
  glabella; + fields of fine lines (forehead, crow's feet, under the eye, round the lips). Each fold: a path over the
  skin (control points WALKED over the surface from their landmark in 0.5 mm steps: an offset alone floats off the
  skin, and seating it along the wrap's ray or onto the nearest vertex put the lid fold 7 mm up one lid and across the
  other eye's corner), a width, a search distance, and the picture resolution it needs (nasolabial, mentolabial,
  tear_trough 1.6 mm a pixel; marionette 1.4; mouth_corner, glabella 0.7; lid_fold 0.5; fine lines 0.4-0.45).
- DETECTOR: at stations every mm along the path, the luminance profile across it (log, blurred to 0.3 x the fold's
  width, averaged over 5 mm along) in the PICTURE and in OUR render through the same camera and light; the valley =
  the darkest point within the search against the lower of its two rims. Rejected: a minimum on the window's edge
  (the slope of something beside the path), a "valley" deeper than 0.42 (a feature's own edge: mouth corner, nostril,
  lashes), stations not on trusted skin or foreshortened. PRESENT = the picture's valley over ours by 0.02 + 70 % of
  ours, along >= 30 % of the visible stations; "ours has more" the other way. Output per side: present / absent / as
  ours, strength (picture, ours), share, extent along the path, placement (mm across the path at 9 stations),
  confidence, the views that saw it. Below its resolution a fold answers "cannot tell". A fold is LAID only from
  confidence 0.5; amount = (picture - ours) / FOLD_REF (what an amount-1 fold of ours reads, calibrated below).
  The valley of the RATIO image was tried first and dropped: beside a fold of ours its roll and shade make false valleys.
- LAYERS: skin.folds -> ONE unique map on the head (skin_marks' sphere wrap, 0.1 mm a pixel; r groove, g roll, b tint +
  shade), three layers: folds_groove (painted height down, up to 0.9 mm x the fold's share), folds_roll (height up: the
  bag over a tear trough, the cheek's pad over a nasolabial fold), folds_shade (multiply). The measured shift / extent /
  per-side amount are the fold's parameters; nasolabial / marionette / glabella replace skin.wrinkles' landmark lines
  (set to 0) when the read lays them. Drawn to the LINE (10 samples a station: measured to the nearest station a lid's
  fold came out as dashes). Without skin.folds the skin's layers are unchanged.
- HONEST LIMITS: painted height shades like a groove seen from the front; no silhouette, nothing in profile, wrong
  under raking light. A heavy bag, hooding, a jowl = geometry (block_in_step {"hooding"}, sculpt). The upper lid's
  SHADE (Tess: 15 L darker than ours under the same light in all three views) is mostly geometry too (eye depth, brow
  overhang, lashes): the read says so in a NOTE and the tints stop at their bounds.

### Validation: folds (spikes/skinread/foldval.py; Tess's head and cameras, the truth photographed under a light the
### reader does not know: another direction, warm cast 1 / 0.93 / 0.84, -0.35 EV, a grey backdrop lit by it; truth =
### folds1.json: all seven folds at amount 1 with known shifts / extents / one side off, forehead + crow's feet lines 1)
| case | result |
|---|---|
| A: picture WITH folds, ours smooth (hits) | 11 of 12 present fold-sides read PRESENT (nasolabial L R, marionette L, mouth_corner L R, mentolabial, tear_trough L R, lid_fold L, glabella L R); the side that was off (marionette R) read absent. MISSED: lid_fold R (read along 26 % of its path, under the 30 % it needs; the bilateral rule then gives it the left's). Earlier settings missed tear_trough L (truth: the inner 60 % only) or mouth_corner R instead: 10-11 of 12 across four runs. |
| B: both smooth (false positives; a young head must say absent) | 0 of 13 fold-sides present. Before the "70 % over ours" rule the mentolabial groove read present (the chin's own shading under another light: picture 0.18 vs ours 0.11-0.13). |
| C: picture smooth, ours WITH folds | 12 of 12 read "ours has more"; one fit round takes the amounts from 1.0 to 0.0-0.8 (the second round goes on). |
| N: the null (the same folds in both) | 0 present, 0 "ours has more", the fit changes nothing. |
| D: case A with the pictures at 1.12 mm a pixel (Garrett's scale) | nasolabial L R, marionette L, mentolabial, tear_trough L R PRESENT (as at full size: 0.20 / 0.14 / 0.10 / 0.23 / 0.17 / 0.19); mouth_corner, lid_fold, glabella and all fine lines: "cannot tell". |
- AMOUNT from one round (truth 1.0 each; FOLD_REF as shipped): nasolabial 0.83, mouth_corner 0.97, mentolabial 1.06,
  tear_trough 0.72, lid_fold 0.84, glabella 0.96 (0.75 on its weaker side); marionette's valley is 0.04-0.11 (its tint is
  light) and falls under the confidence to be laid at the final shade. Within about +-30 %. The null N shows why not
  better: the SAME fold reads 0.39 in the picture and 0.23 in ours when the lights differ (a valley's depth follows the
  light's direction): strength is good to a third, presence and side are solid.
- PLACEMENT (mm across the path; truth in brackets): nasolabial L +2.5..+3.5 at its upper half (+2), R -2.0..-2.8 (-2),
  lid_fold L +1.25..+1.5 where read (+1..+1.5), R +0.25 (0), glabella 0.25-0.75 (0). BIASED for the horizontal
  grooves under a light from above: mentolabial +2.0..+2.75 (0), tear_trough +1.5..+3.0 (0): the darkest line sits on
  the wall the light misses, not in the groove. The second round moves a fold of ours by the distance between the
  picture's valley and OURS (same bias in both, so it cancels; `move`, applied from 1.5 mm): built, NOT validated.
- EXTENT: tear_trough R read [0.07, 0.96] (full), L (truth [0, 0.6]) [0, 0.57] where it was read at all.
- FINE-LINE FIELDS FAIL their null: energy of the 0.25-0.9 mm band over the cheek's reads +0.65 (forehead) / +1.11
  (crow's feet) for lines 1 against none, but +0.47 / +0.68 for the SAME lines under the other light. Reported in the
  read, never fitted (FIELD_FIT = False). On Tess's photographs every zone reads +1.2..+2.2 over ours: that is the
  photograph's skin texture and noise against our smoother render, not wrinkles.

### Validation: colour (spikes/skinread/val.py; the same head and unknown light; truth_a.json = deliberately unusual: tone
### melanin 0.30 / blood 0.55 / undertone 0.4, zones forehead 1.8, midface 0.3, nose 2.0, perioral 0.2, lower_cool 0.4,
### under_eye 2.2, eyelids 0.5, periorbital 1.2, flush 0.6, freckles 0.5, lips blood 0.5 / melanin 2.5, lower 1.6 / 0.7, a
### goatee-like beard (cheeks 0.15, neck 0.3, jaw 0.6), dark dense brows; the start = skin defaults; two rounds)
- ALBEDO error against the truth, rms over 19 regions (Lab): start 12.0 / 2.67 / 3.81 -> fitted 6.4 / 1.03 / 2.69. Hue
  and saturation come back to about 1 a* / 2.7 b*; LIGHTNESS does not (the fitted tone ran 9 L dark: melanin 0.54 for
  0.30): the tone's lightness is not a read (EXPOSURE's note in the code: free it ran dark everywhere; held it stays
  within ~3 L on the two subjects but not on this far truth; a hard hold on the base tone bent the zones instead).
- Per parameter (truth | fitted): nose_red 2.0 | 2.03, lips.blood 0.5 | 0.49, lips.lower.blood 1.6 | 1.62, midface_red
  0.3 | 0.54, perioral_red 0.2 | 0.01, flush 0.6 | 0.87, forehead_yellow 1.8 | 2.15, freckles 0.5 | 0.70 (0.54 after
  the first round), brows density 1.2 | 1.17. FAILED as numbers: undertone 0.4 | 0.0 (melanin took the yellow),
  lower_cool 0.4 | 1.99, under_eye 2.2 | 0.50, eyelids 0.5 | 0.01, periorbital 1.2 | 0.0, lips.melanin 2.5 | 1.49,
  lower.melanin 0.7 | 1.19: the overlapping eye-zone layers and the melanin / undertone / exposure trio are not
  identifiable one by one (the regions' colours they make are: see the albedo error).
- BEARD ZONES: with the free exposure (first design) moustache 0.91, chin 0.90, soul 1.0, jaw 0.66, cheeks 0.0, neck 0.0
  for a truth of 1 / 1 / 1 / 0.6 / 0.15 / 0.3: right. With the exposure held and the zones held even (what ships):
  moustache 0.67, chin 1.0, soul 0.87, jaw 0.10, cheeks 0.0, neck 0.0: the ORDER is right, the jaw under-read. A beard
  was ADDED from none in both. Partial pass.
- THE NULL (start = the truth's own parameters, the pictures under the other, WARM light): NOT clean. The read's chi2
  starts at 439 (should be ~0) and the fit moves undertone 0.4 -> 1.0 (its bound), forehead_yellow 1.8 -> 0.79, lower
  face and lips a little; albedo drift 2.0 / 1.6 / 3.4 Lab rms. The backdrop's white balance leaves about a third of a
  strong cast (1 / 0.93 / 0.84) on the skin. And on this STUBBLED head two folds were laid that are not there
  (marionette R 0.84, mentolabial 0.69: the valley's depth changes with the light where the beard thins round the
  mouth); the smooth young head (case B) had none. So: under a light near ours the reads hold; under a strongly
  coloured or differently aimed light expect about 2 a* / 3 b* of false tone and false mouth folds on a bearded face.
- IRIS: right on the synthetic pictures (#3b2a1a truth, #523e2a fitted from #5a3a1e), WRONG on Tess's photographs
  (grey-green -> orange-brown): off by default ("eyeballs" is opt-in). SCLERA: not fitted.

### Applied (copies; the accepted models are untouched): sr_garrett = garrett_a1, sr_tess = tess_a1; sheets
### human_renders/sr_01_garrett_skin_from_reference.png, sr_02_tess_skin_from_reference.png (reference | after | before |
### references projected per view; eye / eye / mouth close-ups; unseen angles under the studio light); reports
### /mnt/data/hifipushie/skinread/out/go_sr_*.txt, skins go_sr_*.json; overlay of the folds' paths on a picture: foldover.py)
- TESS (three photographs, 0.25-0.27 mm a pixel, backdrop anchor in all three): freckles 0.08 -> 0 (specks / cm2:
  picture 2.1 / 1.8 / 1.6, ours 4.2 / 3.8 / 3.8); tone F1 -> melanin 0.23, blood ~0, undertone -0.51 (her skin read 2-3.5
  a* less red than ours everywhere: ours was pink); midface_red, flush, forehead_yellow, perioral_red -> ~0; lips melanin
  2.8 -> 8.9, lower.melanin 0.4 (upper lip 10.7 L darker and 5 b* browner than ours: now a darker, browner upper lip
  over a lighter lower one); brows #55453a -> #403224, density 0.6 -> 1.29, band placed by brow_read (middle line rms
  2.3 -> 0.6 mm); under_eye / eyelids at their bounds (2.5), periorbital 0.65. Folds: lid_fold read on her left only
  (valley 0.205, 43 % of the path, confidence 0.62), the right takes it (bilateral rule); mouth_corner L 0.54;
  nasolabial, tear_trough, marionette, glabella absent (right for a 22-year-old).
  JUDGED on the sheet: closer than before on freckles (gone), skin hue (olive, not pink), lip colour (two-tone, muted),
  brow weight and placement. STILL WRONG: the skin renders darker / more tanned than hers (lightness is not read, and
  the tone went 3 L down); lips are still a flat fill with a hard border; the LID FOLD is a faint short arc above her
  real crease, not her crease (her fold lies ~2 mm over the lashes, at the edge of what the path's search reaches on
  this head: counted as a FAIL on the real photographs although it passes on synthetic ones); her eye region's depth
  is shade our head does not cast (the read's NOTE: lids 15 L darker than ours); brows a little heavy.
- GARRETT (two paintings, 1.13 / 1.33 mm a pixel; the front one anchors, the desk portrait's lamp + blue room gets
  weight 0.29-0.37 and no anchor): tone melanin 0.04 -> 0.13, undertone -0.4 -> +0.55 (cheek b* 14.5 -> 22.4 on the sheet,
  the reference 20.9; a* 9.9 -> 11.5, reference 12.5); beard: chin 0.45, soul 0.76, jaw 0.84, cheeks 0.53, neck 0.04
  (the old even mask read 6-9 L too dark on chin / soul patch: chin now 6.6 L under the cheek, the reference 4.8, before
  14.5); midface_red 0.45 -> 1.3, nose_red 1.7, lower_cool 2.0 (bound), under_eye 1.63, eyelids ~0; brows density 1.12 +
  placement (colour NOT read at this resolution); lips blood 2.7, melanin 0.24. Folds: tear_trough L and R PRESENT
  (valley 0.13 each, confidence 0.83 / 0.74) -> amount 0.94; nasolabial R 1.17 (L not found), marionette R 1.16;
  "NOT raised" on nasolabial R and both troughs in round 2 (laid, and our render still shows < 1/3 of what that amount
  should read under the fitted light); lid_fold, glabella, mouth_corner, fine lines, freckles, iris: "cannot tell".
  JUDGED on the sheet: the beard no longer reads as a dark mask and the skin's hue measures right. STILL WRONG, bluntly:
  he looks ORANGE (the head renders ~12 L darker than the picture before and after, and the right chroma at a lower
  lightness reads as a tan); the bags are DETECTED but barely show (painted relief under a flat frontal light; they
  are geometry); the nasolabial fold came out on one side only, as a streak (his left fold is a lit / shaded STEP in the
  painting, not a valley: the detector does not see steps), and reads as a smear from the low angle; lips are still a
  flat pink fill, the upper lip 11 L lighter than his; the mottle at variation 1.3 reads blotchy on the new tone.
  Net: an improvement in the lower face and hue, not yet "him".
- Unseen angles (the last rows): no seams, nothing baked: it is the ordinary procedural skin.

### What to do next (in the order I would)
1. LIGHTNESS: give the read an exposure anchor. A grey card is not in a reference; what is: the picture's own WHITE
   things with known albedo (teeth, a shirt collar, paper) or the user's word ("fair / medium / dark": Fitzpatrick as an
   input, the fit then holds the tone's L hard and only tints). Until then tone L is a manual setting.
2. BAGS / FOLDS AS GEOMETRY: the read's path + extent + strength are exactly what a sculpt layer needs; the block-in has
   no bag / nasolabial move. Either a `folds` displacement on the one-mesh (true vertex displacement at the eye region's
   0.5 mm mesh) or GNM expression-like local moves. Painted height is not enough under frontal light (measured: laid
   amount 0.94 reads < 1/3 of its calibration).
3. STEP DETECTOR for side-lit folds (nasolabial under a lamp): an edge across the path with the right polarity for the
   fitted light's direction, beside the valley detector.
4. LID CREASE on photographs: search from the LASH LINE up (the picture's own lash line through eye_ruler / lidfold.read_lid,
   which already reads fold height per column), not from the model's lid; lay it with skin.folds.lid_fold's shift.
5. LIPS: the vermilion needs a gradient and a soft border (the fill is flat whatever its colour); a read of the lip's
   own L profile (darker seam, lighter centre) could drive lip_seam / lip_sheen.
6. The NULL's cast: calibrate the reader's own light colour by rendering a grey card in the stage (LIGHT_WHITE is a
   guess) and re-run val.py mode=null; false mouth folds on stubble: read folds on the stubble-free render pair.
7. tests/test_toolsets.py fails on main for another reason (block_in_solve is in no toolset): not mine, not fixed here.

## skinfolds (2026-10-12, "skinfolds" agent, branch worktree-agent-a50baa552dfb299b5; continues skinread. Joe agreed to four
## steps: folds and bags as GEOMETRY (measurement-driven, general parameters, no hand sculpting), an exposure anchor for
## skin lightness, lips with a gradient, a step detector + the lid crease from the lash line. Scratch DURABLE in
## /mnt/data/hifipushie/skinfolds: run.sh <script> (capped, this worktree's src, main's workspace), fv.sh <tag> <truth>
## <start> [k=v] (foldval), clay2.sh, patch*.py (how the code got here), out/; scripts in spikes/skinfolds; sheets sf_*)
STATE / NEXT (skinfolds, 2026-10-12): BUILT + validated (folds as geometry round trip 10 of 12, 0 false; lightness prior inside its bound); on the subjects an improvement, not a likeness (Garrett: one bag of two, folds unplaced; Tess: a lid fold at last, tone still tanned). Full state and NEXT: "### Status" at the end of this section.

Joe (2026-10-11): "these reference hints are where we will pick up aging cues that gnm can't model, garrett's baggy
eyes, garrett and tess's eyelid folds, the extras around the mouth. we need a system to look for them and parameters
and layers for such things." Agreed 2026-10-12: bags and folds may be real displacement on top of the shape model as
long as it is driven by measurement and general parameters. (This supersedes, for these soft-tissue features only,
the 2026-10-10 "never a geometry layer" / "we shouldn't really ever use our 'fix' [lidfold]" decisions: GNM still owns
the head's shape; base.head.fold (lidfold.py) stays unused.)

### 1. Folds as geometry (src/hifipushie/skin_folds.py `prims`, sdf modifier kind "tissue")
- WHERE THE DISPLACEMENT ENTERS: the skin part's FIELD, as "modify" primitives after everything else of that part
  (spec._compile; the place base.head.fold's lidfold modifiers already used). Not the GNM vertices (the template's
  cheek quads are 3-5 mm: a 3 mm groove cannot live there, and the IMLS kernel would smooth it) and not a Blender
  displacement (the export and the reader would not see it). In the field it is meshed by every consumer at its own
  resolution: the head stage (1 mm, 0.5 mm in the eye and mouth boxes), store.build, look close-ups, the export's
  high poly.
- `spec.geometry` used to drop all of spec["skin"]; it now keeps `spec["tissue"] = skin_folds.geometry_key(skin)`
  ({"folds": validated options, "part", "v"}) ONLY when a fold has an amount and skin.fold_relief is not "paint". No
  folds: no key, no primitive, the same build key and prim fingerprints as before (tested): no BUILD_VERSION bump
  needed, nothing existing re-meshes; models WITH skin.folds (only sr_* so far) rebuild because their key changes.
- One primitive per fold and side: the path's stations refined to 0.5 mm, per sample point / normal / across /
  along; the field moved by a PROFILE of the signed distance across the line (`profile`): a groove (depth G, the
  fold's width as FWHM; where the fold has a roll the wall on the other side is 2.2 x wider: a step, not a channel),
  a roll rising from the groove's own line (smoothstep shoulder x a Gaussian peaking r0 out: lidfold's finding that a
  symmetric bump half fills the groove), a platform on the minus side (the lid). Smooth along the line (normalised
  Gaussian over the nearest samples, as sdf.mod_fold), relief eased in over 4 mm at each end of the extent, the roll
  swelling toward the fold's middle (a bag is a crescent). RELIEF (mm at amount 1): nasolabial 0.6 deep / pad 1.3
  (5 mm out, sigma 3.4), marionette 0.5 / 0.6, mouth_corner 0.3, mentolabial 0.8, tear_trough 0.6 / bag 1.4 (5.5 mm up,
  sigma 2.8), lid_fold 0.6 / roll 0.5 / platform 0.15, glabella 0.35. New per-fold key `depth` (x), `roll` now 0..3.
- KEEP-OUTS: (a) the displacement fades to nothing between 3.2 and 1.2 mm from the lid margins (the opening's eight
  landmarks as a closed line per eye) and from the lips (vermilion borders, seam, and two lines through each lip's
  body): tested, the field at those lines is unchanged to 1e-5 m. (b) where a fold pushes the skin IN it is clamped
  0.4 mm outside each eyeball (head["eyes"], head["eye_r"]): min(new, max(old, distance to the ball)).
- PATHS, the first bug: they are now seated on the fold-free field (`field_surface`: the part's primitives without the
  tissue ones; the same surface for geometry, paint map and reader, so nothing chases its own displacement). Seating
  by the field's CLOSEST POINT put the lid's landmarks on the lid's INSIDE and walked the tear trough round the
  socket (ball clearance -2.4 mm; the groove vanished into the eyeball clamp, the bag's roll never decayed). Now a
  path's control points are landmark + offset in the HEAD's own frame (right / front / up from the landmarks: a posed
  head carries its folds) and seated where a ray from in front first meets the skin (the visible skin).
  lid_fold's path got five control points along the upper margin's own landmarks (three cut across the corners into
  the opening); tear_trough's five follow the orbit's rim down and UP again to the outer corner (three ran on down
  and out: the bag was a box with a cut end).
- Fast loop: spikes/skinfolds/clay.py ray-marches the field itself as clay (no mesh, no Blender; 30-50 s a box,
  frontal | raking side | raking above); section.py prints the displacement really made across each path (mm).
  Read off the field on Tess (amount 1): nasolabial -0.60 at the line, +1.08 at 4-5 mm; tear trough -0.60, bag +1.40
  at 5-6 mm falling to 0 at the lid; lid crease -0.60 / roll +0.50.
- Colour: with geometry on, the fold map keeps only `folds_shade` (tint line + soft shade); folds_groove / folds_roll
  (painted height) exist only with fold_relief "paint".
- First dressed look (out/shots_sf_t0_all1.png: Tess's head, all seven at amount 1): the bags are plainly there under
  the frontal photo light, folds and lid crease under frontal and raking light and in 3/4. Blunt: at amount 1 the
  whole set on a 22-year-old reads as a tired 50; the nasolabial + marionette + mouth_corner meet in a busy knot at
  the mouth's corner; glabella lines are two straight nicks.
- THE LID'S CREASE needed its own occlusion: at amount 1 the geometric crease (0.6 mm) was a faint line in the dressed
  render (read_lid darkness 0.05-0.13 on the validation pictures; Tess's photographed fold line reads 0.31-0.38): a
  rasteriser has no skin-on-skin shadow at 0.5 mm. Now: lid crease 0.85 mm deep, roll 0.6, and with geometry on the
  fold map's r channel carries the crease's OCCLUSION (lid 1.0, glabella 0.45, mouth corner 0.4, nasolabial 0.35,
  marionette 0.25; 0.6 x the groove's width) for a dark multiply layer `folds_crease` ([0.42, 0.30, 0.28]).

### 2. The lightness anchor (skin_read.context / fit; `skin_from_reference(tone=...)`)
- A picture gives exposure x albedo. Order: (1) the PRIOR = the model's stated skin.tone (or `tone=` a Fitzpatrick
  type / skin.tone keys, written to the model before the first read); (2) a KNOWN WHITE in the picture (`_white`: the
  parser's figure that is neither skin nor hair, under the chin, bright (sRGB > 0.35, L* > 62), neutral (chroma < 9),
  250+ px; albedo taken as 0.8 and lit as the face: INFERRED); a grey backdrop gives the white balance only; the sclera
  is never used (skinread: 0.45-0.9 x).
- In the fit: the exposure is a free factor (sigma 0.6 log; with a white: centred on the white's, sigma 0.15) and the
  plain skin's albedo L* (PLAIN zones, the forward model) is held to the prior's with sigma 1.0 L* (white: 4.0). After
  the solve a HARD BOUND: if the plain skin left the prior by more than 3 L* (white: 8), the tone's move is scaled
  back (bisection on the share of the move) and the reply says so. Later rounds keep the FIRST round's prior L (else
  3 L a round). The reply states anchor, plain L* before -> after, bound, exposure.
- Garrett (prior = garrett_a1's tone, melanin 0.04): plain L* 66.78 -> 66.55 / 66.77 / 66.78 over three rounds;
  skinread had taken it to melanin 0.13 ("orange", ~12 L under the picture). Tess (prior F1): 73.23 -> 73.20 / 73.19.
  Neither picture set has a white the detector accepts (Garrett's shirt is not in the head crop as a neutral).

### 3. Lips (skin.py, VERSION 7)
- Gradient (`lips.gradient`, 0..2.5, default 1): `lip_inner` (a wide soft line along the seam: darker, more venous),
  `lip_corners`, `lip_body` (the lower lip's lighter middle), all inside the vermilion. Border (`lips.border`, mm,
  default 1.5; the lower lip's 1.3 x): the outline's own soft edge (was 0.96 mm for both: a cut-out fill).
- WHY THE LIPS WERE "STUCK" on Garrett (the read: upper lip 14 L darker than ours at +4 a* / +3 b*; three fits left
  11 L): (a) lips.melanin is x the TONE's melanin: on a very fair tone (0.04) even the bound, 9, is little pigment;
  (b) lips.blood saturates at ~3 (the blood fraction caps at 0.5); (c) the lip layers' opacity is 0.85 - 0.2 x masc: a
  third of a man's lip is his skin whatever the parameters say. With L weighted under chroma the fit took the redder,
  LIGHTER lip. Now: lips.melanin's bound 30, lower.melanin down to 0.1, and `lips.strength` (0.2..2, x the layers'
  opacity) as a fitted parameter. Tried and dropped: `lips.venous` (oxygenation 0.62 -> 0.25 moved a lip 2 L and took
  6 a* off: not a lever).
- NOT read: the gradient and the border (no sub-region read of a lip at these resolutions): set by eye.

### 4. Step detector, lid crease from the lash line (skin_read._fold_view, _lid_read)
- STEP: per station, window means of log luminance either side of a centre c (windows max(width, 2 mm), gap 0.25 x
  width), plus minus minus, of the DIFFERENTIAL profile (picture - ours), signed by the fitted light: -sign(l . across)
  (with the light from the plus side the steep wall under the roll is in shade). History of making it honest:
  v1 (the largest signed step within the search) fired on EVERYTHING on Garrett's paintings (92-100 % of every path,
  the line jumping +-4 mm station to station): the max over a window is positive for noise. v2: the step counts only
  OVER the largest step of the other sign, the picture alone must step that way too, the line must be smooth (1 mm
  rms about its median-filtered course) and run 8+ mm. Null B then still had 3 false (mentolabial 0.14, both tear
  troughs 0.10-0.11 per unit of cross light: our fitted light standing in for theirs), and Tess's photographs gave
  both tear troughs at +5.0 mm = the search window's edge (her lower lid's margin). v3 (shipped): only folds that ARE
  steps (those with a roll), STEP_MIN 0.3 per unit cross light (real amount-1 folds: 0.3-0.7), no step within 1.5 mm
  of the window's edge, runs of 10+ mm, and a fold read by its step alone is laid at most at amount 1.
  Synthetic lamp case (truth lit from low on the figure's right): with the folds as geometry the VALLEY detector
  already finds both nasolabial folds (0.20 / 0.22): the step is needed for paintings, where there is no valley.
- COARSE PICTURES (PLACE_MM 0.7): above 0.7 mm a pixel a fold's place across its path is not read (shift / extent /
  move dropped; laid whole on its landmark path): on Garrett's paintings (1.1-1.3 mm) the shifts were noise (+-5 mm)
  and round 2's "move" ran to -8 mm. Shifts that are read are now a parabola through the stations (a fold's line is
  smooth), inside the search. Confidence's share term saturates at 50 % of the path (was 70 %: Garrett's left tear
  trough, valley 0.20 along 31 %, fell to 0.45 and was never laid).
- LID FROM THE LASH LINE: lidfold.read_lid on the picture (the detector's lid line as the lashes, the strongest valley
  1.2-8.5 mm over it per column, 5 columns) in the most frontal view at 0.5 mm a pixel or finer; shift = the picture's
  height over ITS lashes - the nominal path's height over the same line. Tess: line at 4.55-4.8 mm (L) / 3.95-5.1 (R)
  over her lashes, darkness 0.31-0.38 in every column of both eyes; the nominal path sits at 3.0-3.6 -> shift +1.0..
  +1.8 mm: her fold is HIGHER than the nominal path (skinread's read along the path found a faint arc; it could not
  see a line 1.5 mm outside its own valley window of 2 mm). On the synthetic pictures the lash-line read is poor
  (our rendered crease is faint; 2 of 5 columns land on the brow's shadow without the 8.5 mm reach): there the path's
  valley / step read gives presence and strength and the lash line only places it.
- LID PRIOR: when the pictures cannot resolve a lid at all (Garrett: 1.1 mm a pixel) the fold is laid from norms and
  flagged INFERRED in the reply (amount 0.6, platform show women 3.3 / men 2.0 mm over the lashes, hooding by age).
- Later changes to section 1 (after the first dressed looks and Garrett's sheet): the tear trough's path moved UP to
  the lid-cheek junction (0.175 x the pupils' distance under the lid, ~10 mm; at 0.215 Garrett's painted troughs sat on
  the reader's window edge), the bag 4.6 mm over it (sigma 2.4); nasolabial 0.4 deep at 4.5 mm wide, marionette 0.35
  (at 0.6 / 0.5 they were incised lines with a pit where each began beside the mouth); relief eased in over 7 mm.
- A second tone bound, COLOUR: the plain skin's a*b* may move 5 from the prior's on a backdrop's white balance (10
  with a white). A backdrop "neutral within 7" may be 7 of real colour: Garrett's painted backdrop read his skin
  +9 b*; exposed like the picture that head was 5 b* too yellow (the "orange" of sr_01). The solve wanted +6.4 b*, held
  to +5.0. Bisection now runs between the PRIOR tone and the solved one in every round.
- THE SHEETS WERE UNDEREXPOSED: under the fitted "photo light" our renders sit ~10 L under their reference (Garrett's
  cheek: reference L 68.0 a 12.3 b 20.8; a1 59.2 / 9.9 / 14.5; sr_garrett 56.1 / 11.7 / 22.9), and the same a*b* at a
  lower L reads as a tan. The read is in ALBEDO (levelled: exposure is not observable), so this is the render's
  exposure, not the tone. sf_* sheets expose the photo-light tiles of all three models by one factor per view (the
  reference's face luminance over AFTER's: Garrett x 1.27, Tess x 1.36 / 1.44 / 2.20) and say so in the title.

### Validation (spikes/skinfolds/foldval.py, toneval.py; Tess's head and cameras; truth pictures under a light the reader
### does not know: other direction, warm 1 / 0.93 / 0.84, -0.35 EV, grey backdrop; logs /mnt/data/hifipushie/skinfolds/out/fv_*.log)
- FOLDS, ROUND TRIP (case A3: all seven at amount 1 as GEOMETRY with known shifts / extents / one side off -> pictures
  -> read -> skin.folds -> render -> read again, 2 rounds; sheet human_renders/sf_03_fold_validation_roundtrip.png, truth
  | read back under the photo light and a raking light): 10 HITS of 12, 2 MISSES (both lid folds), 0 FALSE; the side
  that was off (marionette R) read absent. Strength on the hits: mean +0.10, rms 0.31 (1.50 1.28 1.50 1.50 0.84 0.96
  0.81 0.81 1.00 0.80 for a truth of 1.0: three at the 1.5 cap). Shift (median mm, truth in brackets): nasolabial L
  +2.8 (+2.0), R -2.3 (-2.0), marionette +0.4 (0), mouth corner +0.1 / +0.5 (0), glabella +0.2 (0); BIASED as before
  for grooves under a light from above: mentolabial +3.0 (0), tear trough R +1.5 (0).
  On the sheet the read-back head shows the same bags, nasolabial folds, marionette and glabella lines as the truth
  under both lights and in 3/4; the lids' creases are missing.
- THE LID FOLD IS NOT READ BACK ON SYNTHETIC PICTURES (0 of 2). Our rendered crease is too faint for either reader
  (lash-line darkness 0.05-0.13 where a line needs 0.08 in 3+ columns; the path's valley 0.06). On Tess's
  PHOTOGRAPHS the same reader finds her fold in all 10 columns of both eyes at darkness 0.21-0.38. So: validated on
  real pictures for presence and height, unvalidated for strength (it goes to the 1.5 cap and says so).
- NULL (case B2, a smooth young head against smooth pictures, final code): 0 of 13 fold-sides present, no
  displacement laid. (The first step detector gave 3 false here and 3 on Tess: see section 4.)
- LAMP (case AL, the truth lit low from the figure's right, read only): 11 of 12 present (both nasolabial folds by
  their valleys, 0.20 / 0.22).
- Calibration at amount 1 (case A, valley over ours): nasolabial 0.18 / 0.08 by side, marionette 0.07, mouth corner
  0.10 / 0.09, mentolabial 0.28, tear trough 0.18 / 0.23, glabella 0.15 / 0.11 -> FOLD_REF (nasolabial and marionette
  lowered to 0.11 / 0.055 with their shallower grooves: a guess, their strengths came back +0.3..+0.5).
- LIGHTNESS (toneval.py: truth = Fitzpatrick f with its own hue (blood 0.6, undertone +0.35), photographed at two
  exposures; start = the same type's default hue; base tone Lab truth | prior -> fitted; "plain" = the bound's metric):
  | truth | EV | plain skin L* | base tone error before (L a b) | after |
  |---|---|---|---|---|
  | F2 | -0.7 | 65.91 -> 64.45 | +4.5 -4.2 -3.2 | +1.5 -2.4 -2.1 |
  | F3.5 | -0.7 | 59.15 -> 58.31 | +3.9 -3.8 -1.6 | +1.5 -1.5 -1.8 |
  | F5 | -0.7 | 41.39 -> 41.28 | +2.3 -2.1 +0.9 | +1.6 -0.5 -0.3 |
  | F5 | +0.4 | 41.39 -> 41.28 | +2.3 -2.1 +0.9 | +1.6 -0.5 -0.3 |
  | F3.5, prior F2.5 (wrong) | +0.4 | 64.28 -> 62.80 | +9.2 -4.7 -5.1 | +6.2 -3.1 -3.9 |
  At +0.4 EV: F2 +1.5 -2.5 -2.0 (plain 65.72 -> 64.29), F3.5 +1.7 -1.7 -1.8 (59.15 -> 58.30), F5 as in the table. The
  result does not depend on the exposure (all three tones within 0.2 Lab between -0.7 and +0.4 EV). The plain skin never left the prior by more than 1.5 L* (bound 3.0); the base tone itself (skin.tone_rgb, without
  zones) moved up to 3.1 L. Hue and saturation come about half way (the solve sends undertone to 0 and blood to
  ~0.5 for a truth of 0.35 / 0.6: the melanin / undertone trade skinread found). A WRONG prior stays wrong by design
  (one type too light: 9.2 -> 6.2 L).
- THE WHITE ANCHOR IS NOT VALIDATED: the synthetic collar (a white band painted under the chin) was not accepted by
  `_white` (the run fell back to the prior), and neither subject's pictures have one in the head crop. The code path
  exists and is bounded (8 L*); treat it as untested.
- Tests: tests/test_skin_read.py (test_folds_are_geometry: no folds -> no key / no primitive; groove and pad of the
  asked size where asked, nothing 9-14 mm away, the off side untouched; keep-out lines unchanged to 1e-5 m; the
  eyeball clamp; the step profile; test_step_and_tone_bound: amounts by how a fold was read), test_skin.py,
  test_toolsets.py pass.

### What the game asset keeps (spikes/skinfolds/export_check.py: sf_garrett's head stage through export_asset, 20 k
### triangles, 2048 atlas; out/export_check.log)
- GEOMETRY: the low poly is cut from the built surface, folds included: body 15.9 k triangles, distance to the exact
  (folded) field p50 / p99 / max 0.04 / 0.4 / 0.98 mm. On a head-only asset at this budget the bags and folds (0.4-2 mm)
  are in the triangles. NORMAL / HEIGHT / AO maps are projected from the exact field ("height range +-1.74 mm"), so
  whatever the triangles miss is in the maps. A whole character at 15 k triangles has a few thousand on the face: there
  expect the broad forms (bag, cheek pad) in geometry and the creases in the normal map. NOT measured: the full-body
  export, the wrap topology (parts.body.topology "wrap": the template's loops are fitted to the same field, so it
  follows it at its own density), face shapes (they displace the exported vertices, so a fold rides the lid or the
  lip; a blink does not close the crease). The Cycles preview of the GLB failed in my script (an Image, not bytes):
  the asset's look was not judged.
- Cost: a head stage sync 80-180 s with or without folds; no folds = no primitive (tested).

### Applied (copies: sf_garrett from garrett_a1, sf_tess from tess_a1; garrett_a1 / tess_a1 / sr_* untouched; reports
### /mnt/data/hifipushie/skinfolds/out/go_sf_*.txt; sheets human_renders/sf_01_garrett_folds_tone_lips.png,
### sf_02_tess_folds_tone_lips.png: REFERENCE | AFTER | BEFORE (sr_*) | BEFORE THAT (a1) | references projected per view,
### eye / eye / mouth under the photo light and a raking light, unseen angles under another light)
- GARRETT (two paintings, 1.12 / 1.33 mm a pixel; 2 rounds). Tone: prior held (plain L* 66.78 -> 66.74 -> 68.2;
  colour +5.0 b* of a wanted +6.4, +5.7 in round 2 before the bisection was fixed): melanin 0.007, blood 0.19,
  undertone +0.61. Lips: blood 2.0, melanin 12.4, strength 1.54, lower 0.47 / 0.12. Folds: nasolabial 1.31 (R by its
  valley 0.15 along 53 %; L 1.0 by its STEP 0.70 per unit cross light along 41 %: the painting's lit / shaded step, no
  valley), marionette 1.03 (R 0.55), tear trough 0.435 on his right (valley 0.098 along 58 %), 0.16 on his left
  (INFERRED from the pair: its own valley reads along 10 %), lid fold 0.6 / roll 1.47 from norms (INFERRED: 1.1 mm
  a pixel cannot show a lid). Placement: none read (coarse pictures): all on their landmark paths.
  JUDGED on sf_01, bluntly. BAGS: his right eye now has a real pouch with its trough, under the photo light and the
  raking light; his left barely. The painting has clear bags under BOTH eyes, larger than ours: half delivered. LID:
  a soft crease shows under raking light, hardly under the photo light; the painting's heavy hooded fold is not
  there. NASOLABIAL: both sides are form now and read from the front, 3/4 and low angle; they sit closer to the mouth
  and more upright than the painted ones (no placement at this resolution). MARIONETTE: a short nick at the lower
  corner of the mouth, reads as a scar: wrong. TONE: exposed like the reference the skin is a warm beige between a1's
  grey-pink and skinread's orange; still yellower than the painting. LIPS: dark upper, pale lower, a gradient into the
  seam: closer in structure than the flat fill; too saturated a red-brown, the border still reads drawn.
- TESS (three photographs, 0.25-0.27 mm a pixel; 2 rounds). Tone: prior held (73.23 -> 73.20); melanin 0.157, blood
  0.08, undertone +0.04. Lips: melanin 11.4, strength 1.16, lower 1.21 / 0.33. Folds: lid_fold 1.5 (its cap) placed
  from her lash line (her line at 4.4-5.1 mm over the lashes, the nominal path at 3.0-3.6: shift +1.0..+2.0 mm);
  mouth_corner L 0.40; nasolabial, marionette, tear trough, glabella absent (right for her age; the first step
  detector had laid a nasolabial fold and both tear troughs: false, see section 4).
  JUDGED on sf_02. LID: there is now a fold above each lid with a roll over it, at about her crease's height: the
  first version of her that has one. It is paler and thinner than her soft dark line, has a kink at the inner end and
  a break in the roll's middle under raking light (where the lid lies thinnest over the ball: the eyeball clamp stops
  the crease there). TONE: still a tan beside her pale neutral skin, as sr_tess: NOT fixed. The plain zones hold the
  prior's lightness, but the eye-zone and lower-face layers sit at their bounds (eyelids 2.5, under_eye 2.5,
  lower_cool 2.0) and melanin went 0.02 -> 0.16 with blood down: within the bounds, visibly darker and yellower. LIPS:
  two-tone with a gradient; the upper lip an orange-brown where hers is a muted brown-mauve.

### Status
STATE (skinfolds, 2026-10-12): BUILT and wired: skin.folds as geometry (field modifiers; keep-outs; eyeball clamp;
crease occlusion), the lightness prior + bounds (L 3, colour 5), lips gradient / border / strength, the step detector,
the lid crease from the lash line, coarse-picture rules, look_skin light "rake", guide, tests. VALIDATED: folds round
trip 10 of 12, 0 false, strength rms 0.31; null 0 of 13; lightness exposure-invariant and inside its bound on three
tones. NOT validated: the lid fold on synthetic pictures (0 of 2), the white anchor (never fired), the asset's look.
ON THE SUBJECTS: an improvement, not a likeness. Garrett: one bag of two, folds as form but unplaced, tone warmer
than the painting. Tess: a lid fold at last, tone still tanned, lips orange.
NEXT, in the order I would:
1. TESS'S TONE: the zone layers at their bounds darken and yellow the face while the "plain" zones hold the prior.
   Bound the WHOLE face's mean albedo to the prior (not PLAIN only), and look at why eyelids / under_eye / lower_cool
   run to their bounds on photographs (skinread's NOTE: lid shade that is geometry).
2. GARRETT NEEDS A CLOSER PICTURE. At 1.1 mm a pixel nothing is placed and a lid cannot be read; the bags' strength
   came out 0.44 / 0.16 where the painting shows ~1. With one 0.3 mm picture of the eyes everything here applies.
3. The lid: the eyeball clamp breaks the crease mid-lid at amount 1.5; the crease should thin, not stop (scale the
   depth by the lid's clearance along the path); and the lash-line read's strength needs a calibration at the
   picture's own resolution (ours is read at the 512 px crop, hers at 0.25 mm).
4. Marionette: start it lower and ease it in longer, or fold it into the nasolabial path's lower end; mouth-corner /
   nasolabial / marionette meet in a knot.
5. The white anchor: make `_white` fire on a real shirt (test pictures with a collar), then validate it.
6. Lip HUE: lips.melanin is brown; a muted mauve lip needs less chroma, not more pigment (a desaturating control, or
   read the lips' a*b* at full weight and their L from the seam / body profile).
7. Asset: run a full-body export with wrap topology + face shapes on sf_garrett and look at the GLB; fix
   export_check's preview.
