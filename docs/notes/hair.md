# hifipushie notes: hair

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `hair.py` + `blender_hair.py` (2026-09-29; replaced the SDF groom on branch hair-sdf-wip: a mop with corduroy grooves,
  13 min builds): hair as curve locks in the Blender scene. Each lock is a legacy Bezier curve object (collection "hair")
  with one shared Geometry Nodes group `hp_lock`: resample, flat side facing away from the head centre + Flip + Twist and
  the curve's own tilt, a lens profile (width x thickness, the edges cupped toward the head) swept with Curve to Mesh,
  scaled along it (Root, Belly, Taper) x the point radius; it stores hp_along/across/out/lock/grey/tangent for the
  material (`material`: gaps and roots dark, a sheen band along the crest, per-lock value, grey, uneven soft grooves as
  bump). Chosen over Hair Curves + the Essentials groom nodes: those are strand tools (clump/curl/trim around guides)
  and give a fuzzy strand look; stylised hair wants a few big editable locks, and legacy Bezier curves give handles, Alt+S
  radius, Ctrl+T tilt and per-object modifier numbers a person can edit, instantly (a lock evaluates in ~1 ms).
  Capture profile attributes BEFORE scaling the profile (captured after, "across" was +-2 mm and the material never
  showed). Tilt is applied on top of a Free curve normal (checked): `lie_tilt` turns each lock's flat side onto the
  volume's own normal (facing the centre, locks across the upper side stood on one edge); `lie_cup` = the head's sag
  over half the width.
  Spec `spec["hair"]` = groom (hairline from the landmarks, parting, volume per region, flow words, tiers, `drawn`
  clumps), locks ([azimuth, elevation, height over the scalp] per control point round a centre from the landmarks, so
  they follow head edits; width, thickness, cup, taper, belly, root, twist, flip, grey, radius/tilt/handles per point),
  look, stage ("mass" = the groom's volume as one shell). `spec.geometry` strips it; `store.save` of a hair-only
  change skips the base-body validation. Scalp = rays from the centre, cached on disk by geometry
  (`hair_scalp_<key>.npz`). The volume (`envelope`): a dome highest behind the front hairline falling to the crown,
  rounded across, each side azimuth's profile filled to its convex hull (`_fill`: the top over close sides pinched a
  waist, the user's "divots"). The underlayer is the volume sunk by the covering locks' thickness (`under`); never a
  visible surface. Tiers: `strip` (sides/back: long locks along the streams converging on a point under the nape, in
  shingled segments), `gap` (roots where the locks so far leave the volume bare, splatted coverage), `drawn` (the top
  drawn by hand on the top view: the user's call after every generated top came out busy or jumbled), plus the older
  `big`/`crown`/`clumps`. Looks (`look`): the head-cropped stage file `hair_stage.blend` (the scene cropped to the
  head; 42 MB vs 300-440), EEVEE, material + clay rows, thumbnail, reference crop; 4-15 s. Gates measured every look:
  `silhouette_gate` (front + near side of 3/4: outline dent inside its own hull <= 1.5 mm at a 12 mm scale over
  brows+2 cm .. top-2 cm; notches at 6 mm reported; `hair_point_owners.npz` says which lock makes each outline bin)
  and `mass_share` (an ID render: bare volume / visible hair, target < 10%). Round trip: `blender_hair.read` compares
  each lock with the state the sync wrote (`hp_set`), `scene.pull` -> `hair.pull_locks` writes moved points, handles,
  radius, tilt and modifier numbers back (tested: 3 locks edited headless, pulled, re-synced, second pull empty).
  Export (`hair.export_part`, called by `asset._export` when the spec has locks): the locks at 24 x 10 (`hair.EXPORT`,
  `spec.hair.export` overrides; 12 x 8 read faceted and dark in Cycles: the thin lens edges shaded as flat planes) + the underlayer
  decimated, one uv island per lock (round the lens x along) + smart-projected underlayer, packed by Blender, colour /
  roughness / normal baked by Cycles from the low poly's own material (selected-to-active from full-res locks picked up
  neighbouring locks where they overlap); its own atlas in the GLB with KHR_materials_anisotropy (rotation 90 deg:
  along the lock) and KHR_materials_sheen; bound to `parts.hair.rig_bone`.
  Reference matching (2026-09-29, the user's call after hand-drawn tops kept missing the reference's part and flow):
  `fit_camera` (pose + focal by least squares on lm_* joints vs reference pixels, pinhole at the image centre, the crop
  as Blender lens shift; `blender_scene.render` takes a view "shift"), `ref_trace.json` (part, hairline, outline,
  clump flows, landmarks; example `examples/disc_golfer_ref_trace.json`), `from_trace` (rays through the camera onto
  the volume/scalp -> parting `line` (`_part` then measures distance to it), hairline `front_points`, drawn clumps as
  `azel`), `fit_metrics` + the matched row in every `look`. dg_hair2: part 30 px -> 0.2 px off, clump directions
  20 -> 4.7 deg, IoU 0.53 -> 0.62 (the stylised cranium sits left of ours: hair can't close that). `parting.flat` /
  `parting.full`: the part side flatter, the swept side fuller. The back view was never gated and was ~20% bare
  volume: gap locks 60 mm wide at spacing 0.7 (sides/back/top) fixed it. Pull skips a lock whose scene copy was built
  from another version of the spec (`hp_hash` != `lock_hash`): a stale scene.blend had clobbered the spec with zero
  widths on export. Sync the hair (`hair.sync`) before exporting after a regrow.
  Hand-shaping (2026-09-30, the user's call after the procedural rounds: "hand shape the front locks in blender"; model
  `workspace/dg_hh`, a copy of dg_hair2, renders hh01-hh04): edit the curves in scene.blend (a live session: the person's
  Blender, or `blender -b scene.blend --online-mode --command blender_mcp --port N` + BLENDER_MCP_PORT=N), then
  `scene.pull`. Every lock edited there comes back with `"hand": true`; curves added to the "hair" collection (Shift+D
  on a lock, or a new Bezier curve) come back as new locks (tier "hand", named by their object); deleted ones leave the
  spec and are listed in `hair.removed`. `hair.groom` (regrow) keeps hand locks and never regrows a removed name; the
  sync records the locks it made (collection prop `hp_made`) so deletions are seen; a live pull re-syncs the edited
  locks (`scene._restamp_hair`: stamped with the old hash, the next edit of the same lock read as stale). What worked:
  few BROAD locks (7-10 cm wide, 6 mm thick, thin edges `edge` 1.6) lying on the volume (h = volume - 2 mm, tilt =
  `lie_tilt` smoothed along the lock, the root's tilt = the next point's: the volume's normal turns sideways at the
  parting and roots stood as fins), a top fan from the part whose rows never cross (slerp arcs, an under-row between
  each pair where the fan spreads), sides/back as ~8 broad locks brushed back to the nape (the procedural strips and gap
  locks read as tiles and shingles on edge), sideburn, nape and behind-ear locks for coverage. The groom's volume still
  shapes the silhouette: `volume.ramp` (0.028 default: the front a wall the front locks jutted over like a cap's peak;
  0.06 leans it back), `volume.across`, `parting.depth` (0.45: the roots stopped climbing out of a trench). Dents in
  the gate: find the lock that makes each height of the outline (`hair_point_owners.npz`) and pull it out 2-4 mm.
  Hair through MCP (2026-10-01; the user: another LLM consuming hifipushie over MCP couldn't do hair at all): tools
  `groom_hair` (groom patch deep-merged, null deletes, then regrow; hand locks kept), `look_hair` (sheet + layout +
  gates as text, incl. `hair.hierarchy`: area share by lock width vs the artists' 6-3-1, width spread), `hair_reference`
  (store the trace, fit the camera from its landmarks, `apply` = from_trace into the groom), `sync(hair_only=True)`
  (pull, then hair.sync); `edit_model` takes dotted kinds ("hair.locks", "hair.groom") and a hair-only edit validates
  only the hair (a base body recompile was ~1 min). `guide(topic="hair")` = `hair_guide.md`: the artists' workflow
  with sources (silhouette volume, big drawn shapes with a size hierarchy, sides/back as drawn ROWS of broad blunt
  locks, a light breakup, material) for the tools. Found doing it through the tools (renders hair_t01-t13): under
  clumps sank 1 x thickness, i.e. under the underlayer, so the volume showed between every pair of wedge tips (now
  `drawn_under` sink 0.35, per row); unders across az 180 averaged through the front (a lock over the face); the
  generated strip/gap tiers read as tiles and a mop (t13: 47 drawn locks in rows, no tiers, back bare 0.07).
  Silhouette round (2026-10-02, model `workspace/hair_vol`, renders hv01_*/hv02_*):
  - `trace.views` adds matched views: another figure in the same picture shares the lens (`fit_camera(focal=)`;
    with a free focal it ran off to orthographic). They are stored in `ref_cameras.json` and listed by
    `hair.ref_views`; each gets a matched row and its own fit.
  - `outline_regions`: on rays from the head centre in each matched view, the outline per head region (labelled by
    the volume point that makes the outline there), ours vs the reference vs the bare head, in mm; plus
    `over_brow_mm`.
  - A face-only camera fit left the cranium's pitch loose: the bare skull already reached the reference's hair top.
    One ear-side landmark (`lm_jaw_0.R`) fixed it.
  - The golfer's hair was 10-14 mm TOO TALL and too full on the swept side, not flat. New `volume.crest` and
    `volume.taper`. IoU near 0.73 -> 0.76, far 0.75 -> 0.84 (mass), 0.74 / 0.86 with locks.
  - The flakes along the part were roots twisting and climbing. lie_tilt at a root came out ~100 deg off the next
    point (now the root takes the next point's tilt, and |tilt| <= `TILT_MAX`), and roots were sent to the scalp
    under a 2 cm volume (now they dive just under the underlayer).
  - `hair.folds` (look_hair "folded locks"): in-plane bend x half width >= 1. `ease_bends` on drawn paths.
    `look_hair(only=)` isolates locks.
  Hairline round (2026-10-02, model `workspace/hair_r3` = copy of hair_vol, renders hr00-hr04; guide 3b/3c): new
  look_hair numbers per matched view: `front_edge` (rendered edge along the traced hairline: rough_mm vs its running
  median, tooth_mm, teeth by lock), `front_flow` (strand angle to the hairline, structure tensor on the reference and
  our render; the golfer's reference reads 10-30 deg, a shallow diagonal), `bare_where` (bare pixels by head region,
  "hairline" = within 15 mm), `fins`, `root_ends` (blunt cut ends). Fixes: cap rows follow the hairline (a 1 deg
  grid serrated the rim), traced front_points ease onto the default line (`HAIRLINE_JOIN`), `parting.front`,
  `volume.edge_sink`, drawn `to_hairline` / groom `hairline_edge`, `root` + `climb` (narrow roots growing out of the
  layer: full-width roots read as scales along the hairline and crescent fins at the part), roots past the hairline
  buried in the skin, ROOT_TILT (nape fold flags were the root's climb in a tilted lens), drawn clumps patched by name.
  hair_vol -> hr04: edge rough/tooth 1.21/6.4 -> 0.54/2.0, bare front 0.176 -> 0.095, direction err 25.5 -> 19.8 deg,
  hierarchy 0.8/0.2/0 -> 0.64/0.27/0.09, folds 7 -> 2. Open: the part-side temple corner's direction (ours ~80 deg vs
  15-40), sideR1's root fin on the swept side, 3-way nape splits read as a comb from behind.
  Drawn
  clumps take `"split"` (`split_tips`: tip into n narrower locks fanned apart, the clump tapering out under them, held
  inside the hairline); look keys `band_shift` (each lock's sheen band slides along it) and `tip`/`tip_amount`. The
  look's reference image is the trace's own (no golfer default).
  Soft, loose hair (2026-10-05, "hair cards" agent, branch worktree-agent-aff168a4b06a3ed59; cards s0urc3's Tess:
  plates, hard hairline, stiff one-sided tail; renders `workspace/hair_renders/hc_*`, references
  `workspace/hair_refs/` (CC photos + CC-BY Sketchfab card models, refs.json; `ponytail_right.jpg` is the target look);
  guide part "Hair: soft, loose hair as strand cards" with the artists' method and sources). STATE: two spikes, a
  decision pending with the user (Blender's hair system vs our cards); nothing is wired into MCP, tests or docs yet.
  - Built (numpy, works in look_hair's pipeline): `hair.style: "cards"` (default "locks": untouched path, but NOT yet
    checked bit-for-bit) realises every lock as layered cards (`hair_cards.py`: `atlas` = generated strand atlas, 10
    tiles dense/medium/sparse/hairline/fly/baby/band with colour+alpha, normal, aux root/id/depth/alpha; `spine` /
    `frames` / `_lock_cards` / `mesh` / `fit_budget` / `join`), `hair.strands` numbers (wave, wavelength, curl, random,
    clump, frizz, flyaway, layers, card_width, tips, baby, soft, round), the underlayer as a hair cap wearing the
    hairline tile (`hair.card_cap`), baby hairs (`hair.baby_locks`), `blender_hair.card_material/card_object` (dithered
    alpha, bent custom normals, id pass and clay for cards), tied hair `groom.tie` (`hair_tied.py`: gather rows to a
    tie point, tail round a core line under gravity, coil = bun, plait, escape strands, a band mesh), locks that leave
    the head (`"space": "xyz"`, `free`, `core`; `hair.lock_world` / `lock_address`; pull writes them back in their
    space), solid locks' `Free` input (node group VERSION 11: a hanging lock's underside is lit), `hair.export_cards`
    + asset.py COLOR_0 / alpha MASK / extras (WRITTEN, NEVER RUN).
  - Blender's own hair, spiked on the user's question (scratch scripts kept in `spikes/hair_strands/`: strands.py +
    bl_strands.py, atlas_bake.py + bl_atlas.py, look.py, tess.py, refs.py): our locks' spines as guides of a Hair
    Curves object + the Essentials node groups loaded headless from
    `<blender>/5.1/datafiles/assets/nodes/procedural_hair_node_assets.blend` (Duplicate, Clump, Curl, Frizz, Noise,
    Shrinkwrap, Set Hair Curve Profile; Braid has a hair-tie input; Interpolate needs a surface UV map: not tried),
    Principled Hair BSDF. Works headless with no fuss. Cycles strands are far the best LOOK (hc_12: tess's scalp hair
    and hairline read as real hair; hc_13: the golfer as realistic combed hair): 42k strands / 1.9M points, ~20-25 s
    a 640 px frame on the laptop's CPU, evaluation < 1 s. EEVEE draws the hair BSDF near black (needs its own
    material) at ~8 s a frame. Settings are touchy: frizz / noise distances of 2-4 mm made a cloud (0.2-0.4 mm is
    right), Clump at 0.15-0.35 collapses every guide's strands into a round ROPE (dreadlocks), 0 gives the soft mass.
    A lock as a broad FLAT clump (the golfer's sculpted look) is not one Essentials setting: Duplicate spreads
    radially; it needs our own lens-shaped child distribution or guides per clump edge. The golfer as strands is
    bigger and softer than his reference (IoU 0.57 vs 0.63 cards, ~0.74 locks) and has no distinct clumps.
  - "Volumised" strands (points -> volume -> mesh, 2 mm voxels, decimated 379k -> 12k): a lumpy blob / shower cap
    (hc_13 lower row). As tried it fails; no source for the remembered production pipeline was found in one search.
  - Atlas baked from Blender strand clumps (bl_atlas.py, Cycles, 10 s): works; first try has too little coverage in
    the dense tile, no ragged tips, lit colour baked in (hc_15: scalp shows through). Needs tuning + id/depth/root
    passes; then it replaces `hair_cards.atlas`'s drawing, the card mesh / budget / export code stays.
  - Recommended to the coordinator (not yet agreed): groom + look = Blender Hair Curves with our locks as guides
    (Cycles strands as the truthful look and the video path); game path = our card mesh from the same guides with
    an atlas baked from those strands; stylised solid locks stay as they are.
  - Open, in order, whatever is decided: the grey band / hard arc at tess's forehead (on the old dark-skin stage it
    was skin's shaved-scalp paint; hc_tess was re-synced without it, not re-judged with numpy cards), scalp gather
    coverage holes above the ear, tail collision with neck / shoulders (only the head's rays are used), export never
    run, bit-for-bit check of style "locks", MCP tools (groom_hair docs for tie / strands, look_hair numbers:
    triangles, hairline softness), tests, guide workflow section.
  Strand grooms (2026-10-05, "hair2" agent, branch `hair2` from the cards branch + main; decided with the user: the
  groom and the look move onto Blender's Hair Curves; renders `workspace/hair_renders/hs_*`; models `hs_tess` (copy of
  hc_tess, tied wavy groom) and `hs_golfer` (copy of hc_golfer); scratch scripts kept in `spikes/hair_strands/hs2/`:
  run.sh <script>, look.py (a look with overrides, HS_SKIP=Noise,Frizz drops modifiers), mk_tess.py, tiers.py
  (strands + every card tier in one sheet), atlas.py, export.py, golfer.py (locks | strands with gates), cmp_locks.py,
  v.mjs (Khronos)). STATE: WIP, stopped by the session's usage limit; no tests, no MCP wiring, no guide workflow yet.
  - `hair.style: "strands"` (`hair_strands.py` + `blender_strands.py`): the spec's locks are GUIDES. `hair_guides` /
    `hair_guides_free` = one Hair Curves curve a lock with per-point `hp_side` / `hp_out` (the lock's half width and
    half thickness as vectors) and per-curve hp_n (strands / 8), hp_k (sub clumps = width / clump_size), hp_fd
    (fly-away reach <= 0.8 x width), hp_rs (root stagger x4 on locks rooted at the hairline), hp_ts. Children come
    from OUR node group `hp_lens` (VERSION 9), not Essentials Duplicate (radial = the ropes): each copy is placed in
    the lock's lens section, drawn toward its sub clump's line by Clump x t^(0.35 + 2.65 x Clump Shape), let go again
    at the tip (Tip Spread), each sub clump swings on its own phase (Wave / Wavelength / Curl), single strands wander
    (Loose), some let go (Flyaway), every strand has its own start and end (Roots, Tips). It stores hp_sub, hp_cv (a
    value per sub clump: the material's streaks), hp_rand. Then Essentials Hair Curves Noise + Frizz (Cumulative
    Offset OFF: on, thin locks fanned out), Shrinkwrap, Set Hair Curve Profile. `hair_under` = the scalp layer: flow
    guides seeded every 11 mm inside the hairline (direction = the nearest lock spines laid in the scalp's tangent
    plane, rising to just under them; baby-hair seeds on the line), children by Essentials "Interpolate Hair Curves"
    on `hair_scalp` (a mesh of the scalp with UV = azimuth / elevation and `hp_density` = hairline fade x parting).
    `hair_scalp` also renders a dark tint by density (`look.scalp_tint` 0.85): without it 30k strands showed skin.
  - `hair.strands` (hair_cards.STRANDS) holds the dials, 0..1 mapped onto safe ranges in `hair_strands.physical` /
    `SAFE` (frizz <= 0.6 mm, coherent noise <= 6 mm, fly-aways <= 12% of strands, tips lose <= 55%): count, thickness,
    clump, clump_size, clump_shape, tip_spread, loose, roots, under, under_length, flat, wave, wavelength, curl,
    frizz, flyaway, tips, source.
  - COST: Essentials Shrinkwrap against the body mesh took 70-250 s a look; against `hair_collide` (the head, neck
    and shoulders as the scalp's rays see them, ~8k triangles) the whole look is 10-25 s in EEVEE at 30k strands.
    Curl Hair Curves subdivides x4 (dropped: the lens group's Wave/Curl does it).
  - `hair_tied`: escaped strands fall down the cheek (they left the head at 45 deg: tufts), 6-14 mm wide.
    `groom.parting.side` defaults to "left": a tied groom needs `"none"` or the cap and scalp density get a part cut.
    Thin free locks (< 16 mm) keep their point, get few strands and less wave; a tail's locks are x1.5 wide and
    round in section (flat ribbons twisted like bacon), lock phases nearly in step (random phases = pasta).
  - Game path (design a-g agreed with the coordinator after research; see hair_guide.md's last section):
    `hair_strands.evaluate` builds a strands job in an empty Blender scene and dumps every strand (mode
    `hair_strands_eval`; `strands_of_model` caches it in `<HOME>/_cache/hair_strands`). The card atlas's tiles are
    now the groom's own strands: `tile_job` = one flat guide lock a tile (dense .. baby) through the same lens group
    and numbers, `tile_lines` -> `hair_cards._tile(lines=)` (the drawn generator is `_drawn_lines`, `strands.source:
    "drawn"`); rasterised in numpy/PIL (alpha, id, depth, root; NOT a Cycles bake: say so). The atlas is 2 : 1: the
    right half is the SCALP CHART (`cap_chart`: every strand close over the scalp drawn where it lies over an opaque
    base that starts `soft` inside the hairline); `hair.card_cap` maps the cap mesh onto it (seam vertices doubled)
    and the cap is lifted 2 mm + its sagitta. `hair.CARD_TIERS` hero 40k / main 16k / npc 6k / far 1.5k (layers,
    card width, segment, cap step); `hair_cards.fit_budget` now drops cards one by one by `prio` (it dropped whole
    layers). `hair.export_hair(name, out, tiers)` -> `<name>_hair_<tier>.glb` (one atlas, MASK, two-sided,
    anisotropy + sheen, extras.hifipushie_hair with the recipe and layer ranges) + `<name>_groom.abc` / `.usda`.
    RUN on hs_tess: /mnt/data/hifipushie/hair2/tess_export, 78 s for four tiers, Khronos 0 errors 0 warnings
    (39,994 / 15,994 / 5,974 / 1,478 triangles). `hair.export_part` sends style "strands" through the cards too.
  - Groom export, tested (spikes/hair_strands/bl_groom_export.py): Blender 5.1's Alembic writer keeps curves, widths
    and the object's custom properties (groom_version_*) but DROPS per-curve / per-point attributes; its USD writer
    keeps them all as primvars. So the .abc is the minimum Unreal imports (guides, ids, root uv = importer defaults);
    the full schema would need pyalembic.
  - Style "locks" is unchanged: hs_golfer's look rendered with main's src and with this branch's is pixel-identical
    (max diff 0 over three views; cmp_locks.py). The job dict gained keys (free, strands, core, new look defaults).
  - The golfer as strands (hs_14_golfer_locks_vs_strands.png, NOT yet looked at by me: judge it first): IoU 0.597
    vs locks 0.624, bare 0.06 vs 0.107, silhouette gate FAILS (front 4.1 / 6.6 mm vs 1.3 / 1.4; hairline edge rough
    0.88 mm / tooth 5.3 vs 0.29 / 1.4) with clump 0.9, clump_size 12 mm, shape 0.3, flat 1.6. No recommendation yet.
  - READ so far (EEVEE only; the user called the spike's strands "kind of ok"): hs_12_tess_tiers.png = strands over
    hero / main / npc / far. Strands: reads as a ponytail with a loose wavy tail, no ropes, soft face wisps; still
    crimped wisps, clumps a bit pasta-like in the tail, strands at the temples stand off in arcs. Cards: hairline
    and cap read (no skin through, the far tier is a helmet with real flow); cards are much darker than the strand
    look (two materials, unreconciled), tails thin out to wisps at npc / far.
  - NOT DONE, in order: (1) a Cycles look: every attempt waited 30+ min on `resources.heavy` behind exports and
    cloth sims and was cancelled; needed for the before/after on "kind of ok" (count, taper, hair BSDF, rim light)
    and to settle the card-vs-strand colour; (2) the first sheet to the coordinator: Tess strands beside
    ponytail_right.jpg + the tier sheet; (3) judge the golfer sheet, recommend on migrating stylised hair; (4) one
    per-clump volumise try, then close it in the guide (research found nothing documented; Sprite Fright's hair
    meshes were sculpted by hand); (5) round trip: `blender_strands.read` exists (moved guides by stamp, stack
    numbers) but nothing in hair.py / scene.pull consumes it, and hair.sync was not run with strands; (6) look_hair
    numbers for strands (coverage = id pass red share is there; hairline softness in mm, IoU on tied hair not);
    (7) MCP tools (groom_hair / look_hair docs for strands + tie, an export_hair tool), guide workflow section for
    strands, tests (none exist for hair), GLB preview render of each tier, usdc instead of 32 MB usda; (8) Braid
    node for plaits, tail collision beyond the proxy, baby tile nearly empty (coverage 0.06).
  Hair 3 (2026-10-06, "hair3" agent, branch `hair3` = hair2 + main; renders `workspace/hair_renders/ht_*`, exports
  /mnt/data/hifipushie/hair3/tess_export_v*, scratch in `spikes/hair_strands/hs3/`: run.sh <script>, var.py (rows of
  spec variants), iso.py (what makes a pattern in a tier), diag.py (export + check_tiers), pair.py (GLBs side by
  side, alpha test / dither), dist.py (tiers at their distances), clear.py (cards under the skin), tools.py (the MCP
  tools called directly), cmp_locks.py, groom_check.py (Alembic / USD read back), regroom.py; Khronos validator in
  /mnt/data/hifipushie/hair3/val). The user on hs_12: the strand look "is looking really good", the game export
  "seems to get corrupted"; so this round was the card path. Supersedes the hair2 notes above where they differ.
  - Cycles strand look works (87-270 s): three causes of the pale haze it was: `hair_strands.STRAND_RADIUS` is now
    a real hair (0.04 mm) at `REAL_COUNT` 100k, wider by (100k / count)^0.8 (EEVEE draws >= 1 px, a path tracer the
    true width); `hair_bounces` 10 (render() cut transmission at 2); lights `hair.LIGHTS["salon"]` (key, fill, rim;
    default for strands / cards, `look.light`; locks keep the stage's sun). Own `hp_profile` group for the radius
    (root, taper to the tip: `strands.taper`). Cycles reads lighter and more ginger than EEVEE: not reconciled.
  - Pasta and crimp: sub clumps swing nearly in step (`Wave Random` = strands.random; they were on random phases
    and wavelengths, and at 3x the lock's own amplitude: `SAFE["sub_wave"]` 0.25), `strands.stray` (strands that
    only half join their clump fill between clumps), per-curve `hp_ws` / `hp_wl` (a wisp swings less and slower).
    Gather locks (`hair_strands.is_gather`: name t<i>g<row>_<n>) narrow into the tie and are not tip-trimmed.
    Lens group VERSION 10. Wisps root 8 mm inside the hairline (`hair_tied`: at 2.5 deg they rooted on skin).
  - DIAGNOSIS of the "corrupted" tiers (ht_01, ht_02): not the atlas, UVs, normals or colour space. (1) baby-hair
    cards under an alpha TEST = brown stamps; (2) the tail a lattice of thin ribbons on separate phases, no opaque
    base; (3) fixed costs (cap, baby, tie) ate 22-68% of a tier and lower tiers were the same thin cards thinned
    out; (4) shade applied twice (atlas depth AND vertex colour x0.6 on layer 0: the dark band above the forehead,
    with every upper card starting 2 cm behind the line); (5) the budget stretched every hero card to 3 cm segments.
  - Cards are cut from the STRANDS now (`hair_cards.strand_grid` / `_clump` / `clump_cards`): strands resampled on
    a common grid of their lock's parameter (NaN outside each strand's own start / end), clustered by tier key
    `group` ("sub" = the groom's sub clumps, "pair", "lock", "free" = only hair off the head), a card's centre = the
    clump's mean, width = 2.5 x its spread (cards overlap a third: where they only met, every seam was a shadow
    slit), wide clumps cut across into slices by strand; frame carried on where "outward" degenerates (cards stood
    on edge round the tie). Layers: 0 dense (hairline tile at the line), 1 the hairline tile again (its roots come
    in one by one: staggered roots on the dense tile drew brick lines under an alpha test), 2 medium, outlier
    strands = fly cards (hero). Wisps (free lock < 16 mm): 2-3 thin cards on the fly tile (a few THICK hairs, 3
    texels, root at full strength, no depth shade). `tail_cores` + `core_mesh`: a solid surface in a tied tail from
    the strands' radial extent per station / direction (layer -1 like the cap). `hair.CARD_TIERS` hero / main /
    npc / far: group sub / pair / lock / free, card_width 12 / 20 / 28 / 70 mm, far's cap = the groom's volume
    (`cap: "mass"`, eased up from the line). `fit_budget`: segment x1.5 at most, then cards by `prio` (fly, baby,
    top layers first; coverage last). Old lock-cut cards remain for `strands.source: "drawn"`.
  - One shade: atlas colour = gap -> lit by depth (0.45 + 0.55 d) x a value per strand (x3 vary) x `look.card_gain`;
    vertex colour = root-tip ramp x per lock / card value only. Card material and GLB: roughness >= 0.5, specular
    halved and tinted to `look.sheen` (KHR_materials_specular without the texture; a card mirrored the rim light
    as a white plate). Tiles (`hair_strands.TILE_KIND`): medium / sparse roots staggered over the first quarter,
    baby = 4-6 hairs with empty margins, fly / baby lines >= 1 texel and faded before every quad border.
  - `hair.card_clearance` (in every cards job): vertices under the skin (the head as the scalp's rays see it)
    counted by lock, then moved out to `CARD_CLEAR` 1.5 mm; `detached` = free cards whose root lies outside the
    hairline. Measured on Tess: 0 hero vertices under the skin (11-12 gather vertices <= 2.7 mm at main / npc);
    the wisps "starting on skin" were roots faded by alpha + two rooted 3.7 mm outside the line.
  - Tooling (what found all of the above): `hair.look_glb` (a GLB re-imported by Blender's glTF importer on the
    head stage; alpha "test" | "dither" | "off"; `dist`), `hair.look(debug=)` "layers" | "cap_only" | "cards_only"
    | "no_normal" | "unlit", `hair.check_tiers` + `tiers_text` (sheet, table, WARNINGs), `hair_checks.py` (iou /
    bare / value / sat vs the strands, `stamps` = detached rectangular blobs, `straight_share` = plank edges,
    `mesh_verdict`). MCP: `export_hair` (new; check=True, save=sheet), `look_hair(tier=, debug=, engine=)`,
    `groom_hair(style=, strands=, look=)` + tie in its docs; guide section "Strand grooms through the tools".
    `tests/test_hair_strands.py` (9 tests; the last exports npc through Blender on hs_tess).
  - Tess after (export v8; ht_07 / ht_09 / ht_10 sheets): 39,986 / 15,990 / 5,984 / 1,468 triangles, 94 s for four
    tiers + groom; Khronos 0 errors 0 warnings (infos: the unused specular texture). bare vs strands (alpha test)
    hero 6-21%, main 7-24%, npc 8-28%, far 13-50% (front views: face wisps and the strands' fringe); value x strands
    0.89-1.05 (back view 0.78: strands glow under the rim, cards don't transmit), sat 1.0-1.2; stamps 0. Groom read
    back by Blender: 29,977 curves / 489,076 points; .abc in cm (position, radius), .usdc in m with groom_* (10 MB;
    the .usda was 33).
  - Style "locks" unchanged: hs_golfer's look with this branch vs main's src differs by <= 1 level on 2-11 of 1.57M
    pixels, and main against itself by 9 (EEVEE's own run-to-run noise); same code twice can also be identical.
  - Cycles colour, one more data point (ht_t_cyc3.png: flat light | salon without denoise | vary 0.2 + no tip
    colour): the strands read light ginger-blond in ALL three, so it is neither the rim light nor the per-strand
    value: the hair BSDF's colour itself comes out ~2x lighter than `look.lit` (#5c3b28, dark brown) and than EEVEE.
    Next step: calibrate the BSDF colour (a gain, or melanin) against lit by measurement. Without the denoiser
    (200 samples) strands keep their grain; with it the mass goes waxy. The three renders waited 19 min, 107 min and
    8 min for the heavy slot: queue Cycles looks and do other work.
  - Volumise, tried once and CLOSED (volumise.py, ht_12): Points to Volume -> Volume to Mesh per sub clump of the
    tail = 3.6M triangles in 45 s, rows of beads, no strand detail; written up in the guide. Stylised hair stays on
    locks.
  - READ: hero at bust distance is combed hair with a clean hairline and matching colour, still smoother and
    flatter than the strands; a few dark slits between cards on the back / top; npc cards lift at the crown like
    roof tiles; far = helmet + solid tail, no wisps; tails have mass at every tier.
  - NOT DONE: Cycles atlas bake + flow / AO passes (the atlas is the numpy raster; said in the guide), Godot render
    (godot is installed at ~/.local/bin/godot: untried), clearance against a decimated game skin, core for loose
    long hair (only tied tails), the golfer as strands judged (hs_14: strands lose the designed clump shapes and
    fail the silhouette gate 4.1 / 6.6 mm vs 1.3 / 1.4; my read: keep stylised hair on locks, no migration), the
    round trip (`blender_strands.read` exists; nothing consumes it), strand measures in
    look_hair beyond the @@strands counts, hair_r3 / golfer card exports re-checked with the new cards.
  Garrett as strands (2026-10-08, "hairgarrett" agent, branch `worktree-agent-a3e326852c098a6dd`; the user: "one-mesh +
  new hair + clothes as the new default human path"; model `workspace/hs_garrett` = om_garrett v17's head + his 624 hand
  locks as guides; sheets `workspace/hair_renders/hg_*` (hg_v4_sheet.png = concept | solid locks | strands in Cycles |
  hero cards | main cards, front / three-quarter / side, + the four tiers at their distances; hg_v4_tiers.png =
  check_tiers); export /mnt/data/hifipushie/hairgarrett/exp_v4; scratch DURABLE in /mnt/data/hifipushie/hairgarrett/:
  run.sh <script> (worktree code, main workspace, through `capped`), mkcopy.py, reseat.py (hs_garrett takes
  om_garrett's spec for everything but the hair, then scene.sync: 6.5 min), look1.py <tag> <engine> '<strands json,
  "_look": {...}, "_style">' <views> <save> (a look with patches), fuller.py <tag> '<{region: m}>' <save> '<patch>'
  '<trim json>' (hair.lift(fill) + trim + look + outline), strandfit.py (the front photo's head + hair outline vs the
  model's head + the last look's hair points through om_garrett's fitted camera: mm per level and side; needs
  onemesh2's hairfit.py on PYTHONPATH), cal2.py <model> <engine> [fit=A,p] (rendered vs asked colour over 7 hair
  colours; also spikes/hair_strands/hs4/cal2.py), haircol.py (hair pixels' sRGB percentiles vs the concept's),
  exp.py <tag> (hair.export_hair + check_tiers, with a watchdog that dumps stacks past 3 GB), sheet.py <tag> <export
  dir>, q3.sh <tag> (export then sheet), dbg_job.py <tier> (a tier's cards job step by step with peak memory: 0.53 GB),
  napeq.py).
  - His locks ARE the guides: `groom_hair(style="strands")` on the existing hand locks, no regroom. Dials for a short
    combed cut: count 100000, clump 0.3, clump_size 0.006, clump_shape 0.5, stray 0.8, loose 0.4, frizz 0.2, flyaway
    0.03, tips 0.6, tip_spread 0.5, roots 0.4, under_length 0.015, wave 0.003 (clump 0.4 / stray 0.6 at 60k: strings).
    The scalp layer takes 60% of the strands whatever `under` says (its cap in hair_strands.job).
  - Grey: a lock's `grey` is the SHARE of grey strands it grows (per-curve `hp_gr`; the scalp layer takes the nearest
    lock's), x `look.grey_locks` (default 1) + `look.grey_amount`. Before, strands ignored the locks' grey. In EEVEE
    0.37 x 1.0 is striped silver; in Cycles the same share is a faint greying (true-width hairs average).
    The card atlas draws the same share (the locks' mean: `look.grey_share`, set in cards_job) by a THRESHOLD on the
    strand id above the base's depth: a hash of the id speckled every anti-aliased pixel and turned the cap's base grey.
  - Side volume by measure (strandfit.py): his hair was 9-18 mm thinner per side than the photo's outline at the
    lower levels (mean -8.8). `hair.lift(fill=True)`: locks lifted AND thickened by twice their mean lift, so the
    strands fill from the scalp (strands live in each lock's lens: lifted alone they are a shell over the short
    scalp layer). sides +12 mm, back +4: mean side miss +1.0 mm (L -5 / R +6: the photo's sweep is the other way),
    IoU above the ears 0.874 -> 0.909, top +5 mm. It reads as volume, not a helmet. `hair.trim(spec, sc, below,
    where)`: locks cut where they run past the hairline; his nape hung as a mullet of strand tips until
    {"below": -0.015, "where": ["nape"]} (cut 15 mm INSIDE the line: the scalp layer carries the edge).
    MCP: `groom_hair(fuller=, trim=)` (no regrow when only those are given: a regrow buries hand locks).
  - Cycles colour: measured (cal2.py: the brighter half of the hair pixels vs the colour asked, linear, 7 colours)
    rendered = 0.646 x asked^0.307 (rms log 0.024): #55504b came out 3.5-4x too light, black at 0.15. The floor
    (~0.09 linear) is the white specular lobe + thin strands, not invertible. `hair_strands.CYCLES_FIT` (0.75, 0.307)
    is now the default inverse (`look.cycles_fit` [1, 1] = off): grey / blond within 5%, #55504b x1.35-1.45 (EEVEE's
    strand material reads x1.6-1.8 by the same measure). It is applied to the colour's LUMINANCE with the hue kept:
    per channel (first version) the 1/p power tripled every channel ratio and a faintly warm grey (#5a4f47) rendered
    light brown (hg_v3_sheet). A Cycles look of 4 views at 100k strands: 330 s; 3 views at 420 px: ~100 s.
  - `look.scalp_tint` 0.85 (made for dark hair) shows as black slits between layers of grey hair; 0.5 lets skin
    through at the crown in Cycles; Garrett 0.7.
  - Card tiers (exp_v4; Khronos 0 errors 0 warnings on all four; 39,998 / 15,486 / 6,000 / 660 triangles; his solid
    locks in exp_garrett6: 25,803): `hair_cards.join` of nothing raised (a far tier of a short cut has no cards and
    no baby hairs: the first export died after writing nothing); fixed. check_tiers vs the strands: iou 0.83-0.87
    hero / main / npc (far 0.75-0.85), bare 4-13%, value 1.06-1.18 x (cards are lighter and more silver than the
    Cycles strands: two materials, the sat warning reads 1.4 x), stamps 0. "936 card vertices under the skin, deepest
    64 mm" at hero (baby locks and locks by the ear: moved out by the clearance; not looked into).
  - BLUNT READ of hg_v4_sheet: the Cycles strands read as a real man's combed greying hair, the best of the three,
    but darker and more slicked than the concept's lighter, tousled salt-and-pepper, and the denoiser makes it waxy
    at 420 px. The cards at bust distance are WORSE than his solid locks: a streaky silver thatch, ragged dark
    patches along the temple hairline and behind the ear, a pale plate at the front of the crown (the cap); from
    1.6 m they read as short grey hair, at 3 m+ fine. The solid locks stay the cleanest game look up close.
  - The 13:37 OOM was not this: the 4-tier export + check never passed 3 GB of python (watchdog in exp.py).
  - NOT DONE: the head is not settled (re-seat + strandfit once it is: `reseat.py`, then `fuller.py`); cards'
    hairline and colour against the strands (bake the atlas colour from the strand look, a hairline tile that
    follows his temple); a tousled top (his locks are combed back; the concept's front lifts and breaks); per-region
    grey in the cards (one share for the whole head today); Godot render of the tiers; the round trip of strands;
    `under` has no effect past the 60% cap; test_hair_strands' Blender test not re-run.
  Garrett's CUT (hairgarrett round 2, same day; the coordinator on hg_v4: "real hair but the WRONG HAIRCUT: slicked
  back like a 1950s banker"; sheets hg_c3_sheet.png = photo | strands Cycles | hero | main + tiers at distance,
  hg_c3_godot.png; export /mnt/data/hifipushie/hairgarrett/exp_c3; scratch adds mkcut.py <tag> '<loose>' '<strands>'
  '<look>' <engine> <views> (the cut regrown from nothing + look + outline), photocol.py (the photo's hair by region:
  dark / grey cluster colours and the grey's share), sheet2.py (+ card vs strand value / saturation on hair pixels),
  capdbg.py <tag> <tier> cap_only,cards_only,layers (what each part of a tier draws), q4.sh, gd.sh + centre.py (Godot)).
  - The sculpted locks were dropped; the cut is `groom.loose` regrown (replace=True, tiers off, parting none):
    length front 26 / top 20 / sides 22 / back 22 / nape 12 mm, spacing 9 mm, width 2.4, lift 1 mm, body 2 mm, messy
    0.35, uneven 0.8, and NEW per-region keys: `flow` {region: world direction} (front [0.55, -0.45, 0.7] = up and
    forward to his left, top [0.6, -0.15, 0.2], sides [0, 0.75, -0.65] back and down), `out` and `stiff` as
    {region: v} (front out 0.3 / stiff 0.9; sides out 0 / stiff 0.55). Loose locks take `groom.grey` (temples,
    sideburns and now any region: top 0.2, sides 0.45). Strands: count 140000, thickness 1.6, clump 0.15, stray 0.9,
    roots 0.9, tip_spread 0.5, loose 0.18, frizz 0.15, wave 0.0004, under_length 0.022. `groom.volume` back to 3-4 mm
    (round 1's fuller sides had left it at 18 mm: the cap then stood over the side cards).
  - What went wrong on the way: wave 4 mm at wavelength 3 cm + curl on 2-3 cm hair = ringlets and hooks at the nape;
    out 0.6 / 4 cm front = 23 mm too tall; sides at out > 0 or stiff 0.3 = each lock a curled leaf with skin between;
    in CYCLES 100k true-width hairs on a crop are see-through (orange scalp glow, ginger cast): thickness 1.6 +
    140k + scalp_tint 0.85-0.93 closed it. Cycles look of 2 views at 640 px: 240-380 s on a loaded machine.
  - Colour by measure: the photo's hair (photocol.py) is dark #5a4f46 + grey #968e85, grey pixels 12% on top, 21-24%
    at the sides, median (96, 84, 74). Cycles strands with lit #74655a / grey #b3aaa0: front median (115, 104, 98),
    three-quarter (84, 75, 70) (lit #5a4f46: (84, 78, 74) / (61, 55, 52), too dark in the shade). Hue ratio R/B 1.17-
    1.20 vs the photo's 1.30: the hue-keeping CYCLES_FIT holds the asked hue within ~10% (the look colour's own R/B
    is 1.29; the rest is white highlight).
  - Outline (strandfit): IoU above the ears 0.88, mean side miss +0.2 mm per side, top +10 mm (still a little tall).
  - Cards on a short cut, by cause (capdbg.py): (1) the pale dome + dark rim at the temples was the loose groom's
    MASS SHELL standing outside the side cards: no shell under `MASS_MIN` 6 cm mean lock length (the cap is the
    surface under short cards); (2) "936 vertices under the skin, 64 mm" was the clearance measured against the
    scalp's RAYS, which meet the ear first: cards on the head behind / over the ear were pushed out to the ear's
    silhouette (the ragged patches). Clearance is now against the body's signed distance for every groom
    (`cards_job(clear_col=)`): deepest 19.5 mm, 3.8% of hero vertices (short flat cards cutting chords); (3) the
    cap over the cards (volume, above). After: hero 40,000 / main 15,188 / npc 5,474 / far 1,498 triangles;
    check_tiers hero / main iou 0.86-0.90, bare 5-9%, stamps 0.
  - Card colour vs the Cycles strands (sheet2.py, hair pixels): `look.card_gain` 1.1 + NEW `look.card_sat` 1.4 ->
    value 0.99 / 0.93 x (front / three-quarter), saturation 1.24 / 0.93 x; before 0.88-0.94 and 0.57-0.89. Within 5%
    only on average: the two differ by view (cards don't transmit light).
  - Godot 4 (`spikes/godot_hair/look.gd` through godot-quiet; hg_c3_godot.png): the GLBs import as alpha scissor
    0.33, cull disabled; a2c only softens the edge. Godot does NOT use COLOR_0 unless the material's
    vertex_color_use_as_albedo is set (the root-tip ramp is lost: hair reads paler and flatter than in Blender).
  - BLUNT READ of hg_c3_sheet: the strands are now the concept's haircut: a short tousled greying crop with a lifted
    front; still a little tall and even on top, the hairline cleaner and higher than the photo's broken one. The
    cards carry the same cut and silhouette but read as chunky torn-paper tufts, not strands, at bust distance;
    main looks like hero; from 1.6 m fine. In Godot the front hairline shows rectangular card ends.
  - NOT DONE: card texture finer (the tiles are 16 cm strands squeezed onto 2 cm cards: a short-hair tile set),
    a broken hairline (baby / fringe hairs forward of the line), Godot with vertex colour on, the re-seat on the
    settled head, test for loose `flow`.
  Garrett, hairgarrett round 3 (2026-10-08/09; the coordinator on hg_c3: strands "stand up like a brush", hairline
  high / receded / clean, cards "torn paper / leaf litter: a fail"; sheets hg_g2_sheet.png, hg_g2_godot.png, cap chart
  hairgarrett/chart_g1.png; export /mnt/data/hifipushie/hairgarrett/exp_g2; scratch adds hairline_trace.py (the
  photo's skin -> hair boundary carried onto the scalp through the fitted camera, as groom.hairline.front_points),
  patch_mkcut.py (round 3's defaults in mkcut.py), q4.sh <tag> (export, sheet, Godot)).
  - Hair that LIES: longer and softer on top (front 34 / top 36 mm, stiff 0.6 / 0.36, out 0.24 / 0.1, body 2 mm), flow
    top [0.8, 0.45, 0] (over to his left and back), front [0.75, 0.1, 0.45]. Gravity (`stiff`) + the body's collider lay
    it over; at stiff 0.8-0.9 / 2 cm it was a brush. Outline: IoU 0.902, sides +0.3 mm, top +7.7 mm.
  - Hairline: the trace through the camera put the photo's line 7-12 mm HIGHER than the groom's at az 0-30 and 2-11 mm
    lower at az 42-54 (temples), against the coordinator's eye (low middle). Taken: temples filled as traced, the
    middle kept and dipped 3 mm at the centre (front_points), `strands.baby` 3 + `soft` 12 mm for the broken edge. The
    middle's height is NOT settled by measure (camera pitch / forehead height of this head vs the photo).
  - Salt and pepper: grey #cfc7bd on lit #54463c, vary 0.35, grey share top 0.28 / sides 0.55 / temples 0.75. Cycles
    front median (114, 110, 108) (photo (96, 84, 74): still light and too neutral), three-quarter (100, 95, 93).
  - CARDS FOR A SHORT CUT (`hair.SHORT_TIERS`, loose hair under MASS_MIN): the cap wears the scalp chart with EVERY
    strand of the groom drawn where it lies (`hair_strands.cap_chart(short=True)`: the hair's own strands too, up to
    35 mm over the scalp and up to the pole, 1 texel wide on a 2048 chart = ~0.3 mm; the pole left out was a dark
    disc on the crown), and only cards whose line rises `SHORT_OFF` 8 mm over the scalp are kept, on the open tiles
    (medium / sparse: fine strands, no opaque base). hero 16,000 (group pair, 2 layers) / main 7,998 / npc 3,998 /
    far 1,498 triangles (were 40,000 / 15,188). The 2048 atlas makes each GLB 24 MB (four embedded maps): share the
    maps or compress for a game. Card colour vs the Cycles strands (card_gain 0.95, card_sat 0.95): front value 1.01-
    1.02 x, sat 1.06 x; three-quarter value 1.14 x, sat 1.01 x (cards don't shade as deep away from the key).
  - Godot with vertex_color_use_as_albedo ON (look.gd sets it; extras.hifipushie_hair.vertex_color says so; lights
    turned down): reads as a short greying crop of fine strands, no leaf shapes; minification grain / sparkle on
    the cap at bust distance (1-texel strands: needs mips with alpha coverage kept, or the chart drawn 2 texels
    wide for lower tiers), a few stepped card ends at the hairline, a pale patch at the front of the crown.
  - BLUNT READ: strands are close to the photo's cut now (lying, swept, greying, temples filled); too neutral-grey and
    a touch light, top still +8 mm. Cards: the leaf litter is gone and it reads as strands in Godot; in Blender's
    look the top reads smooth / thin (the cap's flat shading where no card stands off) with darker flecks of card
    at the rim. Usable for main; hero buys little over main.
  - NOT DONE: cap normal / depth map from the strands (the cap is lit as a smooth dome), mips keeping alpha
    coverage, per-tier chart width, the middle hairline settled, check_tiers on the short tiers, the re-seat.
  Garrett, short-hair cards as a BAKED CAP (2026-10-09, "hair5" agent, branch `worktree-agent-adfa8889e1104d88e`; the
  coordinator on hg_g2: the top "reads bald / shaved: a pale dome with a ring of dark tufts"; sheets
  `workspace/hair_renders/h5_h6_sheet.png` (photo | strands Cycles | hero | main, front + three-quarter; tiers at
  their distances; a Godot row), `h5_*` looks, hg_s1..s11 = strand rounds; export /mnt/data/hifipushie/hair5/exp_h6;
  scratch DURABLE in /mnt/data/hifipushie/hair5/: hairgarrett's scripts retargeted + cap1.py <tag> <tier> (a tier's
  job timed step by step, the cap's colour / normal / flow saved to out/, an EEVEE look), q5.sh / q6.sh / q7.sh <tag>
  (export, Godot, sheet3.py, check_tiers, Khronos), gd.sh (Godot does not always exit after quit(): the wrapper stops
  it once its log says "done"), gsheet.py, headtop.py (photo's hair top over the BARE head vs ours), hstat.py (hair
  height over the scalp by region), setlook.py, showspec.py, guide_short.md).
  - `hair_cap.py`: the short cut's scalp chart is baked from the strands (numba z-buffer by height over the scalp,
    each strand 0.55 mm wide in metres; per texel the top strand's value, grey (per lock, x `look.card_grey` 0.5
    default, Garrett 0.9), depth (shade between hairs), a normal from the heights (RELIEF 0.35: at the real slopes
    it was tin foil in Godot), flow; an opaque base where the groom is dense; the hairline = strands drawn fewer and
    finer toward the line (in full, the scalp layer closed the cap to the line: a swim cap's edge). The cap stands at
    half the hair's height (`cap_height`), cards lie over it everywhere (SHORT_OFF is no longer used), thinned evenly
    by `prio`; short tiles = 16 / 9 thick straight lit strands. hero 15,996 / main 7,998 / npc 3,998 / far 1,500.
  - THE EXPORT WAS RE-EVALUATING THE GROOM IN BLENDER FOR EVERY TIER AND EVERY LOOK: `hair_strands.key` hashed the
    npz files' BYTES (zip timestamps) and a tmp path ("collide"): never the same twice; the cache held 3.1 GB of
    grooms. Now the arrays are hashed (`_npz_hash`), colours are not in the key, `GROOM_KEEP` 12 files. 4 tiers:
    655 s -> 143 s; a second look 35 s.
  - `export_hair(textures="shared")` (default): the GLBs name hair_*.png beside them (`asset.write_glb(external=)`):
    27 MB for four tiers (was 98). KHR_materials_anisotropy with hair_flow.png as its texture. Khronos 0 / 0 on all
    four (validator with an externalResourceFunction: /mnt/data/hifipushie/tiles/val.mjs <dir>).
  - Godot (look.gd): images of a run-time GLTFDocument load have NO MIPMAPS: that was the sparkle; the script makes
    them, sets anisotropy 0.35 + the flow map by hand (the importer reads neither the extension nor COLOR_0 as
    albedo). Anisotropy 0.6 on the relief = metallic.
  - Card colour vs the Cycles strands (sheet3.py; card_gain 0.56, card_sat 0.38): front value 1.05 x, three-quarter
    1.19 x, saturation 1.2 x (one gain can't meet both: cards don't self-shadow away from the key). check_tiers (vs
    the EEVEE strands): iou 0.68-0.80, bare 12-16% side / back but 29-32% front and three-quarter (WARNING: the
    cards' outline is tighter than the strands' fluff), stamps 0.
  - Strands: the hairline's middle set to the TRACE (+10-12 mm, front_points [0, 1.766] .. [54, 1.748]); top hair
    over the bare head 19 mm against the photo's 13-15 (headtop.py), outline top +6.4 mm (was +7.7), IoU 0.915, sides
    -3.6 mm. Levers by measure: `stiff` is the height (top 0.6 = a brush, +15 mm; 0.22 = +6.4), not length; a raised
    hairline ADDS height (the front roots stand higher); under ~0.3 the locks curl into hooks in EEVEE. Colour: lit
    #4a3524, grey #b39f88, grey_locks 0.75: Cycles front median (101, 93, 87) vs the photo's (96, 84, 74), R/B 1.16
    vs 1.30 (the white highlight), three-quarter (78, 72, 66). `hair.lift` skips loose (xyz) locks.
  - BLUNT READ of h5_h6_sheet: cards are a full head of short dark greying hair in Godot at 0.62 and 1.6 m: no bald
    dome, no leaf litter, no sparkle. Weak: it is a close, combed-flat cap (the strands' tousled volume and lifted
    front are mostly lost), a few wiry single hairs at the hairline and round the ear, lighter than the strands from
    three-quarter; in Blender's glTF look it reads paler and more like felt. hero is not worth its triangles over
    main. Strands: the traced hairline reads RECEDED against the photo to my eye (forehead a third of the face,
    wisps at the front): the trace depends on this head's forehead; re-trace after the re-seat before trusting it.
  - NOT DONE: cards' volume (LIFT 0.7 + cards at the strands' own height at the front), a second shell, alpha
    coverage in mips (engines make the mips), per-tier cap_step for short tiers, card colour by view, the
    "detached wisp ... 3300000 mm" line in check_tiers (inside() far from the line), strands' top the last 6 mm,
    the re-seat.
  - hair5 round 2 (2026-10-09; the coordinator on h5_h6: "a flat combed cap", hairline "RECEDED with wisps: my call
    to trust the trace was wrong for this head"; sheet `hair_renders/h5_r2_sheet.png`, export hair5/exp_r2 (hero +
    main), Godot out/gd_r2.png; q8.sh <tag> = export + check_tiers + Godot, q9.sh = the sheet with fresh Cycles):
    - Cards' volume: cap at LIFT 0.7 of the hair's 85th-percentile height (max 15 mm), every card moved to the TOP of
      its clump (`SHORT_TOP` 1.3 x the clump's spread along its normal; cards now carry `sn`), fly cards (hero 2 /
      main 1 a clump), cards CUT at the hairline (2 mm inside: their thick strands past it were the wires on the
      forehead and round the ear), no baby cards in short tiers. check_tiers bare front / three-quarter 29-32% ->
      16-19% (target 12 not met), iou 0.68-0.70 -> 0.79-0.81, side / back 6-9%.
    - Colour by view: RELIEF 0.7 / SLOPE 1.0 + a centimetre-scale hollow term in the depth + root ramp 0.7 over 45%
      of a card; with it roughness had to go to >= 0.85 (at 0.72 the side shone like gel in Godot). Against the
      Cycles strands (sheet3): front value 0.98 x, three-quarter 1.22 x, saturation 1.3 x: three-quarter NOT fixed
      (check_tiers against EEVEE strands reads 1.07-1.09 there).
    - `groom.loose.lay` (hair_loose.py; test_lay_presses_a_crop_onto_the_head): each step loses that share of its
      outward direction. Garrett: lay top 0.4 / front 0.15 at stiff 0.5 / 0.4: outline top +6.4 -> 0.0 mm, hair over
      the bare head 12.8 mm = the photo's, IoU 0.92, no hooks; sides -6.7 mm (region "top" reaches the upper sides;
      out sides 0.14 gave 1 mm back). Hairline middle half-way: front_points [0, 1.760] .. [54, 1.748].
    - READ of h5_r2: strands = a tidy dark crop combed across, forehead still a little tall, greying barely shows
      in Cycles. Cards in Godot = a full head of dark greying combed hair, matte, soft hairline; the lifted front /
      tousle is gone in BOTH (the lay flattened the strands too). Blender's glTF look draws the cards paler and
      browner than Godot does.
    - Not done: bare < 12%, three-quarter colour, the sides' width, npc / far re-exported, the re-seat (head is now
      garrett4's g4_a / g4_garrett; told it: copy groom + strands + look, regrow, re-trace front_points).
  - HANDOVER (hair5, 2026-10-09, context full; NOTHING of the list below is started). Branch
    `worktree-agent-adfa8889e1104d88e`, last commit = this note; tests: test_hair_strands (minus the Blender export
    test) + test_hair_loose pass. Model `workspace/hs_garrett` (still on om_garrett v17's head) holds the groom of
    h5_r2 (mkcut.py's defaults + lay top 0.4 / front 0.15, out sides 0.14 / back 0.08, lift 0.002; look card_gain
    0.56, card_sat 0.38, card_grey 0.9). Scratch /mnt/data/hifipushie/hair5/ (run.sh <script>; the fast loops:
    `mkcut.py <tag> '<loose patch>' '<strands patch>' '<look patch>' eevee|cycles <views>` = regrow + look +
    strandfit (3 min in EEVEE), `headtop.py`, `hstat.py`, `cap1.py <tag> main` = a tier's job timed + EEVEE look,
    `q8.sh <tag> hero,main` = export + check_tiers + Godot, `q9.sh <tag>` = the sheet with fresh Cycles strands,
    `setlook.py '<json>'`). The sandbox refuses heredocs, JSON-with-loops and `cd` chains: write a script, run one
    plain command. Godot only through gd.sh.
    The coordinator's read of h5_r2 and the next agent's list, in its order, ON garrett4's head (`g4_garrett`: copy
    groom + strands + look from hs_garrett without "locks", regrow with mkcut.py's call; strandfit / headtop /
    hairline_trace read the camera from $CAM_MODEL's human_refs.json):
    (1) HAIRLINE by PROPORTION, not by the trace (it misled twice): measure on the photo and on our render, like
    with like, hairline height above the brows / brow-to-chin (the photo: forehead about a third of the face, ours
    about half), and the temple corners' depth; the photo's line runs nearly straight across with shallow corners.
    Set `groom.hairline.front_points` ([azimuth deg, world z]) from that; the temple values (42-54 deg) are the
    trace's and make deep recessions: raise / straighten them too.
    (2) Front `lay` 0, standing (out 0.2-0.3, flow up and forward-left as round 3: [0.75, 0.1, 0.45]); top laid.
    Keep the upper sides' volume: "top"'s region weight reaches them (hair_loose.grow's `by_region`; hair.REGIONS
    weights W): gate the lay by elevation (e.g. x smoothstep(el 45..65)) or add an "upper sides" exception.
    (3) GREY: photo = salt and pepper, pale grey sides / temples (photocol.py: grey pixels 12% top, 21-24% sides,
    dark #5a4f46 + grey #968e85). Ours: groom.grey top 0.28 / sides 0.55 / temples 0.75 x look.grey_locks 0.75,
    grey #b39f88, lit #4a3524: reads dark brown-black in Cycles (true-width hairs bury the grey). Raise grey_locks
    to 1+, sides 0.6+, a lighter cooler grey, lit less red (R/B toward 1.3 at the photo's value (96, 84, 74));
    thicker grey strands would need a per-strand radius by `hp_gr` in blender_strands (not there). Cards carry the
    per-region grey already (hair_cap.strand_grey x look.card_grey); check card_sat again after the hue change.
    (4) Cards: standing cards at the lifted front follow from (2) (cards stand at their clump's top, SHORT_TOP);
    then bare < 12% (16-19% now) and three-quarter value (1.22 x the Cycles strands: one gain can't fix it; try a
    stronger depth term or baking the strands' own Cycles shading from two lights into the chart).
  Garrett on the NEW head (2026-10-09, "hair6" agent, branch `worktree-agent-a46ee6e0f7cd8c23d`; model
  `workspace/h6_garrett` = garrett4's `g4_a` (head) + the groom; sheet `hair_renders/h6_x2_sheet.png`; export
  /mnt/data/hifipushie/hair6/exp_x2 (hero + main); scratch DURABLE in /mnt/data/hifipushie/hair6/: run.sh <script>
  (M / CAM_MODEL = h6_garrett), mk6.py (h6_garrett from g4_a + scene.sync; g4_garrett's skin has keys this branch
  lacks), base.json (THE groom: loose / strands / look / groom) + mergebase.py <patches>, cut.py <tag> [patch.json ..]
  [engine=cycles] [views=] [grow=0] (regrow + look + every measure below), photoline.py / rline.py <tag> (the hairline
  measure on the photo / on a render), modelline.py (the hairline CURVE projected, + a solve), photocol.py, lookcam.py
  (views `matched_photo` = the photo's fitted camera, `tq_desk` / `side_long` / `back_long` = 1.6 m / 11.5 deg lens;
  light SOFT), cards.py <tag> <tier> [strands=0] [cyc=<cut tag>] [debug=layers|cards_only] [look=file] (a tier's cards
  against the strands, ~90 s), q8.sh <tag> hero,main (export + check_tiers + Godot on garrett4's g4_tex.glb),
  sheet6.py <tag> <export dir> <cycles cut tag>).
  - THE "HIGH HAIRLINE" WAS MOSTLY THE SHEET'S CAMERA. hair.look's "front" is a 30 deg lens 0.62 m from the head: it
    swells the forehead against a long-lens portrait. Measured like with like (`photoline.line`: skin = colour near
    the forehead's own; per station across the forehead the hairline's height over the eye-corner line in units of
    eye line -> mouth-corner line; per level the forehead's half-width in outer-eye-corner spans), the photo against a
    render THROUGH THE PHOTO'S FITTED CAMERA: hair5's round-2 groom on this head was +2.8 mm high at the centre, +0.8
    at the corners, forehead half-width +3.5 mm: nearly right already. Not usable for this: the id pass (the scalp
    layer's and baby hairs' fuzz reads 9 mm low), a hue / saturation skin test on renders (our skin is too pale for
    it), EEVEE strands (grey hairs read as skin). After front_points -3.5 mm in the middle: centre -1.7 mm, outer
    -0.4, half-width -2 mm. Judge a hairline only through the photo's camera (sheet6 does).
  - Front standing, top laid: `hair_loose.LAY_EL` (48-66 deg): the "top" region's lay counts only on the head's top,
    below it that weight takes the sides' lay (test_top_lay_leaves_the_upper_sides). Groom: lay front 0 / top 0.4,
    out front 0.2, stiff front 0.55, flow front [0.85, 0, 0.3], lengths front 29 / top 30 / sides 20 / back 22 mm.
    Outline: IoU 0.944, top -1.3 mm, sides +1.6 mm a side (round 2 on this head: 0.946, -2.5, 0.0), hair over the
    bare head 11.5 mm (photo 12.7).
  - Grey, by measure in CYCLES through the photo's camera (EEVEE's strand material is orange-blond with these
    colours: useless for colour). The salon light's rim blew his left side (lum 185 vs the photo's 103): looks for the
    photo use lookcam.SOFT (a broad frontal key, weak hair light). lit #5e3f28, grey #c8ad8e, grey_locks 0.9, groom
    grey temples 0.8 / sides 0.68 / back 0.5 / top 0.3: hair median (102, 94, 88) vs the photo's (96, 84, 74), R/B
    1.16 vs 1.30 (colours must be asked far warmer than they come out: #5e3f28 has R/B 2.3), light share 0.39 vs
    0.19. Grey #c2bbb1 at sides 0.7 under the salon light = a white-haired man (r1c); #a89d90 at 0.55 = charcoal with
    no grey showing (r2). No per-strand radius for grey strands (not built).
  - CARDS WERE UNDER THEIR CAP. cards_job put a short cut's cards at cap_height + 1.2 mm over the SCALP, but the cap
    mesh starts at the groom's volume (4-7 mm up) + its sagitta lift: every card lay inside the cap, the look was the
    cap's picture alone (the "flat combed cap"; debug=cards_only showed faint wisps, debug=layers shards poking out).
    Now cards stand over the cap's own surface (`capb_`), `SHORT_TIP` 3 mm of tip lift (x 0.2-1.6 a card),
    `SHORT_TIERS.cap_step` (hero 6 / main 7.5 / npc 10 deg: at the long tiers' 5 deg the cap took 4,416 of main's
    8,000 triangles, 1,984 now: 1,414 cards instead of 843), hair_cap LIFT 0.9 / LIFT_MAX 24 mm, the cap's ease at
    the hairline 6 mm over the forehead (`EASE_FRONT`), SHORT_TILE medium 36 x 3.2 px / sparse 22 x 3 (straighter:
    0.12 of their wander), `SHORT_GREY` (a card of a less grey lock is darker by its vertex colour).
    check_tiers (EEVEE strands, its own views): bare close_front / three_quarter 16-19% -> 9-11%, iou 0.79-0.81 ->
    0.83-0.85. Against the Cycles strands through the photo's camera / tq_desk (card_gain 0.62, card_sat 0.42):
    bare 10 / 7-8%, value 0.97 / 1.06-1.07 x, saturation 1.30 / 1.03 x.
  - BLUNT READ of h6_x2_sheet: strands = the right cut on the right hairline: a short greying crop, lifted front,
    pale sides; still browner on top and less visibly salt-and-pepper than the photo, sides stand off a little behind
    the ear. Cards = no longer a cap: volume and a broken outline, right colour and value; but the texture is WRONG,
    a tight tufted wool (astrakhan) in Blender's glTF look and coarse chopped fibre in Godot, not fine combed hair;
    the lifted front is only hinted; hero = main to the eye; a ragged wispy edge at the hairline in Godot.
  - NOT DONE: the wool (cards are 2 cm scraps each turned by `messy` 0.35 and tipped up: try longer cards along the
    flow, 2 layers in step, or tip lift only at the outline), a card front that stands like the strands' quiff,
    per-strand radius for grey, R/B the last 0.14, npc / far tiers, Khronos on exp_x2, the painting's own camera
    (cameras[1]) as the second view, g4_garrett's skin on the sheet (this branch lacks its skin keys), a test for
    "cards over the cap's surface". The groom is handed to garrett4 as spec["hair"] keys groom / strands / look /
    style of h6_garrett (locks regrown by hair.groom(replace=True, patch={"loose": ...})).

  Garrett, longer and swept back (2026-10-09, "hair7" agent; the user on h6_x2: "a little shorter than I visually read
  in the photo. In the photo, it's longer but feathered and kind of pushed back, which makes it look shorter"; model
  `workspace/h7_garrett` = a copy of h6_garrett (h6 untouched); sheet `hair_renders/h7_p7_sheet.png` = reference |
  before (hair6's groom regrown on this code: b0) | after (p7), front through the photo's fitted camera, three-quarter
  and side at 1.6 m long lens, Cycles strands, lookcam.SOFT; scratch DURABLE /mnt/data/hifipushie/hair7/: hair6's
  scripts retargeted (run.sh: M / CAM_MODEL = h7_garrett, this worktree's code), base.json = THE groom now (p7;
  base_hair6.json = hair6's), p1..p7 patches + logs, h7sheet.py <before> <after> <out>). No code changed.
  - p7 = hair6's groom with: lengths front 58 / top 50 / sides 28 / back 28 / nape 14 mm (were 29 / 30 / 20 / 22 /
    12); flow front [-0.3, 0.85, 0.4] (back, a little up, over to HIS RIGHT), top [-0.35, 0.9, 0], sides [0, 0.85,
    -0.55]; lay front 0.38 / top 0.68 (were 0 / 0.4); stiff front 0.5; out front 0.15, sides 0.18; uneven 1.0, messy
    0.4; groom.volume front 8 / sides 7 mm; strands clump 0.32, stray 0.7, frizz 0.08, tip_spread 0.75, tips 0.95.
    Hairline, grey, colours untouched.
  - Measured through the photo's camera (strandfit / headtop): hair over the bare head's top 15.3 mm (photo 12.7,
    before 11.5); across the top 8.9-12.7 mm vs the photo's 7.6-14 column by column (the highest point is the upper
    side over his left, 22.9 vs 19.1); IoU above the ears 0.923 (before 0.944); hairline centre -1.1 / outer -1.2 mm,
    forehead half-width +0.9 mm; colour unchanged (light share 0.38 vs 0.39, R/B 1.15). Lay is what holds a 5-6 cm
    top down: at lay top 0.5 the top stood +3.8 mm over the photo; 0.6-0.68 holds it.
  - Width: his right side (strandfit "L") reads 4-9 mm narrow, his left 0-8 mm wide at the lower levels in EVERY
    variant, whichever way the top is combed (+x, 0, -x changed it by <= 3 mm): a ~6 mm lateral offset of head vs photo
    at ear level, not the groom. Laying the sides (lay sides 0.2) took 8-10 mm off both: keep the sides unlaid.
  - BLUNT READ of h7_p7_sheet: three-quarter and side now show length: strands run back from the front in long
    sweeps (before: a short brushed crop). Front: the silhouette stays the photo's, but the top reads as a smoother,
    darker combed cap with a dark band along the front edge; the photo's front is paler, a little lifted and greyer on
    top. The painting has more lift at the front and more broken, feathered tips than ours; the tips' feathering
    (tip_spread, uneven) hardly shows at these distances. Cards not re-exported (strands first).
  - Round 8 (same agent; Joe: "a little front swoop which adds a lot of the character"; the coordinator on h7_p7:
    too dark / brown, frizzy, a helmet at the back from the side). Sheet `hair_renders/h8_p10_sheet.png` = reference |
    before (p7) | after (p10), same three rows + a front close-up row at the same crop and scale. base.json = p10
    (base_p7.json kept; patch p10.json on p7).
    - NEW `groom.loose.swoop` {at, span, depth, rise, sweep, stiff, length} (hair_loose.grow): locks rooted within
      `depth` m of the hairline and `span` deg of azimuth `at` are combed up-and-back (over to the `sweep` side),
      stand `rise` more out, are stiffer and longer and unlaid; smooth weights. Test
      test_swoop_lifts_the_front_lock_and_turns_it_over. Garrett: at 8, span 35, depth 0.035, rise 0.4, sweep -1
      (his right), stiff 0.75, length 0.018.
    - Straighter: strands frizz 0.03, stray 0.5, wave 0.0002, loose 0.08 (tips kept: tip_spread 0.75). Back / crown:
      lengths back 20 / nape 8 mm, lay back 0.8 / nape 0.6 / sides 0.1, stiff back 0.7 / sides 0.6, out back 0,
      volume crown 4 / back 3 / nape 1.5 mm, under_length 16 -> 12 mm. hstat (hair over the scalp, p90): sides
      12.3 -> 9.7 mm, back 7.0 -> 6.7; reads closer to the skull and straight from the side, nape cut short.
    - Front outline: IoU 0.923 -> 0.930, hair over the bare head 15.3 -> 17.8 mm (photo 12.7: the swoop's lift), but
      the sides went 4-9 mm narrow at 50-84 mm down (lay sides 0.1): the price of the slimmer back.
    - COLOUR, measured on the photo's hair region through its camera (cut.py's regions; photo_hair.json): the photo
      is NOT lighter than ours. Photo hair p50 (96, 84, 74), lum p50 86, light share 0.19; p7 (99, 91, 86) / 92 / 0.38;
      p10 (117, 109, 103) / 110 / 0.49 (grey front 0.55 / top 0.42). By these numbers ours is lighter and greyer
      (R/B 1.14 vs 1.30: the photo is warmer). The "light salt and pepper" read on a white backdrop is contrast, not
      value: don't go lighter by measure; if anything warmer.
    - BLUNT READ: the swoop shows as a lift at the front centre and a forelock flick in the side view, but as a frayed
      tuft, not one coherent lock curling over (the photo's is a clean wave); front sides narrower than the photo.
  - Round 9 (the coordinator on h8_p10: back and texture good; the swoop "a thin frayed tuft standing up" that pokes
    FORWARD past the forehead in profile). Sheet `hair_renders/h9_p12_sheet.png` (before p10 | after p12 + front
    close-up). base.json = p12 (base_p10.json kept).
    - The photo's front close-up read at its own scale (out/photo_front_zoom.png): no visible part; the front lock
      rises from the hairline just left of centre (his left, ~10 deg) and sweeps up and over to HIS RIGHT (image left),
      its ends feathering out over his right temple; the painting agrees (back over the right temple).
    - swoop reworked (hair_loose): the lift is UP-and-back by `rise` (world [0, 0.45, 1]), not along the scalp's
      normal (on the forehead the normal points forward: the cowlick); messy is off inside it (its locks in step);
      new keys `body` (its locks x wider and thicker, per-lock strands tip_spread 0.15, no wave: one coherent lock)
      and `lay` (0.06: at 0.3 the per-step lay killed the lift). Test asserts no swoop lock pokes > 3 mm forward of
      its root. Garrett: at 10, span 40, depth 0.04, rise 0.28, sweep -1, stiff 0.75, length 0.02, body 1.8.
    - Sides back to p7 (lay 0, out 0.18, stiff 0.55; sides p90 12.5 mm). The "4-9 mm narrow" on his right ("L") is
      there in EVERY variant incl. p7 at 50-84 mm down: the head-vs-photo offset noted in round 7, not the groom; his
      left is +0..+6. Top lay 0.8: across the top columns 12.7 / 12.7 / 12.7 / 10.2 mm vs the photo's 14 / 14 / 10.2 /
      7.6 (~13 as asked); the "top of hair" 16.6 is the upper side over his left (21.7 vs 19.1). IoU 0.923.
    - Warmer, not lighter: lit #664126, grey #c6a684, sheen #a88c70, grey front 0.45 / top 0.35: hair p50 (101, 92,
      85), lum 93, light 0.39, R/B 1.19 (p10 117 / 110 / 0.49 / 1.14; photo 96, 84, 74 / 86 / 0.19 / 1.30).
    - BLUNT READ: the swoop is now a darker, combed lock rolling from the front centre over to his right, behind the
      hairline in profile (no cowlick); it is subtle, a little flat, and reads as part of the combed mass more than as
      a lifted wave. Back and texture as round 8.
  - Round 10, the GAME-READY p12 (Joe: "if we can get the game-ready version of it to look like that"). Sheet
    `hair_renders/h10_c6_sheet.png` = photo | Cycles strands (target) | hero | main through Blender's glTF importer in
    EEVEE at the SAME cameras (front through the photo's camera, tq_desk, side_long; lookcam.SOFT) + front close-up +
    a Godot 4 row (look.gd a2c, its own cameras). h10_c1_sheet.png = the first export with round-6 constants (before).
    Scratch: exp.py `set=mod.CONST:json;...` (module constants for one export), cardsheet.py <strands tag> <export>
    <out> [tiers=] (the sheet + IoU + colour per tier/view), olap.py (where the outlines differ, row by row + mask),
    exports exp_c1 .. exp_c6.
    - Budgets (unchanged short tiers): hero 16,000 / main 7,998 / npc 4,000 / far 1,498 triangles; GLBs 1.34 MB /
      660 KB / 322 KB / 114 KB; ONE shared texture set 4096 x 2048 (basecolor RGBA 5.6 MB, normal 6.8, aux RGBA 5.6,
      flow 3.8, ORM 3.1 MB PNG): 27 MB for all four tiers.
    - Cause of the gap, by measure (olap.py on the front): the cards' outline stood 3-5 mm OUTSIDE the strands' all
      round the upper head (a helmet: cap at 0.9 of the hair's height + cards lifted to the top of their clump x1.3 +
      3 mm tips), and the card strands were thick and lit (beige wire). New defaults: hair.SHORT_TOP 1.3 -> 0.6,
      SHORT_TIP 3 -> 1.5 mm, SHORT_EDGE (new constant) 2 -> 0 mm, hair_cap.LIFT 0.9 -> 0.7 (VERSION 8),
      hair_cards.SHORT_TILE medium 36 x 3.2 px -> 56 x 2.2, sparse 22 x 3.0 -> 34 x 2.0, SHORT_DEPTH (new, was an
      inline 0.62) 0.45; the atlas cache key now includes both. look.card_sat 0.38 -> 0.2 (h7_garrett's spec).
    - Front IoU vs strands: hero 0.729 -> 0.754, main 0.721 -> 0.757; three-quarter 0.83 -> 0.85, side 0.89 -> 0.90.
      Colour (hair pixels, front): strands lum 104 / sat 0.146 / R/B 1.15; cards c1 103 / 0.201 / 1.24, c6 102 / 0.168
      / 1.20. Three-quarter and side: cards stay brighter (lum 88 / 80 vs the strands' 73 / 55): cards don't
      self-shadow. Left of the IoU gap: the strands' fuzz along the hairline (the cap's thinned edge reads ~4 mm
      higher than the strands' baby / scalp hairs) and the swoop side's upper rim.
    - BLUNT READ: in Godot the hero tier now reads as short greying combed-back hair of the right colour family, finer
      than round 6; in EEVEE's glTF look it is still coarser and browner than the strands. Wrong still: ragged card
      ends over the ears / sideburns, a pale speckled patch at the nape (the cap's sparse short hair: the nape is 8
      mm), the swoop only a faint lift (no card stands as one lock), hero = main to the eye, tiers' sides lighter than
      the strands. Not done: Godot through the photo's fitted camera (look.gd has its own cameras), Khronos on c6,
      baked depth / two-light shading in the cap chart for the three-quarter value.
  - Round 11, cards judged in GODOT (the coordinator: "a wiry steel-wool cap"; Joe: "a bald spot on the back of his
    head, and a black fringe"). Sheet `hair_renders/h11_c13_sheet.png` = photo | Cycles strands | hero GODOT | main
    GODOT | hero EEVEE (glTF import); rows front (photo camera), tq_desk, side_long, back_long, tq_back (new lookcam
    view, az -140) + a front close-up. Export /mnt/data/hifipushie/hair7/exp_c13 (Khronos 0 errors 0 warnings).
    Scratch: gdcams.py (the sheet's cameras for Godot in glTF axes; the photo camera as an OFF-AXIS frustum
    = Camera3D PROJECTION_FRUSTUM size / offset per near distance), gd2.sh <tag> <tier|-> <std|kk> <name> (look2.gd),
    q11.sh (bald + before + tiers, then covg.py: bare share inside the hair's outline vs the bald render, and the
    outline's dark-rim share), iougd.py, h11sheet.py, swdbg.py.
    - What shipped real-time hair does vs ours (UE groom cards / Scheuermann-Kajiya-Kay / the Sucker Punch, EA and
      Naughty Dog talks): two shifted highlight lobes along the strand tangent (one white, one tinted), wrapped diffuse,
      root-to-tip and in-clump shade, a scalp tint under the hair, alpha-to-coverage. Our Godot check used Godot's
      StandardMaterial: ONE GGX anisotropic lobe from the flow map and nothing of the aux texture (root gradient,
      strand id, clump depth): the uniform fine hatch. NEW `spikes/godot_hair/hair_cards.gdshader` (Kajiya-Kay two
      lobes shifted by aux G, wrap diffuse, aux R / B shade, softened shadow, a2c) + `look2.gd` (given cameras, std |
      kk). Biggest single change in the look: broad soft highlight bands, reads as combed hair.
    - BLACK FRINGE: not black RGB under the alpha (atlas tiles: clear / rim / core lum 52 / 49 / 48; cap 103 / 53 / 59)
      but BACK FACES: Godot flips NORMAL on back faces of cull-disabled meshes, and our two-sided cards share one bent
      normal (the recipe says so), so every card seen from behind (silhouettes, over the ears) was lit from inside.
      The shader un-flips (FRONT_FACING). Outline pixels darker than lum 40: 4-14% (std) -> 0.3-2.8% (kk). An engine
      on a StandardMaterial keeps the fringe: the recipe's "do not flip them on back faces" is the requirement.
      Also edge padding from the strand core (hair_cards.EDGE_SOLID 0.5: the rim takes the core's values; it was
      0.03), test test_atlas_edges_are_padded_not_black (passes either way on the drawn atlas: the fringe was shading).
    - BALD SPOT: the cap chart's opaque base needed coverage 0.3+; the 8 mm nape is sparser, so skin showed in a big
      pale patch. hair_cap.BASE_DENSE (0.3, 0.35) -> (0.05, 0.2) and BASE_DEPTH 0.22 -> 0.5 (the base is a scalp tint
      in the hair's own colour, at 0.22 a near-black band), VERSION 10. Bare share inside the hair from behind 9.7% ->
      0.7%, three-quarter back 4.9% -> 1.3% (hero; far 0.6 / 1.5%). The nape still reads as a darker band (Cycles has one
      too), and the back's card texture is curlier than the strands'.
    - SWOOP as cards: `lk["swoop"]` (hair_loose marks the swoop's locks; LOCK_KEYS, resolve), hair.cards_job gives the
      strongest SWOOP_CARDS 3 locks their own cards: starting SWOOP_BACK 6 mm inside the hairline, narrow root,
      tapered tip, SWOOP_LAYERS 3 stacked fine short-tile cards SWOOP_GAP 1.2 mm apart, risen SWOOP_LIFT 4 mm mid-lock
      (the wave), kept first by the budget. On the DENSE tile they were a smooth grey plate on the forehead (its 16 cm
      strands squeezed onto 4 cm). In Godot the front now lifts and rolls back in profile; from the front it is still
      not a distinct lock.
    - Godot front IoU vs the strands' id pass is ~0.6 for every tier (c6 std 0.648, c13 hero / main / far 0.617 /
      0.613 / 0.595): NOT comparable with EEVEE's 0.75, Godot's body is garrett4's exported head (g4_tex.glb), a
      different face, and the hair sits a little smaller in the frame. Godot hair colour: lum 118, sat 0.14, R/B 1.14
      (std: 117 / 0.067 / 1.06, grey-blue).
    - Hero vs main: the same atlas, the same cap; hero's extra 8k triangles go to a second card layer that overlaps
      the first: nothing reads at bust distance. Ship main as LOD0, or give hero a different job (a denser hairline
      and sideburn of fine cards, more swoop layers) before it earns its triangles.
    - BLUNT READ (Godot): combed greying hair with soft highlight bands, no bald spot, no black outline; still: the
      back's texture curly, a darker nape band, the hairline a little hard and higher than the strands' fuzz, the
      swoop weak from the front, hero = main.
  - Round 12, judged in Godot (sheet `hair_renders/h12_c19_sheet.png`, same layout as h11; export
    /mnt/data/hifipushie/hair7/exp_c19, Khronos 0 / 0; groom = base.json = p13 + p14 + p15; strand panels p16 (front,
    three-quarter) and p15 (side, back)). Scratch adds naped.py (lum by height band from behind, Godot vs strands).
    - THE CURLY BACK was the GROOM, not the cards: the Cycles strands were curly from behind too, with an orange-brown
      scalp-tint band at the 8 mm nape (a bald-looking strip in the target itself). Straightening card paths toward
      their chord (hair.SHORT_STRAIGHT 0.6, kept: no harm) and `messy` per region (new: `groom.loose.messy` takes
      regions; Garrett front 0.45 / top 0.4 / sides 0.2 / back 0.08 / nape 0.05) changed nothing visible. What fixed it:
      back 28 / nape 18 mm (were 20 / 8), stiff back 0.6 / nape 0.65, lay back 0.7 / nape 0.6, flow back [0, 0.15, -1],
      volume nape 3 mm. Strands and cards from behind now read as short hair combed down.
    - Nape value (naped.py, back view, lum per fifth of the hair's height): Godot c13 [100, 111, 78, 57, 41], nape /
      band above 0.72; c19 [101, 111, 78, 66, 70], 1.06; strands 1.12. hair_cap.BASE_DEPTH 0.5 -> 0.75 (VERSION 11).
      Godot's back is still lighter at the top than the strands' (its key light from above; the strands' back is an
      even 50): lighting, not the asset.
    - Hero's soft hairline: NOT achieved. Baby-hair cards on hero (baby 3 / cm, kept by the budget:
      hair.SHORT_BABY_PRIO, constant kept) are invisible: the baby tile is 1.5-3% covered (a handful of hairs from the
      groom's tile lines, which cap the count); on the hairline tile they were opaque stamps on the forehead. Reverted
      (hero baby 0, SHORT_TILE baby (9, 3.0)). A real soft line needs its own tile drawn as many fine short hairs at
      the strands' height (or the cap chart's edge drawn finer and lower), not a re-use of the long-hair tiles.
    - HERO vs MAIN: still not visibly different in Godot at any of the five views (same atlas and cap; hero's extra
      triangles are a second overlapping card layer). Recommend dropping hero: ship main (8k) as LOD0, npc, far.
    - Swoop from the front: neither the Cycles strands nor the cards read as one lock lifting and rolling over to his
      right from the photo's camera; in profile both lift and roll back. The swoop's strands lie too flat at the
      front for a front-view silhouette; it needs a higher, more forward rise at the root (the cowlick limit) or a
      side-swept front edge: not done.
    - Consumer: spikes/godot_hair/README.md (textures, parameters, the back-face note; not in any game yet) and
      hair_guide.md "Drawing the cards in an engine" + "A front swoop and a combed-down back".

## EEVEE strand look on sparse long hair (2026-10-09, "tess" agent)
- blender_strands' EEVEE material (EEVEE_SAT 0.35, eevee_gain 1.6, specular 0.5 x 0.6, sheen tint) was calibrated on
  Garrett's dense short grey cut. On sparse FREE hair (curtains, wisps, a tail's lower half: few thin strands against
  a light background) the specular and sheen dominate and the gain lifts it: Tess's dark brown free hair read silvery
  grey while her head hair was right. Look keys that fixed it (no code change): eevee_sat 0.6, eevee_gain 1.15,
  specular 0.25, roughness 0.55, sheen_amount 0.2, sheen #5c4231 (not a grey), tip_amount 0.12.
- tie.curtain.along (deg): the front locks run sideways just inside the hairline before falling (hair_tied.py); without
  it a centre part's two curtains diverge in a V that bares the forehead's top corners (root map: spikes/tess/roots.py;
  Tess's front hairline band bare 34% -> 8%).

### Garrett's hair carried onto the new head (2026-10-09, tess agent)
- New general groom key `fit` (hair.fit_to_head / head_ref; test_hair_loose::test_groom_fits_a_smaller_head): the head a groom was made on; lengths / volumes / offsets in metres scale by the new head's scalp radius over that one, traced front_points move with the head centre. Applied in hair.grow and hair.hairline. h7_garrett's groom (hair7-12, head_size 1.138) onto fs_gj8 (1.0): gc_raw (metres as written) vs gc_fit. Hand-traced hair outlines (trace_garrett.json, gscore.py): front IoU old 0.687 / raw 0.476 / fit 0.687 (chamfer 9.6 / 11.8 / 8.8 mm). Desk painting: 0.38 / 0.31 / 0.33, unreliable (the painting's fitted camera frames the head differently from the photo crop). Colour: ours lighter than the concept (front mid #9a8c82 vs #6a5e54).

## Hair colour from a photo: look.seen (2026-10-10, "jw2" agent)
- A light-brown photo colour typed into `lit` rendered grey-blond: EEVEE's strand material multiplies the colour's
  HSV saturation by eevee_sat 0.35 (linear) to copy Cycles' chroma loss, so it can never show more than 0.35 saturation:
  a light brown (linear HSV saturation ~0.6) is out of reach for ANY lit. New key `look.seen` (hair.seen_look /
  full_look, used everywhere the look was merged): lit = seen's hue and value at saturation / eevee_sat (capped at 1),
  eevee_sat = seen's / lit's (EEVEE draws seen exactly), gap / sheen / tip as multiples of lit, and the scalp tint
  ("scalp") and card_sat from seen (the boosted lit showed as an orange scalp between partings). Explicit colour keys
  win. test_hair_strands::test_seen_colour_reads_as_asked_in_eevee.
- Measured on jw (flat frontal light, EEVEE): the rendered lit hair matched the photo's lit-hair numbers but came out
  ~1.25x as saturated as seen, and the same numbers read ginger on our grey backdrop beside a photo with a warm wall:
  sample seen from the photo's LIT side (the render makes its own shadows) and ask a little less saturated.

## tesshair (2026-10-11, "tesshair" agent, branch `worktree-agent-a1e75b477d022cecb`): Tess's hair on her accepted head tess_a1
STATE / NEXT: 5 rounds done, BEST = th_T04 (tess_a1 + f3_t1's groom regrown + p02 + p03 + p04), sheet
workspace/human_renders/th_01_tess_hair_rounds.png. Right style, hairline height and tail place; texture, wisps and
the unseen angles are wrong. NEXT: the list at the end of this section (back shell faults first).

Scratch DURABLE /mnt/data/hifipushie/tesshair/ (run.sh <script in spikes/tesshair> = this worktree's code on the main
workspace, capped, 1 BLAS thread; round.sh <NN> <patch.json ..> = a whole round; p<NN>.json = the rounds' patches;
out/ = tiles s_<model>_<view>.png, overlays hline_*, logs r<NN>_*.txt). Scripts `spikes/tesshair/`:
- mk.py <dst> <head model> <groom model> [patches]: head model's spec + hair.carry(groom model) WITHOUT locks +
  deep-merged patches, hair.groom(replace=True). 23 s. Only writes th_* models.
- shots.py <model> [engine=cycles] [extra_only=1]: the dressed stage (garrett3/stage.py, `_g3_<model>`, 53 s sync) with
  the groom through the three fitted cameras (the WHOLE picture squared, so the tail is in frame) + backl (the unfitted
  back picture's side), backq and right (not in the references). Under resources.heavy.
- hline.py <model> [0,1]: THE HAIRLINE BY PROPORTION, like with like: MediaPipe on her picture AND on our render through
  that picture's camera; frame = eye-corner span, eye line, mouth line (U = eye -> mouth), brow line, chin; skin = Lab
  distance to the forehead's own colour; per station across the forehead where skin ends (height over the eye line /
  U), per level the forehead's half-width, forehead / lower-face ratio; and the OUTLINE (head + hair against the
  backdrop): top per station, half-width per level. Misses in mm. Overlay hline_<model>_v<n>.png (check it: red = skin).
- hs.py <model>: the tess agent's hscore.py (traces in /mnt/data/hifipushie/tess) under the heavy slot.
- sheet.py <out> <title>=<model> ..: reference | best | earlier; six rows.
NB a model's stage keeps the hair it was first synced with (the stage key leaves hair out): one model name per groom.

- th_T01 (carry, no patch): groom.fit r 0.0746 -> this head 0.0710 (centre 3.9 mm lower, 1.3 mm back): lengths scale
  x0.951. 86 locks. hscore IoU front / 3q / profile 0.630 / 0.641 / 0.639 (f3_t1 on its own head 0.601 / 0.596 /
  0.651), hairline band bare 16.4 / 22.4 / 9.2%, forehead arch ours - hers +6.3 +5.9 +2.0 +6.1 -1.5 mm (+ = our edge
  lower), colour bands within 2-10 levels of hers. hline FRONT: forehead / lower face 0.37 hers vs ours close (centre
  hairline +0.9 mm, outer -2.1, temples -0.3: the hairline's HEIGHT is right on this head), outline top -5.3 mm (flat),
  width above the eyes her right -1.0 / her left -5.5 mm, and at eye .. mouth level her left -27 .. -35 mm (the tail).
  BLUNT READ: it is recognisably her style (centre part, low side ponytail, right colour family) and nothing broke in
  the carry. Wrong, biggest first: (1) the TAIL is a straight narrow broom hanging down the neck; hers stands out to
  her left / back from the tie and is a bushy, waved, flicked brush twice as wide; (2) the head hair is SLICK: dense
  combed sheets, 5 mm flat on top, no loose halo; hers is matte, airy, tousled; (3) the WISPS are straight comb strips
  hanging from the temples; hers are single fine curved strands; (4) the forehead is a pointed triangle under the part
  (curtains run straight diagonals; +6 mm low at the upper corners); hers is a round arch; (5) a hooked swirl of curtain
  strands in front of the ear in profile; (6) a dark object at the top of the part (seen from behind), dotted scalp at
  the nape.
- UNSEEN ANGLES ARE WORSE THAN THE REFERENCE ANGLES (backl / backq / right): from behind the gathered hair is a shell
  with a frayed rim standing off down her right-back (a hood's edge) and stubble along the crown; from her right the
  first (curtain) row lies as a thick band over the ear like a headband. The groom was only ever tuned through the
  three pictures' cameras. Cause NOT isolated (suspects: the scalp under-layer's 6 cm tips, row 0 riding 8 mm over
  rows 1-2, only row 1-2 roots covering the top behind the part).
- shots.py's unseen views: the front light turned round the head with the camera (lit from the front they were black).
- th_T02 (tail dir [0.75, 0.55, 0.15], stiff 0.5, length 0.24, fullness 0.055, 26 locks, uneven 0.8, taper 0.3,
  tail.strands wave 0.018 / wavelength 0.09 / frizz 0.35 / loose 0.8): OVERSHOT, the tail a flag standing out: IoU 0.48
  / 0.28 / 0.45, front width her left +36 .. +44 mm (T01 -27 .. -35).
- th_T03 (between: dir [0.56, 0.5, -0.35], stiff 0.36, length 0.22, fullness 0.05): IoU 0.758 / 0.469 / 0.682; front
  width her left +2.3 / +0.3 mm at mouth level, -16 at eye level. Tail from behind = crimped ramen (wave 0.018 + frizz
  0.35 + loose 0.8 is too much).
- th_T04 (tail dir [0.8, 0.15, -0.35], fullness 0.046, tail.strands wave 0.012 / wavelength 0.12 / random 0.3 / frizz
  0.15 / loose 0.5; volume front 6 / top 16 / crown 17 / sides 13 mm, gather lift 9 mm): IoU 0.680 / 0.489 / 0.722,
  outline top -3.4 mm (was -5.4), width above the eyes +1.3 / -0.9 mm, her left at mouth level +10 / +4 mm.
- THE 3/4 VIEW CANNOT BE CLOSED BY THE HAIR: through its fitted camera our face is smaller than hers (eye span 52.6
  vs 57.9 mm) while our hair mass is bigger (92k vs 79k px); our hair overlaps her forehead on one side and overshoots
  behind on the other (out/hscore_th_T04_1.png). The head / camera of that view disagree with the picture; front and
  profile agree. Judge the tail on front + profile; the 3/4 IoU is not a hair number on this head.
- th_T05 (T04 + curtain dip -20, escape 6, frame count [4, 3] / width 1.5-3 mm / length 9-17 cm / wave 0.02 /
  wavelength 0.06, gather.strands flyaway 0.25 / frizz 0.3, strands flyaway 0.25): IoU 0.676 / 0.484 / 0.724. Forehead
  arch ours - hers +2.1 +1.5 -3.2 +2.5 -6.3 mm (T04 +6.1 +5.1 +1.6 +6.1 -1.6): the corners close and the arch reads
  rounder, but the centre goes +4.2 mm HIGH (forehead / lower face 0.371 vs hers 0.342; T04 0.339) with a bare notch
  under the part: dip -16 is the next try. The wisps got WORSE: more of the same straight wet strings, in bunches over
  the cheek in profile; no visible halo from flyaway 0.25. Not a clear gain: rounds stopped here.
- BEST = th_T04. Sheet `workspace/human_renders/th_01_tess_hair_rounds.png` (reference | T04 | T05 | T03 | T02 | T01;
  rows front / 3q / profile through the fitted cameras, back-left beside the unfitted back picture, back-right and
  right profile unseen). Numbers T04: forehead / lower face 0.339 vs 0.342 (hairline centre +0.9 mm, outer -1.9,
  temples -0.2), outline top -3.4 mm, width above the eyes +1.3 / -0.9 mm, IoU 0.680 / 0.489 / 0.722 (T01 0.630 /
  0.641 / 0.639), hairline band bare 22.8 / 20.6 / 8.4%, colour shadow / mid / highlight front #291d14 #43352b #625247
  vs hers #221b13 #3f3226 #675342.
- BLUNT READ of T04 against the pictures: hairline HEIGHT right by proportion; its SHAPE wrong (a pointed triangle,
  upper corners ~6 mm low). Top and sides: silhouette within 2-3 mm, but the surface is slick combed sheets, hers is
  loose, matte, tousled with a fine halo. Tail: right place and now about the right size and side, a bushy mass; but
  blunt straw ends, no big S-waves or flicked ends, and from behind a crimped wool. Loose front strands: the worst
  feature: a few straight comb-strips; hers are many single fine curved hairs. Colour: bands within ~10 levels;
  sheen: ours has no warm chestnut highlights (flat grey-brown). Unseen angles: hood rim at her right-back, headband
  band over the right ear, stubble on the crown, dots at the nape, a dark object at the part's top. NOT her hair yet:
  the right style on the right hairline with the wrong texture.
- NEXT, in order: (1) isolate the back shell faults with hair.look(only=) / debug (rim, headband row, crown stubble,
  the dark object) and fix them in hair_tied (likely: a gather row that runs OVER the top behind the part, row 0's
  8 mm ride height, under_length); (2) wisps as single strands: frame pieces' hard-coded strands (clump 0.3, flat 3)
  make comb strips: needs per-piece curl / wave phase and 3-8 strands a piece (a code change in hair_tied / lens
  group, not a dial); (3) curtain dip -16 for the arch; (4) tail: large-scale S-wave of the CORE line + tapered
  uneven ends (tail.strands waves only crimp); (5) a Cycles look for sheen / colour (EEVEE only so far; never queued:
  the heavy slot was free all session); (6) re-fit the 3/4 camera or drop that view for hair.
- TOOLING GAPS (Python-only): hair.carry + regrow onto another head (no MCP tool: groom_hair cannot take a groom from
  another model); dressed renders through the references' fitted cameras (garrett3/stage.py, a spike); hscore and the
  like-with-like hairline measure (spikes); look_hair has no "unseen angles" row, which is where this groom is worst.

STATE / NEXT (end of session): best th_T04, sheet th_01_tess_hair_rounds.png, 5 rounds; NEXT = the list above.

## tesshair2 (2026-10-11, "tesshair2" agent, branch `worktree-agent-a1369a88d9730a4d3`): Tess's hair, second round
STATE / NEXT: 9 rounds (th_T06 .. T14), BEST = th_T14 (th_T04's recipe + spikes/tesshair2/p06 .. p14). Sheets
`workspace/human_renders/th_03_tess_hair_rounds.png` (reference | T14 Cycles | T14 EEVEE | T11 | T07 | T06 | T04) and
th_02 (the EEVEE rounds T11 / T09 / T08 / T07 / T06 / T04). The back shell is whole, the wisps are single curved
hairs, the tail waves and ends in flicked points, the forehead is a round arch (hline stations within 2.2 mm but one),
Cycles gives the soft matte read. Still NOT her hair: see the blunt read. NEXT: the list at the end of this section.

Scratch DURABLE /mnt/data/hifipushie/tesshair2/ (run.sh = this worktree's code, scripts looked up in
spikes/tesshair2 then spikes/tesshair; mk.sh <NN> <patches> = th_T04's recipe + patches, refuses T01-T05; q.sh <tag>
<patches> = 1 min: regrow, front + profile tiles, hline of the front; round.sh <NN> <patches> = a whole round;
copies in spikes/tesshair2/). Scripts `spikes/tesshair2/`:
- iso.py <model> <tag>=<variant> .. [views= size= fov= dz=]: ISOLATE faults: the model's hair changed in memory
  (only:/drop: lock patterns, S.<dial>:v, L.<pat>.<key>:v, LS.<pat>.<dial>:v, joined with +) and rendered on one
  shared stage, a row a variant, ~5 s a frame. Views backq / right / backl / back / topback / top / front / left /
  frontq / frontr. THE tool of this round: every back shell fault was found with it in minutes.
- shared.py: every th_* model has tess_a1's head, so they share ONE dressed stage (th_T04's) wearing the model's own
  hair (no 53 s sync per model); shots2.py / v0.py use it. NB hscore's IoU reads the stage's OWN hair objects (ID
  pass), so hs.py must run un-shared (round.sh does; hs2.py on the shared stage returns th_T04's IoU: do not use).
- cyc.py <model> <tag>=<look json> ..: look variants in Cycles through a fitted camera, the picture beside.
- napedots.py: the scalp mesh's density / radius by elevation at the nape. exptest.py: the Blender export test with
  the workspace env (bare pytest skips it silently: "passed in 0.5 s" = no model found).

### What caused each back-shell fault (th_T04; found by switching pieces off, iso.py)
- BARE WEDGE behind the part / "dark object at the part's top" / the thick "headband" over the right ear / most of
  the "hood rim": ONE cause. The tie is low and to her left ([151, -6]); the inner gather rows root "on the way from
  the hairline to the tie", so rows 1-2 all rooted on the tie's side: the whole right half of the top had no lock but
  the hairline row, which runs round the hairline to the tie (row 0 alone = a turban's band; rows 1 / 2 alone cover
  only the left-back). The wedge between the two banks showed the scalp layer; its banks were the rim and the band.
  FIX `gather.toward: "crown"` (inner rows root up the head from every side; + rows 4, locks 80, reach 0.9).
- "The first row riding 8 mm high" (suspect): NOT the cause. `gather.ride` 0.003 -> 0.001 changed nothing visible.
- "The 6 cm scalp under-layer" (suspect): partly. Alone it is a bowl cut with a mullet fringe below the nape; where
  no lock covered it (the wedge) its ends were the crown's stubble. With the shell whole it is hidden; under_length
  0.06 -> 0.025 all the same.
- STUBBLE ON THE CROWN that stayed: `roots` (strand starts staggered along the lock, x4 on hairline locks) on the
  INNER rows: starts in the middle of the hair. FIX `gather.inner_roots: 0` (the hairline row keeps its soft start;
  roots 0 on every gather lock made the front hairline a hard edge).
- DOTS AT THE NAPE (and dashes floating behind the neck): the scalp mesh. Her nape hairline is at -60 deg from the
  head centre, where the scalp's rays step from the neck (r 0.103) out to the back (r 0.141): the margin row's quads
  spanned that step as a sheet standing out behind the neck, with density 0.04-0.1: its few hairs were the dots.
  FIX in `hair_strands.scalp_mesh`: quads whose corners differ 2 cm in radius are dropped (unconditional: such a quad
  is never scalp).
- TERRACED CONTOUR LINES AT THE TEMPLE ("finger waves" in front of the ear): the hairline row is the only hair over
  the bare skin there (the groom's hairline is high at the sides) and it was THIN (gather density 0.6, the under layer
  taking 60% of the count): its sub clumps drew as parallel lines on skin. FIX `gather.hairline_strands {"density": 2,
  "clump": 0}`, under 2.0 -> 1.2, count 70k -> 85k. Better, not gone.
- WHY flyaway 0.25 SHOWED NOTHING: the dial is x 0.12 (3% of strands), a gather lock's fly distance is x 0.3 of
  min(2 cm, 0.8 width) = 6 mm, it grows as t^1.7 toward the TIP, and a gather lock's tip is IN the tie: 3% of the
  strands lifting 6 mm on their way into the tie. Not a halo by construction. FIX the `halo` dial (below).

### Code (old behaviour is the default everywhere; tests below)
- hair_tied.py: gather `toward` ("tie" | "crown"), `reach`, `ride`, `inner_roots`, `hairline_strands`; curtain `rows`
  (how many rows take the way over the ear), `arch` + `arch_at` (the run raised over the forehead's corners only),
  `smooth`; frame `hairs` (pieces of 1..n SINGLE hairs), `curve` (each piece bowed in its own plane + a slow S + a
  flicked tip), `strands` (the pieces' dials; the old hard-coded ones = FRAME_STRANDS); tail `sway` + `sway_length`
  (the AXIS swings: big soft waves), `flick` (lock ends turn out).
- hair.py: lock key `hairs` (LOCK_KEYS, resolve), look `fine_alpha` (0.5).
- hair_strands.py: a third guide object `hair_guides_wisp` for locks with `hairs` (exactly n strands a lock, Amount 1,
  no clump / flyaway, radius x 0.8, hp_fine 1): a lock's share is never under ~8 strands (hp_n >= 1 x Amount 8),
  which IS the comb strip; a lock's own `clump` / `tips` / `roots` (per-curve hp_clx / hp_ts / hp_rs: the dials are
  one number an object); `strands.free` {dial: value} = the dials of hair that left the head; `halo` dial (stack
  inputs only when > 0, so older jobs keep their cache keys); the scalp mesh fix.
- blender_strands.py: lens group VERSION 11: Halo / Halo Distance / Halo Length (a copy starts anywhere along its
  lock, runs ~5 cm, lifts 4-16 mm off the lock's outer side and curls: ends in the air), Fine + hp_fine, hp_clx;
  the EEVEE material draws hp_fine strands at look.fine_alpha (dithered): a strand is never drawn under a pixel wide,
  so single hairs were 1 mm wires. hair_cards.py: STRANDS `halo`, `free`; cards also take wisp strands.
- hair_guide.md: the low side tie recipe, arch, single hairs, tail sway / flick, halo, free, per-lock dials.
- TESTS RUN: tests/test_hair_tied.py (14 passed: 6 new), test_hair_loose.py + test_hair_lift.py (15 passed),
  test_hair_strands.py (23 passed: 3 new) + the Blender export test on hs_tess through exptest.py (passed, 38 s).

### Rounds (hline front = like-with-like stations; hscore IoU front / 3q / profile; T04 = 0.680 / 0.489 / 0.722)
- th_T06 (p06: toward crown, rows 4, locks 80, reach 0.9, inner_roots 0, under_length 0.025): the shell is whole from
  every side. hline centre +1.4 / outer -0.9 / temples +0.9 mm, top +5.3 mm (T04 -3.4: four rows are taller), width
  her right +7.2.
- th_T07 (+ p07 single-hair frame [10, 6] x 1-3 hairs, curve 0.14, halo 0.5; p07c gather lift 9 -> 5 mm, arch 8,
  dip -9): IoU 0.705 / 0.511 / 0.725; hline centre +1.5, outer +0.6, temples +1.9, top +2.1, width +4.3 / -1.5.
  First tries that were WORSE and why: 12 + 10 pieces x 3 hairs at full opacity = bunches of wires; halo on the tail
  = a bottle brush (now x 0.25 on free hair); curtain rows 3 = a tangled mound over the ear (left at 1).
- th_T08 (+ p08 tail sway 0.012 / 0.17, flick 0.022, taper 0.1, uneven 1, locks 22, tail strands clump 0.75 tips 0.9
  tip_spread 0.1 wave 0.02 / 0.15; strands.free loose 0.22): wavy locks with pointed ends, but IoU 0.649 / 0.440 /
  0.685: the tail stood out too far and was thin (doll ringlets). THE WOOL WAS `loose`: with loose 0 on the tail the
  locks are clean and defined; 0.7 (the head's) crimps every strand (Hair Curves Noise 8 mm).
- th_T09 (+ p09 tail dir [0.7, 0.05, -0.6], stiff 0.3, length 0.25, sway 0.016 / 0.22, wave 0.012 / 0.2 random 0.7;
  curtain smooth 3, left over 24): front IoU 0.691, profile 0.661 (too long); smoothing lifted the hairline +3 mm.
- th_T10 / T11 (smooth 1, dip -6, arch 6; tail 0.225): T11 IoU 0.690 / 0.504 / 0.693, hline centre +0.5, outer +0.1,
  temples +1.6, top +2.0. From behind the tail was thin wet ropes; contour lines at the temple.
- th_T12 (+ p12 hairline_strands density 2 clump 0, under 1.2, count 85k, tail fullness 0.054 locks 28 clump 0.55,
  free loose 0.35): front IoU 0.703, hairline band bare 17.3% (T04 22.8); the denser row made the forehead a TENT
  again (straight diagonals).
- th_T13 = th_T14 (+ p13 arch 8 at 22, her right arch 26, tail fullness 0.049; p14 look cycles_fit [0.9, 0.55]):
  hline front stations (ours - hers, mm, her right .. her left): -1.5 -1.8 -0.8 -0.7 +1.3 +0.8 -0.2 -1.2 +2.2 +3.6
  (th_T06, the shell fix alone with th_T04's curtain: -4.5 -1.8 -0.2 +0.8 +2.8 +3.4 +1.4 -1.2 +1.7 +3.6); centre +0.0, outer +0.1,
  temples +1.8, top +1.8 mm, width above the eyes +4.9 / +2.0; forehead / lower face 0.344 vs hers 0.342.
  IoU 0.695 / 0.514 / 0.674 (profile: ours 114.6k px vs hers 98.4k: the tail is too big from the side), hairline band
  bare 17.8 / 11.8 / 8.5% (T04 22.8 / 20.6 / 8.4).
- THE TWO ARCH MEASURES DISAGREE: hscore's "forehead arch" still says ours is 4-6 mm LOW at the corners (+3.9 +6.4
  +3.7 +5.1 -3.1; centre peak hers 25.2, ours 16.8 mm up) where hline says within 2 mm. hscore finds "highest skin" on
  the beauty render against a traced hull: fine hairs and the denser hairline row count as not-skin. I trust hline
  (same detector on both pictures, overlay checked), but the tent in th_T12's overlay was real and hline's summary
  hid it: READ THE STATIONS, not the summary line.
- CYCLES (item 4): the stored look through the default cycles_fit (0.75, 0.307: fitted under the salon lights)
  renders BLACK on this stage (photo light, exposure -0.55); cycles_fit [1, 1] = a pale ash haze; warm lit colours
  with [1, 1] = ginger. cycles_fit [0.9, 0.55] with the look's own colours = dark brown with warm lit strands: the
  nearest (cyc_th_T13_d_e_f_v0.png, a_b_c). In Cycles the texture is what EEVEE cannot show: soft, matte, fine;
  the EEVEE columns over-state every strand (wires). JUDGE TEXTURE IN CYCLES, form and measures in EEVEE.

### BLUNT READ of th_T14 against her pictures (the list of the brief)
5. Unseen angles: FIXED (wedge, band, rim, crown stubble, nape dots, the object at the part: causes above). Left: the
   nape and behind-ear edge is a clean combed fringe (hers has fine baby hairs), the temple still shows wave lines.
2. Front wisps: BETTER in kind (single fine curved hairs, each its own bend), still wrong: too few and too regular,
   they hang as separate arcs off the face; hers are many, mostly short, tangled into the hair beside the face. In
   Cycles they nearly vanish (true width at 768 px).
1. Texture: BETTER. Tail: big waves, separate locks, flicked tapered ends, bushy from behind; but the waves are too
   regular (a doll's ringlets in EEVEE), and it is 16% too big in profile. Head: still combed bands in EEVEE; in
   Cycles soft and matte, close to hers, but smoother (no loops, no loose strands crossing the flow). Halo: there
   now, faint; hers is longer looping hairs, ours short bristles.
3. Hairline shape: FIXED by measure (round arch, every station but one within 2.2 mm; th_T06 up to 4.5), height kept.
   Her left corner (s +0.4) still +3.6 mm high.
4. Sheen / colour: BETTER in Cycles only (dark brown, warm lit strands); still darker and flatter than her chestnut
   highlights, the back views under-lit; EEVEE stays flat grey-brown (its material desaturates by design).
   Three-quarter view: nothing new learned; its IoU stays ~0.5 for the reason in the tesshair notes.

NEXT: (1) the look: a calibrated cycles_fit for the photo light (the fit was made under the salon lights), lighter
tips / highlight streaks (look.tip_amount, vary), a rim light for the back views; (2) wisps: more and shorter, rooted
along the whole front hairline, some lying INTO the curtain; loops in the halo (Halo Length 5 -> 10 cm, curl back to
the head); (3) the tail's regularity: per-lock sway phase / wavelength spread, two lock lengths, fullness by view
(flatten the tail: it is round, hers is a fan seen from the side); (4) the head's combed bands: break the gather
locks' flow with a few crossing strands (a `cross` share in the lens group), lift at the front (her hair stands
5 mm forward of ours over the forehead in profile); (5) baby hairs at the nape and behind the ear; (6) TOOLS, not
done this round: hair.carry onto another head, renders through the references' fitted cameras, the hline measure
and an unseen-angle row in look_hair are still Python-only (iso.py's views are the row to add: backq, right, backl,
topback).

## Joe on tesshair2 (2026-10-11, th_03)
"I feel like 11 actually reads better than 14, but the actual hair styling is wrong, it's flat across her head instead
of swept back and hanging down. This is a super common hairstyle, so we need to be able to get it right and
repeat/riff on it." -> th_T11 is the start, not th_T14. Round three ("tesshair3" agent, section "## tesshair3"): the
construction of a tied-back style (flow from roots to the tie along the head, root lift, a tail that hangs), as a
repeatable style with a small parameter set and an MCP tool, proven by riffs and on a second head.

## tesshair3 (2026-10-11, "tesshair3" agent, branch `worktree-agent-a9ff53d876e89ff26`): swept-back tied hair as a STYLE
STATE / NEXT: DONE this round: `hair_flow.py` (flow-field gather, hanging tail, escaped hairs) + the STYLE `groom.tied` + tool `tie_hair` + look_hair views "around"; BEST = th_T34 (one style call on tess_a1). Sheets workspace/human_renders/th_10_tess_swept_back.png (reference | T34 EEVEE | T34 Cycles | T11 | T14), th_11_tied_riffs.png (her style + 6 riffs), th_12_tied_other_head.png (hu_w28d). It reads swept back and hanging; NOT yet her hair in texture (tail ends, smooth head, hairline step). NEXT: the list at the end of this section (tail ends first).

Joe on th_03 (round two): "11 actually reads better than 14, but the actual hair styling is wrong, it's flat across
her head instead of swept back and hanging down. This is a super common hairstyle, so we need to be able to get it
right and repeat/riff on it." So this round replaced the construction and made it a style; no dials on the old one.

Scratch DURABLE /mnt/data/hifipushie/tesshair3/ (run.sh <script> = this worktree's code on the main workspace, capped,
scripts looked up in spikes/tesshair3, tesshair2, tesshair; q3.sh <NN> '<style json>' [views] = th_T<NN> regrown + one
row of unfitted views; round3.sh <model> [cycles] = six tiles + hline + hscore; riffs.sh + riffs.txt = the riffs
through the tool; cmp.py = reference | models through the fitted cameras; out/ = tiles, logs, lock plots). Scripts
`spikes/tesshair3/`: mk3.py (a head + a tied style, plot=1 draws the locks' lines from five sides WITHOUT Blender: 1 s,
the fastest check of a flow), riff.py (THE TOOL PATH: server.tie_hair + sync + look_hair as an MCP client calls them),
dbgpath.py (single roots' ways step by step as az / el / degrees over the hairline), sheet3.py (sheets with LARGE
labels from a layout json).

### What groomers do (the check before building; three sources)
- Autodesk's XGen forum on ponytails (forums.autodesk.com "XGen - Styling question", "XGen Interactive Groom - guides
  and clumps"): TWO descriptions, one for the hair pulled back over the head, one for the long hair leaving the tie;
  guides are rooted ON THE SCALP and run to the tie, the generated hair follows them, and a clump scale curve draws
  them into the tie. -> the gather is guides from scalp roots to the tie (we had rows of wide ribbons from the
  hairline), the tail its own thing.
- SideFX forum on long hair (sidefx.com/forum/topic/84298) + Vellum hair practice (Gnomon's course, cgchannel
  2026-01): guides are laid in LAYERS from the sides and bottom up, upper layers over lower; a couple of hundred
  guides are hung under gravity with a bend stiffness and collisions, the render strands generated from them after.
  -> hair rooted further from the tie lies over hair rooted nearer (`body`); the tail is locks that FALL and collide,
  not locks arranged round a drawn axis.
- Polycount on strays (polycount.com/discussion/236202): their own description, each guide spawning ONE hair.
  -> escaped pieces are single hairs (the wisp object of round two), a few from one root.

### What was wrong in th_T11 / th_T14, by construction
- "Flat across her head": the CURTAIN. The hairline row (the one on top of all others: `ride`) was routed root ->
  sideways along the hairline -> down to a waypoint over the ear's top -> tie. That row IS the visible surface, so the
  top read as lateral bands from the part down to the temples (a cap), with terraces where the three arcs met.
  Everything under it ran the great circle root -> tie, which for front roots goes over the crown, not round the side.
- "Sticks out as a stiff mass": the tail's locks were laid round ONE core line (direction integrated with `stiff`,
  `dir` [0.7, 0.05, -0.6]) at a fixed radius profile; nothing fell on its own, the section stayed round to the end.
- Which of T14's changes hurt against T11 (read by eye from the round tiles T11 / T12 / T14 side by side, NOT isolated
  by re-rendering each alone): all three pushed the same way, toward denser and more solid. (1) `hairline_strands`
  density 2 / clump 0 + count 85k (T12): the temple band went from terraced lines to a solid dark slab with harder
  steps, the front edge a heavier roll: the cap read got stronger. Worst of the three. (2) the fuller tail (28 locks,
  clump 0.55, fullness 0.049-0.054): a blockier mass with no air between locks, 16% too big in profile. (3) arch per
  side: the forehead rounder by measure, but the roll over it reads as a headband; neutral at best.

### The construction now: `hair_flow.py` (hair_tied dispatches to it; the old rows / curtain / core-line tail stay
### the default of a raw `groom.tie`, so older models regrow unchanged)
- `gather` (tie.gather.mode "flow"): a FLOW FIELD. Roots: a fine row on the hairline (0.32 x spacing apart, locks
  0.6 x spacing wide), blue noise inside (spacing 2 cm, locks 1.9 x spacing wide), and a row on each bank of the
  parting. Each root is traced over the unit sphere in 5 degree steps: direction = toward the tie along the surface
  (in front of the ears: toward the tie's height at the BACK'S MIDDLE, so both sides of the face are combed back
  alike and the far side's front does not cross over the top to an off-centre tie) + `part_push` away from the
  parting on the root's own bank (within 3.5 cm of the part, only along `part_length`) + `sag` down the head
  (x steepness, never forward, most just after the root, the front and temples most). Keep-in: a way stays above
  the hairline, but for `overhang` deg at the forehead's corners and temples, and never lower in front of / over the
  ear than its top - 3 deg (- `ears`). Height: `root_lift` in the first 15%, `puff` x sin over the way (the top
  more than the sides), `body` x the way's length (far roots over near ones), into the tie at `out`.
  Dead ends on the way: a sideways term in the sag on top of the head opened the parting into a bare furrow all the
  way over the crown; sag weighted by cos^3 of the steepness did nothing at the temples; without the parting rows the
  nearest roots stood up to a spacing off the line (a zigzag furrow); a hairline row of 1.5 x spacing-wide locks made
  the temple edge a saw (where the hair runs ALONG the hairline every lock's start is a cut across it).
- `tail` (tie.tail.hang): every lock leaves the tie inside a cone (`spread`) round the tie's direction (`dir`, else out
  of the head, tilted by the tie's height; none INTO the head), its direction falls to gravity at (1 - stiff)^2 x 45
  per metre (x 0.7..1.3 a lock), each step pushed off the BODY'S collider (hair_loose.collider: neck, shoulders,
  back; each lock its own clearance so the bundle keeps its thickness lying on a shoulder), then the bundle is scaled
  about its own mean line to `fullness` (rms radius x 1.41). sway / flick as before, on the mean line.
  Numbers that mattered on Tess: the exit tilt (+0.12 Z stood the tail out like T02's flag; -0.06 x ... hangs),
  stiff 0.2 + 0.1 x height + 0.04 x tightness (0.5 on a high tie ended 2 cm under the tie: a flag), 26 + 30 x
  fullness locks (14 + 16 drew plank ends from behind).
- `escaped` (tie.escaped): pieces by zone (part / temple / ear / nape), each 3-7 hairs from one root; every hair
  falls on its own (own first direction, fall rate, length, bow plane, wave). Sharing one fall they were a bundle of
  parallel wires standing off the temple (whiskers); toward a high tie they stood up like antennae (the flow
  direction is clamped to not rise).
- `style` (`groom.tied`): the words -> the tie, the parting, strand dials (under the spec's own), loose hair for
  half up. hair.groom_params expands it, so everything downstream sees an ordinary tie; hair_cards.strands_of merges
  the style's strand dials under spec.hair.strands. `hair.needs_body`: a hanging tail / escaped pieces build the
  body's collider for the grow and for the strands' Shrinkwrap (the collider is now also cached per body geometry in
  workspace/_cache: a copy of a model does not pay the minute again).
- Tool: `tie_hair(name, style, carry_from, look)` (hair toolset; hair.tie_style): the style is MERGED into the
  model's (a riff names what changes), carry_from = hair.carry wired (hairline, look, strand dials, style onto
  another head). `look_hair(views=["around"])` = six sides with the bust (the unseen-angle row; + view bust_side_r).
  Guide: hair_guide.md "Tied-back hair as a STYLE" + the tool section. NOT wired: renders through the references'
  fitted cameras on the DRESSED stage and the like-with-like hairline measure stay spikes (garrett3/stage.py,
  tesshair/hline.py); look_hair already renders through a hair_reference's matched camera.
- Tests: tests/test_hair_flow.py (10: defaults = an ordinary ponytail, top runs front-to-back, every way ends in the
  tie and stays in the hair, the parting's banks stay on their side, tightness = lift + sag, the tail hangs and
  fullness is its radius, escaped pieces, the style's words, half up, the old tie untouched); test_hair_tied (14),
  test_hair_loose + lift (15), test_hair_strands (23) pass. tests/test_toolsets.py fails on main already
  (`block_in_solve` is registered but in no toolset): 5 failures, none from tie_hair.

### Rounds (every model = tess_a1 + ONE style call; fitted-camera tiles out/s_<model>_v<n>.png; hscore IoU front / 3q /
### profile, T11 = 0.690 / 0.504 / 0.693, T14 = 0.695 / 0.514 / 0.674; hline + = our hair's edge HIGHER than hers)
- th_T20 (the first grow, style low / left / tightness 0.35 / neatness 0.4): already read as swept back with a hanging
  tail. Wrong: a hard saw edge at the temples, the part an open furrow over the crown, tail straight with blunt ends,
  escaped pieces straight wires over the eyes, halo a bottle brush.
- th_T21 .. T24: part rows, sag only on steep scalp, the front combed to the back's middle (the two sides of the face
  alike), the ear limit, halo x 0.45. T24 through the fitted cameras: form closer than any round-two model.
- th_T25 .. T30: tail tilt and stiffness, per-hair escaped pieces, finer hairline row, overhang window. T30: IoU 0.729 /
  0.496 / 0.625; hline centre +5.3, outer +7.4, temples +6.1 mm: the forehead's corners and temples BARE where her hair
  drapes over them (overlay out/hline_th_T31_v0.png: her skin arch is narrow, ours wide), width above the eyes +11.2 /
  +7.3 mm (two humps beside the part).
- th_T32: with a parting the front runs back AT ITS OWN HEIGHT (the way to the back's middle may not climb: the
  geodesic from the forehead goes over the top, and the hair off the part stayed 3-5 cm over the temples), the sag may
  run forward a little, the hairline row lies lower (lift x 0.6, strand starts staggered x 0.3: staggered x 4 along
  locks that run AWAY from the line the edge stood 5-7 mm behind it). hline centre +1.3, outer +3.0, temples +2.4;
  IoU 0.659 / 0.500 / 0.675 (the tail kicked out sideways: sway 2.7 cm on a random phase, 4.5 cm of clearance).
- th_T33 (sway x 0.65, clearance 0.5 x fullness): IoU 0.682 / 0.557 / 0.716, hairline band bare 12.4 / 19.3 / 9.5%
  (T14 17.8 / 11.8 / 8.5), hline centre +2.1, outer +3.6, temples +3.2, top -3.2 mm, width above the eyes +7.8 / +2.2.
- th_T34 = BEST (T33 with flick 0.04 -> 0.018 x wave: the flicked lock ends were straight spikes standing out of the
  tail): IoU 0.675 / 0.556 / 0.715; hline v0 centre +2.2, outer +3.3, temples +3.1, top -3.1 mm, width +7.7 / +2.0;
  forehead arch (hscore, ours - hers, + = ours lower) -1.1 -3.1 +1.7 +5.5 +1.2 mm. Its style:
  {"tie": "low", "side": "left", "tightness": 0.3, "neatness": 0.2, "tail": {"length": 0.24, "wave": 0.8,
  "fullness": 0.75}} + Tess's traced hairline and th_T14's look (its cycles_fit [0.9, 0.55]; with th_T11's look the
  Cycles column was black).
- The measures against round two: the three-quarter IoU is the best of all three rounds (0.556; it never passed
  0.514), the profile's the best since T04 (0.722), the front's a little under T11 / T14 (0.675 vs 0.690 / 0.695);
  the hairline is 2-3 mm HIGH where T14 was within 2 mm (T14's curtain was tuned to that measure over five rounds;
  this is a style's default).

### Riffs (through the tool: riff.py = server.tie_hair(carry_from=th_T33, style=<only what changes>); sheet th_11)
- R1 high tight ponytail {"tie": "high", "side": "centre", "tightness": 0.9, "neatness": 0.85, "part": "none", tail
  0.32 m / wave 0.1 / fullness 0.6}: reads at once; the tail stands up out of the tie, arcs over and falls.
- R2 low centre ponytail (tightness 0.5): reads at once. R3 low side sleek (tightness 0.85, neatness 0.95): reads; it
  is R-her-style with two numbers changed.
- R4 half up ({"half": true, "tie": "mid", "length": 0.24}): reads; the loose lengths are groom.loose's (straight,
  stringy), the small tail kicks out before it falls.
- R5 top knot ({"tie": "top", "tail": "bun"}) and R6 low plait ({"tail": {"kind": "plait"}}): read at once (the old
  coil / plait under the new gather).
- Her style on another head: th_H1 = hu_w28d + tie_hair(carry_from="th_T33") (sheet th_12, look_hair "around"): the
  same hairstyle, nothing tuned. tie_hair 80 s the first time on a body (its collider), 1-2 s after; sync 40 s;
  look_hair around 38 s.
- What every TIGHT riff shows: the hairline at the temples and sideburns is a hard stepped edge (reads shaved / a
  wig's edge). Loose styles hide it under the drape.

### BLUNT READ of th_T34 beside her pictures (sheet th_10)
- Swept back: YES. From the part the hair runs out, down over the forehead's corners and temples and back over the
  ears' tops into the tie; on the side of the head the strands run back and down like hers; from behind they
  converge on the tie. No lateral bands, no terraces at the temple.
- Hanging: YES. The tail leaves the tie, bulges and falls beside the neck; it lies against the neck / shoulder.
- Wrong, biggest first: (1) the TAIL'S TEXTURE: long straight strands ending in thin strings; hers is a bushy,
  loosely waved brush with a rounded tousled end, about 1.3x as wide at its widest. From behind a flat ribbon of
  gather hair lies over the band and the ends are plank-like. (2) The head hair is SMOOTH and even (a combed,
  slightly wet read in EEVEE); hers is tousled, with loose strands crossing the flow and a soft halo; the escaped
  hairs are few thin lines. (3) The front hairline: a stepped notch at the part and 2-3 mm high at the corners; a
  dark lifted lump on her left bank of the part in the three-quarter view. (4) The top is 3 mm flat and 8 mm wide
  on her right above the eyes. (5) Tight styles: the hard temple edge. (6) Cycles: darker and browner than her
  hair, back views under-lit (uncalibrated, not this round's job; not worse than T14's).

NEXT: (1) the tail's ends and body: strands' own length spread inside a lock (the lens group's Tips is not doing it
on wide free locks: plank ends), a slow curl at the ends, fullness by tie tightness; (2) texture on the head: a share
of gather locks that cross the flow / lift (looseness as lock-level disorder, not strand noise), longer looping halo;
(3) the hairline for tight styles: baby hairs + a density ramp instead of a row of locks starting on the line;
(4) the front hairline's step at the part (the overhang window opens at 4 deg); (5) fit the style's few numbers to a
reference by measure (tie place from the tail's root, tightness from the outline's width, tail length / fullness from
hscore's mask): today they were set by eye; (6) wire the dressed fitted-camera renders and hline as tools; (7) fix
tests/test_toolsets.py on main (block_in_solve in no toolset).

## Joe on tesshair3 (2026-10-11, th_11 riffs)
"honestly, your low side sleek is almost right for tess, if you added front wispies and poofed up the ponytail a bit."
-> the target for Tess is riff th_R3 (low, left, tightness 0.85, neatness 0.95) + FRONT WISPS + a POOFED tail. The
coordinator tried it with round three's dials (th_W1: escaped hairs + wave 0.45 + fullness 0.85): wires standing off the
forehead, a wider tail of straight strings. Both were construction limits: round four, "## tesshair4".

## tesshair4 (2026-10-11/12, "tesshair4" agent, branch `worktree-agent-a162d3a017522856e`): wisps and a poofed tail
STATE / NEXT: DONE: `hair_flow.wisps` (soft clumps of fine hairs that fall along the skin; style word `wisps`), the tail's
VOLUME (`tail.fullness` = the bundle's radius set along it, `tail.wave` = every lock's own wave; hair_tied tail keys bulge /
lock_wave / lock_wavelength / air), the sideburn / temple fix (`gather.feather`), tests, guide. BEST for Tess = th_T48 (one
tie_hair call on tess_a1, style below). Sheets workspace/human_renders/th_20 (reference | T48 EEVEE | Cycles | th_R3 | th_W1 |
th_T34), th_21 (close-ups beside the reference), th_22 (fullness x wave), th_23 (round three's riffs re-grown). Wisps read
as soft wisps from the side and three-quarter, NOT yet from the front (too faint, the hairline under them is a clean arc);
the tail is poofed but smoother and evener than hers. NEXT: the list at the end of this section (front wisps as the
hairline's own loosened hair; tail strays and a ragged end).

Scratch DURABLE /mnt/data/hifipushie/tesshair4/ (run.sh <script> = this worktree's code on the main workspace, capped; q4.sh
<NN> '<style>' [views] [size] = th_T<NN> regrown (mk3.py, hairline + look of th_T34) + a row of unfitted views; batch.sh
<list> = every "<name>|<style>" line THROUGH THE TOOL (riff.py = server.tie_hair, carry_from th_T34) + iso.py; final.sh
<best> = fitted-camera tiles (EEVEE at 1536 = the references' own pixels, Cycles, th_R3 / th_W1 with ROUND THREE'S worktree
code) + hs.py + the sheets; crop.py = head crops of iso tiles; tests.sh). Scripts `spikes/tesshair4/` (+ lists.py = the
riff / dial / Tess style lists, mk_sheets4.py, low.py). Models: th_T40..T48 (Tess), th_Q1..Q6 (round three's riff styles
with this code; th_R1..R6 are untouched), th_D<f><w> (dial sheet).

### What her pictures show (read before building)
Wisps: many fine soft hairs and small loose locks, rooted all along the front hairline, the part and the temples, lying
close to the face: the front's run OUT along the hairline toward the temples and droop a few cm below it, the temples'
hang in front of the ear to the jaw with a slow curve; none stands off the head, none crosses an eye. Tail: a full airy
brush about 11 cm wide from behind (radius ~5 cm), widest right after the tie, loose S waves ~10 cm long with locks out of
step, a tousled uneven end with single hairs leaving the outline.

### Why round three's could not do it (construction, not dials)
- Escaped pieces were 1-2 hairs each on their own way: started 14 deg OFF the surface (`out * 0.25`), bowed in random
  planes, pushed only out of the body, never onto it: wires in the air. One hair is never soft: EEVEE draws no strand
  under a pixel wide.
- The tail: locks left the tie in a cone and fell; one scale factor made the widest station `fullness`, so the bundle
  was a cone closing to parallel lines. Locks were 15 mm wide with taper 0.9 and floor 0 (the floor only opens for
  locks over 12 mm by (W - 12) / 20): every lock tapered to a point, and strand tips at ts 1.67 trimmed up to 92%: strings.
  The wave was the strand dials' (neighbours in step by design: a sheet), 8 mm at 16 cm.

### The construction now
- WISPS (`hair_flow.wisps`, tie key `wisps`, defaults hair_tied.WISPS; zones WISP_AT part / front / temple / sideburn /
  nape): a wisp is ONE lock with `hairs` 6-28 (sideburn: 4-14) (the wisp strand object: hp_fine, part transparent in EEVEE), width 2.5-11
  mm, flat fan (`strands.wisp_fan` 0.6-1.8, `wisp_round` 0.3: a round brush section stood off the skin), its hairs
  ending one by one (`tip_loss` 0.75 = the share the shortest hair loses; hair_strands turns it into the lens group's
  trim factor) = the taper. Its line: rooted 4 mm inside the hairline, then traced ON THE SKIN in 28 steps: direction +=
  fall x pull + curl x (normal x direction); pull = gravity in the surface's tangent plane (plain gravity once 6-12 mm
  off the skin); while within 8 mm of the skin the direction may not point away from it, and each step is put back at
  its gap (1.5-3.5 mm, + 5 mm x softness toward the tip) when the skin under it faces up or sideways (under the jaw it
  hangs). Zones differ in the pull: part / front = out along the hairline toward the temple (`sweep`) fading to gravity
  over the last 40%, never more than 10-26 deg below the hairline in front of az 48 (no hair over an eye); temple /
  sideburn = down, with a pull away from the face that grows toward the eye; `tuck` 0.3 of the temple / sideburn ones
  are drawn back toward the tie over the gathered hair (never up: not for ties above el 30). Strand dials for the wisp
  object: `strands.wisp` (new; hair_strands.wisp_physical): loose 0.25, frizz 0.2, wave 4 mm at 8 cm, thickness 1.0.
  `hair.needs_body` is true for wisps (the body's collider gives distance and normal; without one, the scalp's rays).
  Style words: `wisps`: 0..1 or {amount, where, length [m, m], softness}; 24 x amount clumps a side; default amount
  1.25 x (0.9 - neatness) (none from neatness 0.9 up). `escaped` (single hairs) now defaults to 0.
- POOF (`hair_flow.tail` with tail.bulge 1): after the fall the bundle's rms radius is SET per station: fullness / 1.41 x
  profile (0.25 at the band, full by 5 cm, x 1.12 just after, x (1 - taper x t^2) to the end), factors clipped 0.3..4 and
  smoothed. Every lock then gets its OWN wave (`lock_wave` x 0.45..1.35, `lock_wavelength` x 0.75..1.3, random phase, a
  plane that turns up to 1.2 rad along it, 45% of the swing in quadrature: a lazy helix), `air` m of scatter toward the
  ends, a twist of 60-220 deg (a lock showing one flat side all the way down is a plank), width max(4.5 x full / sqrt(n),
  22 mm) so sections overlap, taper 0.35, lengths 1 - uneven x u^1.5 x 0.4. Strands: tips 0.9 with tip_spread 0.6 (ends
  thin out over the last third, the section stays open), clump 0.3 - 0.15 x fullness, clump_size 6 mm, lock strand wave
  only 0.006 x wave (the lock's own wave is in its points now), free object: frizz / loose / flyaway + 0.25-0.3 x fullness,
  sub clump wave 0.008 x wave at 10 cm. Style: fullness 0..1 -> radius 18..60 mm, 26..56 locks, cone 0.25..0.7;
  wave 0..1 -> lock_wave 1..13 mm at 12..9.5 cm. A raw tie without bulge / lock_wave is round three's tail unchanged.
- TEMPLE (`gather.feather`, 1 in the style): what read as a shaved temple was the hairline row's locks rooted on the
  SIDEBURN (below the ear's top, az 50-100): they had to climb to the flow over the ear, and their starts were a dark
  tooth-edged tuft over bare skin (isolated with iso.py: drop:tg0_* removed it, drop:tg1_* and S.under:0 did not).
  Those roots are not made any more; the sideburn is the scalp layer + wisps. Also: hairline locks that run ALONG the
  line (not beside the part) start narrow with their strands' starts spread (`roots_x` 4, a lock strand key), and inner
  locks rooted within ~3 cm of the hairline behind az 28 likewise.

### Rounds (T40..T46 = q4.sh, the style R3 + wisps 0.7 + tail wave 0.6 fullness 0.85; unfitted views)
- T40 first grow: the tail already full with a bulge, but locks were crimped ropes with broom ends (lock wave 10 mm at 8
  cm, sub clumps at 7 cm fully out of step, lengths down to 60%); front wisps shot off the forehead's corner as horizontal
  wires (pulled back 60% a step: now all the way), wet ringlets on the cheeks (curl 6-16 rad / m + a 4.5 cm strand wave).
- T41: calmer waves, tips 0.9; wisps hugged the skin but fell straight from the part over the eyes as vertical lines.
- T42: front wisps swept along the hairline (the combed direction); every wisp lifted `over` inside the hairline = a
  lace fringe 1 cm off the far temple (now only tucked ones ride over the gather); lock twist against planks.
- T43 / T44: more clumps (16 -> 24 x amount), temple wisps no longer started forward (they ran across the cheek to
  the nose). T45 (no wisps): the temple isolation above. T46: tail locks wider (3 -> 4.5 x full / sqrt(n)), less air
  (ropes from behind when locks were narrow with air between: seed-dependent, T44 fine, T46 dreadlocks).
- T47 = through the tool, fullness 0.75: hscore IoU front / 3q / profile 0.749 / 0.535 / 0.601 (th_T34 0.675 / 0.556 /
  0.715): front the best of all rounds (the sleek head is her outline), profile worse: the tail 25% too big (ours
  122.5k px, hers 98.4k). Wisps a faint fuzz in EEVEE, nearly gone in Cycles (the head's strand thickness 0.7).
- T48 = BEST: {"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "wisps": {"amount": 1.0, "softness":
  0.7}, "tail": {"length": 0.23, "wave": 0.6, "fullness": 0.6}} + strands.wisp.thickness 1.0: IoU 0.721 / 0.549 / 0.669,
  tail 110k px vs hers 98k (still 12% big in profile), hairline band bare 16.3 / 28.8 / 17.2%.
- Riffs (th_Q1..Q6 = round three's six style calls with this code; sheet th_23, round three above, now below): all six
  still read at a glance. Changed: tails are fuller and open below the band (Q1's high tail is a heavier slab than R1's),
  the temple tuft is gone on Q1 / Q3 / Q5, default wisps appear at neatness < 0.9 (Q2, Q4, Q5, Q6: a few soft locks at the
  temples). Fixed on the way: wisps tucked toward a top knot climbed the temple (now never up, none above el 30); a
  sideburn wisp of 20 hairs hanging straight was a dark blade in front of the ear on Q5 (sideburn: half the hairs, 1.4 x
  wider). Still there as in round three: the toothed hairline at the temples of the top knot and the high ponytail
  (hair running UP from the temple: lock starts across the line; feather only softens it).
- Dial sheet th_22 (th_D<f><w>, low centre tie, tightness 0.85, no wisps, tail 0.26 m): fullness 0 / 0.5 / 1 = a pencil
  tail / an ordinary ponytail / a bush as wide as the head from behind; wave 0 / 0.5 / 1 = straight / soft bends / loose S
  waves. Both read in every cell. Fullness 1 with wave 0 is a curtain of straight strands (nobody's hair); fullness 1
  from behind hides the neck like loose hair.
- Cost: tie_hair 44 s on a new model name (collider), 1-2 s after; iso.py six views at 640 px 75-100 s; shots2 at 1536 +
  Cycles at 1024 ~6 min. Tests: test_hair_flow 13 (3 new: wisps, fullness / wave, the sideburn), tied 14, loose 11, lift
  4, strands 24, toolsets 8 pass.

### BLUNT READ of th_T48 beside her pictures (sheets th_20, th_21)
- Wisps soft? From the three-quarter and the profile YES: thin soft locks out of the temple hang in front of the ear
  and lie on the cheek, a few lie out along the forehead's corners; nothing stands off the head, nothing is a wire
  (th_W1 beside it is wires). From the FRONT, NO: at that size they are a faint fuzz along a hairline that is still a
  clean dark arc; hers is a soft mass of loosened hair over the forehead's corners and temples, several times as much
  hair. Ours are also too alike (long thin strands fanning from the temple, like a broom in profile) where hers are
  short and long, thick and thin, some curling back. In Cycles they are fainter still (visible, not gone).
- Tail poofed? YES in shape: it opens out of the tie, is full to its end, waves. NOT in texture: EEVEE draws it as a
  smooth dense mass with rope-like S locks from behind; hers is tousled, with single hairs and thin locks leaving the
  outline all round and a ragged end. Ours is still ~12% too big in profile and, from behind, covers the tie and sits on
  the back of the head as a lump. Cycles is closer (a soft brush with a translucent rim) but uncalibrated and dark.
- The head: sleek and swept back (Joe's pick), reads; the front hairline is a clean V at the part (the stepped notch is
  smaller than th_R3's, still not her soft part), the temple is a clean line, the sideburn nearly bare under the wisps.
  Her head hair has far more lift and looseness than this sleek cap: that is the style word `tightness`, not a fault.

### Dead ends
- Staggering strand starts (roots, roots_x) on the temple's hairline locks to hide their tooth edge: no visible change;
  the tuft was the sideburn-rooted locks' whole first 2 cm, not their start line.
- `feather` beside the part: the banks run along the line there too, and feathered they bared a wider notch.
- Tail air 2 + 10 mm x fullness with 3 x full / sqrt(n) wide locks: separate ropes with dark gaps (dreadlocks) on some
  seeds. A full tail needs overlapping lock sections; the air comes from waves out of step, not from gaps.
- Wisps lifted over the gather everywhere inside the hairline: a fringe standing off the temple.

NEXT: (1) front wisps as the hairline's own hair: a share of the hairline row's STRANDS (not extra clumps) let go and
droop over the forehead's corners, so the edge itself is soft from the front; more variety (short baby wisps 2-4 cm,
a few thick loose locks); (2) the tail's outline: single hairs and thin locks leaving it (flyaway on the free object
reaches only 2 x lock width), a ragged end (lengths by lock AND a slow curl at the ends), fit fullness / length to her
mask (hscore's tail px) instead of by eye; (3) the top knot / high ponytail hairline at the temples (hair running up
across the line); (4) the part's notch; (5) Cycles look calibration for th_* (dark, brown).

## Joe on tesshair4 (2026-10-12, th_20)
Agreed read of th_T48: tail poofed and close in shape, wisps work from the side. Still wrong, in order: (1) the FRONT
HAIRLINE is a hard dark arc with a hard V notch at the part, wisps barely visible from the front; (2) the TEMPLE reads as
shaved skin in the three-quarter (and the toothed temple hairline of the high ponytail / top knot); (3) the TAIL from
behind: rope-like S locks, an even end, ~12 % too big in profile, covers the tie; (4) the CYCLES look is dark and
uncalibrated. Round five, "## tesshair5".

## tesshair5 (2026-10-12, "tesshair5" agent, branch `worktree-agent-a3e04a545de405a3f`): a soft hairline, the temple as hair, a tousled tail, Cycles calibrated
STATE / NEXT: DONE: the hairline as an EDGE BAND (`gather.edge`, style word `hairline`), a part that wanders (`gather.zig`),
wisp kinds (baby hairs `wisps.baby`, thick loose locks `wisps.loose`), the temple / sideburn strip rooted again, a
tousled tail (`tail.tousle` -> ragged / strays / in_step), the tail fitted to her mask by measure (tailfit.py), Cycles
look keys `look.cycles_width` / `cycles_sat` fitted by measure (cyccal.py) + the finding that every "Cycles" column of the
tesshair sheets so far was rendered at 2 transmission bounces; and the bare temple's REAL cause: the hairline puts the ear
1.8 cm above tess_a1's ear (ear.py; fixed on the model with groom.hairline ear / sideburns, NOT yet in hair.hairline).
BEST for Tess = th_T56 (tie_hair + groom_hair on tess_a1, style / look / hairline patch below). Sheets
workspace/human_renders/th_30 (reference | T56 EEVEE | T56 Cycles | T48 EEVEE | T48 Cycles), th_31
(close-ups at the same pixels), th_32 (riffs th_Q* over th_S*), th_33 (the `hairline` word + the tight riffs' temples).
NEXT: the list at the end of this section.

Scratch DURABLE /mnt/data/hifipushie/tesshair5/ (copies of the .sh in spikes/tesshair5/): run.sh <script> (this
worktree's code on the main workspace, capped); go.sh <NAME> (th_<NAME> = tess_a1 + server.tie_hair(styles/<NAME>.json,
carry_from th_T34, look = looks/<NAME>.json) THROUGH THE TOOL (riff5.py) + close-up tiles); cu.sh <model> [iso variant]
[views] (close-ups at ~0.28 mm a pixel: FOV / DZ / SIZE / TAG env; 27 s for three views); riffs.sh <NAME..>; cy.sh <model>
<tag> <look name> (cyccal.py); final.sh; tests.sh; patch/ (the edits as scripts: this harness refused heredocs that touch
the worktree). Scripts `spikes/tesshair5/`: lists.py (the styles), riff5.py, cc.py (crops), hl.py (hairline by azimuth,
look, lock counts), dbgs.py / dbgj.py (the strip's locks, the strands job's per-lock numbers), ear.py (where the ear is
against the hairline's idea of it), tailfit.py, cyccal.py, shots5.py, mk_sheets5.py. Models: th_T50 (= T48's style with
round four's code: the baseline), th_T51 .. T55 (rounds), th_T56 (BEST), th_S1..S6 (riffs; th_S7 = S1 with the ear fix,
first try), th_H0 / H5 / H10 (hairline dial). th_T56 = tie_hair(style {"tie": "low", "side": 20, "tightness": 0.85,
"neatness": 0.95, "wisps": {"amount": 1.0, "softness": 0.7}, "tail": {"length": 0.2, "wave": 0.6, "fullness": 0.66,
"tousle": 0.55}}, carry_from th_T34, look {"cycles_width": 1.8, "cycles_sat": 0.65}) + groom_hair(groom {"hairline":
{"ear": -0.013, "sideburns": 0.035}}, replace=True).

### What her pictures show (read before building; crops /mnt/data/hifipushie/tesshair5/out/ref/)
- Front hairline: NO line. On her right the hair thins to single fine hairs over ~1 cm, lying sideways along the
  hairline; on her left the hair off the part drapes over the forehead's corner and one thick loose lock swoops from the
  part past the brow's tail to the cheekbone. The part is a pale scalp line 2-3 mm wide that wanders, hair standing up
  on both banks; no V.
- Temple (three-quarter, profile): a dense dark mass swept back over the ear's top right down to the ear; its front edge,
  from just behind the brow's tail down in front of the ear, is a soft fringe of short fine hairs. FEW long hangers.
- Tail from behind: the band shows; the hair fans out of it in soft sheets (neighbouring strands wave together), full
  by ~8 cm, ~11 cm wide, a ragged end of pointed wisps that flick out, single hairs all round the outline.

### Why th_T48 could not do it (each isolated by rendering lock classes alone: cu.sh <m> 'only:tg0_*+S.under:0')
- The hard arc and the V: NOT the hairline row (drawn alone, tg0_*, it is a fair soft arc). The INNER locks (tg1_*:
  the part rows and the first blue-noise roots) are 3.8 cm planks whose strands all start on one line (roots 0); beside
  the part they run ALONG the hairline, so their sides and starts are the hard edge, the stair steps and the V.
- The bare temple: between the hairline and where the inner roots begin (0.6 x spacing = 12 mm) there was no root but
  the one row on the line, and round four stopped rooting that row on the sideburn. In front of the ear the hair is a
  strip 1-2.5 cm wide: all of it was in that no-root band.
- EEVEE never draws a strand under a pixel wide, so a thinned row still reads dense: a ramp needs strands drawn FINE.

### The construction now
- EDGE BAND (`hair_flow.roots` / `gather`, tie key gather.edge 0..1): fine blue-noise roots (0.36 x spacing apart) from
  the line to a whole spacing in (over the first inner roots). Their locks: width 0.42-0.62 x spacing, lift x 0.35-0.8,
  strands `density` x (1 - edge x 0.8 x (1 - ramp)), `fine` = edge x (1 - ramp) (a new per-lock strand attribute hp_fn
  -> hp_fine: part transparent in EEVEE), `rim` 0.8 + edge (hp_ex: the lens's Edge per lock, strands thin toward the
  lock's sides), `roots_m` 8-28 mm (strand starts staggered in METRES); ramp = smoothstep(depth / (0.6 x spacing)).
  At the temple / sideburn (az 40-100) the ramp is full by 0.25 x spacing and density x (1 + 1.5 x ramp): the strip has
  one layer of hair, its own. The sideburn's lowest fringe (below the ear's top - 11 deg) grows no lock. Inner locks
  rooted within 3.5 cm of the line (in front of az 60-90): width 1.9 -> 1.4 x spacing, rim up to 2.2, roots 0.6 with
  roots_x 3. gather.edge 0 = round four exactly (same random stream).
- PART (`gather.zig` m, `hair_flow._zig`): the part rows and each root's bank follow x = xp + zig x (sin + 0.45 sin at
  0.41 x the wavelength), wavelength 2-3 cm, phases from the seed. Style: 4.5 mm x hairline.
- WISP KINDS (`hair_flow.wisps`, tie keys wisps.baby / wisps.loose, counts a side): "baby" (lock names twb*: 1.2-4 cm, 2-5
  hairs, 1.5-4 mm, rooted from 3 mm outside to 5 mm inside the line anywhere from under the part to the sideburn; half
  lie back the way the hair was combed and end in it, half droop along the skin; curl x 4 at 0.4 x the wavelength);
  "loose" (twl*: 18-45 hairs, 6-11 mm, 11-19 cm, from az 20-58, drawn back toward the tie over the gather and drooping:
  the tucked wisp's way). Soft wisps in front of the ear are now a short fringe (x 0.45 / 0.7 / 1 of their length), tuck
  0.3 -> 0.45, a tucked one never climbs.
- TAIL (`hair_flow.tail`, tie keys tail.ragged / strays / in_step): ragged = lock lengths 1 - 0.35 x ragged x U, taper
  0.35 + 0.2 x ragged, the profile opens as a fan (0.18 at the band, full by 9 cm, no swell), offsets ABOVE the bundle's
  line come in over the first 12 cm (x 0.6: the band shows); in_step = one wave through the bundle (phase by the lock's
  place in the section, plane shared, swing nearly round: 0.45 + 0.4 x in_step in quadrature), twist x (1 - 0.6 x
  in_step); strays = wisp-object locks (names ty*: 1-4 hairs, 3-9 cm) that ride a tail lock for 1-3 points, then leave it
  outward with a curl, falling. Strands: clump 0.3 - 0.15 fu + 0.3 x tousle with free.clump_shape 0.6 + 0.35 x tousle and
  tip_spread 0.6 - 0.5 x tousle (POINTED wisp ends), density 1 + 0.8 x tousle, free.random 0.35 (sub clumps nearly in
  step), flick + 14 mm x tousle. The band's ring x 0.7.
- STYLE WORDS (hair_flow.TIED): `hairline` 0..1 (default 0.8 - 0.3 x neatness) -> gather.edge, zig, wisps.baby = 70 x
  hairline; `wisps.loose` n a side (default round(2.5 x amount), 0 toward a tie above el 30); `tail.tousle` 0..1
  (default 0.25 + 0.5 x wave) -> ragged 0.25 + 0.75 t, strays (10 + 50 t)(0.5 + fu), in_step 0.7.
- LOOK KEYS (hair.LOOK, blender_strands.material / cycles_width, blender_scene.hair_look): `cycles_width` (x the strands'
  hp_profile Radius for a Cycles render only), `cycles_sat` (the colour's saturation before the Cycles luminance fit).
- Tests: test_hair_flow 17 (5 new: the band, baby hairs + loose locks, the tail's tousle, the look keys; the sideburn
  test now asks for hairline 0), tied 14, loose 11, lift 4, strands 24, toolsets 8 pass.

### Rounds (th_T51 / T52 = go.sh, close-ups cu.sh)
- T50 (round four's code, T48's style, close up): the V and stair steps, the temple bare from the brow's tail to the ear.
- T51 a: band + zig + kinds: the V smaller but dark stair PLATES beside the part (the inner planks, isolated above);
  the temple a gauze; loose locks of 30-70 hairs hanging straight down beside the eye (stiff brushes), a comb of
  hangers down the cheek in profile. b: inner locks near the line soft (rim, roots, narrower): V and steps GONE, the part
  a pale wandering line. c: strip denser (ramp full by 5 mm, density x 2.5), hangers short, loose locks swept back.
- Tail: first try (ragged, in_step, strays, free loose + 0.3 x tousle): every strand wriggled on its own (a crimped
  wet mop): tousle is NOT strand wander. T52 (side 20): waves in ONE shared plane showed from one side only, a straight
  broom from the other (quadrature up); strays pushed out 9 x a step were straight wires 8 cm off the tail (3.5 x, fall
  5); open tips (tip_spread 0.6) ended every lock as a flat 2 cm chunk (clump toward the tips instead).
- The high ponytail (th_S1): a bare wedge above the ear. Two causes: (1) the feathered starts were a SHARE of the lock's
  length (up to 38 %): fine where the hair passes back over the strip (a low tie), 8 cm bare where it runs up out of it
  -> roots_m; (2) with the inner locks narrowed to 1 x spacing, the stretch between the band (12 mm) and the first inner
  roots (2 cm apart) had gaps where hair runs straight away from the line -> the band a whole spacing deep, inner locks
  1.4 x.

### The tail by measure (tailfit.py: our ID mask of the CURRENT hair against her trace mask through the fitted cameras,
### cut at the tie's pixel; profile | three-quarter)
| model | style side / length / fullness | IoU | px below the tie vs hers | length mm (hers 175 / 162) | width mm (hers 154 / 105) |
|---|---|---|---|---|---|
| th_T48 | left (30) / 0.23 / 0.6 | 0.665 / 0.547 | +31 % / +3 % | 217 / 166 | 161 / 115 |
| th_T51 | 30 / 0.23 / 0.6, tousled | 0.639 / 0.509 | +19 % / +5 % | 206 / 164 | 146 / 103 |
| th_T52 | 20 / 0.2 / 0.66 | 0.632 / 0.621 | +1 % / -11 % | 178 / 148 | 137 / 100 |
| th_T53 | 20 / 0.21 / 0.66 | 0.618 / 0.648 | +9 % / -7 % | 198 / 155 | 129 / 101 |
| th_T54 | 20 / 0.2 / 0.76 | 0.647 / 0.611 | +5 % / -2 % | 182 / 147 | 149 / 113 |
| th_T55 | T54 + the hairline's ear lowered | 0.599 / 0.631 | +13 % / +3 % | 185 / 154 | 177 / 121 |
| th_T56 = BEST | 20 / 0.2 / 0.66, ear lowered | 0.613 / 0.637 | +8 % / -7 % | 174 / 143 | 154 / 110 |
(T54 -> T55 changed only the hairline: the tail's own random draw moved its profile width 149 -> 177 mm. The measure
is good to about +-10 % a draw: fitting closer than that is fitting the seed.)
The side was the big one: at 30 deg the tail hung 3-4 cm further out to her left than hers in the three-quarter (the
profile cannot see it). The profile's whole-mask IoU is LOWER than T48's (0.647 vs 0.665) although the tail fits
better: our hair's edge at the temple now carries fine hair 1-1.5 cm in front of her trace's (thresholded) mask, and
the ID pass counts every fine hair as hair; her head hair also stands 1 cm higher over the crown (the style's
tightness, Joe's pick).
FOUND: a model's own stage .blend keeps the hair it was BUILT with (stage.ensure's key leaves the hair out), and
hscore.py's ID pass renders that file in mode "render": after a regrow its masks are stale. tailfit / cyccal / shots5
render the model's current spec hair on the shared stage (hair_look job + id_views).

### Cycles by measure (cyccal.py: dense hair only = our ID mask AND her mask, eroded; L* / chroma / hue of the shadow,
### mid, highlight bands and the mean; front | profile, 512 px, 64 samples)
FOUND FIRST: spikes' stage.shoot(engine="cycles") renders with max 4 bounces, 2 transmission. blender_scene's own
comment: that "leaves fair hair grey and dark hair flat". hair.look_hair(engine="cycles") sets hair_bounces 10. Every
"Cycles" column of th_03 .. th_23 was the 2-bounce render: the near-black hair. With 10 bounces the same look reads
chestnut. So most of "dark" was the spike's render path, not the look.
| look | mean L* front (hers 21) | mean L* profile (hers 16) | chroma (hers 9 / 8) | hue (hers 69 / 71) |
|---|---|---|---|---|
| th_T34's look, 10 bounces | 19 | 22 | 12 / 14 | 66 / 67 |
| + cycles_width 1.8 | 15 | 21 | 13 / 14 | 65 / 67 |
| + cycles_sat 0.65 (th_T54's look) | 16 | 22 | 10 / 9 | 63 / 65 |
| EEVEE (unchanged) | 20 | 17 | 9 / 9 | 61 / 62 |
At true strand width (37 um radius, 70k strands) the head hair is a see-through veil in Cycles (skin through the
temple): cycles_width 1.8. Dense dark hair came out too saturated (chroma 13-14 vs 8-9): cycles_sat 0.65. Mean lightness
over both views 19.0 vs hers 18.5; NOT matched per view (front 5 L* dark, profile 6 light: our front top is in its own
shadow where hers is lit, the lighting / the hair's lift, not the colour). Hue 4-6 deg redder than hers in both engines.
Cost: 3-4 min a 512 px Cycles frame on this machine (and it waits for the heavy slot).

### The bare temple's real cause: the hairline's EAR is not the mesh's ear (ear.py)
After the band the low-tie temple read as hair, but the high ponytail and top knot still had a bare wedge above and in
front of the ear with a toothed edge over it. The strands job (dbgj.py) showed 25 strip locks a side rooted there with
16-128 strands each, starting within 1-3 cm: the hair WAS there; the wedge is OUTSIDE the hairline. hair.hairline puts
the ear's top at lm_brow_outer z + 4 mm (-1.46 cm from the head centre on tess_a1) and runs the line 1 cm over it (-0.5
cm); the scalp rays put the real ear's bump at z -3.2 .. -3.9 cm (az 100). So the line runs 2.5-3 cm above the ear and
the sideburn ends above the ear's top. A low tie's hair passes back over that band and hides it; toward a high tie
nothing does. On the model: groom.hairline {"ear": -0.013, "sideburns": 0.035} (through groom_hair; guide). th_S7 / T55:
the wedge is gone on the high ponytail, Tess's temple is a dense mass down to the ear like hers. This is also what
round four's "shaved" three-quarter was (it un-rooted the tuft that had covered some of it).
NOT DONE: hair.hairline finding the ear on the mesh (it would move every human model's hairline on its next regrow:
its own change, with a look at garrett / jw / lt19).

### Dead ends
- Thinning the hairline row alone (density) to soften the edge: the edge was not that row.
- Tousle as strand wander (free.loose 0.45): a crimped mop.
- Suppressing every offset above the tail's line by 0.8 to show the band: her tail does rise behind the tie in profile
  (the masks: a red cap over ours); 0.6 over 12 cm with the fan profile keeps the band visible from behind.
- Loose locks hanging by the wisps' zone rule (down the cheek): stiff brushes; toward a high tie (no way back over the
  temple) a strap across the cheek: none by default there.

### Riffs (th_S1..S6 = round four's six style calls + the hairline's ear lowered; sheet th_32, round four above, now below)
All six still read at a glance; none got worse. Changed: every hairline is soft (thin rim, baby hairs), the parts are
pale wandering lines without a notch (S2, S3, S4, S6), the high ponytail and top knot (S1, S5) have hair down to the
ear instead of the bare wedge, tails are a little tousled by their wave (S2: a ragged end, a few strays; S1 / S3 at wave
0.1 nearly as brushed as before: tousle defaults to 0.05 + 0.75 x wave, after 0.25 + 0.5 x wave chopped the sleek high
tail into chunks at five heights). Still there: the temple hairline of S1 / S5 is TOOTHED (th_33, close up): hair that
runs straight up off the line shows every lock's start as a tooth; the band thins it less than at the forehead because
EEVEE draws even a quarter-density rim as near-solid from the side.

### BLUNT READ of th_T56 beside her pictures (sheets th_30, th_31)
1. FRONT HAIRLINE: better, not hers. The V notch and the stair steps are gone, the part is a pale line that opens
   gradually, the edge thins out with fine hairs instead of stopping. But it is still a neat arc: her hair DRAPES over
   the forehead's corners (the style's tightness 0.85 holds ours back) and she has several times more loose hair in
   front; from the front our wisps are a few thin strands at the temples, the two thick loose locks lie back over the
   temple and hardly show from the front.
2. TEMPLE: yes for Tess. In the three-quarter and the profile it is a dense mass swept back down to the ear with a
   soft fringe in front of it, like hers (after the hairline's ear was lowered: before, a gauze over skin). Ours is
   sleeker and its fringe has a few straight wiry hairs. High ponytail / top knot: the bare wedge is gone, the edge is
   still toothed.
3. TAIL: partly. From behind the band shows, the hair fans out of it, the end is ragged with pointed wisps, hairs
   leave the outline; it no longer reads as ropes. But it reads as stiff choppy STRAW where hers is soft brushed-out
   hair: strands a pixel wide with dark air between, locks straighter than hers, strays few and thin. Size by measure:
   profile area +8 %, three-quarter -7 % (T48: +31 % / +3 %), length 174 / 175 mm, width 154 / 154 mm in profile; it
   reaches 2-3 cm further back than hers in profile.
4. CYCLES: usable now, not matched per view. Chestnut with lit strands instead of near-black (the bounces), solid over
   the scalp (width), chroma hers (sat); mean lightness right over both views but the front is ~5 L* dark and the
   profile ~6 light. Grainy at 64 samples; 3-4 min a frame.

NEXT: (1) hair.hairline: find the ear on the mesh (the scalp rays' bump) instead of brow_outer + 4 mm, with a look at
every human model's hairline before / after (the real fix for bare temples; today a per-model groom patch); (2) the
tail as HAIR, not straw: more, finer strands in the free object (count by its volume, drawn part transparent like the
rim), strand-level wave shared across neighbouring locks, more and longer strays (hers has dozens of 10-15 cm single
hairs round the outline), then re-measure; fit the tail over 3-4 seeds, not one (the measure moves +-10 % a draw);
(3) the front for a LOOSER reading of her: tightness ~0.6 with the edge band (drape over the forehead's corners),
loose locks that swoop from the part across the forehead's corner (hers), judged from the front; (4) toothed temple
of up-styles: locks that run straight off the line need their strands' starts spread ACROSS the band (root each
strand on the scalp under it, the scalp layer's way) rather than along the lock; (5) tools: tailfit / cyccal / shots5
as look_hair options (matched-camera ID mask of the CURRENT hair, band colours, Cycles with hair bounces on the dressed
stage), a look calibration call that sets cycles_width / cycles_sat from a reference; fix hscore.py's stale ID pass;
(6) Cycles per view: the front top reads dark (hair running away from the camera under a frontal key): check the
photo light fit and the hair BSDF's roughness against the front picture; hue 4-6 deg red in both engines.

## tesshair6 (2026-10-12, "tesshair6" agent, branch `worktree-agent-ac19f4a9531cf46f3`): the ear found, a loose front, the tail as soft hair, up-style temples, look_hair against the pictures
STATE / NEXT: DONE: `hair.ear` (the ear found on the scalp rays; `hairline` passes over it: no per-model patch, Tess
included), the style word `front` (looseness / drape / locks), the tail's tousle rebuilt as SOFT hair on round four's
hang and fitted over 4 seeds, the up-styles' temple edge (finer, not solved), `look_hair` views "ref<i>" + `stage` +
`measure` (outline / tail / colour bands against a picture), hscore.py renders the current hair. BEST for Tess =
th_T66 (one tie_hair call on tess_a1 + groom seed 0, NO hairline patch; style below). Sheets
workspace/human_renders/th_40 (reference | T66 EEVEE | T66 Cycles | T56 EEVEE | T56 Cycles | T48 EEVEE), th_41
(same-pixel close-ups), th_42 (hairline before / after on seven other humans + every head's ear plot), th_43 (riffs
th_S* over th_V*), th_44 (up-style temple edge close up). NEXT: the list at the end of this section (front wisps as
soft curls, the front as separate locks, the tail's lock ribbons).

Scratch DURABLE /mnt/data/hifipushie/tesshair6/ (copies in spikes/tesshair6/): run.sh <script> (HEAVY: renders, syncs;
capped), runl.sh <script> (LIGHT: measures, plots; /mnt/data/hifipushie/bin/slot), tests.sh (through slot), go.sh
<NAME> (th_<NAME> = tess_a1 + tie_hair(styles/$STYLE or <NAME>.json, carry_from th_T34, looks/<NAME>.json) + groom
seed $SEED, THROUGH THE TOOLS: riff6.py), cu.sh / riffs.sh (as round five), final.sh (the whole production, ONE job
after another). Scripts: ear6.py / eardbg.py (the residual map the ear is read from), hlplot.py (NO Blender, 1 s a
head: the head from its scalp rays, the found ear, old line red, new green), humans.py (every model with hair),
mkE.py / syncE.py / hlE.py (copies th_E* of other humans, their scenes, before / after through groom_hair +
look_hair), look6.py (the tool path with ref views + measure), mk_sheets6.py, patch/ (the larger edits as scripts).
Models: th_E0 / E3..E8 (+ "b" = ear_from brow), th_T60 (T56's style, no patch), T61..T63 (tail rounds), T63s0..3,
T64 / T65 (front), T65s0..3, th_T66 (BEST), th_V1..V6 (riffs). MACHINE: one heavy job at a time (a 10-model sync in
one process reached 8 GB and was killed at the cap; the coordinator asked for one model a process and `slot` for light
jobs).

th_T66 = tie_hair(style {"tie": "low", "side": 20, "tightness": 0.85, "neatness": 0.95, "front": {"looseness": 0.6,
"drape": 0.6}, "wisps": {"amount": 1.0, "softness": 0.7}, "tail": {"length": 0.195, "wave": 0.6, "fullness": 0.43,
"tousle": 0.55}}, carry_from th_T34, look {"cycles_width": 1.8, "cycles_sat": 0.65}) + groom_hair(groom {"seed": 0},
replace=True).

### 1. The ear (`hair.ear`, `hair.hairline`)
- FOUND, not guessed: per row of elevation the scalp rays' radius (left / right averaged) is OPENED along the azimuth
  (flat grey opening, 19 cells = 38 deg): what stands off the head narrower than that is a bump. Over 4 mm at the side
  of the head (az 66..126, between brow + 2 cm and nose base - 5 cm, under 5.5 cm) = the ear's core; grown by
  hysteresis into what stands off > 1.5 mm (the helix's top and front lie nearly flat: the 4 mm core alone was the
  ear's BACK half and the line crossed the ear's top, hl_a first try). Top = sub-cell between the highest cell and the
  one above; front / back azimuth over its upper two thirds; lobe. No landmark, no base-specific data: GNM one-mesh
  heads, MakeHuman + GNM head, the template (male_stylized, no landmarks at all).
- First tried a median filter (29 x 9 cells) as the "head without the ear": noisy, negative lobes, the concha split the
  ear in two. The opening along the azimuth alone gives a clean non-negative residual.
- Old guess vs found (ear top, cm from the head centre; hlplot / ear6): tess_a1 -1.5 / -3.3, garrett_v20 -1.5 / -3.0,
  om_garrett -1.2 / -1.8, hu_s_wavy -1.3 / -3.1, hu_s_child -1.4 / -2.3, hu_s_tousled -1.2 / -2.5, hc_golfer and
  dg_hair_long -1.6 / -3.3, rs_real_S3 -1.5 / -1.9, lk_mem -1.5 / -1.6. The old line stood 9 - 29 mm over the ear
  (default 10 mm clearance on top of the guess); the miss is NOT one offset: 1 mm (lk_mem) to 18 mm (Tess).
- The line now: `ear` m (default EAR_OVER 6 mm; 10 left a strip of skin over Tess's ear) over the found top from the
  ear's front to its back; the sideburn `sideburns` m (default 14 mm) below that top, just in front of the ear's
  front attachment; behind the ear down its back to the lobe, then the nape as before. The temple point still hangs
  on the brow (a face feature). Explicit values keep their MEANING (m over / below the ear's top) on the true top;
  an `ear` under 3 mm (old grooms patched the high guess with negatives: Tess -0.013, the golfers -0.004 / -0.03)
  is raised to 3 mm: hair never roots on the ear. `"ear_from": "brow"` = the old line exactly; no ear found = the old
  line. Heads without landmarks use the found ear only on a human base (sc.human; a goblin's ear is what its maker
  built: unchanged).
- Tess: th_T60 = T56's style with NO groom patch: the temple is a dense mass down to the ear, like T56 with its patch.
- OTHER HUMANS (th_42; copies regrown both ways through groom_hair, EEVEE): hu_s_wavy SAME, hu_s_child SAME (long
  hair hides the line), hu_s_tousled SLIGHTLY BETTER (a sideburn in front of the ear), hc_golfer SLIGHTLY BETTER,
  rs_real_S3 BETTER (hair down to the ear, a sideburn), lk_mem SLIGHTLY BETTER, dg_hair_long WORSE FOR THAT GROOM (its
  ear -0.03 rooted hair on the ear to hide its top; the ear now shows whole: `ear_from: "brow"` or longer side hair
  restores it). garrett_v20 / om_garrett / the template: line plots only (th_42 bottom; their syncs were the 8 GB job).
  NOT rendered: lt19, jw (private, untouched).

### 2. The front (`front`: looseness, drape, locks)
- gather.front {"loose", "drape"} (hair_flow.paths / gather): roots in front of the ears (fading az 55..85) get sag +
  1.4 x loose and stand off more (lift x (1 + 1.4 x loose), fading az 50..80); the keep-in over the forehead's corners
  and temples is lowered by 11 deg x drape (az 8..76). The back keeps the style's tightness (loose is x tightness).
- wisps.swoop n a side (locks tws*): 30-70 hairs, 9-15 mm, 13-19 cm, rooted beside the part (az 5..30) ON the gathered
  hair, falling out along the hairline below it (5 + 16 x drape deg), drawn back toward the tie after 42-60 % of their
  length. With a loose front the soft wisps are x 1.5 in number, up to 1.4 x longer, 6+8f .. 14+14s+22f hairs, tuck
  0.45 - 0.2f, strand thickness 1 + 0.4f.
- Rounds: T64 a (sag + 2.2, drape 16 deg): a smooth heavy curtain over the temples that hid every wisp and swoop (the
  swoops, drawn alone, were ruled planks from the part to the temple, UNDER the gather). b: sag + 1.4, drape 11,
  swoops lifted onto the gather with a bow (fall x 1.5, curl): loosened stepped locks over the corners. T65: wisps
  thicker / longer: visible from the front at the temples.

### 3. The tail as hair (tail.soft; the tousle rebuilt)
- What made T56 "shorter, stiff straw kicking out backwards": flick + 14 mm x tousle (the kick), clump + 0.3 x tousle
  with clump_shape 0.95 and tip_spread 0.1 (pointed straw), lock taper 0.55, the fan full only by 9 cm and length 0.2
  (short). All of that is gone from the tousle. It is now `soft` (0.1 + 1.27 x tousle): 30 % x soft + 10 % of the
  locks LOOSENED (out of the bundle to their own side by 1-3 cm toward the end, sagging, wave x 1.35), lengths over
  the last half (rag x (0.35 + 0.2 soft), more long than short), open ends (taper 0.35, tip_spread 0.6 + 0.3 t),
  clump x (1 - 0.6 t), locks 6 x full / sqrt(n) wide (neighbours' strands interleave), strands `fine` 0.2 + 0.3 t at
  density 1.4 + 1.2 t, in_step 0.7 - 0.3 t, strays (14 + 90 t)(0.5 + fu) of 4 .. 8 + 10 t cm with a curl that comes
  and goes, 22 % of them thin locks of 7-15 hairs; the bundle full by 6.5 cm. Hang, fullness, wave: round four's.
- Rounds (unfitted views): T61 a: hangs and waves like T48, but ribbons with dark gaps from behind, a blunt cut end,
  strays as straight wires. b: wide interleaving locks, low clump, curlier strays: one mass of hair. c: taper + 0.25 t
  along the bundle, lengths over the last half.
- BY MEASURE OVER SEEDS (tailfit.py: profile | three-quarter; hers: below-tie area 100 %, length 175 / 162 mm, width
  154 / 105 mm):
  | style (side 20, wave 0.6, tousle 0.55) | seeds | below, profile | below, 3/4 | length mm | width mm |
  |---|---|---|---|---|---|
  | T61 length 0.23, fullness 0.66 | 1 | +50 % | +20 % | 200 / 162 | 195 / 125 |
  | T62 0.21 / 0.5 | 0-3 | +23 % (16..27) | +8 % (0..17) | 193 / 156 | 178 / 123 |
  | T63 0.195 / 0.43 | 0-3 | +13.5 % (4..23) | -3 % (-8..5) | 182 / 150 | 165 / 114 |
  | T65 = T63 + front | 0-3 | +16 % (5..27), sd 9 | 0 % (-4..9), sd 6 | 181 / 150 | 182 / 120 |
  IoU of the whole mask 0.637 / 0.635 (T56 0.613 / 0.637). The profile runs big and the three-quarter small with ONE
  tail: no length / fullness closes both (ours is wider seen from the side than hers, i.e. flatter front to back).
  0.195 / 0.43 is the pick that is good on average over both views; th_T66 is seed 0 (+19 % / -2 %: the seed nearest
  the mean, not the luckiest: seed 1 is +5 % / -2 %). groom.seed carried from th_T34 is 3: "seed 3" = the default draw.

### 4. Up-styles' temple edge
- Isolated (cu.sh th_V1 'only:tg0_*+S.under:0'): the saw is the BAND's own locks (tg0), a dense mass whose every lock
  starts as a slab cut across its direction; staggering starts in metres (roots_m, round five) barely shows because
  EEVEE draws a thinned start as solid.
- Now: the hairline row's roots stand up to ~7 mm inside the line at their own depths (az 28..105, a hash, no random
  draw), and band locks that run AWAY from the line there start their strands over + 2.2-3.7 cm, x 0.7 narrower,
  finer, rim + 0.8, density x (1 - 0.7 (1 - ramp)). Result (th_44): fine combed points instead of 8 mm teeth on the
  high ponytail; the top knot's edge is finer but has more dark stray strands across the forehead's corner. A combed
  edge is what a tight up-do shows; it is still a visible serration close up: PARTLY.
- First try (starts across the band alone): no visible change.

### 5. Tooling
- hscore.py (spikes/tess): its ID pass rendered the stage's .blend in mode "render" and its beauty came from
  stage.shoot, which reads the stage's spec.json: both the hair the stage was BUILT with. Now one hair_look job with
  the model's current spec hair gives both (`current()`), on $STAGE_MODEL or the model's own stage.
- look_hair: views "ref0".. = the fitted cameras of human_refs.json (the whole picture squared), `stage` = a model
  with the same head whose scene is used (th_T66 on "_g3_th_T04": 49 s for three views), `measure` {"view", "mask",
  "tie", "colour"} -> hair.measure_ref: outline_measure (IoU, area, chamfer mm, below the tie: area %, length, width,
  reach) and colour_bands (L* / chroma / hue of shadow / mid / highlight, ours | the picture). Checked against
  tailfit.py on th_T65: IoU 0.641 vs 0.648, below + 31 % vs + 27 %, length 183 vs 181, width 206 vs 201 mm (480 px
  ID pass vs 768). The look uses its own lights ("salon"), not the picture's fitted light: its EEVEE colour bands read
  chroma 1.7 against her 7.9 where the spike's fitted light read 9: the colour numbers depend on the light, the
  outline numbers do not. Setting cycles_width / cycles_sat from them is still by hand.
- Earlier sheets' "Cycles" columns (th_03 .. th_23, and th_T48's Cycles tile) used 2 transmission bounces (near-black
  hair); th_30 on and look_hair(engine="cycles") use 10. In the guide.
- Tests: test_hair_ear 6 (new: the ear found, the line over it, overrides, no-landmark heads, outline_measure,
  colour_bands), test_hair_flow 19 (2 new: the soft tousle, the front word), tied 14, loose 11, lift 4, strands 24,
  toolsets 8: all pass.

### Riffs (th_V1..V6 = the six style calls, no patch; sheet th_43, round five above)
All six read at a glance and none is worse. No riff needs the hairline patch any more (V1 / V5: hair down to the ear).
Tails with a wave are fuller and softer (V2, V4); the sleek ones (V1, V3) nearly unchanged (tousle 0.125 at wave 0.1).

### BLUNT READ of th_T66 beside her pictures (th_40, th_41)
1. HAIRLINE / EAR: yes. No patch, the temple is hair down to the ear in every view.
2. FRONT: better, not hers. The neat arc is gone: the hair off the part hangs over the forehead's corners and temples
   and the temple wisps show from the front. But it is a smooth combed CURTAIN, where hers is separate loosened wavy
   locks with air and fine curls; the swoop locks merge into the curtain instead of reading as locks; the part is a
   hard pale wedge in Cycles; and the wisps in front of the ear are long, thin, STRAIGHT hairs down the cheek to the
   jaw (scraggly lines across the face in the three-quarter and profile) where hers curl softly. The draped temple
   also covers the top of the ear, which hers leaves clear.
3. TAIL: the best so far, not hers. It hangs, is full and waves like round four's, with a soft ragged end and hairs
   round it; no kick, no straw. From behind it still reads as wide wavy ribbons (locks), darker and smoother than her
   brushed-out hair with its light single strands; + 16 % in profile on average.
4. UP-STYLES: partly (above).
5. CYCLES: as round five (usable, dark at the front top, grainy at 64 samples); the tail's fine strands read as a
   haze in Cycles (fine is EEVEE transparency; in Cycles the 2.7 x count at true width goes see-through at the rim).

### Dead ends
- A median-filtered head as the ear's baseline; the 4 mm core alone as the ear.
- sag + 2.2 / drape 16 deg at the front: a helmet curtain that buried the wisps.
- Swoop locks swept hard along the hairline from under the gather: ruled planks, and hidden.
- Stray curl reduced for long strays (to avoid hooks): straight wires; they need MORE curl, varying along the hair.
- Starting an away-running lock's strands across the band without thinning it: no visible change in EEVEE.

NEXT: (1) wisps beside the face as soft CURLS (their strands' wave / curl by length; shorter in front of the ear,
none forward of it on the cheek) and the front as SEPARATE loosened locks (the gather's front locks narrower with
gaps, their own waves, a few lifted off the mass) instead of one curtain; keep the ear's top clear with a loose
front; (2) the tail's ribbons: strand-level wave shared by neighbours instead of lock ribbons (more, narrower locks
or strands interpolated between lock guides), lighter single strands at the outline, Cycles at the tail's rim
(cycles_width per object); its depth front-to-back (profile + 16 %, three-quarter 0 %); (3) up-style edge: root the
band's strands on the scalp under them (the scalp layer's way) instead of along locks; (4) look_hair: the picture's
fitted light for ref views (colour bands then mean something), a `calibrate` that sets cycles_width / cycles_sat;
(5) sync garrett-sized models for th_42 one at a time (8 GB each) and look at their hairlines rendered.

## Joe on tesshair6 (2026-10-12, th_40)
"Honestly, that's the best hair we've seen so far and I'm pretty pleased. We could leave it there and it would be
_almost_ ok. The wispies could be dialed in a little more, but..." and then: "I agree with your 'still wrong' list,
though." -> `th_T66` is Tess's hair for now (the baseline every later round must beat). The agreed still-wrong list:
the draped temple covers the top of the ear (hers is clear); thin straight hairs down the cheek read as scraggly
lines; the front is a smooth curtain, not separate loosened locks; the tail is wide ribbons from behind and ~16 % big
in profile; up-style temples still serrated close up. Coordinator's dial-only pass on the wisps: th_X1 (no sideburn
wisps, shorter, softer), th_X2 (short sideburn wisps, less drape, 3 loose locks a side).

## Joe on th_T66, marked up (2026-10-13)
On his markup of th_T66 beside her three-quarter picture (red lines from the parting; /mnt/data/hifipushie/tesshair7/
joe_markup_part_lift.png): "it still hasn't nailed the _shape_ or the color variation, it's flat, in both senses." Hers:
from the part the hair RISES, arcs up and over, then out and down the side to the temple (three nested convex arcs, real
volume over the crown and sides). Ours: nearly straight lines laid flat along the skull, diagonally down and back; one
flat brown. Round seven, "## tesshair7".

## tesshair7 (2026-10-13, "tesshair7" agent, branch `tesshair7`): volume from the parting, and a hair colour model
STATE / NEXT: DONE: the style word `volume` (gather.volume: the hair stands up out of its root with a bend radius,
a dome by region in layers, the way FALLS from the root before the tie takes it, held until the tie), the look's colour
model (`variation`, `sun` by the hair's age from the scalp, `highlights` as ~6 mm ribbons, `fly_light`, `depth`),
`hair.colour_variation` (strand / ribbon / mass contrast, share of light ribbons; in look_hair's measure), the
stand-off measure, tests, guide, tie_hair's text. BEST for Tess = th_V86 (one tie_hair call on tess_a1, style / look
below). Sheets workspace/human_renders/th_50_tess_volume_colour.png (REFERENCE | th_V86 | th_T66; front, three-quarter,
profile, back 3/4, crown), th_51_part_arcs.png (strand paths from the parting, hers | ours | T66), th_52_riffs.png (nine
riffs on hu_w30 / hu_m30). SHAPE: yes, the hair now rises from the part and arcs, and the outline is hers within ~3 mm
over the top and sides; NOT yet her texture (a smooth helmet, no loose locks) and the up-styles / half up are WORSE with
volume (pleats, a pit). COLOUR: varies now (ribbons, lighter lengths), about two thirds of her measured variation.
NEXT: the list at the end.

Scratch DURABLE /mnt/data/hifipushie/tesshair7/ (copies of the .sh in spikes/tesshair7/): run.sh <script> (this
worktree's code on the main workspace, capped); r7.sh <NAME> [views] [size] (ONE heavy job: th_<NAME> = tess_a1 +
tie_hair(styles/<NAME>.json, carry_from th_T66, looks/<NAME>.json) + seed 0 through the tools (riff7.py), lock plot,
fitted-camera tiles (shots7.py), standoff.py, colvar.py, a row); crop.py <model> [other] (head crops hers | model |
other). Scripts `spikes/tesshair7/`: hv.py (several scripts one after another in ONE process holding resources.heavy:
the light slots were starved all day, ten solver chains queued, so every small step rode with a render), pt.py (tests,
a file a process, inside hv), lockplot.py (locks' lines from five sides, NO Blender, + the top layer's height by
region), standoff.py, colvar.py, flowlines.py, riffs7.py, mk_sheets7.py, shots7.py (= tesshair5's shots5 + S= / drop=
/ tag= isolation in memory, view "crown"). Models th_V70 .. V86 (Tess rounds), th_V9a1..a5 / th_V9b1..b4 (riffs).
FOUND ON THE WAY: th_T04 .. th_T46 and th_T34 disappeared from the workspace while this round ran (2026-10-13 ~12:20;
not this agent: its scripts only write th_V7* .. V9*). The built stage `_g3_th_T04` is still there and shots7.py uses it
as built; spikes that call stage.ensure("th_T04") (shots5, iso, tailfit, cu.sh) fail until that model is restored.

### What groomers and look-dev do (checked before building)
- Root lift is a DIRECTION given to the guides at the root, then a bend: Houdini's Guide Process Lift / Bend / Set
  Direction on the first stretch of the guides, masked to the root zone (Gnomon, "Creature Grooming Techniques in
  Houdini"); guides laid in LAYERS from the bottom up, upper over lower (Gnomon, "Creating a Female Hairstyle for
  Production with Maya XGen"; SideFX forum topic 84298). -> rise with a bend radius per lock, locks at several heights.
- Hair colour in production: melanin + a per-strand random (Blender's Principled Hair BSDF: Random Color "realistic
  hair should have a minimum of variance between each strand"); a root -> tip ramp (MetaHuman Groom colour ramp;
  Softimage's root / tip colours with a crossover); Redshift's Hair Random Color on hue / saturation / value;
  highlights keyed to the clump. -> variation on H / S / V per lock, sub clump and strand; a gradient by the hair's
  age; highlight ribbons by a random per ribbon across the lock.

### 1a. Measured first: how far the hair's outline stands off the skull (standoff.py)
The model's scalp rays projected through each picture's fitted camera = the skull's silhouette; the hair's outline read
off her picture and off our render through the same camera; along rays from the head centre's pixel (0 = straight up,
+ = image right), mm from the skull's edge to the hair's edge. hers | th_T66 | th_V86:
| where | hers | th_T66 | th_V86 |
|---|---|---|---|
| front view, over the top (-30..+30) | 17-19 | 8-17 (8 at the part) | 16-23 |
| front view, her right side (-90..-40) | 17-19 | 13-17 | 21-23 |
| front view, her left side (+40..+90) | 20-24 | 15-19 | 20-22 |
| three-quarter, top and back (+10..+90) | 18-32 | 15-18 | 22-25 |
| profile, over the forehead (-60..-50) | 13-15 | 5-6 | 6-11 |
| profile, the top (0..+30) | 17-23 | 14-16 | 21-23 |
| profile, back of the crown to the tie (+40..+80) | 28-38 | 15-16 | 21-24 |
So hers stands ~18 mm off the skull all over the top and sides and 3-4 cm above the tie; T66 was 5-15 mm short
everywhere and lowest AT the part (a dent where hers has no dent). Not the 3 cm one would guess by eye: the read
"flat" was mostly the missing rise at the root and the straight paths. Still short on th_V86: the forehead (the hair's
first cm over the hairline) and the back of the crown above the tie.
Her arcs (th_51, flowlines.py: stream lines of the image's own strand direction from seeds on both banks of the part,
the same place on the head in every panel): from the front they leave the part ~20 deg below horizontal and bow 18 mm
off their chord; T66's 13 deg and 22 mm, th_V86's 19 deg and 22 mm. This measure is WEAK: at the outline the tracer
rides the silhouette in all three, and in the three-quarter her lines run back over the crown (52 mm long, they leave
the mask) where ours run 11 cm. The lock plot (cyan lines) is the honest picture of ours.

### 1b. Why th_T66 was flat (by construction; lock plot out/locks_th_T66.png)
- NO RISE: a lock's height was ride 2 mm + body x way + root_lift + puff x sin: at tightness 0.85 that is 2.7 mm of
  root lift and 4.4 mm of puff (x 1.7 in front with front.looseness): the top layer 14 mm off the scalp at most, reached
  halfway along the lock, 0 at the root. `lift` only scaled those few mm: a shell offset, no direction at the root.
- STRAIGHT WAYS: paths() steps toward the tie from the first step ("always on toward the tie", v . to >= 0.35), with a
  3.5 cm wide push off the part and a sag that is zero where the head is flat: off the part the hair ran diagonally
  back in nearly straight lines (the red locks of the plot). Joe's lines exactly.
- ONE SHELL: every lock at about the same height; nothing under it but the scalp layer.

### 1c. The construction now (`hair_flow.gather` / `paths`, tie key gather.volume; style word `volume`)
- RISE: h = layer x dome x (1 - exp(-s / rise)) x hold: the hair leaves the scalp at atan(dome / rise) (64 deg at 2 cm
  over 1 cm) and is over within ~2 x rise. 18 points a lock, denser at the root (t^1.6). The banks of a part rise at
  0.35 x the radius (at the full radius the two banks leaned apart: a 2 cm valley, the head a heart with two lobes).
- DOME by region: crown (sin(el)^1.5), sides (fullest high, x 0.3 where the hair passes over the ear: full down to the
  ear the head was widest at the cheek, a bob), the back of the head = the crown's value down to the nape's.
- LAYERS: each lock its own height 1 - layers x (1 - u^0.6); lock thickness + 0.25 x dome; the lock's depth is its
  strands' `shade` (hp_sh) and the look's `depth` darkens the under-layers. The hairline's own narrow locks all sit at
  ONE height (side by side at their own heights they were pleats on the up-styles).
- ARC: for the first 0.6 rad the way's direction is mixed with the FALL (down the head; sideways out of the part while
  the head is still flat; never forward), after a 1 cm lean back along the part (tied hair was pulled back first), and
  the fall stops 8 deg above the ear's line (falling all the way, every way ran along that line: a curtain with a
  thick lower edge) but may reach the hairline over the forehead's corners.
- HOLD: the height is kept until 0.4 + 0.45 x hold of the way, then drawn in; the tie stands up to 12 mm further off
  the head with it.
- With volume: strands loose / frizz / flyaway / halo + by V, gather wave + 6 mm x V, the scalp tint's ramp 22 -> 7 mm,
  the edge band full by 5 mm at the forehead too.
- Style (hair_flow.TIED / VOLUME): `volume` 0..1 or {amount, crown, sides, nape, root, arc, layers, hold}; at 1 the
  top layer stands 3.4 / 3.0 / 1.4 cm off the crown / sides / nape; default = `lift` (= 1 - tightness): a sleek head
  stays a cap, a loose one has body. volume 0 = the old gather exactly.

### 2. The colour model (blender_strands.material / lens_group v16, hair_strands.lock_guides, hair.LOOK)
- New strand attributes: hp_lv (a number per lock), hp_ch (per highlight RIBBON: by where the strand starts across
  its lock, hp_hk = lock width / 6 mm ribbons), hp_a0 / hp_a1 (the hair's AGE in m from the scalp at the lock's start
  / end: a tail's locks start at the median length of the gathered hair, not at a new dark root), hp_sh (depth in the
  mass), hp_fly (hairs that left the mass: fly-aways, halo, single-hair objects; NOT the hairline's fine rim).
- Look keys: `variation` (0.4: lock value +-14 % x v, hue +-0.01 x v by sub clump, saturation +-15 % x v by strand),
  `sun` (0.2: value + 50 % x sun and a little warmer by age, full by 28 cm), `highlights` (0: the share of ribbons
  lighter (x 2 at contrast 1) and more saturated, 62 % of a ribbon's strands, from 1-7 cm off the root, coming and
  going along the hair), `highlight_contrast` (0.6), `fly_light` (0.3), `depth` (0.5). The defaults VARY (every hair
  model's strands change a little on its next render); flat on purpose = variation 0, sun 0, vary 0.
- Export: the attributes are on the evaluated curves (USD keeps per-curve attributes; Alembic does not). NOT DONE: a
  baked per-strand colour primvar for the groom export, and the cards' atlas (hair_cards draws strands with `vary`
  only): game cards do not get the model yet.
- Measure: hair.colour_variation / colour_bands(mm_px) (in look_hair's measure "colour"); colvar.py = hers | ours over
  the dense hair both have, three views:
  | | hers | th_T66 | th_V86 |
  |---|---|---|---|
  | L_sd (all of it) | 7.6 | 3.9 | 5.7 |
  | strand_sd (1.5 mm) | 4.2 | 2.0 | 2.5 |
  | ribbon_sd (1.5 vs 9 mm) | 3.0 | 1.75 | 2.6 |
  | mass_sd (9 vs 40 mm) | 2.4 | 1.6 | 1.8 |
  | light ribbons: share / lift L* | 10 % / 5.7 | 1 % / 6.8 | 6 % / 6.0 |
  | chroma_sd / hue_sd | 3.2 / 5.7 | 0.8 / 2.3 | 1.6 / 2.7 |
  Mean colour th_V86 L* 19-23 (hers 17-20), chroma 10.8 (hers 8-9), hue 65.6 (hers 69.7: ours 4 deg red).

### Rounds (r7.sh; out/row_<NAME>.jpg, c_th_<NAME>.jpg)
- V70 (volume 0.65, first grow): real volume and arcs at once, but a bob: sides 29 mm, a deep open part, the front
  fell FORWARD over the temples; per-lock value +-20 % made the tail's locks flat painted slabs.
- V71 / V72: lean back before the fall, never forward, thicker locks; highlights picked 35 % by the lock = whole 4 cm
  locks pale grey slabs; by the sub clump alone (4 mm) they averaged away; neatness 0.75 turned the tail into a stiff fan.
- V73 / V74: ribbons of 1.7 sub clumps, then by the strand's place across the lock; depth shade; the part's banks
  rise at once; the fall stops above the ear. Ribbons uniform along their length were pale tape: they come and go, 62 %
  of their strands.
- V75 .. V80, the GREY VEIL over the forehead's corners: not fly_light, not the edge band (drop tg0_*), not the scalp
  layer's strands (S.under 0), not the scalp tint (look.scalp_tint 0): it was the WISPS (drop tw*): 36 clumps x 14-37
  fine half-transparent hairs + 56 baby hairs lying on the corners, which the flat hair used to cover and the lifted
  mass exposes. th_V81+: wisps amount 0.45, front.looseness 0.35, no swoop / loose locks, wisps only at temple /
  sideburn (a front wisp hung across the eye).
- V84 -> V86: the look. lit shifted toward yellow + sun's hue shift gave an olive-grey tail (V84); eevee_sat 0.62 a
  ginger one (V85, chroma 14.5); V86 = eevee_sat 0.5, lit #58483a.
th_V86 = tie_hair(style {"tie": "low", "side": 20, "tightness": 0.85, "neatness": 0.95, "volume": {"amount": 0.5,
"crown": 0.75, "sides": 0.6, "hold": 1.0, "root": 0.85}, "front": {"looseness": 0.35, "drape": 0.6, "locks": 0},
"wisps": {"amount": 0.45, "softness": 0.7, "loose": 0, "where": ["temple", "sideburn"]}, "tail": {"length": 0.195,
"wave": 0.6, "fullness": 0.43, "tousle": 0.55}}, carry_from th_T66, look {"variation": 0.7, "sun": 0.35, "highlights":
0.55, "highlight_contrast": 0.7, "depth": 0.8, "specular": 0.3, "roughness": 0.5, "vary": 0.45, "eevee_gain": 1.22,
"eevee_sat": 0.5, "lit": "#58483a", "gap": "#221a13", "fly_light": 0.15, "cycles_width": 1.8, "cycles_sat": 0.65}) +
groom seed 0.

### Riffs (riffs7.py: tie_hair + sync + look_hair on hu_w30 / hu_m30, nothing tuned; th_52)
- sleek low, volume 0, flat colour (both heads): the old cap, reads. LOOSE low, volume 0.7 (both): reads as hair with
  body at once, arcs off the part; big (a bouffant), a kink where the lifted side meets the ear, from behind a small
  furrow where the part ends. Low plait, volume 0.4, highlights: reads, fine streaks.
- WORSE WITH VOLUME: the high ponytail and the man bun (part none, volume 0.5): radial RIDGES round the hairline
  (corduroy), white specks of scalp at the crown; half up (volume 0.6): a bare PIT behind the crown above the tie.
  Hair pulled UP to a tie does not fall from its root; the dome and layers are a low tie's.
- sun 0.9 on a light brown: an orange straw tail from behind (too strong; toned down once, not re-judged).
- Cost: tie_hair 55-60 s the first time on a head, 1 s after; sync 100 s; look_hair three views 30-45 s.

### BLUNT READ of th_V86 beside her pictures (th_50)
1. SHAPE: clearly closer than th_T66. The hair stands up on both banks of the part, arcs over and down the side to
   the temple, the top is a dome instead of a cap, the ear's top is clear (hers), the outline is within ~3 mm of hers
   over the top and sides. Wrong: it is a SMOOTH HELMET (one continuous combed shell; hers is loose locks with air,
   strands crossing, a halo of flyaways); the part is a clean notch with two lobes where hers is short and soft; the
   forehead's first cm lies low (6-11 vs 13-15 mm); the back above the tie is 1 cm short; the hairline is a clean line
   again (the wisps were cut back to remove the veil).
2. COLOUR: no longer one brown: lighter ribbons over darker hair, lighter lengths and tail, darker under-layers.
   Wrong: about two thirds of her variation by measure; ribbons are regular fine pinstripes where hers are irregular
   soft ribbons; no warm highlight where the light catches the arcs (that is shading, not pigment: EEVEE's strands
   have no real specular lobe here); chroma a little high, hue 4 deg red.
3. TAIL: as th_T66's (not this round's), lighter by `sun`; still wide ribbons from behind.

### Dead ends
- Per-lock value +-20 %: painted slabs. Highlights by the lock: pale slabs; by one 4 mm sub clump: invisible.
- The fall with a forward component (- 0.3): a bob's curtain. Falling from the first mm: an open valley.
- Lifting the edge band's thin rim with the mass: a gauze standing over the corners.
- neatness lower for looseness on the head: it is the tail that changes (a stiff fan).
- Shortening the scalp tint's ramp / the band's ramp to remove the veil: not the cause (kept: harmless).

NEXT: (1) the head as LOCKS, not a shell: with volume the gather's 4 cm locks should separate (narrower, their own
waves and heights changing ALONG the lock, a share lifted or crossing), a halo; the part shorter and softer (banks
that fall over it); (2) up-styles and half up with volume: no fall / layers toward a tie above the root (volume there
= a smooth pouf with the hairline's hair rising evenly), the pit behind a mid tie; re-judge every riff; (3) front
wisps again without the veil (fewer hairs a clump, rooted ON the lifted hair's edge, opaque); the forehead's first cm;
(4) colour: ribbons of irregular width, the cards' atlas and the groom export get the model (a baked per-strand
colour), a highlight that follows the light (anisotropic strand shading in EEVEE); (5) tess_n1 was NOT tried (the
GNM-native head's stage would need a build); (6) restore th_T04 or point the tesshair spikes at `_g3_th_T04`;
(7) flowlines.py seeds only on the bank the camera sees, and a mask that keeps her flyaway edge out.

### tesshair7 ROUND TWO: RESTART BLOCK (2026-10-13 evening; written for an agent with no memory of the session)
Joe on th_V86: "That's the best hair yet, for sure. If we got the color/texture and whispies dialed in, I'd likely ship
with it. Keep going." Round two = colour structure, texture (locks, parting), wisps; no regressions on up-styles.
STATE: BEST = th_W04 (tess_a1 + ONE tie_hair call; style spikes/tesshair7/styles/W04_style.json, look
W04_look.json, carry_from th_T66, groom seed 0). It beats th_V86 by measure and by eye in the head crops
(/mnt/data/hifipushie/tesshair7/out/c_th_W03.jpg = hers | W03 | W02; W04 = W03's geometry with a lighter look);
its tiles out/s_th_W04_{v0,v1,v2,backl}.png are rendered at 1536 (EEVEE, fitted cameras). NOT YET LOOKED AT closely at
1536, no sheet built from it.
Colour variation, hers | th_T66 | th_V86 | th_W04 (colvar.py, mean of three views): L_sd 7.5 | 3.9 | 5.7 | 7.6;
strand_sd 4.3 | 2.0 | 2.5 | 3.5; ribbon_sd 3.0 | 1.75 | 2.6 | 3.05; mass_sd 2.4 | 1.6 | 1.8 | 2.4; light ribbons
9 % at + 5.7 L* | 1 % | 6 % | 8 % at + 6.4; chroma_sd 3.1 | 0.8 | 1.6 | 2.0; hue_sd 6.4 | 2.3 | 2.7 | 3.2. Mean colour
W04 L* 17-23 (hers 16.5-20), chroma 9.0 (hers 8-9), hue 66.5 (hers 69.7).
Stand-off W04 (mm, hers | ours): front top 17-19 | 16-23, sides 17-24 | 19-24; profile forehead 13-15 | 5-9 (STILL
SHORT), top 17-23 | 20-23, crown to tie 28-38 | 19-27 (still ~1 cm short).
Round-two items:
- DONE in code + tests written: (1) irregular ribbons (lens v17: hp_ch thin ~4 mm, hp_cb broad ~15 mm, soft wandering
  edges; gathered by hp_su = sun exposure per lock (top layers, round the face, the tail's outside); hp_cm 1.5 mm
  strand-scale value; root_dark; a tail's strands enter the ramp past the dark root); (2) highlight shading: look
  `gloss` (EEVEE: Principled's specular with its normal tilted toward the root + a warm coat lobe tilted toward the
  tip; EEVEE has no anisotropic reflection, the tangent is used for the tilt only). NOT JUDGED in a lit close-up of
  the dome yet; (3) locks: gather.volume.locks (height swells / sinks along each lock, wander, 8 % lifted, widths and
  clump sizes differ; inner strands of a lock darker by hp_b); (4) soft parting: gather.volume.cross (bank locks lean
  over the line), zig x 1.6; by eye the part is still a notch: PARTLY; (5) wisps: `wisps.curls` = hair_flow.curls
  (fine curled locks, 5-12 hairs, names tk<k>, own random stream), flat clumps cut back under volume; they read as
  small curls at the temples in W02 / W03, thin; (6) up-style regressions: default volume is 0 for tie high / top
  (smoothly by tie height) and for half up; asked for there = a pouf (arc / layers / locks 0). NOT RE-RENDERED:
  riffs8.py has never run; (7) export colour: src/hifipushie/hair_colour.py (numpy) -> blender_strands.export_groom
  writes per-point `groom_color`, hair_cards.mesh stores tone / peak in the cards' vertex colour and the atlas is
  lifted by peak. NEVER RUN in Blender / never looked at on cards: only the numpy test; (8) old spikes repointed to
  th_T66 (commit 5b83a4a).
- NOT DONE: seat on tess_n1; sheets th_60 / th_61 / th_62; guide has the new words, CLAUDE.md pointer unchanged (fine).
- TESTS: the last full run was BEFORE the final fixes. test_hair_flow had 1 failure (the hairline-band test; fixed
  since by giving it "volume": 0 and scaling lock width variety by `locks`: NOT re-run); test_hair_strands'
  new test_colour_model_outside_the_material was rewritten after failing: NOT re-run. Run all seven files first.
NEXT, in order:
1. tests: `/mnt/data/hifipushie/tesshair7/tests.sh` (each file through bin/slot; it WAITS for a light slot).
2. Look at th_W04 at 1536 one area at a time beside her photo, then build th_60 / th_61:
   `cd /mnt/data/hifipushie/tesshair7 && TOUT=$PWD/out python3 <worktree>/spikes/tesshair7/mk_sheets8.py th_W04 which=60,61`
   (th_V86's tiles are in out/ at 1024; mk_sheets8's crop boxes for th_61 were set blind: check each pair).
3. Riffs (HEAVY: sync + renders; one job): `W=<worktree> ./run.sh hv.py riffs8.py` -> out/rf8_*.png, then
   `mk_sheets8.py th_W04 which=62`. Judge the up-styles (a3, a4, a6, b3) and half up (a5) against th_52's faults.
4. tess_n1: `HEAD=tess_n1 SRC=th_W04 STYLE=W04 ./r8.sh W10` will fail at shots7 unless STAGE_MODEL=tess_n1 is exported
   (the stage of tess_a1 is `_g3_th_T04`; tess_n1's is `_g3_tess_n1`, stage.ensure may rebuild it: heavy).
5. Still wrong on W04 by eye: the part is a notch; the forehead's first cm lies low; curls are thin dark lines (more
   hairs, finer, lighter); the tail unchanged (wide ribbons); gloss unjudged.
To rebuild the best: `cd /mnt/data/hifipushie/tesshair7 && ./r8.sh W04 v0,v1,v2,backl 1536` (styles/W04.json +
looks/W04.json there are the same files as spikes/tesshair7/styles/W04_*.json). EEVEE only.
WHAT A FRESH AGENT WOULD GET WRONG:
- Machine rules (the coordinator, firmly): ONE heavy job at a time; light jobs through bin/slot and WAIT; never put
  light steps inside the heavy slot (round one did: hv.py without HV_LIGHT=1); never kill a process not positively
  identified as yours (round one killed a shell by a pgrep -f pattern that matched its own command line: never
  `pkill -f` / `pgrep -f` with a pattern that is in your own command).
- r8.sh is the round script (three queues); r7.sh is round one's (everything in the heavy slot): do not use it.
- Scripts run from the worktree as cwd: give ABSOLUTE output paths.
- shots7.py uses the built stage `_g3_th_T04` because th_T04 is gone; shots5 / iso now default to th_T66, whose stage
  does not exist yet (first use builds it: minutes, heavy).
- The look's defaults vary now (variation 0.4, sun 0.2): an old model re-rendered is not its old picture; the "before"
  columns use tiles rendered earlier (out/s_th_V86_*.png, tesshair6/out/s_th_T66_*.png).
- The grey veil over the forehead's corners is the flat WISP clumps (drop=tw*), not the band, the scalp tint or the
  under layer: do not chase those again.
- colvar's numbers depend on the tile size (strand_sd most): compare models at the same size (the table above mixes
  1024 and 1536 tiles for V86 / W04).

### tesshair7 round two, RESUMED (2026-10-14): fixes on th_W04 (the coordinator's read)
RESTART: tests all pass at 65bd468 (92). Best now th_W06 (W05 + wisps.curls 10, length [0.05, 0.14]; tail ribbons at half contrast, part-cross bump 3-7 mm; colvar L_sd 6.6 | hers 7.6, ribbon 3.1 | 3.0, light ribbons 9 % | 10 %. Earlier best th_W05 = W04 style + look fly_light 0.45, code below;
spikes/tesshair7/styles/W05_*.json; `cd /mnt/data/hifipushie/tesshair7 && ./r8.sh W05 v0,v1,v2,backl 1024`).
- CROWN WIRE-GRID (front view, top of the dome): isolated with shots7 S= patches (out/iso_w04b.jpg): it was the
  HALO (short broken hairs standing off the locks), which round one raised to 0.45 x messiness + 0.5 x volume:
  0.12 x volume now. Leftover white glints = gloss's sharp lobe on crossing strands: roughness floor 0.4, specular
  + 0.3 x gloss (was + 0.5). Gloss itself is NOT the grid, and with gloss 0 the hair reads grey and flat (iso_w04.jpg).
- TAIL "flat tan ribbons": the highlight ribbons (gone with highlights 0). Broad ribbons x 0.35 (was 0.6), half a
  ribbon's strands (was 62 %), value + 85 %, saturation + 25 % (was + 100 %: the tan). STILL visible as pale flat
  bands on W05: NEXT lower highlight_contrast for the tail / shade them along the strand.
- TEMPLE hard edge: the scalp tint's ramp (round one shortened it to 7 mm under volume while chasing the veil: not
  its cause): 16 mm now. And no dark root on fine strands (hp_fine: the rim, single hairs).
- WISPS "thin black wires": the curls had the dark root ramp and full opacity: now no dark root (hp_fine), fly_light
  0.45, 8-16 hairs 2-5 mm. On W05 they nearly vanish from the front: NEXT make them read (more, longer, lighter).
- Dark scribbly tuft at the part's start (three-quarter): the `cross` bump of the part's bank locks: NEXT smaller.
- SHEETS (2026-10-14, from th_W06, EEVEE): workspace/human_renders/th_60_tess_colour_wisps.png (REFERENCE | th_W06 |
  th_V86; front, three-quarter, profile, back 3/4), th_61_closeups.png (hers | W06: parting, both temples, forehead
  corner, the dome, tail; the left-temple pair frames a little differently), th_62_riffs.png (riffs8.py, th_W9a* on
  hu_w30, th_W9b* on hu_m30, through tie_hair + sync + look_hair).
- RIFFS read: all ten read at a glance. Up-styles and half up at DEFAULT volume = the pre-volume construction (no
  dome, no fall): half up's bare pit is GONE. The asked-for pouf (a6) and the default up-styles still show the
  serrated temple edge of round six (not volume's). New on every riff: default `curls` (round(9 x amount)) hang as
  small RINGLETS at the temples: reads, a little doll-like on the up-styles; NEXT: fewer / straighter by default when
  the tie is high.
- STATE: best th_W06. Done this resume: crown wire-grid (halo), tail tan ribbons, temple edge, black-wire wisps,
  sheets th_60 / 61 / 62. NOT done: tess_n1; the colour model in the export / cards has only its numpy test (never
  exported through Blender); gloss judged only by eye on W04..W06 (warmer than without; no lit close-up beside hers).
- STILL WRONG on W06 (blunt): the parting is still a hard notch with the two banks' smooth lobes; a small dark tuft of
  crossing / lifted strands at the part's start in the three-quarter; the temple and forehead hairline is cleaner and
  harder than hers (her loose fine hair over the corners is missing); the curls are faint; the tail's lock ribbons
  still read as ribbons from behind; hers is lighter brown overall and warmer (our hue 66.5 vs 69.7).
- NEXT: (1) the part: banks that fall over the line from both sides, short (fade out by 4 cm back); (2) loose fine hair
  over the forehead's corners (wisps.baby / front looseness under volume, without the veil); (3) tess_n1; (4) export
  through Blender once (export_asset hair) and look at the cards' colour; (5) up-style curls by tie height.
- ROUND TWO, third read (the coordinator on th_60 / 61: "I'd take V86's front over W06"), 2026-10-14:
  * DARK WIRY CLUMP at the part's start / forehead corner (three-quarter): in th_T66 and th_V86 too (old). Isolated
    with shots7 (drop= / S= / LS= in memory, out/iso_w06*.jpg, iso_w07*.jpg): NOT the wisps, curls, baby hairs, halo,
    fly-aways, strays, the edge band, the scalp layer, strand wave / curl / loose / frizz / clump, root darkness, the
    arc, the part crossing or the root's bend radius. It goes with the inner locks (drop tg1_*), and dropping the
    part's own root rows only MOVES it to the next locks behind: it is the far bank's strands seen END-ON at the
    silhouette, drawn opaque and dark. Her photo has fly-away loops in the same place, fine and light. Fix: the part
    rows drawn fine (hp_fine 0.55: part transparent, no dark root), density x 1.3. Lighter and smaller on W08, not gone.
    The front view's crown "wavy wires" were `volume.locks` at 1 (W07c, locks 0: gone): default now 0.4 x amount.
  * Curls: corkscrews -> a slow bend (radius 0.8-2.5 mm, 6-11 cm a wave). Ringlets gone (riffs too, by construction;
    th_62 not re-rendered).
  * Colour: lightening was desaturating toward grey: sun + 30 % saturation, highlights + 45 %; look W08 eevee_sat
    0.48, lit #5c4834. Back 3/4 now warm brown, but OVERSHOT: chroma 14.5 vs hers 9 (W09 pulls back).
  * RESTART: best so far th_W08 (style / look spikes/tesshair7/styles/W08_*.json), but too saturated.
  * W09 = W08 at eevee_sat 0.38, lit #574536, gap #211912: BEST (spikes/tesshair7/styles/W09_*.json;
    `cd /mnt/data/hifipushie/tesshair7 && ./r8.sh W09 v0,v1,v2,backl 1536`). Warm mid brown, darker top, lighter
    lengths; chroma 10.7 (hers 9); hue 62.5 (hers 69: ours ~6 deg red, worse than W06's 66.5: NEXT a yellower lit);
    L_sd 6.1 | 7.6, strand 3.4 | 4.3, ribbon 2.75 | 2.95, light ribbons 6 % | 9 %. Sheets th_60 (REFERENCE | W09 |
    V86), th_61 (close-ups), th_62 (riffs re-rendered). Tests: all 92 pass (tests.sh, slots).
  * Riffs: ringlets gone (near-straight temple strands on every riff). CORRECTION: half up's dark PIT behind the crown
    is still there with no volume: it is not volume's (round one's read was wrong). The two other heads' hair reads
    ashy grey: they wear the DEFAULT look (LOOK lit #56352d at eevee_sat 0.35), not Tess's: NEXT a warmer default look.
  * STILL WRONG on W09 (blunt): the PARTING is a clean notch between two smooth lobes (hers: a soft line, hair lifting
    and falling both ways) - item 4, NOT done; no fine HALO of fly-aways along the silhouette (hers has many); the
    forehead-corner fine hair is missing; the part-start loops lighter but present; tail still lock ribbons from
    behind. Not done: tess_n1; the export / cards colour only unit-tested.
  * NEXT (ordered): (1) the parting (banks falling over the line both ways; part short); (2) a light halo along the
    silhouette from the TOP layers only (the old halo on every lock was the crown wire-grid); (3) forehead-corner fine
    hair; (4) default look warmer (riffs grey); (5) half up's pit; (6) tess_n1; (7) export through Blender once.
