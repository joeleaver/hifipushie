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

## Very fair skin (2026-10-10)
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

## Skin feature tour (2026-10-12, coordinator; spikes/tour/skintour.py)
Joe on the feature tour (gnm_atlas.md "## Feature tour"): "I think this pattern will also really help you judge the
texture work, and also set up the textures." `spikes/tour/skintour.py <model>`: per feature and view ONE small image:
reference crop | the model dressed, same camera / crop / fitted light | 50 % overlay | references projected (the bar);
files /mnt/data/hifipushie/tour/<model>_skin/. Use it to JUDGE a dressing and to SET UP one (look at the reference
crop alone, list what the skin must carry there, then read / fit).
First look, sf_tess front (things the whole sheets hid):
- eyes: her brows are soft, thinner, tapered, with sparse hairs at the inner end; ours are a thick solid slab with a
  flat top edge, too brown and saturated. Her upper lid has a crease AND a dark lash line / shadow under it; ours has
  a pale crease line and no lash-line darkness. Our sclera is too white. Our skin is blotchy (mottled noise) where
  hers is even, and tan / orange where hers is pale neutral.
- mouth: her upper lip is a muted mauve-brown, the lower a pale pink with a soft highlight and fine vertical texture,
  soft borders, a dark line between the lips; ours: the upper lip a flat saturated orange-brown with a hard edge and
  too pointed a bow, the lower a flat peach, no highlight. Her nostrils are dark openings; ours are pale inside.
- BUG / caveat: the "references projected" column is NOT pure reference: our own brows and our upper-lip layer are
  drawn OVER the projection (the projected mouth tile has our orange upper lip). The bar column needs those layers
  off (or the projection above them) to be the bar.

## How others do the upper-lid fold (2026-10-12, coordinator; Joe asked for the literature)
Joe: "that dang fold carries so much expression and identity with it, yet requires a ton of triangles and driving, and
gnm and makehuman don't seem to support it, and I'm not sure game triangle budgets support it either."
- Parametric models are KNOWN to fail here: Petikam, Hewitt, Saleh, Baltrusaitis (Microsoft), "Eyelid Fold Consistency
  in Facial Modeling", SIGGRAPH Asia 2024 TC, arXiv 2410.13760. FLAME / BFM / their own models blur or miss hooded
  lids because scan registrations put the same fold on DIFFERENT edge loops, so the statistics average it away; models
  then lean on texture, which breaks blendshape / texture transfer. Their fix: the crease is ONE FIXED EDGE LOOP on
  every mesh (upper lid above, lid platform below; on a hooded eye the platform is tucked BEHIND the hood: real
  overlap), sharpened by a custom "pinch" BLENDSHAPE of the neighbouring loops with per-subject strength, and a
  HOODEDNESS measure along the lid (0 = brow line, 1 = lid margin, > 1 = skin hangs in front of the margin; varies
  nasal to temporal: lateral hooding with age, epicanthal fold nasally). Limits they state: one fold per lid.
- Capture: Bermano et al., "Detailed Spatio-Temporal Reconstruction of Eyelids", SIGGRAPH 2015 (Disney): the lid skin
  "is folded under while opening the eye"; they need a geometric deformation model as a prior + wrinkle detection
  because the folded skin is occluded. Wen et al. 2017: real-time eyelid tracking from semantic edges (excludes
  hooded lids).
- Artists (forum practice, Reallusion's and Roblox's topology guides): the crease is an edge loop placed on the
  subject's crease; model the lid HALF-CLOSED so the loops can serve both ends, then sculpt the open shape (skin
  tucked up under the fold: "a larger shape with its own volume", not a scratched line) and the closed shape
  (unfolded), plus an in-between corrective because the lid travels on an arc round the ball.
- Game rigs (MetaHuman's RigLogic docs): joints for the big motion + per-vertex corrective shapes at LOD0 + expression
  -driven wrinkle maps (a few normal / colour variants blended in the material by rig channels); lower LODs drop the
  shapes and keep maps. Lid-to-ball contact is hidden by an eye-occlusion shell and a tear-line mesh.
- WHAT IT MEANS FOR US: (1) the lid fold belongs in MESH space on a fixed loop of the head's own topology (GNM's lid
  rings), as a per-subject pinch / tuck shape with hoodedness along the lid as its parameters: NOT in the SDF field
  modifier (topology-blind: wobbles, rides the blink) and NOT in GNM's identity coefficients (forced: recipe A,
  |dc| 16-20). (2) Blink / wide = corrective shapes on the same vertices (fold unfolds on the blink). (3) The fine
  line and the far LODs = normal map + painted line. (4) Budget: two or three loops round each eye, of the order of a
  few hundred triangles at LOD0; cheap next to the alternative. Soft broad features (bags, nasolabial, chin pad)
  can stay in the field modifier, with expression gains.
- Topology check (same day; wireframes /mnt/data/hifipushie/tour/topo/eye.png, mouth_cheek.png, drawn without depth
  sorting: the eyeball and teeth show through): GNM's head is 17,821 vertices / 17,662 quads, an animation topology:
  closed concentric quad RINGS round each eye (gnm_fold.py: ring 0 = the lid margin, rows 0.5-0.7 mm apart at rings
  3-6 where the crease sits; gnm_fold.chains() = 7 radial chains x 13 rings up the lid) and a loop flow from the nose
  wing sweeping down round the mouth corner (the nasolabial flow), rings round the mouth. So both the lid fold and the
  nasolabial fold CAN be defined on GNM's own loops; no retopology needed at this level. (The game asset's topology is
  another question: the wrap template / decimation: what survives there is the export test's job.)
