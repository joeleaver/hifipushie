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