- PLAN agreed with Joe (2026-10-12; "it will really increase our quality if we get this right. We're not that far
  away from a MetaHuman competitor, in a different space"): TWO TRACKS. (A) the LID FOLD in mesh space: a per-subject
  pinch / tuck shape on a fixed ring of GNM's lid rings, parameters = crease height and HOODEDNESS along the lid
  (Microsoft's 0 = brow, 1 = margin, > 1 = in front), blink / wide correctives on the same vertices, the fine line in
  normal map + paint; the reads must produce those parameters. (B) the OTHER folds stay in the field layer and get
  EXPRESSION GAIN tables baked into the exported shapes: nasolabial first (tested on a smile), then marionette / jowl,
  bags; chin pad + notch static; crow's feet / forehead / glabella = expression-driven wrinkle normal maps, not
  geometry. Start both when skinfolds2 has reported.
- CORRECTION to the topology check above (Joe asked "was that the eyeball itself I saw?": yes): the first wireframes
  drew GNM's eyeballs and teeth over the skin (no depth sort, all components). Redrawn skin only, depth-sorted
  (/mnt/data/hifipushie/tour/topo/eye_skin.png, mouth_cheek_skin.png). GNM's mesh is 8 components: skin 12,466
  vertices, two eyeballs 1,440 each, 933 + 4 x ~386 (mouth interior / teeth / tongue). What the skin picture shows:
  concentric quad rings round the eye opening, packed tight for the first ~8 rings above the margin (the crease zone)
  then widening toward the brow, with poles at the inner and outer corners; rings round the mouth; the flow from the
  nose wing sweeping round the mouth corner. So the claim stands, now seen and not only read from gnm_fold.py.
- REQUIREMENT (Joe): the lid fold "by itself, really shouldn't affect any other part of the face". Track A's shape
  moves ONLY vertices of the lid rings out to a stated ring (falloff to exactly zero before the brow and before the
  lower lid's rings); brow, brow ridge, eye position and opening stay bit-identical; a test asserts zero displacement
  outside the region. (That locality is exactly what GNM's identity route could not give: its fold lowered the brow
  4-5 mm.)

## skinfolds2 (2026-10-12, "skinfolds2" agent, branch worktree-agent-a61eeaaaf7e7a7d1d; continues skinfolds on Joe's "keep
## going": Tess's tone, the lid crease, the mouth, Garrett within the paintings' limits, the export check. Scratch DURABLE
## in /mnt/data/hifipushie/skinfolds2: run.sh <script> (HEAVY: capped, one thread, this worktree's src, main's workspace),
## light.sh <script> (LIGHT: bin/slot), run_main.sh (a spike under MAIN's src: the sf_* BEFORE tiles), fv.sh, chain*.sh,
## patch*.py (how the code got here), out/; scripts in spikes/skinfolds2; copies sg_garrett / sg_tess; sheets sg_*)
STATE / NEXT (skinfolds2, 2026-10-12): BUILT + validated (shade is not pigment, whole-face bound, declared white, lid crease as one calibrated line, lips at the picture's lips, fold paths from anatomy, symmetry prior, folds under expression in the morph targets; folds round trip 11 of 12 with both lids, 0 false; lightness in bound on 3 tones x 2 EV). On the subjects: Tess no longer tan and her crease reads; Garrett has both bags; neither is a likeness (flat lips, pale sockets, lid placement, bags too small). The asset keeps a third of the nasolabial fold in triangles, the rest in maps; a crease's texture does not fade on a blink (needs an engine wrinkle blend). Full state and NEXT: "### Status (skinfolds2)" at the end of this section.

### 1. Tess's tone: what it was, measured (spikes/skinfolds2/cap.py, imgspace.py, shade.py, pr.py)
- THE SHEETS' -10 L WAS THE SHEET'S LIGHT, NOT THE ALBEDO. Per view, on the plain skin (P picture, R our render under
  the fitted light, A our albedo; linear luminance): Tess view 0 P/A 0.97, R/A 1.18; view 1 1.02 / 1.04; view 2 1.09 /
  0.67. Under the READER's light (Standard view, 0 EV) our render sits +6 L (view 0), +1 (view 1), -14 (view 2) from
  the picture. The sf_* sheets used the judging sheets' template (g3stage.FRONT_LIGHT: -0.55 EV, "Khronos PBR Neutral"):
  x 0.68 on top of that = the "~10 L under", then re-exposed tile by tile. blockin.photo_lighting keeps the face's
  front "as bright as the template lights it": a template's level is not the photographer's exposure. View 2 (the
  profile) is a LIGHT FIT fault on top: its key comes out from 15 deg BELOW (elevation -15, key 0.87, fill 1.55), our
  cheek is 1.6 x darker than hers there. Garrett: view 0 P/R 0.77 (ours 7.7 L lighter), view 1 (the desk painting,
  lamp + blue room) 0.38.
  FIX (the cause): `skin_read.photo_light(name, vi)` = the fitted light + "exposure" = the EV the last read MEASURED
  between our render and the picture on the plain skin (context stores {view: ev} beside the stage:
  `_sr_<name>/sr_exposure.json`; the read's text says it per view). look_skin(light="photo") uses it; the sg_* sheets
  render every model under it (one light, one EV per view for AFTER and BEFORE: like with like), no tile is re-exposed.
  NOT fixed: the profile view's light direction (blockin.lit_render's c0 + w.n on a profile): reported.
- LIKE WITH LIKE (out/pr_sg_tess.png: picture | a1's render x the plain skin's gain): a1 is PINKER than her (a* 10.9
  against 8.6 in image space, view 0), hers a warm light beige, with far more shading (jaw, under the cheekbone, the
  socket) than our head casts under the fitted light. So the read's direction (less red, a little more yellow) was
  right; what made sf_tess a tan was (a) the sheet's exposure, (b) SHADE PAINTED AS PIGMENT, (c) +1..3 b* of overshoot
  that the shade pulled in.
- SHADE AS PIGMENT, measured (image space = albedo space within ~1 Lab, so it is in the pictures, not the reader):
  against the plain skin her eyelid reads -15 L, temple -19, jaw -7.8, jowl -6.7, neck -10, mouth corner -6, each
  WARMER (b* +2.5..+5 on the jaw / neck). Regressing log(picture / ours) per channel on its luminance over all trusted
  skin (shade.py): slopes r 0.81-0.85, g 1.03, b 1.18-1.25 in every view, the same for the darker and the lighter
  half: the picture's darkening has ONE colour (bounce light off skin and scatter: red falls least). Melanin darkens
  along almost the same line, so a picture cannot tell shade from a tan: the PRIOR decides. The old fit gave it to
  pigment: melanin 0.02 -> 0.16, eyelids / under_eye 2.5 (bounds), lower_cool 1.9.
- BUILT (skin_read.fit):
  (a) SHADE: `shade_colour(c)` measures the exponents q per read (clipped 0.7..1.35; 1 1 1 when there is too little
  spread). Each region's target is the read with a shade s >= 0 taken out again along q (target x exp(s q)); s is
  solved inside every residual (7 Gauss-Newton steps per region, closed form), prior SHADE_SIGMA 1.5 log (free), 0.05
  on the PLAIN zones (the lit skin the exposure is levelled on) and on beard zones where a beard may be laid (its
  shadow IS a lightness), 0 on the lips. Reply: "SHADE, NOT PIGMENT: eyelid -12.5 L*, jaw -10.9 ..." with what to do
  if it is pigment after all.
  (b) WHOLE FACE: the mean albedo over every skin zone's trusted pixels (stubble layers skipped) is held to the
  prior's (soft, TONE_SIGMA; hard FACE_BOUND 3 L* / TONE_CHROMA in a*b*, inside the tone's bisection).
  (c) ZONES: no zone's (Lab - face Lab) may leave the prior's by more than ZONE_BOUND 4 L* / 5 a*b*; the zone / eye
  layers' move is bisected back toward the first round's start and the reply says which zone asked for what.
  (d) A MOVE MUST EARN ITS PLACE: after the solve every non-tone parameter is tried back at its start; if that costs
  the fit < PRUNE (0.25) it stays there. Tess's eyelids 2.5 / lower_cool 1.97 were INERT numbers (0.1 L of albedo:
  those layers multiply the tone's blood, which the fit had sent to its floor): now untouched.
  (e) PRIOR_TONE 6 x on melanin / blood / undertone (many triples make one colour). It does not stop Tess's blood
  going to ~0: tonegrid.py shows the tone model reaches her (73.4, 7.3, 16.0) only at melanin ~0.15, blood <= 0.1 (the
  slider's floor is 1 % haemoglobin, not none): a real "pale, not ruddy" corner, not a degeneracy.
  Fit time 75 s -> ~200 s a round (two albedo evaluations per residual + the prune pass).
- Tess, colour fit alone (fitc.py, cached frames): whole face Lab [73.4, 9.6, 14.8] -> [73.5, 7.3, 16.0]; plain L*
  73.23 -> 73.3; zones forehead_yellow 1 -> 0.03, perioral_red 1 -> 0.04, flush 0.3 -> 0.01, nose_red 0.75 -> 1.5;
  under_eye / eyelids / lower_cool / periorbital untouched; AFTER read: plain zones within 1 a*b* of the picture.

### 2. The white anchor (skin_read.white_patch / _white; `skin_from_reference(white=[...])`)
- WHY IT NEVER FIRED: the search ran inside the HEAD CROP (512 px round the face). A collar is under it. toneval's
  synthetic "collar" was a band at the bottom of the picture: outside the crop, and not clothing to the parser.
- NOW: (a) found in the WHOLE picture: the parser's cloth (or figure that is neither skin nor hair) under the chin's
  row, sRGB 0.35..0.97, 250+ px, the median of its lit 40 %; accepted when neutral (chroma < 9 after the backdrop's
  white balance), L* > 62, brighter than 1.1 x the lit skin (75th percentile) and no darker than 0.8 x a neutral
  backdrop; each refusal says why in the read. (b) DECLARED: white=[{"view", "box", "albedo"}] (the caller points at
  paper / a shirt / a wall). Skin albedo = albedo x (plain skin's 75th percentile) / white (lit against lit).
  With a white the plain zones carry no shade of their own and TONE_SIGMA_WHITE is 12 (the white leads, the 8 L*
  bound holds).
- A BACKDROP IS NOT AN EXPOSURE ANCHOR and is not used as one: skin albedo = backdrop albedo x (skin / backdrop) x
  (backdrop's light / face's light), two unknowns each good for a factor 2. It gives only "skin <= 0.9 x ratio when
  lit alike": for Tess <= L* 85. Said in the read.
- ON THE SUBJECTS: Garrett's shirt (the front painting) is a lilac-grey at L* 62: REFUSED ("the clothing under the
  face is not bright (L* 62): not a white"), which is right: taken as a 0.8 white it would have put his skin ~15 L
  too light. Tess: bare shoulders, no clothing. Neither subject has a white; validation is synthetic (below).

### 3. The lid's crease (skin_folds.py, skin_read._lid_read; calibration spikes/skinfolds2/lidcal.py)
- WHY IT WAS A PALE WELT WITH TWO TICKS (Joe: "that crease is still wobbly"), three separate faults:
  (a) THE DARK LINE WAS MEASURED IN 3D. The fold map's pixels lie on the surface WITH the relief, the line on the
  fold-free one; the crease's occlusion fell off with the 3D distance, so it vanished exactly where the fold stood
  highest (mid-lid) and survived only at the eased ends: "two detached tick marks". Now the distance is taken IN the
  skin (the height over the line left out), for every fold, and the colour eases in over END like the relief.
  (b) THE EYEBALL WAS A HARD STOP: mid-lid the lid lies thinnest over the ball, the groove was clamped to nothing
  there and the roll stood alone: a lit ridge. Now each sample's groove takes 85 % of the clearance there is
  (smoothed over 2 mm) and 60 % of the depth it lacks stands out BROAD AND LOW over the line (RELIEF "over": peak at
  2.2 mm, sigma 2.8, shoulder 1.8; a first version, 0.85 mm within a millimetre, was itself the welt). The clamp stays
  as the safety.
  (c) THE LINE FOLLOWED COLUMN NOISE: shift = (picture's height - nominal path's) per column, a parabola through 5
  points held flat past the outer columns: Tess's right lid got 2.8 / 1.1 / 2.6 mm. And it was laid 1:1 in skin
  millimetres although the lid leans back from the picture plane (0.4-0.6): a fold read 1.6 mm over our path came
  out 0.8 over it. Now: the picture's height over its lashes as a STRAIGHT LINE in the column (2 numbers), laid over
  OUR lash line (the upper lid's five landmarks through the same camera, a parabola) at every station between
  columns 0.2 and 0.8, divided by the lean; that shift as a quadratic in t, running out into the corners past the
  outer columns (x 0.25 at the ends: the first try extrapolated the quadratic: +6 mm, a hook). The path itself is
  smoothed (4 mm) after its last seating, in the map and the geometry alike.
- CALIBRATED TO THE PICTURE'S: lidfold.read_lid on OUR render at its full size (capture keeps R2, 1024 px: at the
  512 crop our crease read half) against Tess's photograph, same detector points: amount 1.2 read 0.06-0.10 before
  (a), 0.46-0.49 after (a) with the first colour (a pen line), 0.35 / 0.37 by side with OCCLUSION 1.1, OCC_WIDTH 1.15
  x the groove's sigma, folds_crease [0.5, 0.33, 0.27] (brown, soft); her fold reads 0.32. LID_REF 0.22 -> 0.36.
  The fit's loop closes on it: sg_tess round 1 laid 0.87, the AFTER read says "as ours" (picture 0.318 / 0.315, ours
  0.307 / 0.291).
- THE LID IS READ BY THE LASH LINE ALONE where that read works (3+ columns in the picture or in ours): the valley
  across the nominal path, 1.5 mm off her line, said "ours has more" in round 2 and took half the fold off again.
- HOODING: `lid_fold.hood` 0..1.5: over the outer half the line comes down toward the lashes (HOOD_DROP 1.7 mm), the
  roll stands 1 + 1.6 x hood higher, the keep-out at the lid margin shrinks 30 %. Clay (out/clay_tess_a1_bh.png, hood
  1.0 against ae, hood 0): the outer roll visibly fuller and lower. At hood 1 small artefacts remain at the outer
  canthus (the displaced field folds where the lids meet). The lid prior (pictures that cannot show a lid) sets
  hood 0.9 x age curve 40..75 (Garrett, 52: 0.24).
- JUDGED at the 4x zoom (out/feat_sg_tess_zoomL.png / zoomR, on the sheet): ONE continuous dark brown line across
  the lid at about her height, no welt, no ticks; sf_tess beside it: the pale ridge with two ticks. STILL WRONG: ours
  is greyer and softer than her crisp line; her whole lid between crease and lashes is darker (shade our head does
  not cast, now deliberately not painted: the socket reads paler than hers); no dark lash line; lashes long and
  spiky where hers are a dense short line (not this task).

### 4. Mouth and the fold paths (spikes/skinfolds2/nlpath.py on six heads: garrett_a1, tess_a1, th_E1, el_a1, om2_m1, oh_M1)
- NASOLABIAL, measured: the old nominal path passed the mouth 10-12 mm outside the cheilion and then dropped
  STRAIGHT DOWN for 10 mm (x constant): 20-24 deg from the vertical as a whole on all six. Anatomy: from the alar
  crease at 30-40 deg, 12-15 mm outside the cheilion, on outward to about the lower lip's level. New control points
  (0.17, 0.06, 0.13) / (0.24, 0.1, -0.1) x the pupils' distance from lm_mouth_corner: 12.6-15.1 mm outside the
  cheilion, 27-37 deg as a whole on the six heads.
  THE HEAD'S OWN CREASE: a middle-aged GNM head has a nasolabial crease in its shape (clay of garrett_a1 without
  folds: out/clay_garrett_a1_bm0.png). `own_crease` snaps the nominal path onto it where the skin's own profile
  across the path is concave enough (2nd derivative of the height at a 2 mm scale >= 0.035 / mm along 40 %+ of the
  stations; a quadratic through those): Garrett -1.1 mm along 50 %; the other five heads: no crease of their own
  (0-29 %): untouched. HONEST: on Garrett the own crease curls in round the mouth below the nose's wing, further
  than the snap's 7 mm reach in its lower half; our fold runs outside it there: two lines in the clay under raking
  light (the painted fold is the outer, oblique one). Not solved: either deepen the head's own line or take it out
  of the shape (block-in).
- MARIONETTE: was a 3 mm groove beginning 8 mm UNDER the corner, straight down at 9 deg (a nick: "a scar"). Now from
  the commissure (cheilion + 4, -3.5 mm) down and out at 15 deg over 21-27 mm, 6 mm wide, 0.3 mm deep, the jowl's pad
  beside it (0.5 mm at 7 mm, shoulder 6.5: at 0.8 over 4 mm it drew a second crease), occlusion 0.08, never laid
  along less than 65 % of its path (`min_extent`), read only past its first 30 % (`read_from`: the mouth corner's own
  shadow).
- COMMISSURE (new: the depression at the mouth's corner, 5 mm wide, 0.45 deep) and CHIN_NOTCH (new, Joe on Garrett:
  a midline notch with a lobe each side: RELIEF "sym": the roll on both sides; 0.9 deep, lobes 0.6 at 5.5 mm) are
  NOT READ (`"read": False`): the commissure's detector read Tess's own mouth corners at 0.14-0.19 and laid 1.5 on a
  22-year-old; a chin's midline dip under a frontal light is its own shading and Garrett's is under stubble. Both
  are parameters for the eye. sg_garrett: chin_notch 0.4 BY EYE (INFERRED from Joe's description, not read). At 0.8
  the exported asset showed it as a dark pit under the chin (raking light): too narrow and deep for the bake.
- KNOWN FAULT, NOT MINE: garrett_a1's own field has a ball at his left mouth corner (clay without folds), and the
  GLB shows ragged pale specks along the closed lip line: the head / export, not the folds.
- LIPS: (a) read IN IMAGE SPACE AT THE PICTURE'S OWN LIPS (`_lip_read`: MediaPipe's lip contours on the picture, a
  pixel in; our render inside OUR lips; picture levelled on the plain skin; front-ish views with the whitest light
  only). The albedo-ratio read at our lips' pixels and the image read agree within ~1 Lab on Tess, so the read was
  not the fault: her upper lip IS (46.5, 17.2, 19.5) in the picture, hue 48 deg: a brown. What read "orange" on
  sf_02 was the sheet's exposure (x 1.36 on a -0.55 EV filmic render) over a face 1-3 b* too yellow.
  (b) A lips-only fit stalled: the restart loop stopped at "< 1.5 % of the total cost", and with lips alone free the
  other regions hold 99 % of it: now the gain is measured against what has been gained.
  (c) RESULT, image space after 2 rounds: Tess upper lip rendered (46.9, 16.6, 19.1) for (46.5, 17.2, 19.5), lower
  (59.5, 17.9, 18.7) for (59.2, 18.3, 18.8). Garrett: see "Applied".
  NOT DONE: the lips' gradient / border / highlight are still set by eye (her lower lip: pale with a soft
  highlight and fine vertical texture; ours a flat fill), the bow is the block-in's.

### 5. Garrett within the paintings' limits
- SYMMETRY AS THE PRIOR: tear_trough, nasolabial, marionette come in pairs; one side read with confidence and the
  other NOT READABLE (not seen, or pictures too coarse to place a fold: PLACE_MM 0.7: "not found" is no evidence):
  the unread side takes the read side's amount, and the reply says "INFERRED from the other side". On fine pictures
  a side that reads absent stays absent (foldval's one-sided marionette: still absent). Garrett: tear_trough R 0.435
  (valley 0.098 along 58 %), L INFERRED 0.435 (was 0.16); nasolabial R 1.01 (0.097 along 45 %), L INFERRED.
- The bags' AMOUNT is still under the painting's (0.44; it shows ~1): the valley at the trough's line is what is
  read, and a painted bag is mostly its lit pouch. Not solved at 1.1 mm a pixel.

### 6. The game asset: what survives, and folds under expression (spikes/skinfolds2/export_check.py; sg_garrett FULL
### BODY, his own export settings: parts.body.topology "wrap", triangle_weight 4, 2048 atlas, face_shapes=True; logs
### out/export_g2.log (gains baked), export_g3.log (rigid); sheet human_renders/sg_03_garrett_export_expressions.png)
- THE GLB PREVIEW RENDERS: asset.preview returns PIL images (one contact sheet, or a list per pose); skinfolds'
  script wrote it as bytes. Nothing to fix in the library.
- THE EXPORT: 42,040 triangles on the body (the wrap's own quads: 20,616 vertices "moved onto the field by mean 0.29
  p95 0.96 max 3.9 mm"), edge length on the face p50 2.8 mm, texel 0.9 mm (0.4-0.5 in the head's focus), 53 morph
  targets on body / eyes / teeth / tongue / lashes, 644 s.
- GEOMETRY, measured on points over the head's triangles within 7 mm of each fold's line (relief = folded field -
  fold-free field; error = the low poly's distance to the FOLDED surface; away from every fold the wrap's own fit
  error is 0.73 mm rms):
  | fold (amount) | relief in the exact field rms / max mm | low poly's error rms mm | of the relief LOST from the triangles |
  |---|---|---|---|
  | nasolabial (1.01) | 0.43 / 1.28 | 0.27-0.28 | 0.62-0.65: about a third of it is in the triangles |
  | marionette (0.67 / 1.06) | 0.10-0.15 / 0.33-0.52 | 0.16-0.26 | > 1: under the wrap's own error |
  | tear trough + bag (0.43) | 0.13 / 0.61 | 0.28-0.35 | > 1 |
  | lid fold (0.6) | 0.15 / 0.65 | 0.33-0.38 | > 1 |
  | chin notch (0.8) | 0.20 / 0.63 | 0.51 | > 1 |
  So: at a 2.8 mm quad only the nasolabial fold is partly real geometry in the asset. Everything else (bags at this
  amount, the lid's crease, marionette, the notch) is BELOW THE WRAP'S OWN FIT ERROR and lives in the NORMAL / AO /
  HEIGHT maps (baked from the exact, folded field) and, for the creases, the painted line in the base colour. In
  the Cycles preview of the GLB the bags and nasolabial folds read under frontal and raking light; the lid's crease
  (0.6, a prior) is not readable at 0.4-0.9 mm a texel. Normal-map tilt at the fold's points (rms, through the GLB's
  UVs): lid 22-25 deg, tear trough 16-18, against 13 away from folds, nasolabial 7 (weak as a number: the skin's own
  micro relief is in the same map).
- FACE SHAPES WITH THE FOLDS PRESENT (Joe: "if it's additive to gnm, it won't play nice"), answered with renders:
  neutral | blink 0.5 | blink | eyes wide | squint (eye + cheek) | smile | jaw open, eye and mouth close-ups,
  frontal and raking light, folds RIGID against GAINS BAKED IN (the sheet).
  What goes wrong, per pose (blunt):
  * blink: NO WELT across the closed lid in either version: at this density the lid's crease is texture, not
    triangles. What does ride the lid rigidly is its TEXTURE (the painted line and the normal map's groove are
    carried down with the lid's skin: on the closed lid they sit as a faint line; a real crease unfolds). In a blink
    the fold line's vertices travel 1.8-2.8 mm where the margin under them travels 4.0 (GNM's own blink: the crease
    does move with the lid, 45-70 % of the margin's way). The closed lids' texture smears and a dark streak stands
    at the inner corner under raking light: both versions, the head's own (the export's quality report: "TORN OR
    TANGLED at lm_lid_upper.R, lm_eye_inner.L": 19 + 19 folded edges; folded edges on the head: neutral 131, blink
    158, wide 106, squint 159, smile 118, jaw 131, the same rigid and baked; a fold-free export was not run beside it).
  * eyes wide / squint: the bag grows on a squint with the gains baked (visible in the tile), stays the same rigid.
  * smile / jaw open: no tearing from the folds; the nasolabial fold's gain (+0.65 mm on a smile) is hardly visible
    at this density. The ragged pale specks along the lip line and the teeth showing at the corners are the head's
    own mouth (both versions, also without folds).
  * the chin notch at 0.8 baked as a dark pit under the chin (raking): set to 0.4 on sg_garrett afterwards.
- BUILT, the first step of "fold amounts as a function of expression" (skin_folds.EXPRESSION + `expression`, called
  by asset.export after faceshapes.apply; skin["fold_expressions"] false = rigid): a GAIN per fold and ARKit shape
  (x the neutral amount at the shape's full weight; "Left" / "Right" act on that side):
    lid_fold: eyeBlink 0, eyeWide 1.3, eyeSquint 0.5, browDown 1.2 | tear_trough: eyeSquint 1.4, cheekSquint 1.4,
    mouthSmile 1.2, eyeWide 0.8 | nasolabial: mouthSmile 1.5, cheekSquint 1.2, noseSneer 1.3, jawOpen 0.8,
    mouthPucker 0.6 | marionette: jawOpen 0.6, mouthFrown 1.4, mouthSmile 0.5 | commissure: mouthSmile 0.4,
    mouthFrown 1.3, jawOpen 0.7 | mouth_corner: mouthSmile 1.4, jawOpen 0.6 | mentolabial: jawOpen 0.7,
    mouthShrugLower 1.4, mouthPucker 1.2 | glabella: browDown 1.6, browInnerUp 0.3 | chin_notch: mouthShrugLower 0.6
  (first guesses from anatomy; crow's feet "from 0" need a fold that is absent in the neutral: not built).
  Per fold primitive and low-poly vertex the fold's own displacement is measured on the field (the part's field
  without that fold minus with it, along the fold-free normal); the shape's morph target gets (gain - 1) x it, and
  the target's vertex normals are recomputed. Garrett's export: lid_fold eyeBlink -0.64 mm, eyeSquint 0.32, eyeWide
  0.19; nasolabial mouthSmile +0.65; tear_trough eyeSquint / cheekSquint +0.24; marionette jawOpen 0.13-0.21.
  Tested (test_folds_under_expression): on a blink the lid fold's vertices return to within 35 % of the fold-free
  skin; the other side's shape and shapes without a gain are untouched.
- WHAT A GLB CAN CARRY: per morph target POSITION and vertex NORMAL (and TANGENT) deltas. NOT a texture per target:
  the fold's normal map and painted line are one texture for every shape. Fading the crease on a blink / deepening
  a fold on a smile at texel scale needs a WRINKLE-MAP BLEND in the engine (a mask per fold region x the shape's
  weight, blending a second normal map and a second base-colour line): for oxidegen / S0urc3, not built here. The
  export could write those masks and the "no folds" normal map as extra textures + the gain table in the json.
- THE SPLIT, geometry vs map, for the lid's crease: on the dressed head (0.5 mm mesh) the shallow real groove + its
  broad low lip gives the profile, and the SHARPNESS is the painted occlusion line (the dark line is paint: a
  rasteriser has no skin-on-skin shadow at half a millimetre). In the asset the split happens by itself: the
  groove is under the wrap's fit error and goes to the normal map. So the crease does not fight the blink as
  geometry; what remains to do is the texture's fade (above).
- TESS could not be exported with face shapes: tess_a1 has no base.head.interior / mouth_gap ("face_shapes on a GNM
  head needs a mouth that can open"). Giving her one changes her head: not done on a copy this round. Her lid fold
  under a blink is therefore NOT rendered; Garrett's (0.6, a prior) stands in.

### Validation (skinfolds2; spikes/skinfolds2/foldval.py, toneval.py, lidcal.py; Tess's head and cameras, the truth under a
### light the reader does not know; logs out/fv_*.log, out/toneval.log (final code), toneval_esig06.log / _esig02.log)
- FOLDS, ROUND TRIP (case A3 on folds2.json: the eight read-or-not folds at amount 1 as GEOMETRY with known shifts /
  extents / one side off -> pictures -> read -> skin.folds -> render -> read again, 2 rounds; TRUTH PICTURES RENDERED
  FRESH: the first run reused pictures made before the crease's colour was fixed and "missed" both lids:
  out/fv_A3_stale_truth.log): of the 12 fold-sides the reader reads, 11 HITS, 1 MISS (glabella R: 0.13 in the
  picture along 20 % of its path: "as ours"), 0 FALSE; the side that was off (marionette R) absent; commissure L / R
  NOT READ by design (counted apart). Strength on the hits: mean -0.03, rms 0.35 (1.27 0.75 1.00 0.48 0.51 0.99 0.74
  0.74 1.50 1.50 1.21). BOTH LID FOLDS ARE NOW READ BACK (skinfolds: 0 of 2): the truth's crease reads 0.34 / 0.33
  (ours at amount 1: LID_REF 0.36), round 1 lays 0.9. NOT RIGHT YET: after round 2 both lids stand at the 1.5 cap
  and the final read says "ours has more" (0.50 against 0.34): the loop overshoots in round 2 and needs a third
  round (Tess's own fit: 3 rounds, final "as ours" 0.33 / 0.30 against 0.32); and the lid's PLACEMENT is not
  recovered: -0.3 for a truth of +1.5 mm, -0.8 for 0 (read_lid's line height is good to ~0.5 mm in the picture,
  ~1 mm along the leaning lid). Shifts elsewhere as before: nasolabial +2.9 (+2.0), -2.3 (-2.0); BIASED: marionette
  +2.3 (0), mentolabial +3.0 (0), tear trough R +1.6 (0).
- NULL (case B: smooth young head against smooth pictures): 0 of 12 present, no displacement laid.
  ON TESS'S PHOTOGRAPHS (a real smooth 22-year-old): marionette 0.54 laid (R valley 0.049 along 61 %, the left
  INFERRED from it): a FALSE POSITIVE of the new, wider marionette path (0.16 mm of soft relief: not visible, but
  wrong); mouth_corner L 0.31 as before. The commissure's detector was worse (1.5 on both sides) and is switched off.
- LIGHTNESS, the prior alone (truth = Fitzpatrick f with its own hue (blood 0.6, undertone +0.35); start = the same
  type's default; base tone error to the truth, L a b, before -> after; final code):
  | truth | EV | plain skin L* | before | after | whole face L* |
  |---|---|---|---|---|---|
  | F2 | -0.7 | 65.91 -> 65.14 | +4.5 -4.2 -3.2 | +2.3 -2.4 -2.8 | 66.2 -> 64.6 |
  | F2 | +0.4 | 65.72 -> 64.91 | +4.5 -4.2 -3.2 | +2.1 -2.5 -2.5 | 66.1 -> 64.5 |
  | F3.5 | -0.7 | 59.15 -> 58.79 | +3.9 -3.8 -1.6 | +2.3 -1.7 -2.2 | 59.4 -> 58.5 |
  | F3.5 | +0.4 | 59.15 -> 58.79 | +3.9 -3.8 -1.6 | +2.2 -1.8 -2.0 | |
  | F5 | -0.7 | 41.39 -> 41.41 | +2.3 -2.1 +0.9 | +2.1 -0.5 -0.2 | 41.7 -> 41.7 |
  | F5 | +0.4 | 41.39 -> 41.41 | +2.3 -2.1 +0.9 | +2.1 -0.5 -0.2 | |
  | F3.5, prior F2.5 (wrong) | -0.7 | 64.28 -> 63.51 | +9.2 -4.7 -5.1 | +6.8 -3.1 -4.4 | |
  Exposure-invariant (the two EVs within 0.3 Lab); plain skin and whole face inside their 3 L* bounds (largest move
  -1.6 L*); the error to the truth falls in every case; a wrong prior stays wrong by design (9.2 -> 6.8).
  A FAULT FOUND AND FIXED HERE: with the first shade model the synthetic F2 head came out with "exposure x 0.40"
  and EVERY other region "26-32 L in shade": exposure down + shade up on all regions is a colour cast along the
  shade colour by another name. EXPOSURE_SIGMA 0.6 -> 0.2 and SHADE_MAX 0.7 did not stop it (x 0.48, 21 regions at
  the cap); SHADE IS LOCAL did: the lower quartile of the shaded regions' shade is held to 0 (SHADE_LOCAL 0.03): F2
  now lists temple -18..-20, nose tip / wing -6..-12, under-eye -5..-12 as shade and nothing wholesale. STILL ODD:
  the solve's "exposure" on these synthetic heads is x 0.45-0.6 (x 0.8 on F5) at both EVs although the read is
  levelled on the plain skin; on the subjects it is x 1.02 (Tess) and x 0.95 (Garrett). Not understood; the tone's
  result does not move with it.
- THE WHITE ANCHOR: (a) DECLARED (white=[{view, box, albedo 0.8}] on the truth pictures' shirt: the bust recoloured
  to albedo 0.8 with its own shading): FIRES. F3.5 with a wrong prior F2.5: error to the truth +9.2 -4.7 -5.1 ->
  +0.5 -1.4 -1.2 L a b (the solve wanted -11.6 L*, held at the 8 L* bound). F5 with prior F4: +17.4 -3.7 -2.1 ->
  +8.6 -0.8 -0.7: the white asked for -9 of the 17 L* (a dark skin against a shirt: the "lit as the face" inference
  is good for about half there) and the bound held it at 8. (b) FOUND by the parser: DID NOT FIRE on the synthetic
  shirt ("no clothing under the face that is bright and unclipped": the parser's cloth class on a bald CG bust, or
  the recoloured shirt's clipped highlights; not diagnosed). The found path is tested only with a given mask
  (test_shade_white_and_bounds: accepted when white, refused when grey under a brighter backdrop or coloured). On
  the subjects it rightly refuses Garrett's shirt. So: declared = validated (2 cases, bias toward too light on dark
  skin); found = NOT validated on pictures.
- STABILITY under the final code (one more colour round from the fitted copies onto sg_*_chk): Tess: whole face
  [73.23, 7.23, 16.53] -> [73.28, 7.18, 16.65]: nothing moves. Garrett: b* +2.1 again (17.7 -> 19.8): a fresh call
  on an already fitted copy takes the fitted tone as its new PRIOR, and the solve still wants +7 b* of the painted
  backdrop's white balance: the 5 a*b* bound is per call, not per model. Known hole: repeated calls walk.
- Tests: tests/test_skin_read.py (+ test_shade_white_and_bounds, test_fold_rules2, test_folds_under_expression),
  test_skin.py, test_skin_marks.py, test_toolsets.py pass on the final code (out/tests2.log).

### Applied (copies sg_garrett from garrett_a1, sg_tess from tess_a1; a1 / sr_* / sf_* untouched; reports out/go_sg_*.txt;
### sheets human_renders/sg_01_garrett_bags_folds_mouth.png, sg_02_tess_tone_crease_mouth.png (REFERENCE | AFTER | BEFORE (sf_*,
### rendered by main's code) | references projected; the lid's crease at 4x; eye / eye / mouth under the photo light and
### a raking light; neutral light and unseen angles), sg_03_garrett_export_expressions.png; one small image per feature:
### out/feat_sg_<m>_<front|view1|zoomR|zoomL|eyeR|eyeL|mouth>.png)
- TESS: tone melanin 0.139, blood 0.026, undertone -0.06; zones forehead_yellow 0.02, perioral_red 0.01, nose_red
  1.32, midface_red 1.27, flush 0; under_eye 2.0 -> 1.03, eyelids 1.4 (a1's), lower_cool 1 and periorbital 0 (the
  defaults) (sf_tess: under_eye 2.5, eyelids 2.5, lower_cool 1.92, periorbital 0.97); lips blood 1.31, melanin 14.0, strength 1.08, lower.melanin 0.40; folds lid_fold 0.87 (shifts L
  1.0..3.9..0.35, R 0.6..2.3..0.4 mm: an arc), marionette 0.54 (see the null), mouth_corner L 0.31.
  MEASURED, like with like (mid-face Lab at the same pixels, photo light at the measured EV -0.23 / -0.02 / +0.74):
  reference 67.5 8.9 17.8 | AFTER 69.9 8.0 17.3 | sf_tess 69.0 8.7 18.2 (front); 69.4 9.1 16.6 | 73.5 9.0 17.6 |
  72.9 9.2 18.8 (3/4); 72.5 7.7 17.7 | 78.2 8.5 18.4 | 77.6 8.8 19.0 (profile). Colour within 1 a*b* of hers in all
  three views (sf: up to 2.2 b* yellower); 2-6 L LIGHTER than hers in the mid-face (her shade, not painted).
  JUDGED from the feature tiles, bluntly. TONE: no longer a tan: a pale warm beige like hers, a little greyer /
  flatter; the eye mask is gone. Under ONE light and exposure sf_tess is not far off either: most of "tan" on sf_02
  was that sheet's exposure. Still wrong: blotchy cm-scale mottle where hers is even (skin.variation: not touched),
  the socket and jaw paler than hers (shade we do not cast), the profile view washed out (its light fit).
  CREASE: one continuous dark line parallel to the lashes, no welt, no ticks: reads. Softer / greyer than hers and
  a little nearer the lashes; no lash line; lids pale. MOUTH: the upper lip's colour now matches in image space
  (0.6 Lab) and reads a brown like hers; still a FLAT fill with a hard edge, the lower lip a flat peach without her
  highlight; the bow is the head's.
- GARRETT (two paintings; 1.12 / 1.33 mm a pixel): tone melanin 0.011, blood 0.16, undertone +0.55 (the solve wanted
  +7 b*, held at +5: the same as skinfolds); zones midface_red 1.02, nose_red 1.55, lower_cool 2.0 (its bound, on a
  man: real effect), forehead_yellow 0; stubble zones chin 0.5, soul 0.7, jaw 0.82, cheeks 0.55, neck 0.07; lips
  blood 1.99, melanin 21.9, strength 1.55, lower 0.52 / 0.21 (front view only; upper lip in image space rendered
  (44.3, 17.8, 16.6) for the painting's (39.1, 18.7, 17.4): 15 L too light before, 5 L after two rounds; lower
  (62.8, 17.3, 17.9) for (63.7, 18.6, 18.4)); folds nasolabial 1.01 (L
  INFERRED from R), marionette 1.06 / 0.67, tear_trough 0.435 both (L INFERRED from R), lid_fold 0.6 + roll 1.47 +
  hood 0.24 from norms (INFERRED), chin_notch 0.4 BY EYE.
  JUDGED from the tiles: BAGS under both eyes now, soft pouches under frontal and raking light: right in kind,
  still smaller than the painting's. NASOLABIAL: oblique, from the wing outward, as painted; beside the head's own
  inner line (two lines under raking light). MARIONETTE: a soft fold from the corner down and out, no longer a
  nick. LID: the prior's soft crease; the painting's heavy hooding is not there (0.24). CHIN: a shallow notch.
  LIPS: darker, browner upper lip than sf; still lighter and pinker than the painting's thin dark mouth. TONE: as
  sf (b* held at the bound); the desk painting's view is 6 a* / 11 b* off under its lamp (weight 0.3: expected).

### Status (skinfolds2)
STATE: BUILT and wired (skin_read.py, skin_folds.py, skin_look.py, asset.py hook, server white=, guide, tests):
shade is not pigment (measured shade colour, local, never on the plain zones), whole-face + zone-offset bounds, moves
must earn their place, the white anchor on the whole picture + declared, photo_light at the picture's measured
exposure (+ look_skin light "photo"), the lid's crease (occlusion in the skin, eyeball as a constraint, a low-order
line over OUR lashes, calibrated to a photograph, hood), lips read at the picture's own lips, nasolabial / marionette
paths from anatomy + own-crease snap, commissure, chin_notch, symmetry prior, min extent, folds under expression
(gains baked into the morph targets), export check with poses. VALIDATED: folds round trip 11 of 12, 0 false, both
lids read back; null 0 of 12; lightness in bound and exposure-invariant on 3 tones x 2 EV; declared white (2 cases);
expression deltas (unit test + Garrett's export). NOT validated / FAILED: the found white on pictures; lid placement
(+-1.5 mm) and its round-2 overshoot; a false marionette on Tess; Tess under a blink (no mouth interior); chin_notch
(by eye only); hood beyond clay.
MODELS WITH skin.folds REBUILD (skin_folds.VERSION 10 -> 12: paths, reliefs and the tissue key changed): only the
sr_* / sf_* / sg_* test copies have folds. No BUILD_VERSION bump: models without folds have the same build key and
primitives (tested). The colour fit's results change for every model on its next skin_from_reference call.
NEXT, in the order I would:
1. THE CHIN PAD + JOWL as proper features (Joe on Garrett): chin_notch is a first midline groove with two lobes, set
   by eye; wanted: the pad's width set by the marionette grooves, a jowl line out to the jaw, a detector (profile /
   low-angle views; a raking synthetic calibration), and the bake's pit fixed (wider, shallower).
2. WRINKLE-MAP BLEND for the engine (oxidegen): export a "no folds" normal map + per-fold masks + the gain table, so
   the crease's TEXTURE fades on a blink and deepens on a squint; crow's feet and other folds that are 0 in the
   neutral (EXPRESSION from 0) need an amount-0 fold with its primitive kept.
3. Tess's blink: give a copy a mouth interior + mouth_gap and export; judge the lid's line on the closed lid.
4. THE LID: placement to +-0.5 mm (read the line against OUR rendered line's height, as the amount is), stop the
   round-2 overshoot (a line read at a new place needs one round to settle: damp the gain), a dark LASH LINE and
   shorter denser lashes, the lid's skin in shade (geometry: eye depth; or a declared "lid shade" layer).
5. LIPS: gradient / border / highlight read from the picture's own lip profile (they are still set by eye); Garrett's
   upper lip is still 5 L light at lips.melanin 22: it multiplies a tone melanin of 0.01 (a lip pigment of its own,
   not a multiple of the tone's, would reach it).
6. The tone bound PER MODEL (store the first prior in the model: repeated calls walk 5 a*b* each), and the profile
   view's light fit (key from below on Tess's view 2).
7. The false marionette on a smooth face (read it only where the nasolabial fold is present, or raise its
   confidence floor), glabella R's miss, the found white on real photographs with a white shirt (skin_refs).
8. Skin mottle at the cm scale (Tess reads blotchy), sclera too white, nostrils pale inside: seen on the tiles, not
   this thread's tasks. The "references projected" tiles carry our brows and upper-lip layer over the projection
   (the reruns / refread stages' layering): not fixed here.
9. skintour.py renders under g3stage.photo_light (the -0.55 EV filmic template): its tiles sit ~10 L under the
   references; it should use skin_read.photo_light.

## projskin (2026-10-13/14, "projskin" agent, branch projskin, squashed onto main as projskin-merge). Per-head and
## per-picture notes (numbers by subject, sheets, logs) are NOT in the repo: workspace/private_notes/ (git-ignored) and
## /mnt/data/hifipushie/projskin/ (scratch, scripts' logs, renders). Spikes: spikes/projskin.

WHAT IT IS: skin from the reference pictures as a MEASUREMENT, not as shipped pixels, and the eye-region forms.
- skin_project.py: the fitted views projected into the head's atlas (onemesh UV, 0.235 mm / texel), exclusions (MediaPipe
  parse, wisps, long hair strands connected to the hair, the lid band), de-lighting (order-2 SH through each texel's own
  visibility + a searched soft key; multi-view agreement; per-view CHROMA harmonisation at 12 mm before the blend), fill,
  report, iris read, stage_light (a view's fitted light as scene suns). The atlas is opacity 0 by default (a measuring
  instrument). "ours" (the tone / fill reference) never includes a measured stack (re-projection drifted greyer each pass).
- skin_layers.py: the atlas decomposed into a STACK of layer maps (Tsumura-style optical density: melanin / haemoglobin /
  neutral): base, pigment, redness, periorbital (venous axis), brows, lips (texels or "indications": the photo's outline +
  mid-lip colour, the mesh's own lip rows inside), beard (men / stubble only), shade, parting; freckle and BLEMISH density
  (the fine band's dark excess over its light excess: grain cancels) driving our generators; a fine-texture strength map
  with a floor on plain skin; hidden texels filled by a soft multi-reach blend; redness / shade carried under the lips; the
  base capped below 1 (a clipped red channel read grey). A measured beard layer brings our stubble hairs.
- Eye-region FORMS (gnm_fold, lidfit spike): the upper-lid fold in GNM's mesh (platform, slit, roll; local, blink-safe),
  its crease traced in the front picture; a crease TAIL past the outer canthus (a groove along the traced path on GNM
  vertices, starting where the fold's chains end); bags / tear trough from the bag's lower edge (head.shape eye_bag /
  cheek_flat); the slit only as deep as the drape over it. eyefit: one step of the fold against the photo with the same
  lid reader on our render (platform, misread columns skipped, steps <= 1 mm).
- FORMS FIRST, THEN THE ATLAS: the pictures are projected onto the head WITH its forms, so the de-lighting explains the
  crease / bag shading by the form, not as pigment.
- BAKED OCCLUSION + CREASE LINE (skin_layers.occlusion / crease_map): AO (no eyeball occluders) x a cavity term from the
  final geometry, floored 0.55, soft 1.2 mm, WARM (each channel darkens by the skin's own shadow hue from the atlas, 0.6 of
  it); a crease line on the fold's platform under the hood + the roll's edge + the tail. Strengths measured against the
  photo (occfit: fold-line darkness / orbit darkness by eyecmp, on an EEVEE render). EEVEE's GI loses a lid fold's
  occlusion (Cycles shows it): the bake puts it back; judge in EEVEE, Cycles as the geometry check.
- BLINK: the crease line and the lid's share of the occlusion ("_blink" paint layers) fade with the pose's lid close in
  looks; the export bakes them apart (one material switch "hp_blink", a second colour pass) as <atlas>_blink_multiply.png,
  out of basecolor: shade basecolor x lerp(1, map, 1 - eyeBlink). An export of a human head needs CAP=20G.
- lashes.py (VERSION 20): closed-lid rules only when the head's lids are shut (head["eye_open"] < 1.5 mm); a closed lid's
  lashes hang down along the seam, the seam from the lower-lid landmarks; a degenerate rim prints LASHES WARNING (blocks
  a sheet); cornea-aware opening on GNM-eyed heads.
- retopo wrap: the lid fold's vertices keep their built positions (the field collapsed the re-entrant hood).
- Cycles stage: broad soft suns are hidden from glossy rays (their discs reflected in the cornea as grey patches).
- Tools: skin_project (MCP), skin_from_reference(project=, layers=); guide: skin_guide "projection", "EYE FORMS AND THE BAKE".

OPEN (for whoever continues): the bake's rays in the fold's slit speckle the upper lid in the export; folded edges at the
outer / inner corners in the export (some are faces genuinely under the overhang); a lens-shaped gap at the closed seam on
a hooded head (blink geometry with the fold); orbit occlusion not yet concentrated on the upper lid / inner corner; fine
texture / pores still weak under the stack; freckle density uncalibrated against a freckled synthetic truth; a proper
wrinkle map driven by the faceshapes export's blink weights (the blink map is the minimal version).
RESTART: the detailed history and the per-head state are in workspace/private_notes/skin_notes_projskin_full.md.

## Guide rewrite (2026-10-14, "guides" agent)

skin_guide.md 505 -> ~150 lines: read-the-skin-from-the-reference first (tone boxes, redness, texture, lips, eye
area, brows, creases, facial hair, cosmetics), the stages as a table, craft rules, a per-feature self-review loop,
common mistakes. The stages in detail + sources -> skin_layers; tool sections -> skin_tools. Removed provenance:
"Before 2026-10-10 melanin 0 stopped at ITA 52 and very fair people rendered tan"; "eyeballs in the default groups
since 2026-10-13"; the "(projskin)" label on the eye-forms paragraph.

2026-10-14 (branch projskin2 from main 34346fc): lidfit GUARDS on the lid read: a column's crease must lie in the lower
0.6 of the lid-to-brow distance, within 3 mm of its eye's other columns, the two eyes' medians within 2.5 mm (else the
better eye's columns stand in), and traced crease crossings above the read + 3 mm are dropped; each prints a WARNING. (A
read caught a brow's underside as one column's crease and the trace then followed the brow line: a fold 13-16 mm up.)
Periorbital layer eased into the fill over 2 mm (a thin dark line along the lid band's edge).
2026-10-14 RENDER RULES adopted (machine): every Blender only under bin/capped (the GPU lock script loads there); check
renders sized to the feature (eye / crease / lip close-ups ~512 px, whole head ~768 px; the smallest judged thing >= 3-4
px); supersampled multi-view sheets only for gate sheets; reader-based measures keep their resolution (cu.py size=700).
Sheets wrap their captions (/mnt/data/hifipushie/projskin/sheets/wrapsheet.py).

## Handover 2026-10-14 17:45 (projskin agent; successor: start here, then docs/notes/gates.md)
BRANCH projskin2 (worktree /home/joe/dev/hifipushie/.claude/worktrees/projskin2, .venv symlinked from ../projskin), from main
34346fc + main's gates merged in; last commit 2fab2e3 (see git log). NOT pushed, NOT merged. The old branch `projskin` holds
per-picture history: NEVER push it. Per-person / family notes: workspace/private_notes/skin_notes_projskin_full.md (git-ignored).

SCRATCH /mnt/data/hifipushie/projskin (env.sh points W at projskin2):
- run.sh <script> [args] = LIGHT job (bin/slot); heavy.sh <gb> <script> = HEAVY (resources.heavy + bin/capped, GPU lock) via hv.py.
- tests.sh <test file>: one pytest file per process, assets set; log out/test_<name>.log.
- rset.sh <model> <ref model> <own (fitted-light model)> <out dir> [views] <checklist>: the GATE RENDER SET (faces at the photo
  cameras 768, eyes / eyesR / mouth / cheek close-ups 512, closed eyes, all WITHOUT the groom), eyecmp, skincheck + review pairs.
- rev.sh <render dir> <tag>: bin/review on <dir>/pairs (skin stage: --stage skin..., --not "head shape and proportions; hair").
- fn21.sh: reseat_tail() (stack -> iris -> caruncle -> occfit -> renders), used by s21-s24.
- out/private/gate/<head>_<round>/: renders, skincheck.md (item | ref | ours | pass), pairs/, review1/review.md.
Spikes (worktree spikes/projskin): cu.py (close-ups at the photo cameras; size=, hair=0, views=, only=face,eyes,eyesR,mouth,cheek,
pose=, flat=1, engine=cycles; one highlight-only soft box = sheen + catchlight: sheen=, catch_x=), skincheck.py (the skin
checklist measured + review crops), eyecmp.py (lid reader on render vs photo: crease height / darkness, orbit, roughness),
eyefit.py (one fold-adjust step; young lids lower the crease), lidfit.py (fold + tail + bags from the front photo, with read
guards), smoothfold.py (crease as one arc + seated gate), occfit.py (crease / occlusion strength from eyecmp), famstack.py
(full stack from an atlas), takestack.py (head + another model's stack, re-crease), recrease.py (crease + occlusion maps),
tweak.py (THE HAND PASS: occ= crease= fine= <layer>=strength (edit is absolute from measured: pass ALL edits in one call)
brows.k= eyes.k= skin.k= base.k=), seteyes.py, setop.py, atlas_model.py / atlas_picture.py + tonefit.py (forms-first atlases),
necktone.py, toggle2.py <model> <tag> <prefixes> (TG_ONLY=face|eyes|mouth: renders with skin layers dropped: "which layer
draws this"), iris1.py, exptest.py (export; needs CAP=20G).
CAREFUL: stage caches (workspace/_g3_<model>) keep mesh attributes: after code changes to uv lookup / attributes delete them.
pkill patterns must not match your own command line.

PER HEAD
- Tess: approved head tp_h3 (shape NOT to be changed). Current skin candidate tp_h3_s6 (= stack from tp_h3_lef2 atlas on
  tp_h3_q3 forms + hand pass: occ 0.5, fine 1.0, lips 4.0, shade 0.6, periorbital 1.0, brows 0.6, oil 0.2, brows #4a3020 soft
  .35 tail .85 thick .85 arch 1.3, eye occlusion .4 waterline .3, iris #4f4c38 / inner #5c4a2e, lip roughness .28, lower lashes
  90 x 4.5 mm #2a221e). Checklist workspace/checklists/tess_skin.json. Latest COMPLETE round: out/private/gate/tess_s5
  (skincheck 19/27; review1 MAJORs: brows too dark/blocky/cool [s6 lightens], orange lid band [s6: orbit warmth cap],
  lips flat mauve decal + parting runs past corners, skin yellow-beige going grey at jaw/mouth, pin catchlight + big black pupil,
  closed seam = cut (pale sliver, red corners [s6 fades corner reds]), grey bruise ring round closed socket, cheek no red
  blotching / pores). IN FLIGHT: s6 round (rset + rev.sh) -> out/private/gate/tess_s6 (collect: skincheck.md, review1/review.md;
  if review1 is missing run $S/rev.sh $O/private/gate/tess_s6 review1).
- Garrett: frozen head gp_h6c (never edit). Skin gp_h6c_s (ps_39 gate; closed-lid mask reverted for blink-faded layers).
  Queued from the hair agent: skin too dark / saturated vs photo (their EEVEE: /mnt/data/hifipushie/hair_garrett/out/
  review_hg_G6/pair_1.png) and a light vertical stripe down the back of the neck (same family as the neck-join fix: delete
  his _g3 stage caches and re-render first). Checklist workspace/checklists/garrett_skin.json; no gates round yet.
- The private subjects: see workspace/private_notes (pointer). No gates round yet; their checklists are git-ignored.
- Out-of-stage findings already sent to the coordinator: Tess jaw / chin / ears / eye openings / nose / profile, hair.

TRIED AND FAILED (one line each)
- blink_still mask on crease/occlusion: killed the open-eye crease (reverted to blink-faded layers + export map).
- fills' specular via a soft box in stage_light: metallic nostrils, silver brows (reverted; Cycles hides broad suns from glossy).
- along-ring displacement smoothing of the fold (6 passes): flattened the hood (RING_SMOOTH 0).
- periorbital neutral axis + shade in the socket: purple-brown ring (colour-only periorbital, shade 70 % off the orbit).
- swatch pores / cells for texture: sub-pixel or hatch strokes at face close-ups (now pore-scale speckle + mottle noise).
- fine noise at 1.2 mm: stubble-like stipple. eyelid fold depth x2-3: no visible change in EEVEE (Cycles shows it).
- iris hand colours greener: Joe had approved Tess's iris; measured front view matches (dE 3): keep near measured.
- upper-lip L 54 vs 47.6: photo top-light shading; dispute with evidence, don't darken further (coordinator).

DECISIONS (coordinator / Joe)
- A private subject's crease frozen; the slit ring has ~9 vertices across the lid (a small kink can remain); more crease
  rows = GNM topology / export change: NOT now.
- An iris may need hand-setting when the photo's iris pixels read blue-black from the light. Tess's iris: Joe "eye colors look great".
- Review scope: skin crops without the groom; --stage skin / --not head shape + hair; out-of-stage list to coordinator only.
- No shape changes on approved heads (tp_h3, gp_h6c). Approval only via bin/approve (Joe / coordinator).
- Crease line + lid occlusion: full on the open eye, faded by pose; export ships <atlas>_blink_multiply.png.
- Heavy renders (full sheets, bakes): offload via spikes/offload/remote.sh + job_skintour.py on NICO-TOP (pack with
  spikes/tour/pack_model.py; NOTE: stacked models reference workspace/_images ids, pack_model does not copy them yet).
  Keep only light checks local; log per-frame wall time (> ~5 s risky on the laptop GPU).

NEXT, in order
1. Collect tess_s6; fix the worst skin MAJOR, rerun rset + rev.sh; loop until review PASS (nothing to coordinator before
   PASS / Joe decision / STUCK after 3 approaches). Likely next: lips (colour split upper/lower, sheen, parting ends), grey jaw
   / mouth cast (shade + occlusion under the jaw), closed seam (lens gap is geometry: list as out-of-stage if it persists).
2. Garrett: dark / saturated skin under the hair agent's light + neck stripe; full gates round.
3. The private subjects' gates rounds (private notes).
4. Make the offload route carry stacked models (copy referenced _images ids into the job) and move rset there.

## projskin successor 2026-10-14 evening (rounds s6r+)
- OFFLOAD WORKS for stacked heads (f5fd389): spikes/tour/pack_model.py <model> <job> [ref own ...] copies every model's folder
  (minus history / scene caches: skin_projection/report.json = the fitted lights travels), the pictures (@refs), and every
  content-store file the specs name (16-hex ids in _images / _painted); unpack() on the machine. job_skintour.py runs one
  cu.py per line of <job>/cu.txt. Test tests/test_pack_model.py. Scratch: $S/rset_remote.sh = rset.sh with the renders on
  NICO-TOP (pack + 3 cu lines + remote.sh, eyecmp / skincheck locally). Tess s6: 13 min round trip, stage build 210 s there
  (531 s on the laptop), renders match the laptop's (mean |diff| 0.9 / 255) EXCEPT:
- RED DOTS on NICO-TOP renders (61 on face_v0 at 768, one side only; laptop 0): EEVEE without the soft-box catchlight
  (catch=0) shows none, flat none: they are glints of the blemish cores (blemish_bump: roughness base - 0.14) under the
  specular-only window light, which NVIDIA EEVEE shows and the laptop's AMD EEVEE didn't. The reviewer reads them as red
  dots the reference doesn't have. Fix in the CONTENT (Tess's reference shows no papules), not the renderer.
- Tess closed-lid seam (pale sliver + orange-red corner slits, MAJOR s5-s8): OUT OF STAGE. It survived 3 skin approaches
  (corner reds faded by pose; canthus 0.8 -> 0.5; waterline 0.3 -> 0.1). The lids don't meet at eyeBlink=1, which is geometry;
  the coordinator routed it to the expressions owner. Skin reviews: answer it as out-of-stage, don't keep tuning it.
- Correction: the NICO-TOP red dots are NOT the catchlight's transmission (9a45ebf1 kept as harmless hygiene; dots stayed:
  s9 56). Window gain 0 (sheen=0) and the window on the other side (catch_x=0.9): same count. dots1's "catch=0: none" was
  at 512 px (too small to count); dots3 (768: catch=0 / flat / 64 samples) in flight. Treat dots in NICO-TOP renders as a
  renderer artifact until then; reviews list them and I discount them.
- Garrett's light back-of-neck stripe (reproduces on a fresh build: not a stale cache) = the head atlas' cut down the back
  midline: skin_project.lookup fades every uv-wrapped layer's weight to 0 within SEAM (1.5 + 3 mm) of the cut (per-vertex
  coordinates can't cross it), so the procedural body tone shows there, 7.8 L lighter than his stack at the jaw. Fix as
  content: spikes/projskin/necktone.py (body tone fitted to the stack's jaw colour; needs <model>/skin_layers/recomposed.png:
  copy it from the model whose stack pigment id matches, e.g. gp_h6c_les). General fix owed: a second, unfolded coordinate
  set across the cut blended in the shader, so the cut needs no fade (paintnodes/blender_scene "uv" decals).
- Hand passes from here leave detail at ~0.45-0.9 (defaults read as scratch / hash strokes on every head) and run necktone.
- Coordinator 2026-10-15: Garrett first, then the private heads; Tess minimal until tp_h4 (Joe's small jaw / eyes / lips
  edits) is settled, then re-seat her skin on it. Tess s9 regressed (brow / lip fills lowered: those fills carry the
  darkness); s10 (from s8, stronger brow fill) rendered, not reviewed.

## Handover 2026-10-15 10:00 (projskin successor; next agent start here, then docs/notes/gates.md)
BRANCH projskin2 (worktree .claude/worktrees/projskin2), main merged in (fe2ef302); all work committed, not pushed.
Scratch $S=/mnt/data/hifipushie/projskin: rset_remote.sh <model> <ref> <own> <out> [views] <checklist> (pack + cu.txt + NICO-TOP;
EXTRA="@spikes/projskin/nape.py size=512" adds the back-of-neck view), rset.sh = the same set on the laptop (heavy.sh: capped +
GPU lock), rev.sh <dir> review1. Review --context: for NICO-TOP renders the coordinator allows adding "ignore red pin-dot
render artifacts" (laptop renders have none). dotcount: scratch script counted red dots (r-g minus 7 px median > 18).
QUEUED on NICO-TOP (machine "lost" since ~09:50; Joe asked to bring it back). Clients are running locally and block until
done; outputs land in $S/jobs/results_<tag>/, and the wrapper then runs eyecmp + skincheck into out/private/gate/<tag>/:
garrett_g3 (gp_h6c_s3), privA_g2 (private notes), privB_g3 (private notes), dots3 (renderer diagnosis: face_v0_{D catch=0,
E flat, F 64 samples} at 768 in out/private/gate/dots3 after untar; HOLD for NICO-TOP). If you rerun on the laptop instead,
kill the matching bundle_client (match by pid, never pkill a pattern that is in your own command line).

PER HEAD
- Garrett (frozen head gp_h6c): gp_h6c_s1 = g2 (tones 4/5 pass, cheeks b* ~6 low). gp_h6c_s3 = s2 hand pass (brows #5e5650
  stack .8 soft .5, stubble amount .9 grey .5 #3e3832, redness .5, periorbital .6, detail .9, iris #6a7568 / #5c5a48,
  crease 1.6) + necktone (body tone fitted to the stack's jaw: the back-midline stripe band shows it). g2 review open:
  too pink, hash-stroke texture, no stubble visible, iris should read green-grey, dim catchlight, crease too light.
- Tess: s8 best numbers (lower lip passes), s9 regressed (fills lowered), s10 rendered on NICO-TOP (out/private/gate/tess_s10,
  not reviewed). Closed seam = out of stage (lid geometry). Coordinator: Tess MINIMAL until tp_h4 (Joe's jaw / eyes / lips
  edits) is settled, then re-seat the skin on tp_h4.
- Private heads: workspace/private_notes/skin_notes_projskin_full.md "## 2026-10-15".

NEXT, in order
1. The atlas-cut blend fix (coordinator's ask): skin_project.lookup fades every "uv"-wrapped layer to 0 within SEAM of the
   cut (per-vertex coordinates can't cross it). Instead return a second coordinate set: near the cut (band ~3 mm, computed
   out to ~2x band so straddling triangles stay continuous) uv1 = island i's map extrapolated (unclamped barycentrics of its
   nearest triangle), uv2 = island j's (islands = UV-connected triangle components; i < j per cut edge), s = smooth side
   weight across the cut (0 / 1 outside the band). Consumers: images.project (wrap "uv", images.py ~779), paintnodes "decal"
   attrs (3 comps -> 6: u2, v2, s), blender_scene decal() (~458-525: sample at both, mix by s), skin_read.py:323 (its own
   use of lookup: keep (u, v, w)). Test: a layer's value is continuous across the cut (points straddling the back midline).
2. Laptop gate rounds ONE AT A TIME via rset.sh (capped + GPU lock; every frame < ~5 s, log times; drop samples / size a step
   if over): Garrett g3 first, then the private heads.
3. Tess minimal until tp_h4.

## cutblend (2026-10-15, projskin): uv layers continuous across the head atlas' cut
- The light stripe down Garrett's neck was skin_project.lookup fading every "uv"-wrapped layer to 0 within SEAM of the
  atlas' back-midline cut (crown to neck, 63 edges, ONE island: the cut doesn't separate the atlas, so sides are local).
- Now lookup(both=True) -> (u, v, u2, v2, s, w): the cut's edges get side A / side B by 2-colouring their vertices' atlas
  copies (`_cut_sides`; on GNM A = +X); within 2 x CUT_BAND (3 mm) the other side's map is extrapolated from the nearest cut
  edge's triangle (unclamped barycentrics, `_affine_uv`), the own side keeps the exact closest-point coordinates; s = side B's
  share, smoothstep over CUT_BAND centred on the cut, computed out to 4 bands so triangles straddling where the extrapolated
  set stops see the same side (its weight is 0 there). No fade. lookup() without both keeps the old fade (skin_read).
- Consumers: images.project(both=True) / images._one (samples both, mixes value, colour and coverage by s), paintnodes
  "decal" fallback = 6 attributes for wrap uv (cache key "cut2"), blender_scene.decal samples the image twice and mixes.
- tests/test_skin_project.py test_cut_continuous: a smooth function painted into the atlas, read back at 5872 texel points
  within 6 mm of the cut: p99 error 0.0013 (one set with the fade: 0.79); a pair of points straddling the cut interpolated as
  one triangle's corners gives their mean (one set: the midpoint lands across the atlas).
- Laptop nape render gp_h6c_s3 (out/cutfix_nape/pair_back.png, left g2 before): stripe gone. Build + 2 frames 5 min.
- dots3 collected (NICO-TOP, tp_h3_s9 face 768, dotcount = red single-pixel fireflies): catch=0 57, flat 1, samples=64 134
  (default 56-57). Lighting fireflies that grow with samples, not the catchlight. dots4 queued: raytracing / fast GI / shadows
  off (cu.py eevee=<json>).
- Garrett g3 (gp_h6c_s3, NICO-TOP 875 s, review out/private/gate/garrett_g3/review1, dots discounted in --context): FAIL;
  15/27 items. MAJORs: colour pink-grey vs warm tan (cheek b* 11.5 vs 17.7), stubble sparse dashes (ref dense salt and
  pepper), no age texture (pores, crow's feet, forehead lines; fine rms .017 vs .028), brows translucent grey smear, iris
  saturated mint + no catchlight, lips pale, lash line dashed past the lid, lower-lid grey sliver, neck underside dark band,
  temple horizontal scratch marks. g4 = gp_h6c_s4 (undertone -.97 -> -.35, redness .4 -> .25, detail 1.3, wrinkles .9,
  oil .65, iris #6b6f66 limbal .4, lips blood 1.5 melanin 5.5 stack .9, brows #463f3a density 1.4 stack .5, stubble amount
  1 length 2.5 mm size 1.3 grey .55 shadow .3) queued on NICO-TOP with the nape view.
- CORRECTION: on a stacked head the face's colour is the stack's "base" x its multiply maps; skin.tone is the BODY (necktone
  fits it to the jaw). Changing undertone moves the neck, not the face, and breaks the join. Every head's fitted tone sits at
  undertone ~-1: that's the neck matching a cool stack, not a fit bug. Warm a face via the stack base, then refit the body
  tone: $S/cut/rebase.py <src> <dst> r,g,b [tone_src] (target jaw = old jaw colour x new / old base, linear). The g4 job with
  the undertone edit was cancelled; g4 = gp_h6c_s4b (s4's edits, base [.878 .780 .724] -> [.9 .785 .68]: Lab b 10.3 -> 17.2,
  a 6.5 -> 6.3; body tone refitted) queued with the nape view.
- dots4 (NICO-TOP, tp_h3_s9 face 768): use_raytracing off 0 dots, fast GI off 24, shadows off 56 (default 56). The red dots are
  EEVEE's ray-traced reflections / GI fireflies on NICO-TOP's GPU (the laptop has none). Raytracing off also dulls the look
  (sheen, catchlight, flatter shading: cut/dots_AG.png), so it isn't the fix. dots5 queued: clamp_surface_indirect 1 / 3 and
  raytracing off with fast GI kept.
- Garrett g4 (gp_h6c_s4b): 19/27 (g3 15): cheeks, brows, stubble numbers pass; nape on NICO-TOP clean (cut fix holds in the
  6-attribute Blender path). Review FAIL: overshoots: forehead too yellow (b 20 vs 14), lips peach-orange (melanin 5.5),
  brows a solid dark band, stubble long dark directional strands (2.5 mm), wrinkles .9 = smeared streaks at the temples and
  forehead top; still smooth (pores), no catchlight, black inked lid seam dashes, lavender lower-lid band, grey under-eye.
  g5 = gp_h6c_s5 (wrinkles .65, lips blood 1.6 melanin 4.5 stack .8, brows #4e4640 density 1.2 grey .45 stack .38, stubble
  1.4 mm size 1 grey .65, base [.89 .783 .70] + body refit) queued.

## Handover 2026-10-15 evening (projskin; next agent start here, then docs/notes/gates.md)
BRANCH projskin2, all committed, not pushed. Scratch $S=/mnt/data/hifipushie/projskin; new scripts in $S/cut/: rev2.sh <dir>
(the review with the NICO-TOP red-dot discount in --context, stage / not as briefed), diag.sh <model> <ref> <own> <tag> <cu
lines file> (one NICO-TOP job with custom cu.py lines; cu.py now takes eevee=<json>), rebase.py <src> <dst> r,g,b [tone_src]
(stack base + body tone refit: the way to change a stacked face's colour), dotcount.py, lab.py (Lab of sRGB triples), sk.py
<model> (skin params, compact).
DONE: atlas-cut blend (cutblend above; test_cut_continuous; nape clean on the laptop and on NICO-TOP). dots diagnosed:
EEVEE ray tracing on NICO-TOP (dots4); dots5 (clamp_surface_indirect 1 / 3, raytracing off + fast GI) queued: if a clamp
removes them without dulling the look, make it the stage default (spikes/garrett3/stage.py STAGE_EEVEE).
IN FLIGHT on NICO-TOP (wrappers run locally and block; on return they untar + eyecmp + skincheck into out/private/gate/<tag>;
then run cut/rev2.sh on the dir): dots5 ($S/jobs/dots5.log; untar by hand + dotcount), garrett_g5 (gp_h6c_s5), tess_s11
(tp_h3_s11), privA_g4 (private notes).
PER HEAD
- Garrett: g3 15/27 -> g4 19/27; g5 queued (see the g4 line above for its edits). Open after g5 lands: pores (skin still
  reads smooth at detail 1.3: the pores' depth / colour are the lever, skin.py micro "pores"), no catchlight (every head
  fails it: the stage's catch window or the cornea, try cu.py sheen=2 on one head), the black inked lid-seam dashes at the
  corners (lash roots / lashes painted line), lavender lower-lid band, grey under-eye crescent (check the stack's "shade" map
  as on private A).
- Tess (coordinator, 2026-10-15): eyes read ~30% short and lips flat = this stage. tp_h3_s11 = s10 + upper lashes
  taper_out -0.15 (new lashes option: outer quarter longer), flare 34, count 260, lower taper_out -0.1, eyes canthus .9, lips
  border .9 (crisper bow), gradient 2.2, roughness .16 (lower-lip volume via sheen). Judge: eye length and the visible fold vs
  her reference crops; bow peaks and lower-lip volume. The head moves ~0.5 mm at the lids (jaw round from tp_k10): re-seat later.
- Private heads: workspace/private_notes/skin_notes_projskin_full.md (private A g4 queued; private B: the blotches are shading, a
  variants job is next).
LESSON: on a stacked head skin.tone is the body; undertone edits move the neck only (cost a cancelled round).

## projskin round 2026-10-15 afternoon (successor of the evening handover)
- dots5: clamp_surface_indirect 1 and 3 leave all 56 dots; raytracing off (L) removes them but loses the forehead / nose
  sheen (mean diff small, the look flatter). dots6 queued: trace_max_roughness .3 / .5, ray_tracing_method PROBE, denoise.
- Catchlight: cu.py's window sat at 1.2 x up from the camera (~50 deg): its reflection lands on the cornea's top, under the
  upper lid: no catchlight on ANY head. Now catch_up .45 / catch_x -.35 by default (catch1 test: 1.2 / .3 / .5 on Garrett).
- Garrett g5 (gp_h6c_s5): skincheck tones 4/4 pass; review FAIL, 35 MAJOR: airbrushed (detail 1.3), matte, brows a
  translucent grey band (soft .5 + stack brows), stubble a grey wash, lips peach (melanin 4.5), grey-purple under-eye
  (stack shade .4), temple wavy smears, closed lid an inked line + dots past the corners, neck band. g6 = gp_h6c_s6
  ($S/cut/mk_g6.py: detail 2, oil 1, wrinkles by region, lips blood 2.2 melanin 2.5 dry 1.5, brows soft .15 density 2,
  stubble 1.6 / 1.35 grey .5 white, cheeks .5 neck .6, lashes #3b322c, painted lash line .35, tear .5, stack shade .1).
- Tess s11 (tp_h3_s11): review FAIL 29 MAJOR: brows dense slabs on an airbrushed underlay + a grey ghost arc at the tail
  (the photo's hair over her brow lands in the stack's brows map), socket grey arc / smoky lid (periorbital .4, eyelids 2.48),
  blotchy redness (stack .96), lips flat with a liner-hard border (border .9 overshot), closed lid a black bar, neck greyer
  than the face, nostrils light, pores one uniform stipple. DISPUTED: "lashes heaviest at the inner corner": in the crop
  the dense long lashes are at the outer corner (image left of the image-left eye); the reviewer swapped sides (it also put
  the brow's head fan at the tail). s12 = tp_h3_s12 ($S/cut/mk_t12.py): lips roughness .42 (Joe: NO gloss) border 1.4
  gradient 3 lower melanin .15 blood 1.15; brows density 1.4 soft .3 taper .7 #2a1e16, stack brows .3; caruncle 1.2,
  waterline .35, folds lid_fold .9 (tp_h3 had none; crease 1.35 vs 5.35 mm), eyelids 1.5, upper taper_out -.3, lower 60 /
  .04; stack redness .6 periorbital .2 shade .1. Open: the neck tone (body) vs the face.
- dots6: trace_max_roughness .3 / .5, PROBE, denoise: all 56 dots unchanged (pixel-identical to the default but PROBE).
  So not the ray-traced reflections: bright saturated red-orange single pixels (255,151,129), gone only with use_raytracing
  off (and 56 -> 24 with fast GI off). Suspect the horizon scan or a NaN path in the skin shader on NICO-TOP's GPU. dots7
  queued: fast GI AO-only, 96 samples, fast GI half res, clamp_surface_direct 2.
- Tess head approved: head/tess = tp_k19 (same topology as tp_h3). spikes/projskin/reseat.py <head> <skin model> <dst>: the
  head + the skin model's whole skin + base.lashes + base.head.lid_fold and shape.eye_bag (tp_k19 had neither: without
  lid_fold the crease map is EMPTY, crease_map reads base.head.lid_fold) + recrease. tp_k19_s12 = s12 re-seated (crease
  texels 1432 as on tp_h3). Next Tess rounds on tp_k19_s*; re-check the crease height (margin moved ~0.5 mm).
  NOTE: s12's skin.folds lid_fold .9 sits on top of the GNM lid_fold geometry: if s12 shows a doubled fold, drop it.
- CATCHLIGHT FOUND (local renders on the cached _g3_gp_h6c_s3 scene, out/private/gate/catchL): the eye's coat (1, rough .03)
  works; the window's mirror image sat under Garrett's low upper lid / lash fringe at every camera-relative height tried
  (1.2, .45, .1); at -0.2 it appears. cu.py now AIMS the window by the eyes (catch_aim=gaze default: mean eye -> eye_front
  axis; mirror point catch_deg -4 / catch_side -6 deg off it; the joint axis reads ~pupil-top, hence -4), window
  catch_size .4 x .5 (was .25 x .3: a pin) and sheen 1.6 (was 1). catch_aim=camera keeps the old catch_up / catch_x.
- Garrett g6 (gp_h6c_s6): 19 PASS; review FAIL 43 MAJOR: brows now black slabs (overshoot), stubble white sprinkle on a
  cool grey base, lips salmon, temple ripple stripes (3rd round: wrinkles .9 / .65 / .5 + regions), grey under-eye with
  streaks, matte (no catchlight: above), no nasolabial line, muddy band under the jaw. g7 = gp_h6c_s7 ($S/cut/mk_g7.py) +
  diag gp_h6c_s7w (wrinkles 0: are the stripes wrinkles?).
- Tess s12 (tp_h3_s12, old window): 14 PASS; review FAIL 33: matte everywhere (old pin window), lips now fully matte (.42),
  a 2nd dark crease stroke above the closed seam (= s12's skin.folds lid_fold on top of the GNM lid_fold: dropped), brows
  dense greyish bars, mottling (variation .6), iris saturated green + spokes, strip-lash fan (flare 34 / taper_out -.3 too
  far), red seam corners. Crease height open 1.9-2.0 vs 4.8-5.35 mm still. s13 = tp_k19_s13 (FIRST on the approved head
  tp_k19; $S/cut/mk_t13.py), rendered ref=tp_k19 own=tp_h3_lef2, with the gaze-aimed window.
- skin VERSION 11 (micro relief): blind reviews on Garrett (detail 2) and a private head (1.6) read the cells swatch as
  directional hatching / scales and the pores' dark tint as stubble dots. The cells' depth now follows detail only up to 1;
  above 1 detail deepens the pores; the stacked pores' tint is at most 0.3 (was 0.6 x detail). test_skin passes.
- A flat (albedo) tile on a private head showed no under-eye crescent at all: the grey-purple under-eye there is the head's
  form in the stage light (head-shape stage), not paint. Check flat=1 before painting an under-eye fix.
- DOTS FIXED (dots7 on NICO-TOP, tp_h3_s9 face 768): fast GI AO-only 57, 96 samples 192 (!), fast GI half res 0, direct
  clamp 2 (clamp_surface_direct) 0. The fireflies are DIRECT light samples (more samples, more dots). STAGE_EEVEE default now
  has clamp_surface_direct 2.0 (spikes/garrett3/stage.py): highlights' p99.5 unchanged, look the same (cut: KUV crop).
  Every judging render on NICO-TOP from commit after 0fa59aad has it; rev2.sh's red-dot line can go once rounds confirm.
- DRAWING (coordinator, from mouth_eye_bias; its 5 commits cherry-picked here, one VERSION conflict resolved): skin VERSION
  12. Eyes: the upper lash line's paint is fullest over its outer third and runs FRAME_PAST 2.2 mm past the outer canthus
  along its tangent, tapering; lower line weight LOWER_FRAME .8 (was .55); the inner canthus' dark point (CANTHUS_TIP
  1.2 mm wedge toward the nose, drawn in caruncle_wet, now [.64 .49 .47]); EYE_OCCLUSION .5. Lips: soft sheen on the
  lower pad (roughness - .1, >= .24; was - .22 down to .12 = the gloss), darker soft wet seam thinning to nothing before
  the corners, the vermilion's colour fades 70 % over the last CORNER_FADE 3 mm, the commissures a small rounded dark
  pocket (drawn inside lip_under_shade), UNDER_SHADE default 1. Shader budget test 43 -> 44 (under_shade on). test_skin
  passes. NOT judged yet: no render with v12. Lash GEOMETRY at the corners (sparser) not done: lashes.py, coordinate first.
- Lid / nostril orange (coordinator, export expr_r15): our own s12 render at the photo camera shows only a mild warm upper
  lid and pale (not orange) nostrils; the export's strong orange is mostly the export / EEVEE side. Ours: lower Tess's
  zones.eyelids (1.5 -> 1.0) in s14.

## Handover 2026-10-15 late (projskin; next agent start here, then docs/notes/gates.md)
Stopped at the 100-tool-call rule. BRANCH projskin2, committed, not pushed. Scratch $S=/mnt/data/hifipushie/projskin;
new: cut/waitjob.sh <tag> (wait for a gate / diag job), cut/mk_g6/g7.py, mk_t12/t13.py, mk_lt5/lt6.py, mk_jw5g.py,
spikes/projskin/reseat.py. Launch wrappers with `setsid nohup ... < /dev/null &`: plain nohup ones were killed (exit 143)
mid-queue and had to be requeued.
DONE today: dots fixed (stage clamp_surface_direct 2); catchlight found and fixed (gaze-aimed window, bigger, sheen 1.6);
skin v11 (micro caps) and v12 (eye / lip drawing); Tess re-seated on tp_k19 (tp_k19_s12, s13).
IN FLIGHT on NICO-TOP (collect in this order; each lands in out/private/gate/<tag>, then cut/rev2.sh <dir> review1):
privA_g6 (plain nohup: may have died; check its remote.log), garrett_g7 (gp_h6c_s7, pre-v11 code), tess_s13 (tp_k19_s13,
ref=tp_k19 own=tp_h3_lef2, v11 without the clamp), privB_g5, g7w (diag: Garrett wrinkles 0 -> are the temple ripple stripes
wrinkles?). catch2 is obsolete.
NEXT (order from the coordinator): 1. Tess s14 on tp_k19 with v12: from tp_k19_s13 (+ its review), eyes.occlusion .5
(it was .6 explicit), lips.under_shade 1.5, zones.eyelids 1.0; judge the eyes by the VISIBLE extent (canthus tip to the
frame's end), never on clay. 2. Garrett's LIPS only on v12 (his eye drawing waits for the garrett-eyes agent's approved
shape); g8 from g7's review (brows between g5's grey band and g6's black slab; stubble dark-dominant; temple stripes per
g7w). 3. Private heads (private notes). No head's skin has passed yet; nothing sent for approval.

## projskin round 2026-10-15 late (successor of the "late" handover)
- Collected: garrett_g7 (gp_h6c_s7) 19/27, review FAIL (lips: evenly spaced vertical stripes = lips.dry 1.5, pale
  peach-orange fading into the skin, upper L 62 vs 51; also brows charcoal bands, stubble sparse dark, skin smooth, wet
  specular, purple-grey under-eye crescent, inked closed seam). Private head g6 reviewed (private notes). tess_s13
  (tp_k19_s13) 14/27, review FAIL 24: brows ash-grey with a grey ghost over the outer half (the stack's brows map),
  L 56-58 vs 34-36; wet streaks (brow ridge, under-eye, cheek); flat tone (no warm under-eye, no cheek flush); pale pink
  lower waterline band, lower lashes invisible (60 x .04); orange-red closed-seam ends; lower-lip gloss; upper lip L 59 vs
  48; nostrils light (no paint lever: open). Crease height 6.0 / 6.35 vs 4.85 / 5.25 mm = the approved head's lid_fold.
- Queued on NICO-TOP (skin v12, first renders of it): tess_s14 = tp_k19_s14 ($S/cut/mk_t14.py: occlusion .5, under_shade
  1.5, eyelids 1.0 as briefed; brows #2a1c12 density 1.3 soft .4, stack brows 0, redness .75, periorbital .3, zones
  under_eye 1.6 midface_red 1.3, shading roughness .55, lips blood 2.2 strength 1.3 roughness .4, waterline .15, caruncle
  .9, lower lashes 80 x .06); garrett_g8 = gp_h6c_s8 (LIPS ONLY, $S/cut/mk_g8.py: dry .3, blood 2.6, melanin 2, strength
  .9, border 1.5, gradient 1.6); a private head (private notes).
- LESSON: base.lashes thickness .09 (mm) vanishes at the gate's 512 eye crops: keep >= .12.
- g7w (Garrett, wrinkles 0) beside g7 (wrinkles .25 by region): no temple ripple stripes in either at the face crop, and
  g7's review no longer names them: the stripes were g5 / g6's wrinkles (.9 / .65); g7's levels are clear of them.
- ALL FOUR heads' reviews (private B g5 too) read the skin wet / plastic and the catchlight a hard square dead centre in the pupil:
  the gaze-aimed window at catch_deg -4 / catch_side -6, sheen 1.6 sits nearly behind the camera, so every camera-facing
  patch of skin mirrors it. cu.py defaults now 4 / -12, sheen 1.0 (e10dd63f); tess_s14 carries a c10 bracket eye tile
  (catch_deg 10 / side -6). The first s14 / g8 / private submits were cancelled and resubmitted on it (+ a 2nd private
  head); $S/cut/collect.sh <tags> waits for each and runs the review (log out/private/gate/collect_r1.log).
- Joe's rule (coordinator, 2026-10-15): ALL renders on NICO-TOP by default (remote.sh, <= 12 GB, own folder, detached,
  many frames per submit); the laptop only for small check crops / flat / ID passes; 10 cores for all agents.
- Garrett EYES unblocked (garrett-eyes round 2: the lids are right, the slit look is TONE; ours vs photo sclera/lid
  .92/.90 vs 1.18/1.29, sclera/iris 1.47/1.45 vs 2.18/2.29, lid/cheek .88/.92 vs .79/.86). gp_h6c_s8 (version 2) = g8's
  lips + sclera #d6cec4 (was #b9b1a8), occlusion .3, iris #585c54 / inner #4e4c3e, zones eyelids 1.3, upper lashes
  taper_out .5 thickness .12; submitted as garrett_g8e (g8 lips-only cancelled). Measure with garrett_eyes/id contrast.py /
  litana.py: they read a prepared stage (prep.py <model> <stage>, lit_batch.sh renders locally): needs a prep for s8.
  CONFLICT to settle: skincheck's "sclera (L)" says ours is BRIGHTER than the photo on Garrett (40 / 33 vs 22) and Tess
  (37 / 53 vs 28), while garrett-eyes' ratios say Garrett's sclera is too DARK against the lid: skincheck's sclera box
  is probably not the visible white: it is placed by the PHOTO's landmarks on both images (our aperture differs) and is
  absolute L; garrett-eyes' ratios use each image's own eye frame against its own lid skin: trust the ratios.

## Handover 2026-10-15 night (projskin; next agent start here, then docs/notes/gates.md)
Stopped at the tool-call limit. BRANCH projskin2, committed, not pushed. Scratch $S=/mnt/data/hifipushie/projskin.
RULE (Joe): ALL renders on NICO-TOP (rset_remote.sh / remote.sh, <= 12 GB, own folder, `setsid nohup ... < /dev/null &`);
laptop only for small check crops / flat / ID passes. Cancel a queued batch: `OXIDEGEN_TOKEN=$(cat
~/.config/oxidegen/hifipushie-cloth-token) python3 /home/joe/dev/oxidegen/scripts/bundle/bundle_client.py cancel <batch>`
(batch id in out/private/gate/<tag>.remote.log). New: $S/cut/collect.sh <tags> (waits for each job, runs rev2.sh review1).
IN FLIGHT (all on cu.py e10dd63f: catch window 4 / -12 deg, sheen 1.0), detached:
- tess_s14 (tp_k19_s14, $S/cut/mk_t14.py; + a c10 bracket eye tile eyes_v0_c10.png) and two private heads (privA_g7, privB_g6):
  collector $S/cut/collect.sh -> out/private/gate/collect_r1.log (one line per head: checks | MAJOR count | verdict); the
  review is out/private/gate/<tag>/review1/review.md. If a line says NO PAIRS, run `$S/cut/rev2.sh <gate dir>` by hand once
  check.log has "measured items". (collect_r1.log also lists garrett_g8: that submit was CANCELLED, ignore it.)
- garrett_g8e (gp_h6c_s8 version 2: lips + eye tone) -> collector log out/private/gate/collect_r1g.log.
FIRST: read the s14 review. Did the new window fix the wet skin / square catchlight on every head? (eyes_v0 vs eyes_v0_c10
for the catch height.) Then loop Tess on the worst MAJOR.
NEXT, Garrett eye TONE (coordinator; garrett-eyes round 2 proved the lids right, the slit look is tone; drawing goes on
gp_h6c as is; sheet /mnt/data/hifipushie/garrett_eyes/out/private/sheet_r2.png, notes docs/notes/gnm_atlas.md
"## garrett_eyes" ROUND 2 on branch worktree-agent-a7bbb816b8d44034e):
  1. sclera ~1.2-1.3x the lid skin (colour + less occlusion shade; occlusion alone costs ~3 mm2 white per eye),
  2. iris ~2.2x darker than the sclera, 3. upper lid / cheek ~0.8, 4. lighter / thinner lashes at the outer upper margin
  (up to 4 mm2 of white). Photo: sclera/lid 1.18/1.29, sclera/iris 2.18/2.29, lid/cheek .79/.86, white 47/51 % of the
  non-iris opening (ours were .92/.90, 1.47/1.45, .88/.92, 23/7 %). g8e is the first try (sclera #d6cec4, occlusion .3,
  iris #585c54, eyelids 1.3, lashes taper_out .5 thickness .12). MEASURE with /mnt/data/hifipushie/garrett_eyes/id
  contrast.py / litana.py: they read a prepared stage (prep.py <model> <stage> -> out/id/prep.json, lit_batch.sh lit
  passes): make a prep for gp_h6c_s8 (or ask the garrett-eyes agent how). Then check Tess for the same sclera / iris tone
  issue (skincheck's "sclera (L)" is not usable for this: photo-landmark box, absolute L).
Garrett lips (g8: dry .3, blood 2.6, melanin 2, strength .9, border 1.5, gradient 1.6) ride in g8e. Private heads: private
notes (workspace/private_notes/skin_notes_projskin_full.md). No head's skin has passed; nothing sent for approval.

## Eye tone measure (2026-10-15 late, projskin)
- skincheck's "sclera (L)" item is GONE (a box placed by the photo's landmarks, absolute L: on ours it missed the visible
  white). Replaced by `eye_tone` in each image's OWN eye frame (its MediaPipe lid contours + iris): sclera = opening minus
  iris (0.5 mm in from the margins), as RATIOS: sclera / lid skin (tol 0.08 log), sclera / iris (0.12), upper lid / cheek
  (0.06), visible white fraction (> lid, 0.12 abs). On garrett_g7's face tile: photo 1.19/1.13, 1.61/1.70, .67/.77;
  ours .96/.80, 1.38/1.32, .96/1.06 (all FAIL, same direction as garrett-eyes' contrast.py). The face tile is coarse
  (sclera/iris reads lower than the eye-frame tool's 2.18/2.29): for Garrett the AUTHORITY is the eye-frame measure below.
- Eye-frame measure on gate renders, no laptop lit pass: $S/geye/id (garrett-eyes' prep / ana / contrast / litana with
  their own out dir $S/geye/out) + gtone.py <gate dir> <tag>: resamples the gate's face_v0 + eyesR_v0 + eyes_v0 tiles
  into prep.json's eye frame (all crops of the photo camera: scale + shift) -> lit_<tag>_v0.png; then
  `contrast.py <tag>`. prep made for gp_h6c_s8. Check: g7 R reads .90 / 1.47 (garrett-eyes' own dressed pass .92 / 1.47).
- Tess (tess_s13 tiles, new items) R/L: sclera/lid photo 1.04/1.07 ours .93/.99; sclera/iris 1.59/1.72 ours 1.83/1.92
  (iris contrast NOT short: our iris L 34 vs 25, but the sclera holds up); upper lid/cheek .74/.83 ours .90/.90; white frac
  .53/.55 ours .30/.44. So Tess shares HALF the problem: the upper lid skin is too light against the cheek (no lid
  darkening) and the sclera a little dim against it; the iris is fine. Fix on Tess = darker upper lid, not the iris.
STATE: measure in place; waiting for g8e / s14 collections. NEXT: g8e eye tone vs targets; s14 review; Tess eye tone.
- tess_s14 review (review1): 30 MAJOR, FAIL. New catch window did NOT fix the square catchlight (pair_3/4 MAJOR; catchlight
  peak-median 177 vs 95/112) nor the wet streaks in the 3/4 and side views (brow ridge, nose bridge, under the eye).
  WORST (5 MAJOR + the largest measured miss): brows grey-brown, glossy, thin: brow L 57.9/61.7 vs 35.9/34.3, and getting
  LIGHTER each round (s12 48/52, s13 56/58) as soft / the stack's brows layer went up / off. Others: lips colour + hard
  line past the corners, nostrils light brown, closed-lid seam red runs past the lids, black flat lash strip, pale
  lower waterline, no cheek flush (L), skin a bit light (chin L +7).
- s15 (mk_t15.py): brow_hairs layer MATTE in code (roughness .42 -> .68, specular .45 -> .22: a glossy hair picture under
  the catchlight read grey), Tess brows soft .4 -> .1, density 1.45.
STATE: s15 submitted to NICO-TOP (collector -> out/private/gate/collect_r2.log). NEXT: s15 brows; g8e eye tone.
- garrett_g8e (gp_h6c_s8 v2) eye TONE, eye-frame measure (gtone + contrast), R/L vs photo: sclera/lid 1.12/1.00 (1.18/1.29;
  g7 .90/.74), sclera/iris 2.06/1.93 (2.18/2.29; g7 1.47/1.25), upper lid/cheek .89/.94 (.79/.86), white frac .52/.25
  (.47/.51). Sclera and iris now near the photo; the LID is still too light vs the cheek (skincheck agrees: .94/1.04 vs
  .67/.77), L sclera dim (L white .25). Same lid fault as Tess. g8e review1: FAIL 32 MAJOR, eye-tone not among the worst:
  no age texture (crow's feet, forehead / nasolabial lines), stubble no grey + hatching up the cheek, brows a solid dark
  painted block (soft, sparse, grey in the photo), peach upper / grey lower face split, wet cheek sheen, GREY BRUISE
  SMUDGE under the eyes, bluish-white sliver on the lower inner lid (needs a pink waterline).
- garrett_g8f (gp_h6c_s9 = s8 + zones.periorbital .7, mk_g8f.py; + matte brows from code) SUBMITTED -> collect_r2g.log.
  RISK: periorbital also reaches the under-eye (the bruise MAJOR): if it worsens, use a lid-only darkening (eyelids zone
  colour is blood-red 1.9: Tess read orange; a melanin-only lid layer may be needed in skin.py).

## Handover 2026-10-15 late night (projskin; next agent start here, then docs/notes/gates.md)
Stopped at the tool-call limit. Branch projskin2, committed, not pushed. $S=/mnt/data/hifipushie/projskin.
DONE this session: skincheck sclera item replaced by eye-frame tone ratios (eye_tone; see "Eye tone measure" above);
eye-frame measure on gate renders ($S/geye/id/gtone.py + contrast.py, prep for gp_h6c_s8; re-run prep.py <model> only if
the head SHAPE changes); brow_hairs layer matte in code (all heads: brows were the top MAJOR theme on every head).
IN FLIGHT on NICO-TOP (detached, don't resubmit): tess_s15 -> out/private/gate/collect_r2.log; garrett_g8f ->
collect_r2g.log. Wait with ONE blocking wait (timeout 590 bash -c "until [ -s <log> ]; do sleep 30; done").
NEXT: 1. s15: did the brows reach L ~35 and lose the gloss? Then Tess's next worst: lips (hard line past the corners,
upper L 55 vs 48), catchlight square (177 vs ~100: cu.py's catch box; Garrett's reads 80-100, so it is Tess's eye
material/gaze), wet streaks in the side views. 2. g8f: `uv run python $S/geye/id/gtone.py $G/garrett_g8f g8f &&
uv run python $S/geye/id/contrast.py g8e g8f`; targets lid/cheek .79/.86. 3. Tess lid: same darkening once g8f shows
which way works. 4. Private heads: re-gate with the matte brows (private notes updated).

## MAJORs grouped by cause (2026-10-15 night, projskin; coordinator: step back before fixing one by one)
Source: the last review of each head (tess_s14, garrett_g8e, two private heads A / B: 30 / 32 / 30 / 29 MAJOR). Counts are
skin-stage MAJORs (OTHER STAGES left out), T / G / A / B.
| cause | what the reviews say | T | G | A | B | all |
|---|---|---|---|---|---|---|
| STAGE: the catch window (a 0.4 x 0.5 m rectangle, sheen 1, specular only) is mirrored by EVERY glossy surface | hard square catchlight; wet / white streaks on brow ridge, nose bridge, under the eye, cheekbone; grey sheen band through the brows; lashes pale and glossy; glossy patch on the lid | 6 | 2 | 4 | 5 | 17 |
| PAINT: brow layer (colour, density, softness, shape) | grey-brown / solid block / hard edges / too heavy or too thin | 4 | 4 | 3 | 2 | 13 |
| PAINT / zones: grey cast in shadowed / under-eye skin | grey bruise under the eye, grey-olive shadows, grey band under the jaw, grey chin | 2 | 3 | 4 | 0 | 9 |
| PAINT: lips (colour too grey-mauve or too pale; hard line past the corners; no moist highlight) | | 3 | 2 | 1 | 3 | 9 |
| GEOMETRY / normal detail: age texture, pores, fine lines (too little), hatch lines (too much detail) | | 0 | 9 | 5 | 0 | 14 |
| PAINT: stubble reach and colour | hatching above the beard line, no grey | 0 | 6 | 0 | 0 | 6 |
| GROOM: lashes (density, coverage on closed lids, strip look) | | 3 | 2 | 2 | 0 | 7 |
| PAINT: redness / flush / freckles missing; nostrils light; lid seam colour past the corners; waterline; neck break; iris | | 6 | 2 | 3 | 9 | 20 |
The single cause that reaches every head is the STAGE's catch window: it is a light for the eyes, but every glossy patch of
skin, brow and lash mirrors it (the s14 / g8e window moves changed where the streaks sit, not that they exist), and the
grey brow "sheen" is its rectangle on dark hairs. FIX (this round, all heads): the window lights ONLY the eyes part
(`light["lights"][i]["window"]["receivers"] = [part, ...]`: Blender light linking, works in EEVEE 5.1, checked on a
two-sphere scene; cu.py `catch_on=eyes` default, `catch_on=` = the old all-surfaces window). The skin keeps the key's
own broad window (gain .2) for its sheen. The catchlight's hardness is then the window's size / sheen alone: bracket tiles
catch_size / sheen ride along. After that, per head, one change per region from the rows above.
- Round r3 (one NICO-TOP submit for all four heads: $S/rset_batch.sh <tag> <spec file> = rset_remote.sh with a job folder
  per head; $EXTRA lines take @REF): s15 and g8f were still queued behind ~8 GPU jobs after 70 min and are superseded
  (cancelled). r3 = the linked catch window (all heads) + one change per region ($S/cut/mk_r3.py):
  Tess tp_k19_s16 = s15 (matte brows) + lips (melanin 22 -> 12, blood 3, border 1, under_shade .8, rough .32: grey-mauve,
  hard line past the corners, no moist highlight) + zones.periorbital .5 (lid too light); Garrett gp_h6c_s10 = g8f's s9
  (periorbital .7) + lower_cool 0 (grey bruise) + stubble grey .6 / cheeks zone .2 (no grey, hatching up the cheek) + brows
  soft .6 / density 1.1 / grey .6 (solid block) + lips blood 3.6 / melanin 1.5 / dry .15 (pale, barcode); private heads
  per the private notes. Bracket eye tile per head: catch_size .7 x .9, sheen .5 (tag cs) beside the default .4 x .5 / 1.
STATE: r3 queued (out/private/gate/r3.remote.log; reviews -> collect_r3.log). NEXT: r3 grouping table again (did the
linked window clear the catchlight / streak / brow-sheen MAJORs on every head?), gtone + contrast on garrett_g9 and tess_s16.
- Projection coverage (assembly's item: white hooks inside the nostrils of the exported head; evidence
  /mnt/data/hifipushie/assembly/seam/r19_nos_v33_v34.png, r19_nos_fix_uv.png): the photo's nostril-rim skin projected
  onto the inner wall counted as MEASURED, so the cavity fill never reached it. skin_project.make now leaves out the nose
  region's own cavity texels (ao < CAVITY_AO, unblurred), light or dark (rep "nostril_wall_left_out"). UNTESTED: takes
  effect on the next skin_project run of a head (projections are cached by hash); check the nostril crops + the report
  number on the next projection, and the export at the assembly agent's camera. Same row as "nostrils light" (Tess,
  private A) in the grouping table: re-project before judging those.

## Handover 2026-10-15 night (projskin; next agent start here, then docs/notes/gates.md)
Stopped at the tool-call limit. Branch projskin2, committed, not pushed. $S=/mnt/data/hifipushie/projskin.
DONE: MAJORs grouped by cause (table above); the stage's catch window now lights only the eyes (light linking,
blender_scene window.receivers, cu.py catch_on); one batched round r3 for all four heads ($S/rset_batch.sh, $S/cut/r3.txt,
$S/cut/mk_r3.py) with one change per region; s15 / g8f cancelled (superseded, queue was ~8 GPU jobs deep); nostril
inner-wall texels unmeasured in skin_project (untested).
IN FLIGHT (detached, don't resubmit): r3 batch -> out/private/gate/r3.remote.log; the collector runs eyecmp, skincheck
and the review per head -> out/private/gate/collect_r3.log (tess_s16, garrett_g9, privA_g8, privB_g7; reviews in <tag>/review1).
NEXT: 1. Per head, MAJOR counts by the table's rows, vs s14 / g8e / g7 / g6: did the linked window clear the catchlight,
streak, brow-sheen and lash-gloss rows? Compare eyes_v0 with the cs bracket tile (catch .7 x .9, sheen .5) for the
catchlight. 2. gtone + contrast on garrett_g9 and tess_s16 (`uv run python $S/geye/id/gtone.py $G/garrett_g9 g9 &&
uv run python $S/geye/id/contrast.py g8e g9`): lid / cheek targets .79/.86 (G), .74/.83 (T); did periorbital spread into
the under-eye (bruise row) now that lower_cool is 0? 3. Re-project one head with the nostril change and check the
nostril crops. 4. Next round: the biggest remaining rows (brows paint, age texture for Garrett, lashes), all heads in one
batch. If you touch the garrett-eyes tools, give them --out / --renders arguments (coordinator), don't sed-copy them.

## projskin round 2026-10-15 evening (successor of the "night" handover)
- Nostril re-projection checked (Tess's own projection tp_h3_lef2 -> copy tp_h3_lef2n, atlas crops in
  $S/nos/tess_nos_atlas*.png: before / after / confidence). The cavity-unmeasured change alone (222 texels) only softened the
  orange side streaks: the pale hook at the TOP of the nostril survived, and its confidence channel was "mirrored", not
  direct: the other side's rim skin was mirrored into the wall. Fix: skin_project.make blocks the mirror into the nose's
  cavity neighbourhood (regs nose & the CAVITY_MM-blurred cavity mask; the upper wall reads ao > CAVITY_AO, so `inner`
  alone missed it); rep "nostril_wall_mirror_blocked" (2309 texels on Tess). After: hooks gone, the wall takes the
  inpainted skin round it; left: faint hard-edged "ours" patches inside the cavity (in shadow when rendered) and a thin
  dark measured line in one nostril. tests/test_skin_project.py passes. Heads pick it up on their next skin_project run.
STATE: r3 still queued on NICO-TOP at 18:25 (submitted 18:03). NEXT: r3 grouping + gtone; next round with re-projected heads.
- Full re-projection of the other heads (own models -> <own>n copies) moved MORE than the nostrils on Garrett (neck fill,
  stubble dots, eyes: 194k texels > 20) and one private head (a slight tone shift over the whole atlas): drift since
  their 10-14 projections. So the nostril fix goes in ALONE: $S/nos/graft.py lays the re-projection's nostril box
  (atlas y 830-1000, x 900-1160, feathered 12 px; GNM's UV layout is shared) into each head's current albedo. Garrett
  graft crop $S/nos/g_graft.png: pale wall patch smaller; hard-edged pale "ours" patches inside the cavity remain (fill =
  the nose skin round it, so the wall is as light as the nose; if the render still shows hooks, the wall needs the fill
  darkened toward the cavity, not more exclusion). Main repo cherry-pick bef0229c (per-commit archive link) done here.
STATE: r3 running on NICO-TOP since 18:59 (collector waits). NEXT: r3 table + gtone, then r4 = graft + per-row fixes.
- r3 results (review1 MAJOR, all stages): Tess s16 18 (s14 30), Garrett g9 33 (g8e 32), private A 42 (30), private B 16 (29).
  CATCH-WINDOW ROWS CLEARED on every head: no wet streaks, no grey brow sheen, no glossy lashes / lid patch; the square
  catchlight is gone on T / G / B, one mention left on A (an eye crop). The linking OVERSHOT: the skin now reads MATTE
  (T "no specular response", G "matte like plastic", A "no oily shine on the nose", lips "no moist highlight").
  r3 rows, T / G / A / B (skin-stage MAJORs; duplicates per crop counted):
  | row | T | G | A | B |
  |---|---|---|---|---|
  | catch window (streaks, square, brow sheen, lash gloss) | 0 | 0 | 1 | 0 |
  | NEW: no skin sheen (linked window) | 2 | 1 | 1 | 1 |
  | brows | 3 (now near-black, dense: overshot) | 4 (translucent grey ribbon) | 7 | 0 |
  | grey / dark under-eye | 1 | 3 | 5 | 0 |
  | lips | 3 | 2 | 3 | 3 |
  | age texture / pores / micro-texture | 1 | 9 | 6 | 1 |
  | stubble | 0 | 6 | 3 (grey chin shading) | 0 |
  | lashes | 0 | 2 | 2 | 0 |
  | other paint (tone / flush / iris / sclera / waterline / lid seam / nostrils / neck break) | 5 | 6 | 9 | 9 |
  Garrett eye tone (gtone + contrast, g9 vs g8e), R / L: sclera/lid 1.13 / 1.01 (1.12 / 1.00; target 1.18 / 1.29),
  sclera/iris 2.06 / 1.93 (same; 2.18 / 2.29), lid/cheek .88 / .93 (.89 / .94; .79 / .86). periorbital .7 moved nothing
  measurable; the under-eye did NOT darken (cheek L .625 / .600 vs .628 / .602) but the review still reads a grey smudge
  there. Lid also "saturated orange" (eyelids zone 1.3). Garrett's micro-texture reads as diagonal DASHES (the stubble
  strokes: long, sparse) not pores.
- r4 = one batch, all heads ($S/cut/mk_r4.py + mk_r4_private.py, $S/cut/r4.txt; commit 124bbef8): every head gets the
  nostril graft + cu.py's new skin-sheen window (a second window, 1.6 x 1.6 m, gain .35, all parts: broad sheen without
  the small window's rectangle). Tess s17: brows density 1.0 / soft .35 / #4a3626, lips border .4 blood 4, waterline .5,
  iris #6a5a3c, zones under_eye 1.6 -> .9, midface_red 1.6. Garrett s11: stubble amount 2.2 / length .8 mm / size .8 /
  grey .75 / cheeks .6 (dense grey stipple to the sideburn), brows grey .3 / #3e352e / density 1.5 / soft .3, wrinkles
  amount .6 (forehead .8 glabella .9 crows_feet .9 under_eye .9), nasolabial 1.0, zones eyelids .7 under_eye .25
  nose_red 1.4, lips blood 4.5 dry .05. Private heads per the private notes. Nostril graft on the private heads changed
  more texels (19-31k vs 1-2k) because their re-projection drifted in tone inside the box too: watch for a tone seam
  round the nose tip.

## Handover 2026-10-15 evening (projskin; next agent start here, then docs/notes/gates.md)
Stopped at the tool-call limit. Branch projskin2, committed, not pushed. $S=/mnt/data/hifipushie/projskin.
DONE: r3 counted by row (table above: catch-window rows cleared on every head, but the skin went matte); Garrett eye tone
(lid still too light, periorbital no effect); nostril fix extended (no MIRROR into the nostril neighbourhood: that was the
pale hook) and grafted into each head alone ($S/nos/graft.py); main bef0229c cherry-picked; cu.py skin-sheen window; r4
submitted (one batch).
IN FLIGHT (detached, don't resubmit): r4 -> $S/out/private/gate/r4.remote.log; collector -> collect_r4.log (tess_s17,
garrett_g10, privA_g9, privB_g8). NICO-TOP took ~50 min to start r3 and ~55 min to run it.
NEXT: 1. r4 table by the same rows: did skin sheen come back WITHOUT the streaks / square (if streaks return: sheen .2 or
sheen_size 2.5)? Tess brows between r3's black and s14's grey? Garrett stubble stipple vs dashes, age lines visible?
nostrils dark on every head (if still pale hooks in the render: darken the fill toward the cavity, see the graft note)?
2. gtone g10 vs g9: if lid/cheek is still ~.88 / .93, the lid needs a melanin-only lid layer in skin.py (periorbital and
the blood-red eyelids zone don't reach the target). 3. Then the next rows, all heads in one batch.

## projskin round 2026-10-16 (successor of the evening handover): measured targets per row
Coordinator's process change: every change in a round needs a MEASURED target (a crop statistic of the photo against ours),
recorded as target / before / after per row; a change that worsens its row is reverted.
- New skincheck rows (spikes/projskin/skincheck.py, all crop statistics on face_v0 at the photo camera, photo landmarks):
  brow coverage (fraction of the brow box > 12 L below the forehead), brow hair / skin (L of those pixels / forehead L),
  brow strand texture (fine rms); dots (stubble / pores: dark components vs a 3-px blur: per cm^2, median mm^2, elongation)
  on chin, jaw_R, cheek_R; age lines (log-L band-pass 1..4 px rms) at crow's feet, forehead, under-eye; eye RIM (0..1 mm
  outside the landmark opening: waterline + lash line), eye LID (1..3 mm above the margin), SOCKET (3..7 mm) as Lab minus
  the cheek's; sclera blotch (L cv, a* p90-p10); opening h / w from each image's own landmarks. Measured on copies of the
  r3 renders ($S/out/private/meas/<tag>).
- r3 values, photo | ours (T = tess_s16, G = garrett_g9; private heads in the private notes):
  | row | T R / L | G R / L |
  |---|---|---|
  | rim - cheek dL | -17 -21 / -12 -14 | -23 -21 / +5 +6 |
  | lid - cheek dL | -14 -9 / -5 -3 | -19 -13 / -3 +1 |
  | lid - cheek db* | -3.0 -4.5 / +1.1 -1.1 | -0.7 -2.7 / +1.9 +1.9 |
  | brow coverage | .92 .86 / .68 .60 | .95 .97 / .70 .67 |
  | brow hair / skin L | .44 .40 / .45 .43 | .58 .57 / .71 .69 |
  | brow strand rms | .085 .081 / .099 .105 | .090 .084 / .034 .036 |
  | crow's feet band rms | .061 .031 / .021 .006 | .052 .037 / .030 .018 |
  | forehead band rms | .0079 / .0072 | .0172 / .0094 |
  | stubble jaw_R dots/cm^2, mm^2 | | 81, .116 / 49, .029 |
  | sclera blotch L cv | .27 .23 / .22 .22 | .21 .23 / .15 .16 |
  | opening h / w | .351 .331 / .352 .335 | .272 .261 / .297 .289 |
  Reads: (1) the RIM is the largest eye-region miss on every head (G +27 L, private A +17..+21, T +5..+7, B +2..+4): the
  photo frames the opening with a dark lash line, ours with the pink waterline layer (0.5 opacity, blood 3.5): that is the
  lash review's "pink / lilac rim" and why the opening reads TALL: Tess's opening h / w from landmarks equals the photo's
  (.352 vs .351), so the tall read is TONE (the light rim widens the visible opening), as on Garrett. (2) Tess's sclera is
  NOT blotchier than the photo's on the gate render (cv .22 vs .27), her socket matches (dL, da*, db* within 1 except L
  socket -4 vs -2): the lash review's blotchy sclera / orange socket are on the ga_tess EXPORT (its own material bake), not
  the projected skin; routed back as an export item. (3) Tess's brows are as DARK as the photo's (hair / skin .45 vs .44);
  what differs is coverage (.68 vs .92) and the hard drawn edge: r3's "near-black" read is the hard edge, not the value.
  (4) The upper lid is too light on T / G / A, and the photo's lid is a little LESS red / yellow than the cheek: a neutral
  cool darkening, not melanin (T(melanin) for dL -13 costs db* +7).
- Code: skin.zones.lid_shade (off by default): a neutral-cool multiply [.7 .7 .74] on the eyelid zone, opacity .6 x zone
  (zone 1 ~ x0.82, 1.66 ~ x0.7); test tests/test_skin.py::test_lid_shade_zone. Replaces the planned melanin-only layer
  (the measure says melanin warms it the wrong way).
STATE: r4 on NICO-TOP (queued). NEXT: r4 table by rows + the new rows; r5 targets from the photo values above.

## Handover 2026-10-15 20:45 (projskin; next agent start here, then docs/notes/gates.md)
Stopped before the tool-call limit with r4 NOT yet started on NICO-TOP (queued since 20:05 behind hgf5253 / dgrr-192421;
r3 took ~50 min to start and ~55 to run). Branch projskin2, committed, not pushed. $S=/mnt/data/hifipushie/projskin.
DONE: skincheck rows for the unmeasured rows (brows coverage / hair-skin / strands, stubble dots, age lines, eye rim / lid /
socket Lab vs cheek, sclera blotch, opening h / w), measured on the r3 renders (table in the section above, private heads
in the private notes); skin.zones.lid_shade (neutral-cool multiply, measured hue; test); r5 plan with the measured targets
in $S/cut/mk_r5.py (helper lid(k, need_dL) picks the zone from the measured dL). The lash review's Tess items: the pink
rim = the waterline layer (rim dL short on every head; the opening's h / w from landmarks matches the photo, so "too tall"
is tone); blotchy sclera and orange socket do NOT show on the gate render (export material: route to the export / lash
agent); no visible crease = crease darkness .24 / .18 vs .32 / .29 (passes tol .12 but low: raise lid fold shade if the
lid_shade change doesn't carry it).
IN FLIGHT (detached, don't resubmit): r4 -> out/private/gate/r4.remote.log; collector (pid 1573024) -> collect_r4.log; it
runs the NEW skincheck rows too (run.sh uses this worktree).
NEXT: 1. `offload wait rs_r4`, then the collector; r4 table by the cause rows (catch / sheen streaks: if back, cu.py
skin-sheen gain .2 or size 2.5) AND the new measured rows; keep wins, revert regressions row by row (private A first).
2. Garrett lid: g10's "upper lid / cheek" and "eye lid - cheek (L)" rows; lid_shade from lid(k, need_dL). 3. Rim slope from
Tess s16 -> s17 (waterline 1 -> .5), then waterline / lashes per head to the photo's rim dL. 4. r5: all heads, one batch
($S/rset_batch.sh r5 $S/cut/r5.txt); merge main first if RESTART.txt says the render-speed fix (one Blender per job,
--stage) has landed (not yet at 20:40; main has b35d437b, a gates note).

## r4 landed 21:27 (projskin, same session; next agent start here)
- review1 MAJOR r3 -> r4: Tess s17 18 -> 27 (WORSE), private A 42 -> 31, private B 16 -> 20 (worse), Garrett g10 = NO RESULT:
  every g10 render is MAGENTA (Blender's missing-texture colour: face_v0 81 %, mouth 100 %), with no error in the job log
  (garrett_g10.joblog.txt). skincheck then crashed on eyecmp's None (fixed: n/a row). FAIL, not a measurement: the
  pack (jobs/garrett_g10/ws, 38 MB) or the grafted albedo (nos/graft.py on gp_h6c_s10 -> s11) lost an image. NEXT: open
  gp_h6c_s11 locally (flat pass of one tile) to see which texture is missing; compare its image ids with ws/_images.
- Tess measured rows r3 -> r4 (photo | r3 | r4): brows got LIGHTER and sparser: darkness L 35.9 / 34.3 | 46 / 57 | 60 / 65,
  coverage .92 / .86 | .68 / .60 | .62 / .55, hair / skin .44 | .45 | .63, strands .085 | .099 | .069: REVERT r4's brows
  (density 1.0 / soft .35 / #4a3626) to s16's; the hard-edge read needs another lever than soft + density. Rim dL
  -17 / -21 | -12 / -14 | -14 / -15 (waterline 1 -> .5: better by ~1.5 L per -.5 waterline: waterline 0 gives only ~-3:
  the rim needs the lash line darker, not just less pink). Lid, under-eye, lips, chin tone, catchlight 175 vs 95 unchanged.
- Private A: fewer MAJORs; brow_L coverage and lips upper worse by the measure. Private B: rim and lid R worse
  (waterline .8 made the rim lighter), lips upper worse: revert B's waterline and lips change. Details in private notes.
STATE: r4 counted (Garrett failed: magenta). NEXT: Garrett's missing texture; r5 = revert Tess brows + B waterline / lips,
keep A's r4, then the mk_r5.py plan (lid_shade, rim via lash line) with the measured targets; one batch.

## Handover 2026-10-16 (projskin, after "r4 landed"; next agent start here)
- Merged main (one Blender per job, packed stage, cloth cache): cu.py keeps one shoot per run with the gaze-aimed catch
  window, the skin-sheen window, receivers, eevee and tag; blender_scene._light_rig carries window receivers (light
  linking; their collections go with the rig) and no transmission or volume from diffuse-0 lights.
- Garrett g10 MAGENTA: reproduced LOCALLY (gp_h6c_s11, one 256 px face tile: 82 % magenta, exit 0, no error), so the
  pack is not the cause. The stage's scene.blend has every image (29 images, 21 in the body material, 7 attributes,
  1105 nodes). The one layer s11 adds over s10 (69 -> 70 skin layers) is wrinkle_lip_lines (wrinkles.amount .25 -> .6):
  an EEVEE shader that fails to compile renders magenta. Test queued: gp_h6c_s11x = s11 with lip_lines 0 -> out/mag2
  (check.txt). If that is clean, the cause is shader size, and a layer budget or merge in paintnodes is the real fix (not done).
- Magenta check: render.missing_texture_fraction / magenta_tiles + spikes/projskin/rendercheck.py (writes <dir>/ERROR,
  exit 1); tests/test_rendercheck.py. In scratch, rset_batch.sh runs it before eyecmp / skincheck and fails on a nonzero
  job exit; rev.sh refuses a set with ERROR. On g10 it flags 7 of 16 tiles, and 0 on every other head and on every reference.
- skin hair.lashes.width (x the lash line's radius): the rim lever (waterline moved rim ~1.5 L only).
- r5 IN FLIGHT (detached, don't resubmit): $S/chain_r5.sh -> out/private/gate/chain_r5.log. It waits for out/mag2, runs
  cut/mk_r5_run.py (+ mk_r5_garrett.py, mk_r5_private.py), then ONE batch rset_batch.sh r5 cut/r5.txt with a flat mouth
  tile per head. Garrett drops out if lip_lines 0 is still magenta. Not packed with --stage (the stage is re-meshed there).
  r5 changes, target / r4: Tess s18: brows REVERTED to s16, then thickness 1.25, density 1.8, soft .2 (coverage
  .92/.86 vs .62/.55, darkness 36/34 vs 60/65); lashes width 1.6 (rim -17.3/-20.5 vs -13.7/-15.3); lid_shade .58 (lid
  -14.2/-8.6 vs -5.7/-2.9). Garrett s12: lip_lines 0, lid_shade .5 (lid/cheek .79/.86 vs r3 .88/.93), stubble size 2.2
  (dots .116 mm^2 vs r3 .029), lashes 1.0 / #2a221d / width 1.4 (rim -23/-21 vs r3 +5/+6); crow's feet first measured in
  r5. Private A g10 = r4 + lashes width 1.6 (rim); B g9 = r4 with waterline and lips REVERTED to g7, plus lashes width 1.3.
- Doubled lower lip (coordinator): it is in Tess's EXPORT albedo (ga_tess v38c+, assembly/mh/v38c_sheet.png: a lighter
  lip-coloured band below the vermilion in the smile). Tess's gate render (tp_k19_s17 mouth_v0) shows ONE border. Not yet
  decided whether the cause is the bake (the export mesh's lip against the projection) or our lip paint falloff. The r5 flat
  mouth tile (mouth_v0_flat) gives the neutral albedo at the photo camera: if it shows no band, route it to assembly
  as the bake. Measuring script: $S/cut/lipedge.py (edge count down the centre; noisy on lit tiles, use flat).
- Not done: sheen-streak check on the r4 crops; tests test_skin_project / test_skin not re-run after the merge (run one
  file per process).
STATE: r5 launched (detached). NEXT: read out/mag2/check.txt; `offload wait rs_r5`; count MAJORs by row per head against r4
(T 27, A 31, B 20, G none), keep wins and revert losses; lip band from the flat tile; paintnodes layer budget if mag2 is clean.

## Magenta fixed at the source (2026-10-16, projskin, after "Handover 2026-10-16")
- out/mag2: gp_h6c_s11x (s11 with lip_lines 0) rendered clean, so the cause was s11's one extra layer. Measured cause:
  the body material read 15 vertex attributes (wpos, wnrm + 13 packs of three scalars, hp0..hp12). Blender 5.1.2 EEVEE
  fails at 15 with "EEVEE: Material ... uses too many attributes" (synthetic probe $S/cut/attrlimit.py: 14 compiles,
  15 fails). The material renders magenta and the job still exits 0.
- Fix: paintnodes.PACK = 4. Scalars go four to a FLOAT_COLOR attribute (the fourth is the Attribute node's Alpha).
  paintnodes.MAX_ATTRS = 14 makes a part over budget a SpecError at compile time that names the layers reading the most
  inputs. blender_scene._paint_material counts the built tree's attributes as a backstop (RuntimeError over 14).
  gp_h6c_s11: 15 -> 12 attributes. Checks: s11x renders PIXEL-IDENTICAL to the old code (face_v0 256 px, max diff 1/255).
  s11 (lip_lines .6, the magenta one) renders clean (rendercheck ok). Local checks are in $S/out/mag4.
- A second magenta found on the way: the first re-sync of an existing stage left 55 image datablocks for 26 files
  (x.001 ... x.006, one per image node). Linking failed with "Too many fragment shader texture samplers". The
  mechanism was not pinned down: a unit test of save / reload with relative paths reuses the image even on the old
  code. Hardened: Nodes.image compares realpaths and prints "hp image: reloading" when it replaces a same-named image.
  The material build raises if one file and colour space sit in several datablocks. The next sync had 26 images.
- Tests: tests/test_material_budget.py (pack of four, budget error, Blender reads a FLOAT_COLOR pack's four channels,
  image reused after a save). After the main merge: test_skin 16 passed, test_skin_project 5, test_rendercheck 2.
- Sheen-streak check on r4: no wet streaks or brow sheen on any r4 head (reviews and Tess 3/4 / side crops). The
  opposite problem remains: skin is MATTE on every head (Tess, A: MAJOR "no specular on the nose tip / bridge /
  forehead"). One MINOR on A: pale scratch-like streaks at the brow tail and temple. The profile eye's chrome stripe
  (A, B) is the eye material, not skin sheen.
STATE: magenta fixed and tested; r5 (rs_r5) running on NICO-TOP at 3ade4244 (old code: Garrett s12 has lip_lines 0, so
it is safe). NEXT: collect r5 by rows; lip band from the flat tile; r6 with Garrett lip_lines back and skin sheen up.

## r5 collected, lid_shade was dead, r6 launched (2026-10-16, projskin successor; next agent start here)
- Merged origin/main (c7a22b92). r5 (rs_r5) collected: rendercheck clean on all 4 heads (Garrett too: magenta gone).
  `$S/cut/rowcmp.py <before> <after>` = skincheck rows side by side (FAIL count, WIN / LOSS flips, moves > 25 % of tol).
  NB the r4 sheen rows were scored with the old tol 4.0: their "LOSS" in rowcmp is the tolerance change, not a render change.
- MAJORs (blind review totals incl. OTHER-stage lines) r4 -> r5: Tess 27 -> 43, A 31 -> 38, B 20 -> 24, Garrett 37 (r4 magenta).
  Rows: Tess FAIL 36 -> 34: brows WIN (darkness 59/65 -> 43/43 vs photo 36/34, coverage .62/.55 -> .86/.77 vs .92/.86), rim
  WIN (L -15.3 -> -21.0 vs -20.5). But the review flips the brows from "too light grey strokes" to "solid dark block, blunt
  front, sticker": an overshoot the rows don't see (no softness / inner-texture row). New on Tess: closed-lid seam "cut"
  (pale sliver + orange line, pairs 5/6), under-eye darkness missing, mottle. A / B numbers: workspace/private_notes.
- DEAD LEVER (found here): with a skin.stack, skin.layers dropped every "zones" layer except stack_*, so zones.lid_shade
  never reached a stacked head: r5's lid_shade (Tess .58, Garrett .5) moved nothing (Garrett lid / cheek .94 -> .97, worse
  by noise). Fixed (02733194): lid_shade passes the stack filter; test_lid_shade_survives_a_stack. under_eye / eyelids /
  periorbital zones are still dropped under a stack ON PURPOSE (they painted blotches over its base). Lesson: after an edit,
  check the layer exists ($S/cut/haslayer.py <models>) before spending a batch on it.
- Garrett r5 (s12): tones / lips / texture now measured (magenta fixed): FAIL 31. stubble size 1.1 -> 2.2 changed nothing in
  "dots size" (.029 mm^2 both): probably the measure's pixel floor on the 512 cheek tile, NOT verified. Rim + 6 / + 7 vs photo
  -23 / -21 (lashes width 1.4 moved nothing). Review: stubble sparse dots vs dense grey coverage; crow's feet smeared ripples.
- Lower-lip doubled edge (item 3): the FLAT albedo tile (tess_s18/mouth_v0_flat) shows ONE border (lipedge: 1 edge, no light
  band under the vermilion). So it is not in the projected texture: it is the export bake. Routed to the coordinator.
- Tess export eye region (item 2, lashes r11 lit crops, $S/cut/eyebox.py ref ours [centres]): export lid band (1-3 mm above
  the margin, lashes in) L -38.6 / -34.4 below the cheek vs photo -26.4 / -23.8 (TOO DARK in the export), while the gate
  render's lid is TOO LIGHT (skincheck upper lid / cheek .92 / .93 vs .74 / .83). Under-eye lighter than the photo in both
  (export -16.7 / -15.5 vs -20.9 / -18.7). Lower-lid band beside the iris, export: 12-17 L lighter than the photo over ~12 px
  (the "white-pink shell" is LIGHTNESS, a* matches within ~2), brighter on the image-right eye (75 vs 61 L at the rim):
  the two eyes differ there. Eye opening: h / w passes (.362 vs .351), so "flatter and wider" is tone, as on Garrett.
  NOT done: lids with lashes hidden on the export (needs an export render job), the pale shard above the inner upper lid.
- r6 (LAUNCHED, detached: $S/chain_r6.sh -> out/private/gate/chain_r6.log; ends "R6 CHAIN DONE", r6_rows.txt + reviews):
  makes tp_k19_s19 (brows density 1.5 soft .4; oil .2 -> .6; lid_shade .58 now live), gp_h6c_s13 (lip_lines .6 back;
  lid_shade 1.3; shading.roughness .42), private A g11 / B g10 (oil, lid_shade; private notes), builds the 4 stages locally
  and packs them (rset_batch.sh STAGE=1 -> pack_model --stage _g3_<m>; falls back unpacked on a name mismatch), ONE batch
  with the flat mouth tile and the GAME-DISTANCE SET: face_v0/1 at 234 px (tag game1m) and 78 px (game3m) = the pixels a
  face covers at 1 m / 3 m at 1080p, 60 deg vfov. cu.py now tags the reference crops too (face_v0_ref_game1m.png).
- Game-visible vs close-up-only (by the rule, until the game sets are read): VISIBLE at 1 m: matte skin, brows dark /
  solid, lip colour, hue / neck shift, under-eye darkness, Garrett's stubble coverage. CLOSE-UP ONLY: pore speckle, closed
  lid seam sliver, iris limbal ring, catchlight shape, lash comb, crow's feet ripples, sclera blotch.
- Tests: test_skin (+1 new) passes the new test; the full test_skin / test_skin_project / test_rendercheck /
  test_material_budget run was still going under capped at handover ($S/cut/tests_r6.sh -> out/r6tests.txt).
STATE: r6 running. NEXT: read r6_rows.txt + reviews: keep wins, revert losses (oil = streak watch; Garrett lid_shade 1.3
may overshoot); read the game1m / game3m tiles and reclassify MAJORs; export lids with lashes hidden (assembly / lashes job).

## r6 collected, two more dead levers, new brow / stubble rows, r7 planned (2026-10-16, projskin2; next agent start here)
- r6 tests ($S/out/r6tests.txt): test_skin, test_skin_project, test_rendercheck, test_material_budget all exit 0.
- MAJORs (blind review incl. OTHER) r5 -> r6: Tess 43 -> 34, Garrett 37 -> 33, A 38 -> 39, B 24 -> 21.
  GAME-VISIBLE (classified by `$S/cut/r7/gameclass.py <review.md>...` -> gate/r6_gameclass.txt, rule read off the 1 m sheet
  gate/r6_game1m_sheet.png): Tess 21 -> 14, Garrett 19 -> 20, A 18 -> 21, B 10 (r5 not parsed). Close-up-only (catchlight,
  iris fibres, lash / waterline bands, the closed-lid seam and its shadow, nostril interiors, pore speckle, mottle, lip
  edges) do not block (gates.md). The game-visible set at 1 m: brows (block, hue), lip colour / material, overall hue /
  redness / neck break, T-zone sheen, Garrett's stubble coverage (and grey stubble cast on A), under-eye shadow.
- DEAD LEVERS in r6 (rows didn't move): (1) lid_shade: live after 02733194 but laid FIRST, and stack_base (normal mix,
  opacity 1) painted over it. Fixed: it now goes after the last stack_ layer (test asserts the order). (2) sheen: Tess oil
  .2 -> .6 moved sheen nose 5.2 -> 5.1 (photo 9.1); Garrett shading.roughness .42 moved 4.5 -> 4.5 (photo 11.1). NOT yet
  found why: check whether rough_* layers / shading.roughness reach the gate render's material (cu.py) before spending a
  batch on sheen. Lesson repeated: `$S/cut/r7/order.py <model>` prints the layer ORDER and mixes: an opaque normal-mix
  layer after a lever kills it.
- Tess brows r6 (density 1.5, soft .4) = LOSS on rows (darkness 42.9 -> 49.3 vs 35.9, hair/skin worse, inside spread worse):
  soft raises brow_shadow (+.45 soft), the uniform zone shadow that fills the gaps. Revert soft to 0.
- NEW ROWS (skincheck, 817e671d), the "incomplete checklist" items: brow edge width (20-80 % darkening, mm), brow inside
  spread (L p90 - p10 inside the mask), brow front / middle darkening (medial fifth vs middle); stubble as coverage: beard
  chin / jaw - forehead (L, chroma), beard hair coverage (frac of px off their 3-px blur by > 4 %), area-weighted dot size,
  light dots. All four heads FAIL inside spread (ours ~14-17 vs photo 25-38) and most fail front / middle (.6-1.1 vs
  .35-.57): that is the sticker. Edge width passes on Tess (so softness of the outline isn't it), fails on Garrett / A.
  Garrett beard coverage .21 / .23 vs photo .50 / .48 (the review's "sparse dots vs dense grey").
- Dot size FLOOR verified (cut/r7/dotfloor.py, synthetic dots at u 5.87 px/mm): .029 mm^2 = ONE pixel; true dots of .008 and
  .03 mm^2 read .029 / .058. Garrett's .029 = sub-pixel stubble, not a measure bug; the area-weighted row and coverage
  are the targets now.
- New lever hair.brows.shadow (x the skin-level brow shadow opacity; skin_features; test_brows_shadow_scales_the_skin_shadow).
- Export lids (coordinator, x52 lashes hidden; cut/r7/lidx.py, own MediaPipe landmarks per image): export lid band is
  LIGHTER than the cheek (+4 / +6; lashes add only 2-4 L at the margin), photo -14 / -9, gate s18 -5.5 / -4.3: the lid is
  too LIGHT everywhere. Rim asymmetry is the export's (gate matches the photo's direction, export reverses it): routed.
  r6 also lightened Tess's image-right rim (-21.0 -> -14.9 vs -20.5): LOSS, watch in r7.
- Under-eye: under-eye / cheek ratio is ours 1.10-1.27 vs photo 1.05-1.20 (ours lighter, Tess + Garrett); the review's
  "grey bruise" blobs are on the open-eye crops (pair 3), the closed-lid shadow is close-up-only.
- r7 PLAN (one batch, stages packed, as chain_r6.sh; mk_r7_run.py from mk_r6_run.py; tp_k19_s20 / gp_h6c_s14 / A g12 / B g11):
  Tess: brows soft 0, shadow .35, density 1.5 (target inside spread ~31-38, front/middle ~.4, darkness ~36); lid_shade 1.0
  (target lid - cheek -14 / -9; it is live now). Garrett: brows shadow .35; lid_shade 1.3 (now live: check overshoot
  against .67 / .77); stubble toward coverage .5 (density / size up, sub-pixel now: make hairs >= 2 px at the 768 tile).
  A / B: brows shadow .4, lid_shade per private notes. Sheen only after the dead-lever check. Run haslayer / order.py on
  every r7 model before the batch.
STATE: r6 collected and classified; lid_shade order fixed; brow shadow lever + new rows in. NEXT: sheen lever check, then
the r7 batch above.

## r7: the lever check before the batch found why three levers were dead (2026-10-16, projskin2 successor; next agent start here)
- Gate rule followed (gates.md, main 04987715): a LOCAL two-value check per lever before the batch. Tool:
  `$S/cut/r7b/lev.sh <base> <tag> <ref> <own> <checklist> <variant json>` (saves lv_<tag> = base + dotted skin edits, seeds its
  stage from the base's stage so the sync is ~100 s, renders face + both eyes at view 0, 384 px, lit, 16 samples, then
  skincheck); chains `$S/cut/r7b/levchain*.sh`, results `$S/out/private/lev1` (check 1) and `lev` (check 2); compare with
  `cut/rowcmp.py <A> <B> --all`. A render is ~2 min on the laptop.
- CHECK 1 (code as handed over): lid_shade .58 -> 1.2 moved Tess lid - cheek -6.1 -> -6.2; a new under-eye lever 0 -> 1 moved
  under-eye / cheek 1.09 -> 1.10; brows.shadow 1 -> .35 moved nothing; roughness .55 -> .40 moved nose sheen 4.9 -> 4.4 (the
  wrong way); Garrett roughness .42 -> .30 moved 3.5 -> 3.5. Only stubble moved (density 1, size 3: coverage .20 -> .25).
- CAUSE 1 (lid_shade, under-eye, brow shadow): they were "_pre" layers. Pre layers are composited per vertex into the base
  the SHADER starts from (paintnodes.compile), and stack_base is a shader image layer at opacity 1 over its coverage: it
  paints over every pre layer, whatever the dict order (so 78d55dc4's reordering could not work). Fixed: over a stack,
  lid_shade, under_eye_shade and brow_shadow drop "_pre" (skin.AFTER_STACK / OVER_STACK; test). The brows' "solid sticker"
  was therefore never the skin-level brow shadow: under a stack it was invisible until now. soft 0 is what raised inside
  spread locally (Tess 14 -> 22-28, ref 30-38).
- CAUSE 2 (roughness): the rough_* layers (opacity .6-.85, T-zone, cheeks, patches) were offsets from the OIL-derived base,
  so skin.shading.roughness only set the part base under them. Fixed: they offset from shading.roughness when set (test).
  And rough_tzone's mask includes the eyelids (weight .8): oil also shines the lids (r6: Tess oil .2 -> .6 lightened the
  image-right rim -21.0 -> -14.9 and the lid -4.3 -> -2.0). r7 reverts Tess oil to .2.
- CAUSE 3 (sheen, NOT a material fault): in the gate rig the fitted suns have specular 0 (skin_project.stage_light: their
  discs lay in the cornea) and the catch window lights only the eyes; the skin's only highlight is the large dim sheen window
  (cu.py skin_sheen .35, 1.6 m). A smaller window (sheen_size .4) gave the same nose sheen to 0.1 L. So no roughness or oil
  value can move the sheen row in the gate; it is a rig decision (a specular key on the skin only, by light linking, as the
  catch window is linked to the eyes). Routed to the coordinator; r7 has no sheen change except A's roughness (now live).
- NEW lever skin.zones.under_eye_shade (off by default; a slightly violet multiply on the under_eye zone, kept over a stack
  like lid_shade): the "under_eye" zone is dropped under a stack, so nothing could move the under-eye row.
- CHECK 2 (with the fixes): the levers are live on the model (Garrett A/B diff: -15 L over the lid / under-eye blocks), but
  the eye rows are CONFOUNDED: skincheck's eye_tone "cheek" band (9-12 mm under the iris centre) lies in the under_eye zone,
  so darkening the under-eye makes "lid - cheek" read LIGHTER (Garrett lid_shade 2.0 + under_eye_shade 1.5: lid R -8.2 -> +4.6
  while the lid itself got darker). Clean single-lever reads: lid_shade .58 now non-pre moved Tess lid -6.1 -> -9.2 (R),
  -2.7 -> -5.4 (L); Garrett lid_shade 1.3 moved -2.9 -> -8.2. Garrett at lid 2.0 + under 1.5 read as dark ovals (bruise).
  Measurement follow-up: move eye_tone's cheek band below the under-eye zone (or measure lid against the forehead).
- tests/test_skin.py: its __main__ block sat in the middle of the file, so the last tests (lid_shade survives a stack, brows
  shadow) never ran as a script; moved to the end. Full run exit 0.
- r7 LAUNCHED ($S/chain_r7.sh, log out/private/gate/chain_r7.log; models tp_k19_s20, gp_h6c_s14, A g12, B g11; gate dirs
  tess_s20, garrett_g13, privA_g12, privB_g11): Tess brows soft 0 / shadow .6, oil .2, lid_shade 1.0, under_eye_shade .4;
  Garrett brows shadow .6, stubble density 1 / size 5, lid_shade 1.8, under_eye_shade .5; A / B lid_shade (now live), brow
  shadow 1 (both read lighter than the photo), A roughness (private notes for values). Not changed: the rim band at 1 mm
  (no separate lever; lid_shade's eyelid zone reaches it), sheen (rig).
STATE: three dead-lever causes fixed and tested (0c7f70e9, 29b457f2); r7 batch running. NEXT: collect r7 (offload wait rs_r7,
then r7_rows.txt + reviews + gameclass), count game-visible MAJORs per head, keep wins / revert losses; the sheen rig and the
eye_tone cheek band go to the coordinator.
- HANDOVER (tool-call clock reached while rs_r7 ran on NICO-TOP; ~15 min a head, heads in series, then 4 reviews): the chain
  is self-contained (renders, rendercheck, skincheck, reviews, rows). To collect: `offload wait rs_r7`, then
  `grep "R7 CHAIN DONE" $S/out/private/gate/chain_r7.log`; rows `gate/r7_rows.txt`; game-visible MAJORs
  `$S/cut/r7/gameclass.py gate/<head>.rev...md` (as r6, -> gate/r7_gameclass.txt) against r6's Tess 14 / Garrett 20 / A 21 / B 10.
  Judge the eye rows with the eye_tone cheek-band confound in mind (look at the eyes pairs, not only the lid rows); revert any
  head whose lids read as dark ovals.

## eye_tone measure fix: the lid's reference band moved out of the under-eye zone (2026-10-16, projskin2 successor 2)
- Coordinator decision (b). skincheck's "upper lid / cheek" compared the lid with a band 9-12 mm under the iris centre,
  INSIDE skin.FACE under_eye (lm_lid_lower -0.13 io, z radius .13 io: it reaches ~18-19 mm under the lower-lid margin at
  grow 1.2). The bands now live in spikes/projskin/eyetone.py (importable; skincheck imports it): the reference is the upper
  cheek 21-26 mm under the lower-lid margin's middle landmark (145 / 374), +-6 mm about the iris centre. Row renamed
  "upper lid / upper cheek {R,L}" so no one compares it with old numbers. tests/test_eyetone.py: clearance against
  skin.FACE (io .068, grow 1.2, > 1.5 mm) and a synthetic under-eye darkening leaves the band alone (the old band moved).
  Overlay check $S/out/private/eyeband_tess_s19.png (red = old band, green / cyan = lid + new band): clean cheek skin on both.
- r5 and r6 gate dirs re-read on the fixed measure (old json kept as skincheck_pre_eyefix.json); r7's chain runs skincheck
  from this worktree, so it reads the fixed measure itself. Photo vs ours (lid / upper cheek): Tess R .51 vs .77 (r6),
  L .58 vs .86; Garrett R .58 vs .72, L .65 vs .80; A, B in the private gate. Every head's lid is too LIGHT on the fixed
  measure too (ours .05-.28 above the photo; on Garrett the old band overstated it: .97 / 1.04 vs .67 / .77).
- Seen on the overlay, NOT fixed: the lid band (1-3 mm above the margin) sits on the photo's lashes on Tess (dark), so the
  photo's lid number includes lashes; our render's lashes are thinner. Read the eye pairs, not the lid row alone.

## Sheen rig fix: a skin specular key (2026-10-16, projskin2 successor 2; coordinator decision (a))
- RIG FIX. The fitted light (skin_project.stage_light) has NO key on these heads (report views.*.light.key is None for
  tp_h3_lef2 and gp_h6c_lef): it is all soft suns with specular 0, so "specular 1 on the fitted key" had nothing to act on.
  Instead cu.py takes `skin_key=<gain>` (default 0 = the old rig): a highlight-only sun (diffuse 0, specular 1, no shadow,
  angle skin_key_angle 14 deg) from the fitted light's DOMINANT direction (energy-weighted mean of its suns), energy gain x
  their total, light-linked to the skin part only (skin_key_on, default body). blender_scene: a sun with "receivers" is
  light-linked like a window (hp_sun<i>_receivers, cleared between views). The catch window stays linked to the eyes.
- Local two-value proof (`CUX="skin_key=v" cut/r7b/lev.sh`, view 0, 384 px, 16 samples; chains cut/r7b/skchain*.sh; out/private/lev):
  Tess (ref nose 9.2 / forehead 4.0): skin_key 0 -> .5 -> 1.0 = nose 4.6 -> 3.8 -> 6.5, forehead 2.6 -> 4.8 -> 6.7 (forehead
  passes at .5). Garrett (ref 11.6 / 5.5): 0 -> 1.0 = nose 3.5 -> 22.8 (overshoots), forehead 2.4 -> 7.6. The rows MOVE.
  Cost: the 14 deg highlight is broad and lifts the median too: Tess tone forehead L 82.4 -> 86.9 -> 90.6 (ref 78.0), nose
  78.9 -> 80.6 -> 82.1 (ref 75.4); that is also why Tess's nose sheen dipped at .5 (p50 rose with p99). Strip
  $S/out/private/skinkey_tess.png (photo | 0 | .5 | 1.0): .5 reads as a soft sheen on forehead, bridge, lips, chin, no
  wet streaks; 1.0 washes the forehead. r8 proposal: skin_key .5 with skin_key_angle 6 (a tighter highlight, less wash)
  as the batch variant beside .5 / 14; Garrett ~.4-.5 (1.0 doubled his nose sheen).
- The sheen rows are only comparable between rounds rendered with the same skin_key: r7 and before are skin_key 0.

## Stubble count lever (2026-10-16, projskin2 successor 2)
- hair.stubble.count (hairs per area x, .25-4, default 1 left out of the options so existing maps keep their cache keys;
  skin_marks.stubble_map scatters HAIRS_PER_M2 x count). Why: density is a 0..1 share that saturates at 1 where the beard
  is full (stubble_options clips it to 1), so no density value made Garrett's beard denser. test_stubble_count_adds_hairs.
- Local check (Garrett r7 model gp_h6c_s14 = size 5, 384 px; gsk0 = count 1): coverage chin / jaw_R .34 / .40 -> count 2
  .39 / .47 -> count 3 .34 / .49 (photo .53 / .52). count 2 moves +.05 / +.07 per step (meets the >.05 bar, barely, on the
  chin); count 3 saturates on the chin (dense short hairs blur into a smooth field at this pixel size). With grey .75 the
  extra hairs are mostly pale: beard chin - forehead L -16.3 -> -14.3 -> -13.3 (photo -14.8, still passing). r8: count 2.
  The gate renders are larger than 384 px, so read the r8 row, not this number, for the absolute.

## r7 collected on the fixed eye measure; HANDOVER (2026-10-16, projskin2 successor 2; next agent start here)
- rs_r7 done, chain_r7 done (renders, rendercheck, skincheck from this worktree = the FIXED eye_tone measure, reviews).
  "review exit 3" in gate/<head>.rev.log = verdict FAIL, not a crash; reviews are gate/<head>/review/review.md.
  Rows (gate/r7_rows.txt, r6 re-read on the fixed measure first, so they compare): FAIL rows Tess 48 -> 42, Garrett 42 -> 38,
  A 53 -> 52, B 57 -> 56 (of 96). No row flipped to LOSS. Tess: brow darkness WIN (49.3 -> 33.9, ref 35.9), inside spread
  WIN both (14 / 17 -> 24.5 / 29.2), lid / upper cheek better (.77 -> .71, ref .51), under-eye better. Garrett: lid / upper
  cheek WIN both (.72 -> .60, ref .58), beard coverage WIN chin .23 -> .45 (ref .48) and jaw .21 -> .43 (ref .50) from size 5
  alone at gate size. A / B: lid rows better / one WIN, brows better (private gate for numbers).
- GAME-VISIBLE MAJORs (gameclass, gate/r7_gameclass.txt) r6 -> r7: Tess 14 -> 8, Garrett 20 -> 21, A 21 -> 16, B 10 -> 13.
  Keep all r7 changes for Tess and A. Garrett +1 and B +3 are NOT read yet (tool clock): read their GAME lines in
  r7_gameclass.txt against r6_gameclass.txt; check the eyes pairs for dark ovals (lid_shade 1.8 + under_eye_shade .5 on
  Garrett) and B's brows (shadow 1) before deciding to revert. Tess's remaining GAME items: lip colour / matte lips, no nose
  sheen (the rig, below), cheek blotchiness, brow colour / solidity, jaw-underside grey band, neck colour break.
- Stubble: r7's size 5 already brought Garrett near the coverage target at gate size; count 2 (local +.05 / +.07) would
  likely overshoot the jaw a little: r8 count 1.5 at most, or none.
- r8 PLAN (one NICO-TOP batch, mk_r8_run.py from mk_r7_run.py on the r7 models; renders with CUX-like cu.py kw added to the
  batch lines): (1) skin_key .5 (angle 14) for all heads and a skin_key .5 angle 6 variant on Tess + Garrett (sheen rows
  move; watch tone forehead / nose L, which the broad key lifts); (2) Garrett stubble count 1.5; (3) whatever the Garrett / B
  review read says to revert; (4) Tess lips colour (pink-coral, lighter) and lip gloss as the next game-visible item.
  Run order.py / the lever check on any NEW lever before the batch (gates.md).
STATE: eye measure fixed (50e92e4d), sheen rig skin_key + stubble count in and proven locally (30ee8e2f, 030a1f69), r7
collected. NEXT: read Garrett / B r7 reviews (keep / revert), then launch r8 as above.

## r8: r7 reviews read, three levers found / fixed, lid measure lash-free, r8 launched (2026-10-16, projskin2 successor 3)
- r7 READ. Garrett +1: the new MAJORs are "eye surround colour" / "lid colour" / under-eye "cool grey bruise": the cool
  lid_shade colour [.7,.7,.74] at zone 1.8 and under_eye_shade .5. Row "eye sock - cheek" (3-7 mm ABOVE the margin, the
  lid's fold) b* went .5 -> -5.6 (photo -.1). B +3: the new items are matte / nose sheen / cheek (the rig, untouched by r7:
  review variance); its socket rows went cooler the same way (lid_shade .9). B's brows: every brow row better, kept.
- NEW skin.zone_colors.{layer: [r,g,b]} (test): a zone layer's colour replaced. Lever check (384 px local, cut/r7b/lev.sh;
  out/private/lev r8g*, r8b*): Garrett socket b* cool -5.2 / neutral [.745,.726,.716] -2.0 / warm [.8,.71,.64] +3.7 ->
  interpolated [.762,.721,.693] measured -0.3 / -0.1 (photo 0 / -1.3). under_eye_shade .5 -> 0 moved under-eye / cheek
  1.17 -> 1.18 (it did nothing measurable; the reviewer saw a bruise): off. Tool cut/r8/lidcol.py (Lab shift <-> multiply
  colour; the render's b* moved ~2x what a plain multiply predicts, so calibrate with two renders, not the model).
- LID MEASURE (eyetone.lash_line, test): at face distance (~4.5 px/mm) the photo's lashes on a hooded lid merge into a dark
  band 1-2.5 mm tall, and the fixed 1-3 mm band sat on it (overlay out/private/lashov_tess_s20.png: red = lash line, green =
  skin band). Lid skin is now read 0.3-2.3 mm above the lash line found per column; rows "upper lid skin / upper cheek" +
  "lid band lash share" (ref .22 / .26 on Tess's photo, ours ~0: our lashes don't form a band). A black top-hat (thin dark
  lines) found nothing in the photo: the lashes are a band, not lines, at this size. Tess's targets moved .51 / .58 -> .60 /
  .69 (ours .71 / .79): the lid gap was mostly lashes. r7 gate dirs re-read (old json skincheck_pre_lash.json).
- LIPS WERE DEAD UNDER THE STACK: lips_upper / lips_lower are "_pre" layers, stack_base covers them (as lid_shade before):
  Tess's lips.melanin 12 changed nothing. NEW opt-in skin.lips.over_stack (test). Live: melanin 12 -> upper L 39 (photo 47.6),
  melanin 3 / blood 3 / strength 1 -> 52; lower 55.4 a* 24 (photo 61 / 16). r8 Tess: melanin 5, blood 2.5, lower.blood .8.
  Gloss (lips.roughness, dry) NOT checked: a lever for r9.
- SHEEN (skin_key): FAIL on the stated goal. skin_key_angle 6 gives the SAME median lift as 14 (Tess forehead L 86.9 at .5
  both): the lift is the specular lobe of roughness .55, not the sun's disc. Tess's forehead is already +4.4 L over the photo
  at skin_key 0, so no key value keeps it within +-2 (.25: +6.8, sheen forehead 3.1 vs 4.0, nose 4.0 vs 9.2 unmoved);
  key .5 + roughness .40 hit nose sheen 9.0 (ref 9.2) but forehead sheen 9.4 (ref 4.0) and L 90.6. Tess: NO key in r8; her
  forehead / nose albedo (+4.4 / +3.5 L) is the lever to fix first. Garrett key .3 angle 6: nose 11.9 (ref 11.6), forehead
  3.3 (5.5), L +2.9 (base +1.8). B key .3: nose 8.3 (8.2), forehead 3.1 (3.6), L +0.6 over base. A: over the photo's sheen
  WITHOUT a key (nose 7.7 vs 4.2; .3 -> 12.5): no key. Sheen rows compare only between renders with the same key.
- Stubble count: not changed (r7 coverage .45 / .43 vs .48 / .50 already within tol; count 2 overshoots the chin).
- r8 (chain_r8.sh, log gate/chain_r8.log, batch rs_r8; models tp_k19_s21, gp_h6c_s15, privA_hd_g13, privB_hd_g12; gate dirs
  tess_s21, garrett_g14, privA_g13, privB_g12; scripts cut/mk_r8_run.py, mk_r8_private.py, cut/r8.txt with a 7th column of
  per-head cu.py kw, rset_batch.sh now reads it): Tess lid_shade 1.4 + neutral colour, lips over_stack; Garrett
  under_eye_shade 0, lid colour, skin_key .3/6; A unchanged (control: review variance); B lid colour, skin_key .3/6.
  The chain writes r8_rows.txt (vs r7 re-read on the lash-free measure) and r8_gameclass.txt.
STATE: zone_colors (4059d6e1), lash-free lid (9b2a16b2), lips.over_stack (560ac621); r8 running. NEXT: `offload wait rs_r8`,
`grep "R8 CHAIN DONE" gate/chain_r8.log`, count game-visible MAJORs vs r7 (Tess 8, Garrett 21, A 16, B 13; A is the
no-change control: its delta is the review's noise), keep / revert per row; then Tess forehead / nose albedo (-4 L) before
any key on her, lip gloss lever check, and B's brow hue (khaki / grey-green: no row measures brow hue yet: add one).

## r9 (2026-10-18, projskin2 successor 4): r8 collected, review chain fixed, tile reviews, levers
- r8 REVIEWS DID NOT RUN: every gate/<head>/review/review.md was "You've hit your weekly limit" (bin/review's `claude -p`
  account, until 2026-10-19 13:00 MT) and gameclass printed GAME 0 for all four heads. FIX (scratch, not in the repo):
  `/mnt/data/hifipushie/bin/review` now exits 4 and writes "REVIEW FAILED (no VERDICT line ...)" when claude fails or no
  VERDICT line comes back (old copy projskin/review.bak_r9); `rev.sh` prints "REVIEW FAILED: did not run" for exit != 0/3;
  `cut/r7/gameclass.py` prints "REVIEW FAILED" for such a file instead of zeros. "review exit 3" alone was never a crash test.
- r8 ROWS (gate/r8_rows.txt; FAIL rows Tess 44 -> 42, Garrett 40 -> 39, A 52 -> 52 (control, no change), B 58 -> 55):
  - Tess lips.over_stack + melanin 5 / blood 2.5: upper WIN (dE 8.7 -> 5.7). Lower worse inside tol (3.5 -> 5.7): a* 22.2 vs
    16.8, too red. KEEP; r9: lower.blood down.
  - Tess lid_shade 1.0 -> 1.4: lid rows better (L -6.0 -> -7.2 R, -3.2 -> -5.5 L; ref -14 / -9) but the socket (3-7 mm above
    the margin) went darker MORE than the lid did: LOSS R -11.3 -> -14.2 (ref -8.2), L -8.7 -> -11.9 (ref -2.0). The eyelid
    zone mask peaks at the fold, not at the lash line: this lever can't make the lid darker without the socket. REVERT to 1.0
    (keep the neutral colour: socket b* better both sides). A lash-line-weighted lid mask is the real lever (NEXT).
  - Garrett skin_key .3/6: sheen nose WIN (4.6 -> 10.5, ref 11.1), forehead better. Its side effects are relative rows: the
    key lifts the cheek / forehead, so "eye sock - cheek" L (LOSS R, worse L) and "beard jaw - forehead" L (LOSS) went darker
    without any paint change. KEEP the key; those rows compare only between renders with the same key.
  - Garrett lid colour [.762,.721,.693]: socket b* WIN both (-5.6 -> -0.2, -4.5 -> 0.2) but lid L a* / b* LOSS (+1.9 / +2.2
    warmer than ref). r9: halfway to the old cool colour, [.754,.724,.705] (both rows inside tol by linear interpolation).
  - B skin_key .3/6: sheen nose / forehead WIN; brow_L rows a little worse (likely the key on the skin around it). KEEP.
- LOOK (r8, feature tiles; bin/review still refused, so fresh blind subagent reviewers, images only, the gates brief, no
  captions; tiles = the gate pairs minus the full-face frames: gate/<head>/tiles_r9/, reviews gate/<head>/review_r9.md).
  GAME-visible MAJORs (gameclass): Tess 8, Garrett 14, A 14, B 10 (all FAIL). Not comparable 1:1 with r7's bin/review counts
  (another reviewer, no full-face frames). Shared cause across ALL FOUR heads: BROWS (near-black / uniform blocks, blunt
  heads, no fade): row "brow front / middle darkening" FAILs (Tess .88 / .59 vs .46 / .34, Garrett 1.07 / .82 vs .57 / .47)
  while "darkness" passes: the mean is right, the distribution isn't. Then lips (Tess coral-pink matte, Garrett pale, A
  mauve-brown, B dark plum), lip sheen (all), Garrett stubble read as salt-and-pepper DOTS + no beard-zone shadow, A tone
  cool pink-mauve + violet-grey socket, B tone salmon + neck break, Tess iris olive (row iris FAIL: ours L 34 b* 18 vs 25 / 11).
- NEW ROW "sheen lip_lower (L p99 - p50)" (skincheck; the lips.roughness lever had no row): Tess 4.1 vs photo 11.5, Garrett
  5.7 vs 9.7. Lever checks running (cut/r9_lev.sh: lips.roughness .32 / .15; cut/r9_lev2.sh: brows shadow .3, density 1.0 +
  a darker, less yellow iris), out/private/lev/r9*.
STATE: r8 read, chain fixed, tile reviews in, lip-sheen row added; lever checks running. NEXT: read r9_lev*.log, then r9 batch.
- LEVER CHECKS (Tess, 384 px local, out/private/lev r9lr32 / r9lr15 / r9bs3 / r9bd1):
  - lips.roughness .32 -> .15: lip sheen 4.2 -> 5.3 (photo 11.8). ALIVE but weak; colour rows unchanged. Something else caps
    the lip highlight (lips.dry 2.5? the light's size?): check dry and the specular level next.
  - brows.shadow .6 -> .3: "front / middle darkening" .94 -> .94: DEAD for that row (hair / skin +.01). brows.density 1.5 -> 1.0:
    front / middle also unmoved (.94); hair / skin .39 / .36 -> .46 / .45 (ref .44 / .40), darkness L 36.7 -> 45.7 (FAIL on L).
    NO existing brow parameter fades the brow's head: the blunt-club read (all four heads' top GAME item) needs a NEW lever,
    a density / shadow ramp over the inner ~25 % of the brow's length (skin_features brows, `taper` is tail-side only).
  - iris #6a5a3c / inner #5c4a2e -> #584a34 / #4c3e2a: iris L / b* 34.5 / 18.4 -> 29.1 / 14.8 (ref 25.5 / 10.9), PASS. It
    exposed "sclera / iris" 1.79 -> 2.09 (ref 1.58): the SCLERA is too bright (~L 60 vs ~40 in the photo), a row of its own.
- r9 LAUNCHED (chain_r9.sh, log gate/chain_r9.log, batch rs_r9; models tp_k19_s22, gp_h6c_s16, privA_hd_g14, privB_hd_g13; gate
  dirs tess_s22, garrett_g15, privA_g14, privB_g13; cut/mk_r9_run.py, mk_r9_private.py, cut/r9.txt): Tess lid_shade 1.4 -> 1.0
  (revert), lips.lower.blood .8 -> .6, lips.roughness .15, brows.density 1.25, iris darker / less yellow; Garrett lid colour
  halfway [.754,.724,.705]; A and B unchanged (two controls for review noise under the new tile reviewer).

## Handover 2026-10-18 (projskin2 successor 4; next agent start here, then docs/notes/gates.md)
1. COLLECT r9: `grep "R9 CHAIN DONE" /mnt/data/hifipushie/projskin/out/private/gate/chain_r9.log` (else `offload wait rs_r9`).
   Rows: gate/r9_rows.txt (vs r8). Expect the chain's reviews to say REVIEW FAILED until bin/review's account resets
   (2026-10-19 13:00 MT): then re-run tiles: copy each gate/<head>/pairs pair minus "full face" into gate/<head>/tiles_r9/
   (NN_A_reference / NN_B_result + regions.txt; pairs.txt has no trailing newline: read the last line too) and spawn one
   fresh blind reviewer per head with the gates brief (prompt in this session: images only, write review_r9.md in the
   bin/review format, VERDICT line), then `cut/r7/gameclass.py <abs path>` (it needs absolute paths).
   r8 tile counts to beat (GAME-visible): Tess 8, Garrett 14, A 14, B 10; A and B are unchanged controls in r9 = noise.
2. Keep / revert per row: Tess socket rows should come back (lid_shade revert); iris row should PASS; watch brow darkness L
   (density 1.25) and lips lower a*. Garrett: lid a* / b* and socket b* both inside tol is the goal.
3. NEXT LEVERS (prove each locally with cut/r7b/lev.sh before a batch): (a) brow head fade (NEW, all four heads' top item;
   row "front / middle darkening"); (b) lip sheen: lips.dry, specular; (c) lid darkening weighted to the lash line, not the
   fold (Tess lid L still -7 vs -14 while the socket is already too dark); (d) sclera brightness row + lever; (e) Garrett
   stubble reads as salt-and-pepper DOTS + no beard-zone shadow: no row measures dot contrast (add one: stubble white-dot
   share / dot L spread vs photo), then stubble shadow / colour; (f) A: tone cool pink-mauve + violet socket, B: salmon tone,
   neck break, brow length (A / B numbers in the private gate only); (g) B's brow hue row (from r8 NEXT, still open).
4. Tone note for other threads: the hair-garrett sheets render ~1 stop darker than these; this thread's light is the
   reference for tone (they added `ev=` to match; not checked here).
STATE: r9 running on NICO-TOP; chain reports review failures explicitly now. NEXT: item 1 above.

## r10 (2026-10-18, projskin2 successor 5): the brow head fade
- r9 (rs_r9) started on NICO-TOP only at ~10:26 (the chain's stage syncs ran first); collect later (Handover item 1).
- BROW PROFILE, DESCRIBED FROM THE PHOTOS (skincheck now prints `PROFILE brow_X ref / ours`: darkening mass per column in 10
  bins medial -> lateral, over the middle's mean, and a row "head rise (mm, 20-80 % of middle mass)", tol .4 log). On the
  r8 renders (tess_s21, garrett_g14, privA_g13, privB_g12) every photo brow ramps up from ~.2-.4 at the inner end to the body
  at ~40-50 % along: ref bins 1-5 Tess R .37 .54 .75 .92 1.01, Garrett R .40 .74 .93 1.05 1.11, A R .29 .42 .66 .88 .99,
  B R .17 .38 .68 .87 1.04; head rise 4.3-6.8 mm. OURS reach the body by 10-20 %: Tess R .70 1.05 1.10, Garrett R 1.01
  1.12; rise 0.0-2.8 mm (B R 4.6 the one pass). (B's brow_L photo profile .01 .. 2.2 is a lit / masked oddity: don't fit it.)
  The mean darkness passes because the club and a fading head have the same mean.
- LEVER `hair.brows.head` (share of the length over which the inner end fades in, by hairs LEFT OUT, the count kept by
  drawing the rest elsewhere) + `head_density` (share kept at the inner end, default .05) in skin_swatch.brow_image.
  2D check on the drawn picture (the alpha saturates where hairs overlap, so a mild thinning shows nothing: head .4 /
  density .25 gave bins .41 .84 1.10): head .65 / .05 gives ~.24 .6 .82 .99 1.05 (photo ~.3 .5 .75 .9 1.0); coverage -13 %.
STATE: lever built, 2D-proven; Tess 3D lever check running (out/private/lev/r10h0 vs r10h65). NEXT: read it, then batch.
- SCLERA LEVEL row (skincheck "sclera level R/L (eye_tone)", ratio tol .1): on the r8 renders ours / photo = Tess 1.43 / 1.33,
  Garrett 1.24 / 1.11, A 1.25 / 1.09, B 1.55 / 1.62 (all too bright; "sclera / lid skin" passed on Tess because the lid is
  too light as well). Lever: skin.eyes.sclera (sRGB hex) scaled by ~1 / ratio; to be proven locally.
- LIP SHEEN, why lips.roughness was weak: the lower lip's sheen pad (skin:lip_sheen, opacity .8, painted after lips_lower)
  sets roughness max(lips.roughness - .1, .24): below .34 the pad's highlight never changed. NEW `lips.sheen` (the pad's
  roughness, no clamp) and `lips.specular` (pad + lower lip specular level; skin default .36). Row: sheen lip_lower
  (Tess 4.1 vs 11.5, Garrett 5.7 vs 9.7; A / B pass). To be proven locally.
- BROW LEVER, 3D CHECK (Tess tp_k19_s22, 384 px local; out/private/lev r10h0 vs r10h65; sheet out/private/lev/r10_brow_sheet.png
  = photo | before | after): head .65 -> profile R .33 .54 .74 .83 1.00 (photo .39 .57 .78 .94 1.02), L .17 .35 .55 .75 .96
  (photo .22 .42 .72 .91 1.00); front / middle R .94 -> .44 (ref .49) PASS, L .57 -> .26 (.32) PASS; head rise R 1.2 -> 6.5 mm
  (6.2) PASS, L 2.8 -> 7.1 (5.9) PASS. ALIVE. Side effect: darkness L R 36.7 -> 50.1, L 41.8 -> 53.8 (ref ~35) FAIL, coverage
  and hair / skin FAIL (the box mean includes the head; the body reads unchanged on the sheet). By eye: the inner ends are
  sparse, feathered single hairs now (the photo's read), the club is gone. Next check: head .55 + density 1.5 (r10h55d15).
STATE: brow lever proven; compensation check + sclera / lip check (r10sl) queued locally. NEXT: read both, batch r10.
- COMPENSATION (r10h55d15: head .55, density 1.25 -> 1.5): profile R .27 .49 .78 .89 1.05, L .12 .31 .62 .80 .98; front /
  middle and head rise PASS both; darkness L R 43.5 / L 46.4 (ref 35; tol 8: R just out); coverage R pass, L .71 vs .85.
  BEFORE / AFTER TILE: out/private/lev/r10_brow_before_after.png (photo | r9 model | head .55 + density 1.5). Look: the inner
  ends are sparse, feathered hairs growing up (the club is gone); the body is still a heavier, thicker band than the photo's.
- SCLERA + LIPS CHECK (r10sl: sclera #d4c9bc -> #999187 (x.72), lips.sheen .14, lips.specular .6): sclera level R .568 -> .463
  (ref .403), L .562 -> .441 (.439) PASS; sclera / iris R 2.05 -> 1.66, L 2.12 -> 1.69 (1.58 / 1.70) PASS both; sclera / lid
  skin FAILs now (R .80 vs 1.02): the lid skin is too light, its own open fault (lid darkening at the lash line, item c).
  Lip sheen 5.1 -> 7.1 (photo 11.8): ALIVE, still short (next: specular .8-1 / sheen .1, watching Joe's "wet plastic").
- r10 BATCH (chain_r10.sh, waits for R9 CHAIN DONE; log gate/chain_r10.log; cut/mk_r10_run.py, mk_r10_private.py, cut/r10.txt;
  models tp_k19_s23, gp_h6c_s17, privA_hd_g15, privB_hd_g14; gate dirs tess_s23, garrett_g16, privA_g15, privB_g14; rows r10_rows.txt
  vs r9): ALL heads brows.head .55 + density x1.28 (cap 1.6: A was already at the clip (2.0 = 1.6), so A's brow will read
  lighter: watch darkness), sclera x.72 Tess / x.77 Garrett, A / x.6 B (capped; B's photo white is in lid shadow), Tess and
  Garrett lips.sheen .14 + specular .6.
STATE: r10 queued behind r9. NEXT: collect r9 (keep / revert), then r10, tile reviews for both.
- r9 COLLECTED (gate/r9_rows.txt vs r8; reviews: REVIEW FAILED on all four (bin/review account until 2026-10-19 13:00 MT): the
  chain now says so instead of GAME 0). FAIL rows: Tess 47 -> 47 (of 103 now: the new r10 rows count), Garrett 44 -> 42,
  A 55 -> 55, B 58 -> 58 (the two controls: rows reproduce exactly). KEEP ALL r9 changes:
  - Tess iris darker: iris R / L WIN (dE 11.6 -> 5.1, 12.1 -> 5.5); sclera / iris L LOSS follows (the sclera is too bright: r10).
  - Tess brows.density 1.25: hair / skin WIN both; brow_L darkness 35.6 -> 40.3 (PASS, worse).
  - Tess lid_shade revert: socket R WIN (-14.2 -> -10.5, ref -8.2), socket L better (-11.9 -> -7.8, ref -2.0); lid L LOSS
    (-5.5 -> -3.1, ref -8.6): as predicted, the zone lever can't do the lid alone (lash-line lid mask still NEXT).
  - Tess lips lower blood .6: better (dE 5.7 -> 3.6, a* 22.2 -> 19.8); lips.roughness .15: sheen 4.1 -> 5.0 (the pad clamp).
  - Garrett lid colour halfway: lid a* / b* WIN both (inside tol), socket b* stays inside tol. KEEP.
  - SUSPECT: Tess "crease height mid L" 5.4 -> 12.9 mm (LOSS) with no lid geometry change: the crease reader likely jumped to
    another edge once the lid got lighter. Check it on the eye tile before acting on it.
STATE: r9 kept in full; r10 chain now running (it waited for R9 CHAIN DONE). NEXT: collect r10, tile reviews.
