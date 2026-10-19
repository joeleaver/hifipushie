# hifipushie notes: hair

BEST GARRETT CARDS FOR EXPORT (2026-10-18, hair-garrett c6): /mnt/data/hifipushie/hair_garrett/cards/exp/c6M = c4L's cards (identical geometry / atlas: same verts and unique triangles) + hair.BACK_FACES 1 (each card's back its own triangles, outward normals, material doubleSided false: no viewer flips them, the crown shards stay gone in ANY engine); index triangles hero 26040 / main 10164 / npc 4704 / far 1380, verts 16115 / 6561 / 3228 / 915 (all inside budgets.json ranges). Preview with blender_cards ONE_NORMAL 1 + GLTF_SPEC 1. Previous line (c4/c5): unchanged GLBs, preview them with blender_cards.ONE_NORMAL 1 (c5 default), the old flip drew black crown shards): the branch hair-heads2 DEFAULTS at c4's commits (c3's EVEN_CAP_KEEP .6,
  GREY_QUANTILE 1 + c4's WIND_TO_NORMAL 1, GREY_SPREAD 2) + hair.export {"card_gain": 2.1}, ALL FOUR tiers from one export_hair:
  /mnt/data/hifipushie/hair_garrett/cards/exp/c4L/hg_G88a_hair_{hero,main,npc,far}.glb (14570 / 6130 / 2958 / 1024 tris,
  shared atlas). LODs OK: STYLE yes (same cut at every tier, no pompadour), QUALITY no. Blind A/B c3 (c3q hero + c3a tiers)
  vs c4L: hero front / 3/4 / side / back TIE, 2 / 4 / 8 m NEW (lighter, greyer) -> kept. Open MAJORs (both): black shard
  flaps at the crown, no silver sides (uniform grey), hairline / temples / sideburns stop short (cards' geometry), flat
  front top. Not shippable as a finished likeness: draft.

BEST GARRETT CARDS FOR EXPORT (2026-10-18, hair-garrett c9; NOT approved yet: bin/approve is Joe's / the coordinator's): /mnt/data/hifipushie/hair_garrett/cards/exp/c9M = c6M's cut + spec hair.strands {"flow_top": {"cards": 30, "hw": 0.015}, "hairline_row": {"hw": 0.012, "az": [40, 100], "el": [-40, 25]}} (rows skip far: min_triangles 3000); index triangles hero 28892 / main 11516 / npc 5420 / far 1380 (far = c6M's), all inside budgets.json ranges; blind A/B vs c6M (c6o renders): slim NEW (side + back NEW, 3/4 OLD, front / 2 / 4 / 8 m TIE). To use: put those two keys in hg_G88a's spec hair.strands (code defaults stay off). Previous BEST (c6): /mnt/data/hifipushie/hair_garrett/cards/exp/c6M = c4L's cards (identical geometry / atlas: same verts and unique triangles) + hair.BACK_FACES 1 (each card's back its own triangles, outward normals, material doubleSided false: no viewer flips them, the crown shards stay gone in ANY engine); index triangles hero 26040 / main 10164 / npc 4704 / far 1380, verts 16115 / 6561 / 3228 / 915 (all inside budgets.json ranges). Preview with blender_cards ONE_NORMAL 1 + GLTF_SPEC 1. Previous line (c4/c5): unchanged GLBs, preview them with blender_cards.ONE_NORMAL 1 (c5 default), the old flip drew black crown shards): the branch hair-heads2 DEFAULTS at c4's commits (c3's EVEN_CAP_KEEP .6,
  GREY_QUANTILE 1 + c4's WIND_TO_NORMAL 1, GREY_SPREAD 2) + hair.export {"card_gain": 2.1}, ALL FOUR tiers from one export_hair:
  /mnt/data/hifipushie/hair_garrett/cards/exp/c4L/hg_G88a_hair_{hero,main,npc,far}.glb (14570 / 6130 / 2958 / 1024 tris,
  shared atlas). LODs OK: STYLE yes (same cut at every tier, no pompadour), QUALITY no. Blind A/B c3 (c3q hero + c3a tiers)
  vs c4L: hero front / 3/4 / side / back TIE, 2 / 4 / 8 m NEW (lighter, greyer) -> kept. Open MAJORs (both): black shard
  flaps at the crown, no silver sides (uniform grey), hairline / temples / sideburns stop short (cards' geometry), flat
  front top. Not shippable as a finished likeness: draft.

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

## Hair colour from a photo: look.seen (2026-10-10)
- A light-brown photo colour typed into `lit` rendered grey-blond: EEVEE's strand material multiplies the colour's
  HSV saturation by eevee_sat 0.35 (linear) to copy Cycles' chroma loss, so it can never show more than 0.35 saturation:
  a light brown (linear HSV saturation ~0.6) is out of reach for ANY lit. New key `look.seen` (hair.seen_look /
  full_look, used everywhere the look was merged): lit = seen's hue and value at saturation / eevee_sat (capped at 1),
  eevee_sat = seen's / lit's (EEVEE draws seen exactly), gap / sheen / tip as multiples of lit, and the scalp tint
  ("scalp") and card_sat from seen (the boosted lit showed as an orange scalp between partings). Explicit colour keys
  win. test_hair_strands::test_seen_colour_reads_as_asked_in_eevee.
- Measured on a private test subject (flat frontal light, EEVEE): the rendered lit hair matched the photo's lit-hair numbers but came out
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
its own change, with a look at every human model).

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
  NOT rendered: the private test subjects (untouched).

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
### STATE / NEXT (2026-10-14, end of the arc on Tess; MERGE-READY, not started on NEXT)
STATE: branch tesshair7, BEST = th_W18 (= W17 + the front lightened like the back, below; styles/W18_*.json; W17 on the
GNM-native head th_W20). Joe: "basically happy with Tess's hair shape now"; colour = the game-shader round (th_63).
Sheets human_renders/th_50..52, th_60..63. The checklist "What makes hair read as hair" opens hair_guide.md (rule /
fault / measure / knob, incl. the game-shader terms and how cards carry them). Regression sheet spikes/tesshair7/
regress.py + accepted.json, accepted run "final" (2026-10-14; Tess W17 + 10 riffs). Tests 112 pass, 0 skipped (hair
flow / tied / loose / lift / strands / ear, toolsets, tooling; one file a process through bin/slot).
Small faults left: the part is a V (rule 5); a curly tangle at the forehead's corner seen end-on; hue ~6 deg red; the
back view lighter / tanner than hers; half up's pit (not volume's); the export / cards colour only unit-tested;
game-shader terms not built into the card export (written as card-material terms).
NEXT ARC (agreed with the coordinator / Joe, NOT started): make the hair work LEARN.
 (3) HAIR READER, like skin_from_reference: from the reference photos measure colour statistics (colour_bands +
     colour_variation, edge / core), outline break-up / halo density, parting softness, hairline density, wisp count;
     set the style and look from those as the START; measured vs set reported, INFERRED where a photo can't show it.
     Gives rules 4 (halo) and 5 (part) their numbers.
 (4) TEST on a clearly different hair type: propose 2-3 licence-clean references (curly, short, grey or a man's cut) to
     the coordinator; Joe picks one; a fixed budget of 4 rounds starting from the reader + the checklist only; report
     how far it got and which rule was missing.
 Run the regression sheet before every gate (`run.sh regress.py run tag=X`, `regress.py sheet tag=X`).
WHAT A FRESH AGENT WOULD GET WRONG: (1) machine rules: one heavy job at a time (run.sh = capped + resources.heavy via
the scripts), light jobs through bin/slot and WAIT; Blender with -t 6 (spikes/tesshair7/blender6 via
HIFIPUSHIE_BLENDER, set in run.sh / runl.sh / tests.sh); never kill a process not positively yours. (2) r8.sh is
the round script; shots7.py renders a groom variant in memory (drop= / S= / LS= / look= / tag=) to isolate faults.
(3) th_T04 .. T46 are gone: stages default to th_T66 / the built _g3_th_T04. (4) Look defaults now vary
(variation, sun): an old model re-rendered is not its old picture. (5) colvar numbers depend on tile size, and its
edge / core values on the mask intersection: compare at one size, as a direction.

### SUMMARY (one page; the diary follows)
Goal: Tess's swept-back, loosely tied side ponytail as a STYLE any head can wear. Joe's verdicts: th_V86 "best hair yet";
th_W09+ judged better than V86 by the coordinator. BEST = th_W13 (tess_a1 + one tie_hair call; spikes/tesshair7/styles/
W13_*.json); the same on the GNM-native head = th_W20. Sheets human_renders/th_50..52 (round one), th_60..62 (round two).
What was built (all as style / look words, tested, in the guide):
- `volume` (hair_flow.gather): rise from the root with a bend radius, a dome by region, layers, a fall from the root
  before the tie (convex arcs), hold; `locks` (height / width variety), `cross` (hair over the part). Gated off for
  up-styles and half up.
- the colour model (blender_strands.material, look keys variation / sun / highlights / highlight_contrast / fly_light /
  depth / root_dark / gloss; hair_colour.py for the groom export's groom_color and the cards' vertex tone).
- `wisps.curls` (escaped near-straight strands), `wisps.halo` (fine hairs off the top layer, some across the part).
- measures: hair.colour_variation (in look_hair's measure), spikes standoff.py / colvar.py / flowlines.py / lockplot.py
  / loops.py; shots7.py renders any groom variant in memory (drop= / S= / LS= / look=) to ISOLATE a fault.
The rules that came out of it are the checklist at the top of hair_guide.md ("What makes hair read as hair").
Faults found by isolation (each looked like something else): crown wire-grid = strands.halo on every lock; grey veil
over the forehead = flat wisp clumps exposed by the lift; dark tangle at the part's start = the far bank's strands seen
end-on (old: in T66 / V86 too); crown wavy wires = volume.locks at 1; tan tail bands = saturated highlight ribbons;
ashy lengths = lightening that desaturated; hard temple edge = a shortened scalp-tint ramp.
Still wrong on W13: the part dips (hair crosses it now); her tail narrower / more pointed; hue ~5 deg red; the
export / cards colour only unit-tested; half up's pit (not volume's). NEXT: the learning work (distil, regression
sheet, hair reader, a different hair type in 4 rounds).

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
- ROUND TWO, fourth read (the coordinator on W09: "better than V86"), 2026-10-14: (1) THE HALO: `wisps.halo` n fine single
  hairs (hair_flow.halo, names <pre>h<k>) rooted on the TOP layer of the gather (locks with shade < 0.2), following
  their lock 4-13 cm while standing 2-9 mm off it mid-way, a gentle loose curve (0.4-1.3 mm at 4-9 cm); 28 % rooted on
  the part's banks (lock strands `bank`) CROSS the line. Default round(420 x volume share x (1 - up)) = 420 for Tess.
  At 240 with 0.8-2.5 mm curls (W10) they were kinky wiggles. th_W11 = W09 + this: BEST. The silhouette in front and
  profile now has her fine standing hair. Part: hair across it, still a dip; far-bank tangle in three-quarter still the
  weakest spot. RESTART: `./r8.sh W11 v0,v1,v2,backl 1536`; style / look spikes/tesshair7/styles/W11_*.json.
  (3) far-bank tangle: part rows fine 0.85 at normal density (W12): reads as fine light fluff like hers. (4) tail from
  behind: tail strands fine 0.35 + 0.3 t, in_step 0.55 - 0.3 t, and Tess's tail wave 0.6 -> 0.35 (W13): strands, not
  wide wavy ribbons. th_W13 = BEST (styles/W13_*.json; `./r8.sh W13 v0,v1,v2,backl 1536`). Colour variation W13 |
  hers: L_sd 6.7 | 7.5, strand 3.25 | 4.3, ribbon 3.2 | 2.95, light ribbons 9 % | 9 %. Still wrong: the part dips
  (hair crosses it now); hers' tail is narrower and more pointed; hue a few deg red.
  tess_n1 (GNM-native Tess): th_W20 = W13's style + look through tie_hair(carry_from th_T66) on tess_n1, rendered on
  its own stage (`HEAD=tess_n1 EXTRA="stage=tess_n1" ./r8.sh W20 ...`): seats with no work (dome, halo, curls, tail);
  colour variation the same as on tess_a1 (L_sd 6.6 | 7.4, ribbon 3.1 | 3.1). Tests: 93 pass (two tail tests' bounds
  follow the less-in-step default). ROUND TWO DONE except: the part still dips; the tail narrower / more pointed in
  hers; hue a few deg red; the export / cards colour only unit-tested.
  NEXT (queued by the coordinator, Joe agreed): make the hair work LEARN: (1) distil a "what makes hair read as hair"
  checklist into hair_guide.md (rule + measure + knob) and cut the guide; a 1-page summary atop "## tesshair7";
  (2) a regression sheet script (current best styles + riffs beside the last accepted renders); GATE; (3) a hair
  reader from reference photos; (4) a test on a different hair type, 4 rounds.
- LEARN step 1 + 2 (2026-10-14): hair_guide.md now OPENS with "What makes hair read as hair" (13 rules: rule, the
  fault when missing, measure, knob) and is 98 -> 59 KB: the sculpted-locks / cards workflow moved to guide topic
  `hair_locks` (hair_locks_guide.md), practice / sources / engines / what-went-wrong to `hair_background`
  (hair_background.md). REGRESSION SHEET: spikes/tesshair7/regress.py + accepted.json (Tess = W13 through her fitted
  cameras, 4 views; riffs a1..a6, b1..b4 on hu_w30 / hu_m30 through look_hair on their synced copies th_W9a1 /
  th_W9b1). Accepted = run "base" (2026-10-14, out/reg/accepted). A second run: mean |diff| 0.00 on all eleven
  (deterministic): any > 0.3 flags MOVED. Probe (W12's three-quarter swapped in): 2.65, the diff image outlines the
  tail. Cost: one heavy job ~10 min (11 tie_hair + renders). Blender now runs with -t 6 (blender6 wrapper via
  HIFIPUSHIE_BLENDER in run.sh / runl.sh / tests.sh). GATE: waiting for the coordinator on the checklist + the sheet.
  RESTART: then step 3, the hair reader.
- Gate passed (checklist, guide cut, regression sheet). W14 / W15 on the two small faults: crossing halo hairs 16 %,
  near-straight; part rows density x 0.7 and 1.2 x higher; part scalp line 2.5 mm under volume; all halo curls 0.2-0.6
  mm; look fly_light 0.8. Corner tangle a little less curly, the part still a V: both SMALL, on the list. th_W15 =
  current (styles/W15_*.json). Joe: "basically happy with Tess's hair shape now" but "we haven't nailed the color".
  NEXT: the shader test (EEVEE stand-in vs Cycles Principled Hair BSDF vs her photo), then the reader.
- GAME-SHADER COLOUR ROUND (2026-10-14; Joe: "we haven't nailed the color"; the coordinator first asked for a Cycles
  hair-BSDF comparison, then REVISED: no ray tracing, "our first target is general game assets"). A Cycles melanin
  render of W15 was made before the revision (out/s_th_W15_c640_*_cyc.png, look key `cycles_melanin`): NOT used,
  not judged. Built in the EEVEE strand material (blender_strands.material), each a term a game shader has:
  `tip_alpha` (dithered alpha over a strand's last 30 %), `backscatter` (a Translucent BSDF, lit from behind,
  warmer / brighter, weighted to thin hair: tips and fine / single hairs), `scatter` (by depth hp_sh: core darker and
  more saturated, outer layers lighter); transparency is one final mix with a Transparent BSDF. The two highlight
  lobes were already `gloss`. Defaults 0 (others unchanged). Measure `colour_variation` edge_L / core_L / edge_chroma /
  core_chroma (3 mm rim vs > 8 mm in). W15 (now) -> W16 (terms on) -> W17 (terms + darker base: eevee_gain 1.4,
  eevee_sat 0.3, backscatter 0.6, scatter 0.8), at 1024, hers | ours: L_sd 7.5 | 6.9 -> 7.7, strand_sd 4.2 | 3.3 ->
  3.9, mean L* front 21.4 | 20.4 -> 20.5, chroma ~8 | 10.5 -> 10.2, hue 69 | 62 -> 63. Edge vs core: ours ~0 -> +4.4
  (W17). Her own value read +5.5 (W15 run) and +2.4 (W17 run): the masks are intersections of hers and ours, so the
  numbers are not on one scale: a direction, not a match. By eye: softer see-through ends, warmer tail tips, a
  stronger dome band; the back view still lighter and tanner than her deeper brown, hue ~6 deg red. Sheet
  human_renders/th_63_game_shader.png (REFERENCE | EEVEE now W15 | EEVEE new W17: front, 3/4, back 3/4, dome, tail).
  BEST = th_W17 (styles/W17_*.json; `./r8.sh W17 v0,v1,v2,backl 1024`). Cards: tips' alpha is in the atlas; gloss /
  backscatter / scatter are card-material terms (anisotropic two-lobe spec on the cards' tangents, a transmission /
  wrap term, depth already in the cards' vertex colour): written in the checklist, NOT built into the card export.

## Joe on th_63 (2026-10-13): the references disagree on colour
Joe: the back-view reference's highlights are a different colour from the front view's, and the FRONT view is the one he has
been judging. Tess's references are generated concept views and are not colour-consistent across views, so colour measures
averaged over all views chase a mix. NEXT (whoever tunes colour again): take hair colour targets from the front view only (the
3/4 as a check), say which view each target came from, and do not judge the back view's colour against its own reference.

- FRONT LIKE THE BACK (2026-10-14; Joe likes OUR back three-quarter's colour in th_63, wants the front like it; the
  target is our own back render, not a photo: Tess's references disagree on colour between views). WHY they differed:
  NOT the light rig (the front under the back view's rig was as dark: core L* 14.9 vs the back's 21.9); the hair's AGE
  along the strand: from the front one sees the first 2-10 cm of every strand (the dark-root stretch, too young for
  `sun`, full only by 28 cm, and before the ribbons start), from the back the 10-25 cm lengths. FIX: look key
  `sun_length` (m by which sun-lightening is full; default 0.28 unchanged) + Tess's look sun 0.7, sun_length 0.06,
  root 0.05, root_dark 0.5, highlights 0.7 = th_W18. colour_bands (our renders, spikes/tesshair7/bands.py), back
  target | front before | front after: mean L* 27.0 | 24.4 | 26.4, shadow 16.1 | 13.7 | 16.6, highlight 38.1 | 37.0 |
  37.4, core 21.9 | 17.8 | 22.7, chroma 11.1 | 10.9 | 11.9. A little root darkness kept at the part. The back itself
  got ~2 L* lighter with it. Sheet human_renders/th_64_front_like_back.png (OUR BACK | front before | after; 3/4
  before | after). Regression: only Tess moved (1.3), riffs identical; accepted run "w18". Tests 112 pass, 0 skipped.

## hair-garrett (2026-10-14, "hair-garrett" agent, branch `worktree-agent-a9414ffa57394154a`): the hair READER, new hair types
Goal: show the checklist (hair_guide.md "What makes hair read as hair") carries to new people and hair types, and build
the hair READER. Subjects: a short men's cut from a held-out photo set, then two family heads. Per-person / per-picture
notes are NEVER here (held-out set: /mnt/data/hifipushie/hair_garrett/notes_private.md; family: workspace/private_notes/).
### STATE / NEXT / RESTART
STATE (2026-10-14, END OF THE BRIEF: the man 4 rounds + a rule-15 step (r5), two long-haired heads 4 rounds each;
sheets sent): `hair_read.py` + MCP `hair_from_reference` (read incl. long hair: bottom / waviness; START for a short cut
and for loose long hair; `compare=` ours | picture; `colour_step`: grey hair per channel on the modes, other hair in Lab
on the mean) + tests (test_hair_read 17, test_hair_loose +1: lift per region; test_toolsets updated); `groom.loose.lift`
may be per region; loose locks at the hairline get the hairline ramp (hair_strands.EDGE_*). Regression accepted "hg2".
Checklist rules 14, 15 added; rule 4's knob note: loose hair has none that reaches the halo.
NEXT (proposed): (1) halo / fly-away words for LOOSE hair (rule 4 / 7: the knob that is missing on long heads); (2) a
one-side ear tuck and curtain bangs from a centre part as groom.loose words; (3) the nape fade (the hairline ramp running
down over 1-2 cm) on the man's crop; (4) re-seat the man's groom on projskin's head once its skin stack is on main.
Earlier STATE (after the man's 4 rounds):
Checklist rules 14 (short cut: length and lay by region) and 15 (fine strands at the picture's scale) added.
Sheets workspace/human_renders/hg_00 (reader start) .. hg_04 (round 4). Regression run "hg1": all eleven 0.00 (same).
Round 4 by the reader (ours | picture): stand-off sides -0.4, back +2.7, nape +1.8, top +4.8, front -5.3 mm; mean L*
39.9 | 41.9, highlight 51.5 | 53.6, light share 0.36 | 0.45; chroma 6.4 | 4.9 (browner); strand_sd 9.3 | 6.8 (coarse);
hairline softness 1.0 | 3.5 mm. By eye: a combed-back short grey cut now (no curls), but coarse wiry strands, a
comb-teeth hairline, a ragged nape.
NEXT: the family heads (GO given; reader start + up to 4 rounds each; sheets after r1 and r4); open faults on the crop: rule 15
(strand fineness, the hairline's density ramp), front stand-off, chroma (one more colour_step).
RESTART: scratch DURABLE /mnt/data/hifipushie/hair_garrett/: env.sh, run.sh <script> (heavy: capped; scripts in
spikes/hair_garrett, tesshair7, tesshair5, garrett3), runl.sh (light: bin/slot), blender6 (-t 6). Scripts
spikes/hair_garrett/: copyhead.py <src> <dst> (hg_* / hj_* / hl_* copies; skin copied, never edited), readprobe.py
<model> (read + start + overlays), hround.py <head> <dst> [patch=@json] (reader start onto a copy + a round patch through
server.groom_hair; ABSOLUTE patch paths: run.sh cds to the worktree), hgshots.py <model> [stage=<head model>] (EEVEE tiles through the fitted cameras + the front camera turned: y125, y180;
this branch has no skin layer stack, so skin.projection / skin.stack are dropped from the STAGE in memory),
mksheet.py <model> [prev=] (REFERENCE | ours | prev + close-ups), cmp.py <model> (hair_read.compare on the tiles), pyc.py (a snippet in this environment). Round patches: /mnt/data/hifipushie/hair_garrett/styles/r1..r4.json (r4 = best). The regression: TOUT=/mnt/data/hifipushie/tesshair7/out run.sh regress.py run tag=X, then runl.sh regress.py sheet tag=X.
### Reader findings (general)
- The face parsers find short grey hair on a pale backdrop well (MediaPipe crisper at the outline, BiSeNet softer):
  hair = their mean; the pixel-level hairness (backdrop -> dense hair colour) carries the fine edge the nets smooth.
- The skull (scalp projected through the fitted camera) can stand OUTSIDE the photo's hair at the back of the head in
  a profile: the head's shape and that picture disagree (or the camera's fit is off there); the stand-off goes negative
  there and the views disagree by > 10 mm at the back. Read such a region from the other views; don't groom to it.
- Baby-hair counting needs a thin-shape test (area < 0.5 mm x length): skin texture (pores, creases) counted 4x.
- Validated on Tess's pictures: the reader's stand-off over the top 16.6-19 mm = tesshair7's standoff.py (17-19);
  halo 0.25 and 7 wisps / 10 cm on her loose updo vs 0.07 and 1.7 on a combed short cut: the measure separates them.
- Light shares must be compared at ONE threshold (the picture's): each image's own Otsu split counted different things.
### The short man's cut in 4 rounds (general findings; per-picture notes are private)
- `groom.volume` does NOTHING to loose hair (only the generated tiers): a loose groom's stand-off is `lift` (+ `body`
  as locks come down over each other) + the strands' own spread (~5 mm laid). `lift` is now per region.
- THE CURLS on a short back were not strand dials (all off: still curls) nor the under layer. Isolated (back view, one
  change each): (a) LAY with 6 mm thick locks: the lock's guide lies ~2.5 mm off the skull, half its strands are under
  the skin and are pushed out crumpled (r2: astrakhan; lay 0.3 + lift 4 mm: straight); (b) SHORT locks (19 mm) with a
  LIFT near their length rise and fall in one arc: every lock a hook, the back fish scales / curls (lift 12 mm on 19 mm
  locks: worst; narrower locks only showed the scales one by one). Straight laid short hair needs lift << length
  (2 mm on 30 mm) and locks <= 3 mm thick. Locks under 8 mm are skipped by hair_loose: a 6 mm nape left bare scalp.
- The stand-off of clipped sides (12 mm here) is not reachable with 1-2 cm hair laid flat: by measure the sides need
  ~3 cm laid hair (or a fuller under layer); trust the stand-off over "it looks short".
- Colour: one `colour_step` (asked x picture / render per linear channel, front view) took the mean L* 30 -> 40 (42);
  the rest was the grey SHARE, not the grey colour: grey strands are finer than a pixel, so the light pixels' median is
  a mix; the start now asks for the lightest quarter of them as the grey strand colour.
- Stages: a dressed stage per groom model (stage.ensure(model)) costs a sync each AND fills the shared _g3_ budget,
  so store.prune_stages evicted another agent's stage (the regression's _g3_th_T04; rebuilt from tess_a1 as th_T04,
  regression identical). hgshots.py now takes stage=<head model>: one stage for every groom on a head.
- RULE 15 STEP (r5, before | after close-ups human_renders/hg_05_*): (1) EEVEE draws every strand at least a pixel
  wide; at the pictures' own scale (~0.3 mm a px) a hair is a 0.3 mm wire. Judging renders now SUPERSAMPLE
  (hgshots ss=2: rendered 2x, averaged down) with more strands (count 300k): strand_sd 9.3 -> 8.4 (picture 6.8). The
  game analogue is TAA / alpha-to-coverage on thin cards, not thicker strands. Supersampled, coverage drops: mean L*
  39.9 -> 33.8: colour_step again after changing ss. (2) loose locks at the hairline got no hairline treatment
  (only tied / gathered locks were flagged `at_hairline`): now loose locks rooted within EDGE_START + EDGE_RAMP
  (3.5 + 8 mm) of the line stagger their roots and keep EDGE_MIN (0.15) .. 1 of their strands
  (hair_strands.EDGE_*): front softness 1.0 -> 2.8 mm (picture 3.5). (3) nape holes closed by spacing 0.007 + a
  denser, longer scalp layer (under 1.6, under_length 16 mm). Left: the hairline still reads as a line with a dark
  scalp-layer band under it; the nape ends in a ledge, not a fade (the nape's density needs the same ramp DOWNWARD,
  over ~1-2 cm: not built). Regression hg2: riff_a5 (half up's loose part) MOVED 1.96: the same style, its strands
  redrawn by the hairline ramp (no new fault seen; not accepted: the coordinator's call).
### hair-heads (2026-10-14, branch `hair-heads` from main 8343151): one head at a time to Tess's th_W18 standard
Joe: the arc isn't done; each head is "a completely different hairstyle" (Garrett's front, both family heads). Method
per round: describe the style in words from every photo (now Step 0 of hair_guide.md), then ours, then the differences;
rebuild from the description; isolate before fixing; sheet REFERENCE | now | previous every round.
Garrett round 8 (sheets human_renders/hg_08_garrett_front_style.jpg + hg_08_garrett_front_crops.jpg; patches
hair_garrett/styles/r8*.json; per-picture description in the private notes):
- ISOLATED: the dark band under the front hair is NOT the scalp-layer strands (under 0: still there): loose roots
  started 4 mm inside the hairline (hair_loose ok(): inside > 0.004), the strip in front was scalp-tinted skin. New
  `groom.loose.inset` (m; default 0.004 unchanged): 0.0005 puts the roots on the line.
- STYLE: from the photos the front is combed ACROSS to one side, lying low, its edge lower and rounder than the bare
  hairline; ours was brushed up and back (the reader's "sweep" read it so) and stood as a palisade. Tried a forward
  side-swept fringe (r8: a bowl fringe to the brows, wrong) and a short stiff one (r8b: spiky, wrong); r8c (flow front /
  top across, lay 0.6, no fringe) gave the right kind of front; r8d lowered the front points ~1 cm (temples 1.3 cm).
- Left on Garrett: the sweep is diagonal where his edge is a rounder arc; the top reads browner than his grey top;
  nape (next); the halo.
Garrett round 9 (sheets human_renders/hg_09_garrett.jpg + hg_09_garrett_front_crops.jpg; styles/r9*.json):
- front edge an even rounded arc: the hairline's front points lowered 0.5 cm at the centre and 1.2 cm over the temple
  corners (the M notches closed), the front combed mostly back with a little across ([-0.3, 0.05, 0.35]); a fully
  across comb (r8) fell diagonally low on one side; a fully up-back comb (r9c) brought the palisade back.
- shorter and closer: top 4 / sides 2 / back 2.2 / nape 1.2 cm, lift 1-4 mm, width 1.2, clump 0.1.
- the dark temple patches (3/4, profile) were the scalp TINT on the receded corners (isolated: look.scalp_tint 0.15
  removes them; the reader now sets 0.15 on grey hair, was 0.5).
- grey top: groom.grey per region (top / front 0.3) + a less chromatic `seen` (x0.55 chroma, as floats).
Left: his profile front edge curls a little FORWARD (ours stands up in tufts); the nape; the halo.
Garrett round 10-11 (sheets human_renders/hg_11_garrett_density.jpg + hg_11_garrett_crops.jpg; styles/r10, T7, T8 = r11):
- TEXTURE / DENSITY (the coordinator: wiry and sparse, scalp between, a ragged temple corner). Isolated on the 3/4 view
  one at a time on r10: count 600k (a little denser), strand thickness 0.55, a combed set (stray / tips / roots / frizz
  low), clump 0.35: none changed the read much. The cause was the LOCK level: 8 mm root spacing with locks 1.2 x wide
  left ridges with scalp between and a wedge at the temple corner where the front's comb and the sides' meet. Spacing
  5 mm, width 2.4, body 4 mm (+ 600k strands): a continuous combed surface, the temple corner closed. The reader's
  short-cut start now uses these (and count 600k).
- r10 (inside r11): nape hairline 1.2 cm lower (groom.hairline.nape -0.012), fade width 3 cm, nape lay 0.8; front flow
  with a little forward ([-0.3, -0.25, 0.35]).
Left: the profile front edge (his projects forward; ours ends short); the nape still shows a crown whorl hole and a
curly bottom row in the back views; the halo.
Garrett round 12 (sheets human_renders/hg_12_garrett.jpg + hg_12_garrett_crops.jpg; styles/r12.json): front points +5 mm
at the centre (+2.5 over the temple corners; the coordinator: brow-to-hairline ~15 % short after r8-r9); look fly_light
0.1 + strands tips 0.3 (the bright ragged tips read as wire); nape stiff 0.8 / lay 0.5 (the bottom row no longer curls).
OPEN, isolated but not found: a radial "whorl" bare spot at the back (az ~180, mid-height). It is on the head (stays put
from y160 and y180), not the scalp layer (under 0), not halo / flyaway, not the collider (scalp-ray collide mesh: same),
not the locks' directions (all point down there), not scalp-radius spikes or scalp-mesh holes; it moves when the back's
lift / lay change. Next suspect: the strand generator's root spread at the head's back pole.
GPU: a second amdgpu context loss ("hard recovery") with 600k strands, the scalp layer off (all of them in the locks),
2048 px: judging renders now use count 450k.
Private test subjects A and B, rounds (sheets and per-person descriptions in the private notes). General findings:
- `face` < 1 let loose long hair hang over the face in profile: keep 1 for loose long hair (0.5 put curtains over
  the face's edges but hid the whole face in profile: rejected).
- `tuck.from` (new): the front hair from the part is tucked too on that side. A profile picture can show the OTHER
  side from the one its name says: tuck the side the fitted profile camera sees. Halo share capped at HALO_MAX 0.2 as
  a guard (loose x2 x soft x4 reached 0.56).
- New strand dial `wave_from` (m along the lock where waves start: 0.12 = straight top, waves below the ear): a smooth
  top with waves only in the lengths (smoothing the top had otherwise straightened the lengths too).
- VOLUME: the reader's stand-off can read ours WIDER when the picture's room (couch, shirt) hides the hair's outline;
  measure by height from the parser (spikes/hair_garrett/widths.py) instead. groom.loose.body + waves in the lengths
  fill the mass out (the top stays smooth). Compare hair THICKNESS (outline minus the skull's own width at that
  height), not the outline's width, before tuning width: most of a cheek-level width difference can be head / camera
  scale, not hair.
- `groom.loose.face` may be {"left", "right"} (tested): a ONE-SIDED face rule for a curtain on one side and a tuck on
  the other. With the curtain side's face 0 the curtain still hangs beside the cheek, not over it: the hair falls
  straight down from the part, so a curtain OVER the cheek needs that side combed forward / across as it falls (a flow
  word for the lengths), not only the face rule let off. Open.
- Colour: a measured MEAN can match while the RANGE is too narrow (shadow / highlight L*, L_sd); darker roots
  (root_dark), depth, sun with sun_warm and highlights did not open it much. Open: the colour range (light lengths,
  dark roots).
Garrett's back whorl: still open. It has been in every loose groom's back view since the first rounds (a pit at the back
in r2 too); the roots' sampler is uniform on the sphere (no seam at az 180).
### hair-heads2 (branch from main 118bf2f): a centre part's bald stripe, Garrett's front hairline, thickness, the whorl
- A centre part's "bald stripe" (Joe, on a private test subject): isolated from the front and from ABOVE (hgshots view `t60`: the front camera tipped 60 deg
  over the top). Above showed the real cause: the whole top was a patchwork of flat lock ribbons with scalp between
  (loose spacing 18 mm, width 1.5); the part was only its worst line, and every root next to it was combed sideways off
  it (the away comb), opening a V toward the forehead. New `groom.loose.part_soft` (roots beside the part not combed
  away, the away comb over 15 mm, 25 % crossing; test) + spacing 10 mm, width 2.4, 220k strands + scalp_tint 0.15: hair
  runs up to the part from both sides, a few gaps left at the crown from above. Sheet (private)
  (REFERENCE | now | before; front crop + from above).
- From above (the coordinator: game cameras look down on heads): crown gaps + wide crossing ribbons. Narrower, denser
  locks (spacing 7 mm, width 2.0) made it WORSE (more crossings, more gaps); what closed it: scalp_tint back to 0.85 on
  dark hair (a dark scalp reads as the shadow between hairs, as on a real dark head: 0.15 suits GREY hair only) and the
  part's crossing share 0.1 (crossed locks left gaps behind them). scalp_tint by the hair's
  darkness: dark hair 0.85, grey / fair 0.15-0.3.
- Joe: "still left bald spots" (the dark tint only hid them) + two principles (now the top of the checklist): roots
  EVEN over the growing area (parts are the comb, not missing roots); hair ARCS up from the scalp then falls (flat from
  the root is a style choice). BUILT: `strands.even` (0..0.95): that share of the strands is a new object `hair_even`,
  Blender's Interpolate Hair Curves on the scalp mesh (even density, its own mask `hp_density_even`: no thinning at the
  part, none in the first EVEN_EDGE 12 mm inside the hairline / EVEN_FRONT 40 mm over the face), shaped by the nearest
  3 lock guides within 3 cm (the locks' own guide curves). First try hung a sparse veil over the forehead and eyes:
  children rooted in front of the guides take their shape translated forward, past the face rule; the edge / front
  masks fixed most of it. E2 (even 0.7, lift 12 mm, out top 0.25 / front 0.2, stiff 0.35): from above an even
  cover with a clean thin centre part (the crossing ribbons and crown gaps gone), volume from the arc. A few stray
  interpolated hairs still cross the forehead.
- The veil, isolated (front, one change each): it is the even layer (even 0: clean), not halo / fly-aways. Interpolated
  children TRANSLATE their guides' shapes: one rooted beside / in front of its guides falls where the guide would if it
  stood there, past the face rule, which only the guides obey. Splitting the scalp into two mesh islands along the part
  (Part by Mesh Islands: children use only guides on their own side) did NOT remove it; masking the front 4 cm did, but
  left the front of the part uncovered. What works: the even layer is a COVER layer, trimmed to EVEN_LEN 7 cm (x
  0.6-1): it covers the scalp under the lengths, the lengths are the locks' (E5: face and profile clean). Dense
  narrow Python locks instead (spacing 6 mm, width 1.3, even 0: E4) kept the face clean but from above read as ribbed
  ribbons with scalp along the part.
- Coverage, the long head (magenta, % of the hair region; lock-rooted r14 -> even cover layer E5): from above 4.83 -> 0.87,
  behind 0.3 -> 0.0, 3/4 back 0.08 -> 0.0, profile 0 -> 0. The rest is one patch beside the part's front half (comb
  direction parting the cover layer there, not missing roots). The reader's loose start now sets even 0.5 + out by
  region (dbf260f). STATE: coverage gate in the guide; NEXT: the part-front patch, then even roots on the other heads and Garrett
  (whorl), Garrett's hairline, the widths thickness / scale measure.
- ALL ROOTS EVEN, properly (coordinator / Joe: locks are guides, not root owners; strands.even 1): every strand an
  interpolated child at an even root, the locks marched dense as guides (spacing 4 mm, ~1900 on a long head), no trim. The
  veil, found by evaluating the strands (spikes/hair_garrett/veileval.py: strands crossing a box in front of the face, by
  object and root): (1) children ROOTED ON THE PART fell straight down the forehead: Blender's "Part by Mesh Islands"
  did not keep them to their bank, even with the right island's UVs moved to u + 1 (kept); fixed by one OBJECT per bank
  (hair_even = left, hair_even_r = right: own guides, own density mask hp_density_even_l / _r): 58 -> 47; (2) the rest
  were `part_soft.cross`: guides combed over the part among their neighbours, children averaging both ways: cross 0 ->
  0 strands over the face. No guide ever crossed the face (veilq: 0 locks): it was always the children. Then (3) the
  lengths hung dead straight: lock_guides damps waves on narrow locks as wisps (W = 2.4 x 4 mm: 0.32 x amplitude,
  1.6 x wavelength) and random per-guide phases cancel in the average: in even mode ws = wl = 1 and the phase is a
  smooth field of the root (~3 cm); interpolated children get Blender's Clump Hair Curves (guide distance =
  clump_size). E9: face clean, waves in the lengths, magenta only ON the part line (t60 1.24 %, behind 0.01 %).
  hcover counted by brightness and missed dim magenta under dark hair: by hue now (recounted: r14 8.37 %, E5 4.61 %,
  E9 1.24 % from above). Open: the profile reads as a darker solid mass than E5 (less separation).
- Nearest guide (strands.even_guides, auto 1 at even 1): every split in the comb (part, tuck behind the ear, a curtain's
  edge) makes children that average both sides take the middle path: a tuck put a sparse veil over the cheek.
  One guide (4 mm away at most) never takes a middle path, and keeps each guide's waves (E10: more lock texture
  than E9, face clean, 1.45 % from above = the part line). On a side part: cheek mostly clean, but from above a 3 cm starburst
  of scalp at the front of the part (9 %: the divergent comb with lift 0.001; open). Garrett on the frozen head
  (hg_h6 = gp_h6c) E2: the crown hole is GONE (the whorl was the lock layout), speckles low on the back / nape
  (1.1 %), but darker, less grey and streakier than r14: the even guides lost their grey (eg took `gr` only with a
  "head" group; loose hair has only "free": fixed), Clump and nearest-guide bundles suit long hair more than a crop.
  360k strands for Garrett's magenta render (450k: the job's memory cgroup killed Blender at 5.5 GB).
- Long loose hair after the merge (coordinator: E10 a heavy solid black hood in profile, flat on top). MEASURED first
  (spikes/hair_garrett/profover.py: our outline over the picture through the fitted camera, edge distance from the head
  centre per ray). FIRST READ WAS WRONG: "our face behind the picture's" was the front edge of our HAIR (it hangs down
  over the cheek); drawn with the render's whole silhouette (blue) the head registers on the photo (forehead, nose,
  chin). Read: our side hair falls straight down from the forehead corner over the temple and cheek where the
  picture's sweeps back over the temple to the ear. The "hood" is that, not the top's height. Tuck on both sides
  (E14) only thinned it at the jaw: the temple needs its comb swept back (open). The hood: look dials alone (E11: depth .85, gloss .6, variation .6, highlights .35, clump .75) barely moved
  it; the even children had none of the colour model's per-lock numbers (hp_lv, hp_ch, hp_cb, hp_cm, hp_a1: the lens
  makes them): hp_cells (blender_strands) gives them from the root's jittered cell per scale + the strand's length
  (E13: some lock light behind / 3-4; the profile still one dark mass). Open: separation in the mass (gaps between
  locks, see-through edges), and the profile camera.
- Re-seated on the private subjects' newer heads (coordinator). E15: flow sides [0, .8, -.6] (combed back to the ear),
  lift and body lowered: the profile outline closer on top and at the back. The cheek was still covered:
  the FACE RULE holds hair out of 58 deg either side of the face's centre, which in profile is mid-cheek. `face` now goes
  to 1.6 (1.5 = to the ear, ~87 deg): E16 face 1.5: the cheek clear, our front edge on the picture's from the forehead past the
  temple to behind the jaw. From the front E16 is narrower than the picture's sides (body: next), a few strands stand up
  at the part. Garrett E3 (grey fix): the grey is back; the back reads coarse / streaky ("pine needles", nearest-guide
  bundles + Clump on a crop) with speckles low on the back (~1 %): for a crop the even layer is not yet better than r14.
- Nearest guide only where the comb splits (coordinator): on a crop every child copying one guide made bundles of
  identical strands with gaps ("pine needles", Garrett E2-E3). The even layer is now split per bank into a BLEND object
  (3 guides) and a NEAREST one (`_n`, 1 guide) by a split-zone mask (hair_strands._split_zone): long loose hair
  (> 15 cm) is ALL split zone: blending outside the hairline strip (E17) hung children of a front and a back guide
  across the neck and chest (the shoulders are a split too); a crop blends everywhere except round a tuck. Garrett E4
  (blend): the top and sides a fine combed surface; left: a starburst of scalp at the back above the nape (0.96 %
  behind: guides combed apart there, the whorl hunt) and the nape hairline's speckles. groom.loose.body by region.
- Front width on a private subject: measure the outline through the fitted front camera (profover rays now reach
  +-150 deg, the cheeks) before trusting a sheet's impression of "too narrow": a photo's asymmetry (hair behind one
  shoulder) reads as narrowness. Side body and side lift change the mass inside, not the silhouette (outline
  unchanged to 0.1 mm).
- Garrett on the frozen head (hg_h6 = gp_h6c), the hairline round: the groom's hairline front_points are WORLD heights
  measured on the old head: on gp_h6c ours sat 8-24 mm above his (hlinetrace, forehead corners worst): lowered by ~85 %
  of it (E5: the temple corners filled). The even layer stands lower than lock strands did (the lens spread each lock's
  strands over its thickness): E4 4-6 mm off the skull vs his 11-13: lift up (E5 top -0.3 mm, crown +3, back -2). But
  9 mm of lift on 2 cm back hair stood its ends up as fur with swirls; the reader's "light share" counts lit hair, not
  only grey (setting grey from it made him silver: E5). E6: lift by region (top 10, front 6, sides / back 4, nape 2 mm),
  the grey back to the read regions. STATE: Garrett E6 rendering. NEXT: judge E6 (front edge ridge, back combed),
  then subject A lock separation, subject B on (private model) (part starburst, colour range).
- THE WHORL, FOUND (Garrett's back rosette / bare spot, every round since hair-garrett): the loose march's collider push.
  Over the back of the head the body field's gradient tilts ~10 deg up from the scalp normal; on short hair the march
  steps ~0.5 mm and the push to the clearance outweighed the step (the step's direction is unit(step + push)), so crop
  locks there CLIMBED the scalp: 19 of 66 back-centre locks ended above their roots with the collider, 0 without
  (spikes/hair_garrett/guidefield.py plots the roots' comb from behind, red = upward). Fix (hair_loose.grow): over the
  scalp the clearance is pushed along the scalp's own rays; the collider only where the body intrudes well inside it
  (an ear) or off the scalp (neck, shoulders): 0 of 66 rise. Also: no Blender Clump on short even hair (end-on its tips
  read as starbursts). The scalp layer (hair_under) was not the cause (the rosette stayed without it).
- Render sizes (coordinator / Joe, 2026-10-14: EEVEE renders share the laptop GPU with the compositor): adopted. Checks
  are cropped to the feature (~768 px, the smallest judged thing 3-4 px+), sheets read as crops (< ~1600 px), full
  supersampled multi-view sheets only for gate sheets; coverage-by-hue and profile overlays keep their resolution
  (1024 x ss 2) because their numbers depend on it. All Blender through run.sh (capped: the GPU lock). Note: 360k strands
  with the scalp layer off put 11.5 M points in one object: amdgpu context loss: keep an object under ~6 M points.
- Garrett E8-E10 (frozen head): E8 (collider fix): the rosette gone (magenta behind 1.15 -> 0.01 %), the back a fine combed
  crop; the back's stand-off fell (no climbing locks: -5 mm). E9 longer back + a fade: the crown step stays (the top's
  4 cm ends lie on the back), the nape stays blunt (a fade shortens guides; the even children follow them, the edge
  row still ends level). E10: grey by region x 0.6 (the photo's salt-and-pepper, not silver), top 3.4 / back 2.8 cm (a
  smaller crown step), soft back to 4.5 mm: the best so far (sheet human_renders/hg_garrett_E10_*), told the assembly
  agent (copy groom / strands / look, regrow with groom_hair, front_points z by the head's height). Open: the front edge
  a blunt lip (his thins out), the nape's straight bottom row, sides -6.7 mm.
- Garrett E11: front lift 3 mm, inset 2 mm, soft 6 mm: the front edge a little sparser, still a line. The fade thinned
  only lock strands: the even roots now get it too (hair_strands.scalp_mesh: the even mask x the fade's density ramp
  over the back): E12's nape sparser and ragged at the bottom, a softer taper.
- GATES (docs/notes/gates.md, from main): every round DESCRIBE (workspace/checklists/<piece>.json, git-ignored),
  MEASURE (spikes/hair_garrett/gatetable.py: item | reference | ours | pass from cmp.py, hlinetrace.py, hcover.py),
  LOOK (mksheet.py pairs=<dir>: each region's reference and result crop; /mnt/data/hifipushie/bin/review, blind),
  APPROVE (coordinator / Joe only). Scratch gateround.sh runs a full round. Nothing goes to the coordinator before
  the review PASSES on every region (or STUCK after 3 honest attempts, or a decision of Joe's).
- Gate rounds G1-G9 (Garrett, short crop; per-picture notes private): what generalises:
  - the hairline item measures the VISIBLE boundary, so it moves with the comb (combed forward the line read 8 mm
    lower than combed back): read it with the comb you mean to keep; tolerance 2 mm, plus a brow-relative item;
  - front_points must be ONE smooth curve: a dip left by stacked corrections made the "sharp notched M" every review
    flagged; carry a temple recession on through the temple (to ~70 deg) before the sideburn drops;
  - a whorl small against the region combs makes a SECOND whorl and a seam where the combs part: whorl.core (spiral
    within it, radial beyond, large radius) when the hair grows out of it; small and off-centre for a crop;
  - the face rule must only steer hair that reaches the face (FACE_MIN_LEN 6 cm);
  - hairline.nape_v gives the nape a rounded point; 1.5 cm hung a V 3-4 cm down the spine: keep it small (~4 mm);
  - THE BLIND REVIEW CONTRADICTED ITSELF on comb direction: forward when we combed back, back when we combed
    forward. Settle a contradicted item from the photos themselves, the view that shows it best (direction: the
    three-quarter and profile), and say so with the crops (no overruling by opinion).
  - the even-roots surface Joe liked (G6): colour by region x 0.6, mid-grey grey strands, no Clump; Clump is now on
    for short hair too (the starbursts were the collider), small factor.
STATE: Garrett G10 (G6 + front crest, temple recession carried to 70 deg, whorl off-centre low, gentle nape) running.
NEXT: G10's review; front / three-quarter / top pairs to the coordinator once direction passes; then subject A, subject B.
- spikes/hair_garrett/hcover.py: the MAGENTA check (scalp #ff00ff at full tint; magenta share of the hair region per
  view: t60, y180, y125, v1).
### hair-heads STATE (merge-ready, 2026-10-14)
Regression hg7: all eleven identical. Tests: test_hair_loose 19, test_hair_read 17, test_hair_strands 26, test_toolsets 8.
New words: loose.inset, loose.tuck.from, loose.face per side, strands.wave_from; guards HALO_MAX; reader: scalp_tint 0.15
on grey, a denser short-cut start (spacing 5 mm, width 2.4, body 4 mm, 600k). Checklist: Step 0 (describe first), rule 1
(measure by height in a room), rule 15 (density = lock coverage). Heads: Garrett r12, the private subjects' latest rounds.
NEXT (the coordinator's order): cheek-level width, Garrett's back whorl; a curtain over the cheek and colour range.
RESTART: ./run.sh hround.py hg_g0 hg_<tag> patch=@styles/<tag>.json; ./run.sh hgshots.py hg_<tag> views=v0,v1,v2,y125,y180
stage=hg_r4 size=1024 ss=2; ./runl.sh mksheet.py hg_<tag> prev=hg_<prev>.
### hair-garrett3 (2026-10-14, branch `hair-garrett3` from main e5dcc62; the last round: MERGE-READY, STOPPED)
STATE: `strands.halo_soft` 0..1 (a dense soft halo: x4 halo hairs at 1, their stand-off x 0.35 (~4 mm), length x 0.4;
pair with look.fine_alpha 0.2-0.3; hair_strands.SOFT_HALO); `look.seen` may be [r, g, b] sRGB floats and the reader's
colour step emits them; `look.sun_warm` 0..1 (0 = sun-lightened lengths ASH: lighter, slightly less saturated, no warm
turn). Tests: test_hair_loose 18, test_hair_read 17, test_hair_strands 26. Regression hg5: all eleven identical.
Sheets (REFERENCE | now | previous): human_renders/hg_07_garrett_final.jpg (the private subjects' sheets: private).
FINDINGS: (1) the "render path's hue shift" on near-grey brown was 8-BIT QUANTISATION: at chroma ~5 one hex digit is
5-10 deg of hue, so the Lab step's +6 deg came back as the same hex, and `seen_look` then amplifies the saturation x
1/eevee_sat. With seen as floats one step landed: hue 33.7 -> 40.3 (picture 39.9). (2) halo_soft: the man's crop halo
0.083 vs his 0.071 (matched; a visible soft fuzz on the crown's outline); the two long dark / brown heads did not move
(0.05-0.08 vs 0.22-0.25): faint (alpha 0.3) single halo hairs over dark long hair are not the photos' dense bright
fuzz: the remaining tell, to build as a back-lit / lighter halo (fly_light) or many more fine hairs, not more alpha.
(3) Ash lengths + a few grey strands on a brown head (sun_warm 0, grey_amount 0.04, highlights 0.5): reads ash-brown
with lighter lengths, but overall L* 30.6 vs 23 (too light) and the grey / ribbon strands are distinct white lines:
less of each next time.
### hair-garrett2 (2026-10-14, branch `hair-garrett2` from main 1b2817d): loose-hair words, the nape fade
STATE: groom.loose words `halo` / `flyaway` (loose hair's free locks no longer get the tail's quartered halo, and
LOOSE_HALO 2x), `tuck` (one side behind the found ear), curtain bangs (`fringe.sweep "away"` + `curtain`; the face rule
keeps them to the face's sides), `fade` (the nape shortens and thins over `width`); the reader sets halo / flyaway on
long hair and a fade on a short cut. Tests: test_hair_loose 16 (tuck, curtain, fade, halo factor). Regression hg3 / hg4:
all eleven identical. Sheets (REFERENCE | now | r4): human_renders/hg_06_garrett_now.jpg (+ hg_06_garrett_fade_closeups),
the private subjects' sheets (private).
Measured, ours | picture: wisps / 10 cm 2.5 -> 6.8 | 6.8 and 3.3 -> 7.5 | 16.1; halo density 0.06-0.08 -> 0.073-0.076 |
0.22-0.25: the halo dial now reaches the hair but the measure barely moves: EEVEE's halo hairs are single, half-alpha
(fine_alpha 0.5) and few; the pictures' edge is a dense soft fuzz. The tuck works (the ear shows, the hair passes behind
it). Curtain bangs: the first try hung as a thin veil over the forehead (fringe locks are thin and exempt from the face
rule); now thicker, swept out first, kept to the face's sides. A bug caught by test_loose_hair_falls_and_stays_out:
`~False` on a Python bool is -1, not True (use `not`). The fade softens the nape's ledge but the line is still
horizontal and high, with the scalp layer's dark band under it.
NEXT: a dense soft halo (more, opaque-ish fine hairs at the outline) if the halo measure is to match; the nape hairline's
own height and shape (a fade needs the line lower and tapered at the corners); the front hairline still reads as a wall.
### Two long-haired heads, 4 rounds each (general findings; per-person notes are private)
- The reader on phone pictures in a room: the backdrop must be read LOCALLY (a warm wall, a dark couch, a black
  shirt beside dark hair were counted as hair with one global backdrop colour); hair hanging over the cheeks meets
  skin too and is not a hairline (kept only above the sideburns in front of the ears); a frame that cuts the hair off
  makes its length a LOWER bound (INFERRED; both heads fall 10-15 cm past the shoulders).
- GREY vs LIT by chroma: the light pixels of grey hair are LESS chromatic than the dark ones (0.73 on the man), the lit
  side of brown / black hair MORE (1.4-1.55 on three heads). Without that rule a brown head without grey got grey strands.
  With no grey, `seen` = the lit mode.
- COLOUR STEP for hair without grey must be in Lab (lightness, chroma, a small hue turn) on the MEAN colour: per linear
  channel, the step turned a brown purple and a near-black green (round 2 lost to it): `seen` derives `lit` by
  dividing the saturation by eevee_sat, so a small hue change in `seen` is a big one in the strands. Lit modes are no
  good either when ours has 1 % lit pixels and the picture 30 %. One Lab step: L*/C/h 20.0/16.5/51 -> 26.0/9.5/34 (picture
  23.0/8.2/40) and 5.4/10.8 -> 12.6/4.2 (11.0/4.5).
- Long loose hair from the guide's recipes (long straight; loose waves) with the reader's level / body: the outline
  matched within 1 mm on one head, +6.5 mm at the sides on the other (body 6 mm is the floor).
- MISSING KNOB (rule 4 / 7 for loose hair): `strands.halo` is quartered on free locks and loose locks are free, so
  halo 1.0 + flyaway 0.1 left halo at 0.04-0.08 vs the pictures' 0.22-0.25 and wisps at 2.5-3.3 vs 6.8-16 per 10 cm.
  Loose hair needs its own halo / fly-away words (as tie_hair's `wisps.halo`), and a one-side ear tuck and curtain
  bangs from a centre part (neither is a groom.loose word yet).
- GPU: one 3072 px supersampled EEVEE render of long hair lost the amdgpu context ("hard recovery"); these renders
  stay at 2048 px (1024 x2).
- Short cuts: the STRAND groom owns the shape and the look (it is what the reader and the sheets judge); the game
  export of a short cut stays the guide's baked cap + sparse cards, baked FROM the strands (export_hair's SHORT_TIERS):
  one source of truth, the cap / cards are its LOD, not a second groom.

## Guide rewrite (2026-10-14, "guides" agent): what left the hair guides

hair_guide.md 678 -> 131 lines: describe-the-hairstyle-first (9 items incl. coverage), stages with gates, the two
principles, craft rules, self-review loop, common mistakes, limits. Details moved to hair_checklist (15 rules +
strand dials), hair_tied, hair_loose, hair_short, hair_colour, hair_export, hair_tools (tool sections; test_toolsets
now checks groom_hair there). hair_locks_guide 413 -> 273 (describe-first and self-review added at the top; hairline
/ fins / hand-shaping / material / cards detail -> hair_locks_detail; the card-makers' method -> hair_background).
Provenance removed from the product (kept here): the two principles are Joe's (hair-heads); step 0 is from Joe on
three heads ("a completely different hairstyle"); the checklist is tesshair7's from seven rounds of Tess's ponytail;
the studio measures named in it: spikes/hair_garrett/hcover.py (MAGENTA coverage gate: no head ships with magenta off
the part line from above, t60; ~1.2 % for a clean part on a long head; nothing from behind), spikes/tesshair7/
standoff.py, spikes/hair_garrett/widths.py, flowlines.py, lockplot.py, hgshots ss=2, shots7.py drop= / S= / LS= /
look=@file, the regression sheet (run.sh regress.py run / sheet / accept, accepted.json: Tess's best + ten riffs,
MOVED over 0.3 mean difference), spikes/tesshair5/cyccal.py. Tess numbers (L_sd 7.5, strand_sd 4.2, ribbon_sd 3.0,
chroma 8-9 hue ~69, eevee_sat 0.38, gloss 0.6, tail.wave 0.35, cycles_width 1.8 / cycles_sat 0.65, sun_length 0.06,
tip_alpha / backscatter / scatter 0.5 / 0.6 / 0.8, eevee 0.3 / 1.4, stand-off 17-19 / 17-24 / 30+ mm) are now "e.g."
values; one head's saturation note (~1.25x) kept anonymous; hair-garrett r4 strand_sd 9.3 vs 6.8; hair-heads r11 density;
round four's shaved temple; tesshair6's ear from the brow; th_30's 2-bounce Cycles sheets. The golfer's locks numbers
(face-only camera 10 mm off, IoU 0.60 -> 0.73 with an ear point; crest 0.025; parting.full 12 mm; 10-14 mm too tall;
hair_t13 47 locks back bare 0.07; workspace/hair_r3 hr01-hr04; hierarchy 0.8/0.2/0 -> 0.64/0.27/0.09) are generic now.

## hair-cards (2026-10-14, "hair-cards" agent, branch `worktree-agent-a54a66de6d6970c0b` = main + the assembly branch)
Goal: Tess's approved strand groom th_W18 re-seated on her approved head tp_h3, then game cards that look as good.
Scratch DURABLE /mnt/data/hifipushie/haircards/: env.sh, run.sh <gb> <script> (heavy: capped + resources.heavy),
runl.sh (light slot), tests.sh, mk_reseat.py (tie_hair carry_from: the REGROW), mk_seat.py (hair.reseat: lock for lock),
shots_hc.py (shots7 + an id pass = exact hair masks; `like=th_W18` = W18's cameras moved and scaled with the head),
measure_hc.py (IoU / area / tail / wisps / ear cover / colour vs W18), probe.py, wisps.py, ears.py, mont.py, crops.py +
rv.sh (review crops / bin/review), seat_round.sh <model> (build, render, measure, montage). Checklist
workspace/checklists/tess_hair_reseat.json (copy in scratch checklists/).

### Re-seat: why the regrow failed, and the fix
- tp_h3's scalp is 81.5 mm median radius vs tess_a1's 71.0 (x1.149), and its face is bigger still for its skull
  (chin-nose 80 vs 66 mm). tie_hair(carry_from th_W18) REGROWS from the words: (1) fit_to_head scaled the tail length
  but not the tie's other absolute metres (dome stand-off, wisp lengths, strays, sway: hair_flow.style writes them),
  so the tail grew 15 % and the wisps didn't; (2) a new head re-rolls which wisp / curl gets which length (W18's long
  face-framing wisps came out short); (3) tp_h3's own fitted cameras frame the face smaller for its skull, so
  picture-space pairs mixed head shape into the hair (the assembly review's "longer tail").
- `_TIE_KEYS` + `fit.abs_r` (carry stamps the head the tie metres were grown at): those keys now scale too; a groom on
  its own head is unchanged (test_carried_tie_scales_its_absolute_metres).
- `hair.seat_locks` / `hair.reseat` / tie_hair(carry_from, reseat=True): the GROWN locks lock for lock. Near the scalp
  a point keeps (az, el) and h x k; > 9 cm off (a hanging tail) it moves rigidly with the head, scaled about its centre;
  widths / strand metre dials x k. `_ear_warp`: elevations near the ears remapped so hair over A's ear top passes over
  B's (tp_h3's ear top is 0.15 R higher: without it the hair lifted into a LEDGE at both temples, hc_s1).
- Numbers (measure_hc, W18 | ours, cameras moved with the head): regrow hc_r1 IoU 0.79 / 0.78 / 0.82 / 0.85
  (front / 3q / profile / back), wisps 680 | 571 px; reseat hc_s2 IoU 0.86 / 0.89 / 0.93 / 0.94, area 0.94-0.99,
  tail tip 830 | 828 (profile), 810 | 808 (back), tail width 287 | 276, 295 | 296, 308 | 309, wisps 680 | 669, 764 | 727,
  ear cover 0.455 | 0.45, 0.178 | 0.178, front colour L* 29.0 | 28.9, chroma 12.3 | 12.5, hue 63.6 | 64.4.
- REVIEW reseat_r1 (/mnt/data/hifipushie/haircards/review/reseat_r1): PASS, no in-stage MAJOR. MINORs: the hair edge
  above the ear sits a little higher (more helix shows in 3q), front wisps hang in front of the ear rather than
  across it. OTHER STAGES (not hair): face / skin / neck seam / bust cut (the ga_tess stage's draft skin).
STATE: re-seat hc_s2 PASSES review; sent to the coordinator for approval. NEXT: the cards on the approved re-seat.

## Handover 2026-10-14 ~18:00 (hair-cards agent; stopped by the coordinator for context size)
Branch `worktree-agent-a54a66de6d6970c0b` (worktree .claude/worktrees/agent-a54a66de6d6970c0b) = main 76b6292 (budgets) +
the assembly branch (worktree-agent-ad0815704f43e0e00: blender_game, shading, lods, the card-cut fixes) + this work.
Commits: d3f6066 (re-seat), 1f2e17b (cards WIP), + the handover commit (pooled single hairs: UNTESTED, compiles).
APPROVED: hair/tess_reseat = hc_s2 (coordinator, from review/reseat_r1 sheet_views.png).

### Re-seat (done): see "## hair-cards" above. hair.reseat / tie_hair(carry_from, reseat=True) = W18's grown locks lock
for lock (scaled by the scalp radius ratio 1.149, far points rigid, `_ear_warp`), fit.abs_r for tie metres. Compare
heads through the ORIGINAL's cameras moved with the head (`like=th_W18`), never the new head's own fitted cameras.

### Scratch /mnt/data/hifipushie/haircards (all through capped / slots; env.sh = this worktree's code + main workspace)
- run.sh <gb> <script> (heavy: resources.heavy + capped), runl.sh <script> (light slot), tests.sh <pytest args>.
- mk_seat.py <dst> (head tp_h3 + reseat th_W18), mk_reseat.py (the old REGROW, for comparison), seat_round.sh <m>.
- hx.py <model> <out dir> [tiers=hero] [tt={"hero": n}]: export_hair without the check; prints the budget report
  incl. `by_class` (face / hanging / head / single x layer: cards + triangles cut vs kept) and the fixed parts.
- shots_hc.py (local, a Blender start per view; 768 px 8 samples now) and spikes/haircards/shots.py (IN THE REPO: all
  views in ONE Blender start via per-view light rigs; strands, or glb= cards drawn by blender_cards.game_material;
  `like=`, `only=` triangle ranges to isolate cap / layer0 / layer1). Both write s_<m><tag>_<v>.png + id_ (hair masks).
- card_round.sh <exp> <tier> [params] [views]: render a tier GLB + measure vs the strands (tiles hc_s2L) + montage.
- measure_hc.py <A> <B> tagA= tagB= [cams=th_W18]: IoU (closed masks) / area / bottom (tail tip) / lower width /
  face-wisp reach / ear cover / front colour (L*, chroma, hue). mont.py: A / B / mask-diff rows (for MY look only).
- glbprobe.py <m> <glb> <report> <tier>: each layer's height off the scalp by region vs the locks.
- colprobe.py <glb> <basecolor>: COLOR_0 and atlas colour stats. layers.sh: render layer ranges alone.
- crops.py + rv.sh: the review's region crops + bin/review. offload.sh <job> <renders.json> <exp dirs>: pack hc_s2 +
  th_W18 + GLBs, spikes/offload/remote.sh -> spikes/haircards/job_cards.py on NICO-TOP, tiles back into out/.
- IN FLIGHT at handover: offload job `e3a` (remote/r_e3.json: strands hc_s2 tag R + e3 hero cards tag _e3heroR, 1024 px
  / 24 samples on stage hc_s2). Results: remote/results/hc-e3a/e3a/ (out.tar, log.txt). First use of the route by this
  agent: check log.txt before trusting it.

### GPU rule (coordinator, 2026-10-14): the laptop GPU was reset 3x by heavy Blender hair renders. Locally: fewest
strands that still judge, ~768 px, low samples, log frame wall time (> ~5 s a frame is a risk). Heavy renders (full
grooms, card GLBs with alpha, gate sheets) go to NICO-TOP via spikes/offload/remote.sh (COMMIT first: the repo travels
at HEAD; batch views per Blender start: shader compile 50-90 s).

### Cards: state (hero only measured; budgets.json hero hair_cards = 25k / 12.5k / 8.25k / 2.5k for hero/main/npc/far)
- CARD_TIERS' triangles now come from budgets (hair.tier_triangles; hair.export.role / tier_triangles override).
- e0 (as inherited) -> e1 (cap under cards) -> e3 (all fixes below), hero vs the strands (measure_hc, 768 px): IoU
  front / 3q / profile / back 0.69 / 0.71 / 0.73 / 0.76 -> 0.74 / 0.78 / 0.78 / 0.79; tail tip (profile) strands 828
  | cards 779 -> 815 px; tail lower width 296 | 221 -> 194 (narrow); front L* 26.7 | 13 (CARDS FAR TOO DARK).
- Where e3 hero's 25k go (hx by_class): cap 3.1k + core 0.55k + tie 0.13k; head L0 398 cards 12.5k; hanging L0 4.9k
  (+1.2k L1); face L0+L1 2.6k; head L1/L2 (24k) and singles (7.5k) all CUT. The cut coarsens to group 'lock' (24 mm
  cards) at 25k: the 'sub' cut's coverage layer alone is over 45 % of the tier. Keeping everything at the 'lock' cut
  is ~70k. THE TRIANGLE CURVE IS NOT MEASURED YET (hx.py tt= at 25 / 40 / 60 / 80k + review each).
- Open MAJORs by my own look (no blind review run on cards yet): far too dark; tail narrower / shorter than the strands;
  forehead hairline a hard dark notched edge (strands: soft, light); face wisps faint; one-layer head reads flat (no L1
  at 25k); halo absent (pooled singles just written, untested); e1 had plank cards standing up at the part (fine part
  rows -> sparse tile in e3: not yet looked at).
- Why hair3 v8 was good: its groom (hs_tess) had ~100 broad locks: the 'sub' cut fit 40k with 2-3 layers. W18 has 950
  locks (325 gather rows in volume layers, 420 halo hairs, 72 baby, 59 strays, 20 curls, 14 wisps): cut per lock it
  explodes (7k cards / 243k triangles), the budget drops layers and whole classes, and the coarsened 'lock' cut gives
  one narrow card per thin lock. Three faults independent of the groom, fixed: (1) the cap = the groom's ENVELOPE stood
  25 mm off the top where the cards lie at 17: the lighter "helmet" with a seam (hair.cap_under_cards); (2) face wisps
  are free locks, never `at_hairline`, so ranked as single hairs and cut first (lock["face"], PRIO_FACE); (3) fly-tile
  hairs 0.12 mm wide on a 5 mm wisp card fell under the alpha cutoff (FLY_HAIR 0.07 of the tile's width).
- Colour: atlas covered texels linear ~0.14 (lifted by hair_colour.peak 2.55), COLOR_0 mean 0.64: albedo ~0.09; the
  strands render ~2.5x the luminance under the same light. The shading notes' aux-shade formula (shading.py, the
  assembly's) DOUBLE-applies root / depth / strand value already in the atlas: blender_cards defaults aux_shade 0;
  fix shading.py's formula to match, then calibrate a card gain (look.card_gain, in the atlas) by the measured
  luminance ratio and write it + the backscatter / translucency term into <asset>_shading.json/.md.

### Tried / dead ends
- tie_hair(carry_from) regrow on tp_h3: re-rolls wisps, IoU 0.78-0.85 (reseat 0.86-0.94). Without the ear warp: a ledge
  at both temples. Comparing through tp_h3's own fitted cameras: misleading (head proportions differ).
- export_hair(check=True) needs the model's scene.blend (hc_s2 has none): use hx.py + shots instead.

### NEXT (in order)
1. Read the e3a offload result; if the route works, all card renders go there (remote/r_*.json, several per job).
2. Colour: fix shading.py's hair_cards formula (no aux shade on top of the atlas), measure the strand / card luminance
   ratio in the common mask, set the card gain (and backscatter) so front L* / chroma match within 1.5.
3. Tail width / length: why the hanging cards are narrower (hw clip 0.9 x card_width, end_share); compare the tail's
   strand spread per station with the cards'. Hairline: the cap edge / hairline tile at the forehead.
4. Test pooled_singles (halo as ~50 fly cards); tests for cap_under_cards, face priority, pooled singles,
   tier_triangles (card tests live in tests/test_hair_strands.py).
5. Triangle curve: hero at 25k / 40k / 60k / 80k (hx.py tt=), each rendered and blind-reviewed (crops.py + rv.sh,
   --stage "game hair cards: silhouette, coverage, flow, separation, colour, card artefacts" --not "head shape; skin;
   garments"); report to the coordinator the triangles the approved look needs per tier vs 25k (Joe's decision).
6. Then main / npc / far, the checklist workspace/checklists/tess_hair_cards.json (NOT written yet), the shading notes'
   game terms (root-to-tip, per-strand tint, th_63 colour), docs.

## hair-cards round 2 (2026-10-14 evening, restarted agent)
- Offload: e3a never ran: remote.sh asked 16 GB, NICO-TOP's slot is 14.1 GB (offload.sh now RAM=10 CPUS=6). The route
  works (e4a: strands 4 views 82 s, cards 61 s at 1024 / 24 samples; shader compile ~53 s of it). Jobs queue behind
  other agents' (GPU one at a time): 10-40 min waits. Light local checks (768 px / 8 samples, one view, frames 1.5-6.5 s)
  through capped WITHOUT the heavy slot (shots.py via capped directly) while a round is queued.
- Cherry-picked 13e1d85 (assembly: albedo terms applied once; params.albedo_terms in the shading notes).
- COLOUR: front L* (1024 / 24 samples) strands 31.4 | cards gain 1: 15.2, gain 3: 35.0 -> look.card_gain 2.55
  (interpolated in log luminance; chroma / hue already match: 11.9 / 64 deg). Passed via hx.py look= (not yet in
  hc_s2's spec: it is the approved model; decide where the card gain lives: export setting vs look).
- Pooled halo (33 cards / 400 tris): ranked PRIO_HALO 0.35 (kept at 25k); narrowed to 2.4-4 mm (at 10 mm the fly tile's
  hairs were 0.7 mm: brown leaves).
- Blind review c1 (e4g, gain 3): FAIL. MAJORs: crown crest of upright planks; tail patchwork of light / dark blocks;
  tail too light; black blob at the tie; pale stripe down the centre back; temples' hard blunt edge; face wisps missing.
  * crest = the CAP (layer isolation, s_hc_s2_e5Lcap_v0): vertices with no card CENTRE LINE within CAP_REACH (4 deg)
    kept the groom's envelope (the halo's height). cap_under_cards now uses the cards' whole surface (centre +- hw
    edges), CAP_FAR 12 deg for orphans, and no vertex above its neighbours' mean + 1 mm. Crest gone (e6 cap render).
  * patchwork = per-card highlights on 24-48 mm cards (a ribbon is a few mm): no highlight on cards wider than
    HIGHLIGHT_W 8 mm.
  * tie blob = the gather cards ran out to 15 % width at the tie and showed the band (strands hide it): to 50 %.
  * face wisps: Tess's face-framing locks are tk* (9-16 hairs, 12-19 cm) + tw*; on the fly tile at <= 7 mm they were
    grey wires. Now: 8+ hairs = a bundle: first card on the sparse tile, up to 10 mm, its 3 cards spread 1.3 sx apart,
    all three kept (prio 0.3 per layer); fly_light applied to fly / wisp / pooled cards (strands do it, cards did not).
  * tried and reverted: turning cards to the strands' principal spread (PCA): cards stood out 10 cm at the sides.
    Card frames now carried by a rotation-minimising transport where "outward" is unsure (no visible change at 25k).
- Round 3 (e7/e8, review c2/c3, 2026-10-15): tie black hole FIXED (band tile in the hair's median colour x 0.8 unless
  look.card_band; the strands hide their band). Crown "tuft" = halo single hairs (th, 1-2 hairs) flagged face-framing
  (rooted at the hairline near the part) -> 2-3 wisp cards each: face now needs hairs not in (1, 2) (tuft 32 -> 21 mm).
  "Silver-grey strips" at the temples / grey wisps = atlas highlight strands on the 14-hair fly tile (2 lit hairs = a
  pale card): no atlas highlights on fly / baby tiles. Pale strips across the sweep = fly_light on every fly card:
  only face-framing bundles now. Dark wire rim = 'fine' gather rows on the sparse tile at the outline (rimk.py): lifted
  by half the fly_light (untested in review). A facing-weighted translucent rim term in blender_cards DARKENED the
  hair (reverted). Highlights now ribbons in the atlas (22 % x highlights of dense / medium / sparse strands).
- Coverage is NOT the budget: area ratio (cards / strands mask) 0.74-0.80 at 25k, 0.77-0.81 at 40k, 0.82-0.85 at 60k,
  0.79-0.85 at 80k (e7 code); the tail tip ~30 px short and the lower tail width 0.75-0.87 at every budget. Tail locks
  (39 tt, 33-42 mm) all have full-length L0 cards whose widths sum to 1.5-2x the lock width (ttprobe.py), yet the
  strands' tail has a right-hand lobe and S-waves the cards lack. Open.
- card_gain: 2.55 gave front L* 29.6-30.2 once the per-card highlights went (target 31.4): 2.7 from e9.
- Probes in /mnt/data/hifipushie/haircards: planks.py / card1.py / part.py (card geometry vs lock spines: spines are not
  the strands' top, misleading), tuft.py (cards standing off the scalp near the part), rimk.py (who makes the outline),
  ttprobe.py (tail locks' cards), tailL.py (L* by region), wisp2.py / tailk.py (lock classes). HP_CARDS_DUMP=<pkl>
  on hx.py dumps the kept cards.

## Handover 2026-10-15 (hair-cards agent, round 4; stopped for context size)
Branch worktree-agent-a54a66de6d6970c0b at this commit. Scratch /mnt/data/hifipushie/haircards (see the 10-14 handover
for the scripts; new: probes listed in "round 3", tailL.py, review/c1..c4_*). Offload: `./offload.sh <job>
remote/r_<x>.json <exp dirs>` (commit first; RAM=10 CPUS=6 default now); several renders per job; queue waits vary
(minutes to an hour when NICO-TOP is busy). Light local checks: shots.py through capped directly (768 px / 8 samples,
one or two views, frames 1-6 s).
- Current best: e9 (hero 25k, card_gain 2.7 via hx.py look=; NOT yet written into a spec / export setting).
  Measures vs strands (1024 / 24 samples): front L* 30.9 | 31.4, chroma 11.3 | 12.0 (COLOUR PASSES);
  IoU v0/v1/v2/backl 0.74 / 0.80 / 0.81 / 0.81; area 0.75-0.83; tail tip 25-35 px short; lower tail width 0.76-0.83.
- TRIANGLE CURVE (e9 code, reviewed blind, review/c4_e9*): MAJORs 25k 27 | 40k 28 | 60k 26 | 80k 25, all FAIL; IoU
  front 0.74 / 0.76 / 0.80 / 0.76, back 0.81 / 0.83 / 0.85 / 0.86. THE LOOK IS NOT BOUGHT WITH TRIANGLES: the faults
  are the same at every budget (structural). Evidence for Joe: more than 25k does not fix this groom's cards; the
  cut (one card per 38 mm lock / pair) loses the strands' waves and volume.
- Open MAJORs (every round, c2-c4), worst first:
  1. TAIL: a straight flat sheet, no S-wave clumps, narrow, ends cut straight (brush), zig-zag texture in the lower
     tail, a dark flat polygon where it turns down from the tie. Tried: hanging cards 3.2 sigma wide / FREE_END 0.06
     (little change), no per-card highlights (patchwork gone). Idea: cut the tail per SUB clump (or by the strands'
     own wave phase) even at 25k, paid by dropping head L0 overlap; ragged ends: vary u1 per card / extend cards by the
     tile's tip fade; zig-zag = check the dense tile at the tail's stretch (UV v scale) / normal map.
  2. CROWN FLYAWAYS: halo as cards (pooled, 2.4-4 mm) read as thick dark kinked ribbons; tried: cap crest fix, face
     flag excludes 1-2 hair locks, narrower pooled cards. Next: drop the halo cards above the crown at hero (a MINOR
     "no flyaways" beats a MAJOR), or a lighter, finer fly tile.
  3. FACE WISPS: still faint / grey straight ribbons (bundle = sparse tile, fly_light). Strands' are thick light-blonde
     wavy locks to the jaw: cut them per sub clump with the medium tile, warm tint (sun_warm) not just lighter.
  4. DARK RIM at the outline (fine gather rows on the sparse tile): half fly_light did not fix it; try the medium tile
     for fine rows or wrapped diffuse in the notes' shader; NOT a translucent mix (darkened, reverted).
  5. PART: light criss-cross of card roots at the part, skin notch; 6. centre-back seam strip (a gather card or cap
     chart showing between L0 cards).
- Not yet done: tests for cap_under_cards / face priority / pooled singles / tier_triangles; checklist
  workspace/checklists/tess_hair_cards.json IS written (DESCRIBE done); main / npc / far tiers.

## hair-cards: top/part research (2026-10-15, hair-cards agent; Joe: "a different strategy for the top of the head/part area")
What shipped pipelines and card artists do (sources below; marked where nothing was found):
- Layers from the scalp out: a CAP under the cards ("some sort of cap under ur cards ... separate geo or painted straight
  onto the head", Polycount), then a CORE / coverage layer of wide, mostly opaque cards that "should not intersect the scalp"
  (Epic's Hair Card Generator tutorial: coverage 50 clumps / 2k tris / 25 textures, shared heavily; mid 200 / 7.5k / 60;
  top 500 / 25k / 60; flyaways one card per strand, 371; short hairs 500 / 10k / 75), then mid, top, flyaways. Cards get
  narrower and sparser outward (80.lv "Creating hair for real-time game characters"). Triangles and texture detail go to
  the VISIBLE layers; coverage repeats few textures.
- Cards are cut from strand CLUMPS ("strands that converge, creating a distinct volume"), each clump optionally three cards
  for volume; textures are the clump's strands projected onto the card (Epic: Depth, Coverage, Tangent, Attributes);
  "Num Textures" < cards: islands are shared; "Texture Compression" squeezes along the strand direction.
- The cap / helmet: Unreal projects a groom's strands onto any mesh's UVs ("Trace Type" inside for hair, "Trace
  Distance") into the same maps, "for grooms made of cards and ... hair helmets" (Generating Groom Textures). FiberBake
  (Blender) bakes colour / opacity / root-tip / flow / depth / ID per card and paints card layers onto a head. So the
  part and root density live in the CAP's baked picture, not in card geometry.
- Part line: NO primary source found on part handling. Practice (forum / general): the part sits where the comb changes
  direction; cards are placed per side, combed away from it, with finer shorter cards over the seam; the scalp shows
  only as the cap's own picture there. (Unsourced: treat as craft knowledge, check against the reference.)
- Root zone alpha: alpha-to-coverage = a multi-sampled alpha test (~9 levels at MSAA, "softer result", Polycount);
  dithered alpha + TAA (screen-door) used by shipped games for most hair (a GDC/SIGGRAPH write-up on gcores), with ghosting
  on fast motion. Both are ENGINE settings; we author soft alpha (roots faded in, edges faded) that survives them.
- Shells / parallax on the cap: no source found for head hair (fur shells are a fur technique); not chosen.
- Naughty Dog: no part-specific talk found ("tons of cards, tons of time, manually place cards", Polycount on their
  workshop). Frostbite / EA: strand rendering, not cards. MetaHuman: strands at LOD0-1, cards from LOD2 (or "Use Cards").
Sources: https://dev.epicgames.com/documentation/unreal-engine/creating-hair-cards-and-lods-using-hair-card-generator ,
https://dev.epicgames.com/documentation/unreal-engine/hair-card-generator-for-grooms-in-unreal-engine ,
https://dev.epicgames.com/documentation/unreal-engine/generating-groom-textures-in-unreal-engine ,
https://80.lv/articles/creating-hair-for-real-time-game-characters/ , https://polycount.com/discussion/comment/2609200 ,
https://polycount.com/discussion/comment/2500017 , https://www.gcores.com/articles/180107 ,
https://superhivemarket.com/products/fiberbake-hair-cards ,
https://dev.epicgames.com/documentation/metahuman/controlling-metahuman-levels-of-detail-lods .
CHOSEN for Tess's part and crown: (1) the cap wears the strands BAKED onto it (part gap, root density, flow) in a chart
without a pole at the crown; (2) top cards are clumps cut PER SIDE of the part (no card spans it), their roots start
3-4 mm off the part line, faded in, lying flat along the comb; (3) the crown's halo becomes a few single-strand flyaway
cards (Epic's one card per strand) with soft sparse alpha, only where they break the silhouette.

## hair-cards: clump cards baked from strands (2026-10-15, hair-cards agent, round 5: the change of approach)
Why: one card per 38 mm lock lost the waves and volume at every budget (25-80k all FAIL). Now (hair_clumps.py, tier
"cut": "clumps", hero default): as Epic's Hair Card Generator / FiberBake do (sources in "top/part research" above).
- CUT: the groom's lock strands (not the scalp layer) per class: head (lying / gathered), tail (hanging), face (each
  face-framing lock its own clump), single (halo, strays, baby: flyaways). Per class and layer (coverage / mid / top)
  k-means on positions at 6 fractions of length + length, K from the triangle budget (LAYERS shares x 0.8 budget /
  triangles per card). Head strands rooted within PART_SPLIT 4 cm of the part are clustered PER SIDE (a hard split: a
  soft side key in the features still mixed them; test_no_card_spans_the_part). Flyaways: one card per single strand
  (FLY_TRIS share), the furthest off the mass but under FLY_FAR 2 cm (spikes otherwise).
- FIT: along a REFERENCE strand (the clump's ~longest; along_reference maps every strand point to its nearest
  reference station). Averaged at the same distance from each root, the clump's centre started mid-way between its
  roots: the front of the head bare (b1 top view). Width = 90th percentile spread (97th for the tail), capped per layer.
- BAKE: each kept card's strands projected into its own frame (across, along, depth over the plane), PIL-drawn at 2x
  into its island: alpha, id, depth, root-to-tip, flow, TONE (hair_colour.strand_tone per strand from root cells, as
  blender_strands' cells; / peak, normalised by its mean in the atlas: at tone x peak the 8-bit atlas clipped and the
  hair went grey-white, b3). Islands shelf-packed into a 2048 x 1024 block UNDER the tiles + cap chart (atlas 2048^2),
  texel ~0.57 mm across, x3 along (Epic's "texture compression" along the strand). Coverage cards get an opaque core
  (blurred coverage) that stops before the tips; every picture fades in over 4 mm at the root and out at the sides
  (>= 1.5 texels). Non-baked meshes' v remapped to the top rows (hc.remap_v).
- FOUND on the way: the cap / tail core / tie wore vertex colour 0.8-1.0 while cards carry tone / peak (~0.5): wherever
  the cap showed it was twice as light (the pale crown patch in b1; likely the old "lighter helmet" and the pale
  centre-back stripe). Now / peak.
- Card gain: hair.export.card_gain (export setting, read by cards_job over look.card_gain): 1.8 on hc_s2 (local 768 px
  measure: front L* 33.4 -> target 27.2 at gain 2.7 with baked tone). Re-check on the offload renders.
- Numbers (local, v0 / v2): b4 IoU 0.748 / 0.803, tail lower width 232 | 296 px, tail tip 798 | 828, top 141 | 115 px.

## Handover 2026-10-15 late (hair-cards agent, clump cards; stopped at the 100-tool-call rule)
Branch worktree-agent-a54a66de6d6970c0b (main merged at the start of this round). Code: src/hifipushie/hair_clumps.py
(new), hair_cards.py (atlas bake block, remap_v, island uvs, tone_k), hair.py (cards_job "cut": "clumps" for hero,
part_side_of, export.card_gain, cap / core / tie colour / peak, bake after the budget fit), tests/test_hair_clumps.py (8).
Scratch /mnt/data/hifipushie/haircards/bake/: dumpin.py (pickles clump_cards' inputs: in_hero.pkl, for fast offline
iteration), cut0.py / bake0.py / topv.py (top view of kept cards by layer) / proud.py (cards over the strands' envelope) /
nchk.py / tonechk*.py, setgain.py (hc_s2 hair.export.card_gain: now 2.85, from the b5 OFFLOAD measure; local 768 px
renders read lighter than offload ones, never calibrate locally).
- Reviews (offload 1024 / 24, blind): c5_b5 27 MAJORs, c6_b8 27 MAJORs, both FAIL. Fixed since c6 but NOT yet
  reviewed: crown crest (head cards stood 6-8 mm over the strands near the part -> envelope clamp; crown halo flyaways
  dropped), flat light colour (baked tone now has the strands' depth in the mass, strand_shade), tail as one sheet
  (tail clumps within their locks), dark stair-step bars across the flow (ANISO 3 -> 2, coverage islands at 0.55
  density). b11 (all of these) was exporting + queued for offload when I stopped: out/off_b11.txt; renders land as
  out/s_hc_s2_b11R_*; then: measure_hc (tagA=R tagB=_b11R), crops.py review/c7_b11 ... + rv.sh (absolute paths: runl.sh
  cds into the worktree). NICO-TOP queue waits were 40-90 min today; offload.sh's outer timeout killed b9 in the queue.
- Still open from c6 (worst first): tail S-wave clumps / dark gaps and its ragged blocky end; the part read (a soft V of
  skin instead of a crisp dark line: the cap chart's part is what should show; check the cap under the part cards);
  face wisps too wide / too many / pale flat (now 4 hairs a card, 3.5 mm: unreviewed); nape under the tail a dark hard
  slab (coverage core now starts 12 mm from the root: unreviewed); temple fragments / black specks (texels with id/depth
  padding at low alpha: look at EDGE padding in bake); colour vs reference (2.85 gain + shade: measure).
- Local look at b10 (before ANISO 2): tail shows lock waves now but the texture swirls (strands of a lock crossing in the
  card frame); side of head reads as brush strokes. The approach is not yet near a pass; the same MAJORs (crown, part,
  wisps, tail, colour) have had 1-2 honest attempts each under the new cut, not 3.
- Joe approved head/tess = tp_k19: keep developing on hc_s2 / tp_h3; when near a pass, `mk_seat.py <dst> head=tp_k19`
  (src hc_s2 or th_W18) and do the final reviews there.
STATE: clump cards + strand bake implemented and tested; 2 blind reviews FAIL; b11 queued. NEXT: review b11 (c7), fix the
worst MAJOR, loop; then re-seat on tp_k19.

## Handover 2026-10-14 17:40 (hair-garrett agent -> successor)
Branch `hair-heads2`, worktree /home/joe/dev/hifipushie/.claude/worktrees/agent-a9414ffa57394154a (main merged in at
f630998; last commit: see `git log -1`). Repo rule: stage by path, never `git add -A`; nothing of Garrett's photos or
the family in git (Garrett per-picture notes: /mnt/data/hifipushie/hair_garrett/notes_private.md; family:
workspace/private_notes/). No jobs in flight.

### Process (docs/notes/gates.md): describe -> measure -> blind LOOK review -> approve (coordinator / Joe only)
- Checklists (git-ignored): workspace/checklists/garrett_hair.json (19 items), and the private subjects' (git-ignored).
- Groom only on approved heads: Garrett = gp_h6c (copy hg_h6, stage hg_h6). the private subjects' heads (private notes): not yet approved, check `bin/approve get head <name>`.
- Nothing to the coordinator until the review PASSES every region, except Joe's decisions or STUCK (3 honest
  attempts). Send front / three-quarter / top pairs as soon as DIRECTION passes (coordinator's ask).
- Review scope flags: --stage "hair: hairline, part, comb direction, volume and stand-off, lengths, separation,
  colour, coverage" --not "head shape and proportions; skin". Out-of-stage faults: one short list to the coordinator.

### GPU rules (2026-10-14: hair frames wedged Joe's laptop iGPU for everyone)
- A heavy EEVEE strand frame (~6.6 M curve points: 360k strands even layer + scalp layer) runs past the driver timeout
  ("ring gfx timeout ... device wedged"). Never retry into resets: stop and tell the coordinator.
- Laptop: LIGHT checks only (checkround.sh: half count 180k, 768 px, ss 1, 12 samples; wall time per frame printed).
  Light renders draw strands as thick speckled ribbons: the reviewer then calls texture / colour wrong (G10) and the
  colour items fail to measure: judge DIRECTION and SHAPE from them, never texture or colour.
- Full-count gate renders: NICO-TOP (RTX 3070 Ti) via spikes/offload/remote.sh (main). COMMIT FIRST (the env is the
  repo at HEAD). New runner spikes/offload/job_hairshots.py (committed, NOT yet run): job folder = ws/<model>/ +
  ws/<stage>/ (spikes/tour/pack_model.py <model> <job> for each: spec + refs; the projected skin is stripped by
  hgshots, so its images need not travel), model.txt, stage.txt, args.txt (one hgshots run per line, e.g.
  `views=v0,v1,v2,y125,y180 size=1024 ss=2` and `views=t60,y180,y125,v1 size=1024 ss=2 tag=_mag look={"scalp":
  "#ff00ff", "scalp_tint": 1.0}`). Call: `spikes/offload/remote.sh spikes/offload/job_hairshots.py tiles.tar,log.txt
  16 8 gpu <job dir>`; untar tiles into $TOUT, then gatetable / mksheet pairs / review locally. Untested: if the
  stage sync or strand eval fails there, read log.txt.
- Every local Blender through run.sh (bin/capped + the GPU lock); light jobs runl.sh (bin/slot).

### Tools
Scratch /mnt/data/hifipushie/hair_garrett/ (env.sh sets W = this worktree, HIFIPUSHIE_HOME = main workspace,
PYTHONPATH spikes): run.sh <script> (heavy), runl.sh <script> (light; looks in spikes/hair_garrett, tesshair7 ...),
styles/*.json (Garrett g_G1..g_G11, the private subjects'), out/ (Garrett tiles, tables, reviews), fam/ (family).
- gateround.sh <h> <tag> <style> <stage> <src head> <checklist> [prev]: FULL round (groom, renders 1024 ss2 + magenta,
  table, pairs, review). Too heavy for the laptop now: use for remote-rendered tiles only (skip its render steps).
- checkround.sh <same, count>: LIGHT round (see GPU rules).
- evround.sh: groom + 5 views + coverage (old, heavy). hround.py <src head> <new> patch=@<style.json> (ABSOLUTE path):
  copy head + the reader's start + patch through server.groom_hair.
spikes/hair_garrett (in git):
- hgshots.py <model> views= stage= size= ss= samples= tag= look= S=: EEVEE tiles $TOUT/s_<model><tag>_<view>.png;
  views v<i> (fitted cameras), y<deg> (front camera turned: y180 back, y125 back-3/4), t<deg> (tipped over the top).
- hcover.py <model> [render=0]: magenta-scalp coverage %, by HUE (t60 above, y180 behind, y125, v1).
- mksheet.py <model> [prev=] [pairs=<dir>]: REFERENCE | ours sheet + per-region crop pairs for the review, incl. the
  tight top-front DIRECTION crops (three-quarter, profile): whole-head pairs made the reviewer contradict itself.
- gatetable.py <model> <checklist>: MEASURE table (cmp.py stand-off / colour, hlinetrace.py hairline, hcover).
- hlinetrace.py (hairline photo vs ours by |az|: it measures the VISIBLE boundary, so it moves with the comb),
  profover.py (our outline on the photo through the fitted camera, rays +-150 deg; blue = whole render: checks head
  registration), widths.py, guidefield.py (guide comb plotted from behind: red = starts upward), veileval.py,
  cmp.py (hair_read.compare), copyhead.py <src> <hg_/hj_/hl_ dst>.

### Garrett: state
- Joe on G6: "I don't hate the look, could almost be there, if we can get it facing the right way". KEEP G6's look
  (colour, coverage, density, surface: styles/g_G6.json; colour measured L* 42.3 vs photo 42.4, grey share 0.464 vs
  0.466, coverage 0.24 % above / 0.10 % behind). G6 ran WITHOUT Clump: set strands.clump 0 to reproduce it.
- Direction and shape as read from his photos (the coordinator agreed): in notes_private.md, section
  "Handover 2026-10-14 photo reads" (never in git), and in the checklist's style_in_words.
- G10 (g_G10.json) = G6 + front crest (out front 0.25, lift 1 cm) + temple line carried to 67.5 deg + whorl
  [215, 42] r 4 cm spiral 75 + nape 0.01 / nape_v 0.004. Light review (out/review_hg_G10/review.md): crest = spiky
  forward fringe (drop it), temples now TOO deep (+18.7 mm), centre +0.6 PASS; texture / colour notes are light-render
  artefacts.
- G11 (g_G11.json, GROOMED as hg_G11, NOT rendered) = G10 without the crest (G6's out / lift) + temples halfway
  (front_points 42.5: 1.735 ... 67.5: 1.705). Render it (remote, full count) and review next.
- Open MAJORs (latest full reviews G6-G9): temple M shape; nape a blunt straight cut (want a rounded taper, not a
  V); whorl reads as a starburst (want a soft off-centre spiral with slight scalp show); hard hairline edge (sparse
  roots, no lip); a seam / tier where top meets sides; flat "slicked" top in some rounds. Stand-off: photo measures
  say sides / back / nape 3-7 mm under; trust them over the reviewer's "too bulky", re-check in the reviewer's view.
- Assembly agent (ad0815704f43e0e00) builds game-ready Garrett: told to copy groom / strands / look (not locks) from
  the latest good hg_ model and regrow with groom_hair; tell it when a groom passes.

### General code added this thread (all tested)
- strands.even 1 (every strand a child of dense lock guides 4 mm apart; banks per part side; nearest guide on long
  hair, blend 3 on crops; hp_cells colour numbers; Clump on all even hair); scalp-ray clearance push (the collider's
  tilted gradient made short back hair climb: the old whorl / rosette); fade thins the even roots.
- hair_loose: face up to 1.6; face rule only for hair >= FACE_MIN_LEN 6 cm; body / lift per region; whorl {at,
  radius, turn, spiral, core} (core > 0: spiral inside, radial beyond); hairline.nape_v (nape centre lowered).
- hair_read start: even 1, spacing 4 mm, out by region (arc up then fall) for loose long hair.

### Tried and failed (one line each)
- Forward comb (G3, G7-G9): reads as a fringe / bowl cut; the photos show up-and-back.
- A forward baby-hair fringe for the hard edge: rejected (nothing lies forward in the photo).
- Density ramp 6 -> 15 mm alone for the hard edge: the line still reads hard.
- Shorter sides / back (G3): cap and ledge seams, bare nape.
- Whole-top whorl r 13 cm (G9): pinpoint starburst, radial bristles.
- Grey from the reader's light share (E5): silver; light share counts lit hair too.
- nape_v 1.5 cm: a V hanging 3-4 cm down the spine (keep ~4 mm). hairline.nape +2 cm: still "blunt".
- Nearest-guide children on a crop: "pine needle" bundles (blend 3 on crops).

### Family heads
State, best rounds and open faults: workspace/private_notes/ (git-ignored) and the fam/ sheets;
their checklists are in workspace/checklists/.

### NEXT, in order
1. Garrett G11 full-count render on NICO-TOP (job_hairshots.py; commit first), gatetable + mksheet pairs + review;
   fix the worst MAJOR; loop. Send front / three-quarter / top pairs once direction passes.
2. Temple M, then nape shape, whorl softness, edge.
3. Then the two family heads (their open items: workspace/private_notes/), same gates.
4. Coordinator also asked: a garrett_hair_export checklist (card export beside the strand groom at the same cameras,
   now in game-like EEVEE per gates.md) once Garrett's groom is checkpointed.

## hair-garrett 2026-10-14 evening (successor): remote gate renders, direction
- Remote runner works (spikes/offload/job_hairshots.py on NICO-TOP; ~75 s a 1024 ss2 full-count frame, ~15 min a 9-frame
  job + queue). Scratch helpers (not in git): remote/mkjob.sh <model> <stage> <job> (pack + args), remround.sh <model>
  <results job dir> <checklist> [prev] (untar, table, pairs, review), dirstrip.py (own look: ref | rounds direction crops).
  Pitfalls: request <= 12 GB (NICO-TOP's slot cap is 14.1 GB: 16 GB sat queued forever); look='{json}' needs single
  quotes in args.txt (shlex); stage paint images must travel (pack_model now copies _images / _painted ids the spec names).
- G11 full review: FAIL. Own look at the direction crops: the front strands lean FORWARD (up and toward the face) in the
  profile and three-quarter; the photo's rise from the line and go back. Measured colour L* 49.7 / grey 0.736 (G6 42.3 /
  0.464): strands.clump 0.1 (added after G6) lightens it; G12+ set clump 0 (G6's look).
- G12-G14 (light checks): front flow [0.1, 0.9, 0.4] (was [0.55, 0.6, 0.35]: mostly sideways to his left), top [0.12, 1, 0]
  (was [0.4, 0.85, 0]); now flows back in both crops. G14 also front out 0 / lift 8 mm / lay 0.6 (flatter, leans back
  more; G13 keeps the lifted front). Both rendered remote for the review.
- SETTLED DIRECTION (coordinator, 2026-10-14 evening, from the tight crops; do NOT flip it again): top and front combed
  FORWARD and slightly to his left, the front edge = strand TIPS over the line (short, sparse, lightly lifted, never a
  heavy fringe / bowl edge); sides back and down; whorl high at the back right of centre. The earlier "rises from the
  line, up and back" was a misread of whole-head views: G13 / G14 (back) read as slicked back with a widow's peak.
- Remote (NICO-TOP) hair renders ~10 levels lighter than local (skin pixels equal): calibrate colour against G6 rendered
  remote; colour items must come from the same renderer as the judged sheet. dirmeasure.py (spikes/hair_garrett):
  structure-tensor strand angles per cell, ref vs ours (axial: tells "/" from "\", not forward from back).
- The blind review is NOT a usable judge of comb direction: whatever our direction, it calls the reference the opposite
  (G13 / G14 back -> "should be forward"; G22L / G24 forward -> "should sweep up and back"). Direction is settled by the
  coordinator's decision above; review direction MAJORs are answered with that, not chased.
- Forward groom: top / front flow {from: whorl [215, 42], bias [0.15, 0, 0.0 / 0.9 front]} (from the vertex [200, 72]
  the top radiated in spikes); temple corners midway between G11 and G21 (with a forward comb the hair from behind
  covered shallow corners); a single world direction for the top hung the temple-corner hair forward over the recession.
  Shape faults the reviews agree on (and the table): sides 3 mm vs 12.6 stand-off, a ledge where top meets sides,
  hard spiky front tips. G25: sides 2.2 cm / lift 9 mm, back 2.6 cm, nape 1.2 cm, front bias up 0.9, messy 0.25.
- Laptop gate frames (when NICO-TOP is down): 0.47 s GPU a sample at the full 360k count and 1024 px ss 1; 10 samples
  = ~4.7 s (localgate.sh in scratch). Scene load is ~15-20 s of the printed frame time.
- G25r (remote, x0.84 look): colour PASS (L* 40.1 vs 42.4, grey 0.394 vs 0.466): the calibration works. hlinetrace
  "none traced" on the forward grooms (the line is covered by tips): the hairline / temple items need another trace.
  Review MAJORs: side slab + ledge + bald notch above the ear (sides lift 9 mm / out 0.1 stood off as a shell), boxy
  back, blunt nape, whorl small. G26-G31 (light): sides 1.8 cm lift 6 mm out 0.03 lay 0.6, sides flow {from: whorl,
  bias [0, 1.2, -0.6]}, G6's temple points (shallower), back 1.8 cm laid 0.8. NAPE: hairline.nape is a HEIGHT (+ raises
  the line: 0.03 made it worse); -0.012 lowers it below the ear lobes and, with fade {width 0.07, length 2 mm, density
  0.2} (fade acts behind fa 100 deg only), gives a sparse taper instead of the hanging horizontal cut.

## Handover 2026-10-15 (hair-garrett agent -> successor)
Branch `hair-heads2` (main merged at ec950f6a; private subjects stay out of tracked files entirely: workspace/private_notes/).
Read: the two "hair-garrett 2026-10-14 evening" sections above (remote renders, SETTLED DIRECTION, review unreliable on
direction, calibration, nape findings).
### State
- Direction SETTLED by the coordinator: forward and slightly to his left, tips at the line, sides back and down. Sent
  to the coordinator as STUCK on the review (it flips every round): out/send_forward_G25r_G31r.png. Don't chase review
  direction MAJORs.
- In flight: G32r on NICO-TOP (batch hgf32; log remote/jf32.log; results remote/results/hgf32/jf_G32r). Then
  `./remround.sh hg_G32r remote/results/hgf32/jf_G32r <checklist> hg_G31r` (prints the table, writes
  out/review_hg_G32r/review.md). G32 = G31's sides + G23's temple points (receded) + nape 0 / fade 6 cm + top 4 cm,
  lift front 14 / top 11 mm.
- Styles: scratch styles/g_G<n>.json (local look) and g_G<n>r.json (remote look = seen x0.84, grey #9c9791; the
  remote renderer draws hair ~9 levels lighter). Colour passed on G25r (L* 40.1 / 42.4).
### Open faults (G25r / G31r reviews and table), worst first
1. Top: flat short cap with no front lift (stand-off front 8-9 vs 14.5 mm); front edge dense to the line, not soft and
   sparse. Next: front-edge thinning (there is no front `fade`; the back fade code in hair_loose.py ~line 370 is
   behind fa 100 deg only: a general "fade at any hairline" would serve), more front lift.
2. Back: boxy and too light / speckled vs the photo's darker smooth back; nape a horizontal cut. hairline.nape is a
   HEIGHT (+ raises it); -0.012 left sparse long strands down the neck (coverage behind 6.9 %).
3. Whorl: pinched starburst; the review wants it broad and soft with slight scalp show (whorl radius / spiral / core).
4. hlinetrace finds no line on forward grooms (the tips cover it): the hairline / temple items need a trace that
   ignores overhanging tips, or the review only.
### Tools (scratch /mnt/data/hifipushie/hair_garrett, not in git)
remote/mkjob.sh <model> <stage> <job> [args], remote.sh call: `BATCH=x TIMEOUT=60 spikes/offload/remote.sh
spikes/offload/job_hairshots.py tiles.tar,log.txt 12 8 gpu <job>` (12 GB max), remround.sh, lc.sh <round> [prev]
(VIEWS=... light check + ref | prev | this strip), localgate.sh (laptop gate frames, 10 samples, only if NICO-TOP is
down), dirstrip.py. In git: spikes/hair_garrett/dirmeasure.py; hair_loose flow {from, bias}.
### NEXT
Review G32r; fix the worst MAJOR (top lift / soft front edge); loop. Then temple M, nape, whorl. Then the private heads
(state in workspace/private_notes/). The export checklist (handover 2026-10-14 NEXT 4) is still owed.

## hair-garrett 2026-10-15 (successor 2): length and softness
Coordinator's read of G25r / G31r: the biggest fault is LENGTH and SOFTNESS (a short stiff standing bristle; the photo is
longer on top, soft, lying in flowing strands, sparse soft front edge; back darker, smooth, tapered). Direction settled.
- G32r never rendered: its job failed on NICO-TOP with a sha256 mismatch because a NEW remote.sh submit from the same
  directory re-pointed `repo.tar.gz` (a symlink to the HEAD archive) while G32r was queued. RULE: one directory per
  queued batch (remote/b<n>/), or don't commit + submit while a batch is queued. G32r (the bristle look) was dropped.
- Photos (85 mm direction crops): top strands run 3-5 cm visible; the front is a rounded mass lifted ~1.5 cm above
  the line whose tips end about at the line, fine wisps over it; no lip, no dark band.
- New code: `fade.front {width, density, reach}` (hair_loose + the even / scalp layers' density in hair_strands):
  fewer roots near the front line; forward-combed tips end `reach` (x0.3-1.7 per lock) past the line. `length.top_el
  [e0, e1]`: the top's length only above e0..e1 deg (a long top hung down the upper sides as a bowl).
- Light checks G33-G44 (laptop, 120k strands): long front + low stiff + forward comb = a fringe / bowl (G33, G35);
  reach caps it at the line (G36+); front lift 12 mm + stiff 0.6 made an overhanging lip with a dark band of short hairs
  in its shadow under it (G37-G39): lift 6 mm / out 0.05 / stiff 0.45 / lay 0.6 lies onto the line (G40). Top bias
  [1.0, -0.5, 0] (more to his left, a little forward) reads as the photo's sweep in the three-quarter. top_el [32, 72]
  (a [50, 66] band left a step where top meets sides).
- Back: the bare band over the nape with sparse long strands (G31-G43) was the FADE (length 3-4 mm, density 0.3-0.65
  over 2.5-6 cm: a barber's fade the photo doesn't have). G44: fade width 2 cm / length 8 mm / density 0.9, back 1.5 /
  nape 0.9 cm, back stiff 0.45 lay 0.9 lift 2 mm, grey back 0.07: dense to a rounded tapered nape, darker.
- G44 = lengths front 4.5 / top 5 / sides 1.8 / back 1.5 / nape 0.9 cm, clump 0.08, whorl radius 5 cm spiral 50.
STATE: G44r queued on NICO-TOP (remote/b44). NEXT: remround.sh on it, review, fix worst MAJOR; send pairs when
length / softness read right.

## Handover 2026-10-15 ~15:20 (hair-garrett successor 2 -> next; stopped at the 100-tool-call rule)
- IN FLIGHT: G44r on NICO-TOP, submitted from its OWN folder: client log remote/b44/jf44.log (nohup, keep it alive;
  it was queued behind a 20 GB lashes batch the coordinator is having resubmitted). Results land in
  remote/b44/results/hgf44/jf_G44r. Then: `./remround.sh hg_G44r remote/b44/results/hgf44/jf_G44r
  /home/joe/dev/hifipushie/workspace/checklists/garrett_hair.json hg_G31r` (scratch /mnt/data/hifipushie/hair_garrett).
- RULE (remote): one folder per submit (remote/b<n>/): remote.sh re-points ./repo.tar.gz, which killed G32r. The runner
  path must be ABSOLUTE ($W/spikes/offload/job_hairshots.py). Build the remote model first: `./run.sh hround.py hg_h6
  hg_G<n>r patch=@$PWD/styles/g_G<n>r.json`, then `remote/mkjob.sh hg_G<n>r hg_h6 remote/b<n>/jf_G<n>r`.
- mksheet pairs= needs an ABSOLUTE path (relative wrote into the worktree's out/).
- Whorl (light checks, back view): az 215 / el 42 drew it high and right of the photo's; G46 / G47 whorl.at [207, 28-30],
  radius 6 cm, spiral 70 sits about where the photo's is (slightly right of centre, ~15 % down the head). Keep the
  top / front / sides flow `from` at [215, 42] (G47): moving it with the whorl straightened the top's sweep. Still a
  point-like centre; the photo's is broad with scalp showing (no whorl density option yet).
- NEXT: review G44r (length / softness / front edge / back); if length and softness read right, send front, 3/4, top,
  back pairs to the coordinator. Then G47r (G44 + whorl). Open: strand texture reads speckled / striped (white vs dark
  strands; colour calibration from G25r kept); front view still a thin cap vs the photo's fuller rounded sides.

## 2026-10-15 ~15:30 (hair-garrett successor 3)
- G44r's client in remote/b44 died (log stuck at "queued"); resubmitted G44r + G47r (G44r + whorl.at [207, 30], radius
  6 cm, spiral 70) as ONE batch hgf4447 from remote/b4447/ (12 GB, 8 cpus, gpu, TIMEOUT=240). Log
  remote/b4447/jf4447.log; results remote/b4447/results/hgf4447/jf_G44r, jf_G47r.
- STATE: queued on NICO-TOP. NEXT: remround.sh on both (prev hg_G31r for G44r, hg_G44r for G47r), review.
- G44r / G47r rendered (batch hgf4447, ~75 min incl. queue). Table (both): colour PASS (L* 43.4 / 42.4, grey 0.51 /
  0.47), coverage PASS, hairline centre / temple PASS; STAND-OFF FAILS on 5 of 6: front 8.2 / 14.5, top 7.9 / 12.7,
  sides 4.4 (G47r 3.7) / 12.6, back 5.6 / 12.1, nape 2.0 / 9.3 mm (crown 8 / 10.9 passes). Review FAIL (both).
  My look (ref | result x0.84, tmp/g44_a.png, g44_b.png, g47_b.png): thin cap that follows the scalp, flat sides,
  blunt front ledge; back a flat laid curtain ending in a ragged pointed nape; strand texture striped / speckled;
  whorl a pinpoint. Answers: direction MAJORs (comb back / radial) = disputed, direction settled with Joe; volume,
  nape, whorl, texture = accepted. Whorl: on the back view the photo's centre is ~on the head's midline (+3 px of a
  ~300 px head); G47r's [207, 30] is ~54 px right (~24 deg az): az 180 = midline, so az ~182. Scalp-show at the whorl:
  no option yet. A stray vertical strand down the neck centre (nape crop).
- Submitted batch hgf4849 (remote/b4849/, detached setsid): G48r / G49r = G47r + whorl [182, 30] r 8 cm + volume:
  G48r lift f/t/s/b/n 10/9/8/6/3 mm, lay .5/.6/.6/.7/.8; G49r lift 14/12/11/9/4 mm, lay .45/.5/.5/.6/.75.
- STATE: hgf4849 queued. NEXT: remround both (prev hg_G47r); pick the one closer on stand-off without a shell / slab
  look; then nape taper (short, darker, no ragged points) and strand texture.
- G49r (G47r + whorl [182, 30] r 8 cm, lift 14/12/11/9/4 mm, lay .45/.5/.5/.6/.75): stand-off front 14.4 / 14.5,
  top 13.9 / 12.7, crown 13.9 / 10.9 PASS; sides 9.1 / 12.6, back 6.2 / 12.1, nape 3.8 / 9.3 FAIL; colour PASS (L* 40.9,
  grey 0.42). Review 29 MAJOR lines (G47r 36). My look (tmp/g49_a.png): top finally rounded with a fuller front;
  whorl now ~on the photo's spot (still a tight point, no scalp show); a ledge where the lifted top overhangs the
  flat sides (profile); back / nape still laid flat; texture still speckled / lock-striped. G48r (milder) not
  reviewed: G49r is the direction.
- Submitted hgf5051 (remote/b5051/): G50r = G49r + sides / back / nape lift 15 / 13 / 7 mm, lay .4 / .45 / .6;
  G51r = G50r + look.vary 0.08 (from 0.25: lock-to-lock brightness = the stripes?).
- STATE: hgf5051 queued. NEXT: remround both (prev hg_G49r); keep the volume if sides / back pass without a shell;
  judge vary on the texture.
- G50r / G51r: sides 10.3 / 12.6 PASS now (lift 15 mm lay .4), back 7.9 / 12.1, nape 4.8 / 9.3 FAIL; front / top /
  crown PASS. G51r (vary 0.08) colour L* 42.0 / 42.4, grey 0.46 / 0.47 (closest yet); review MAJOR lines 24 (G50r 34,
  G49r 29): lower vary softens the lock stripes, KEEP. My look (tmp/g51_a.png): sides fuller; nape still a hard dark
  cut with a drooping fringe and the stray vertical strand down the neck centre; front view still thinner than the
  photo's rounded sides; whorl still a pinch point (no thinning option); profile ledge top over sides persists.
- Submitted hgf5253 (remote/b5253/): G52r = G51r + back lift 18 mm lay .35, nape lift 10 mm lay .5 length 6 mm,
  fade {width .04, length .004, density .4}; G53r = G52r + sides lift 20 mm, out .06 (front fullness).
- STATE: hgf5253 queued. NEXT: remround both (prev hg_G51r).
- G52r / G53r: back stand-off PASS (9.6 / 9.9 vs 12.1), G53r sides 12.7 / 12.6 PASS (lift 20 mm, out .06: fuller front
  and 3/4, the best top / sides yet); nape 5 / 9.3 FAIL. REGRESSION: fade {width .04, length .004, density .4} opened a
  bald rectangle across the lower back with sparse long strands (coverage behind 5.1 %): DON'T use it. Review 30 / 27
  MAJOR lines; also a "seam" between the pale top and darker spiky back, temple not silver enough.

## Handover 2026-10-15 ~19:30 (hair-garrett successor 3 -> next; stopped at the 100-tool-call rule)
- IN FLIGHT: G54r = G53r with G51r's fade restored ({width .02, length .008, density .9}); batch hgf54 from
  remote/b54/ (detached setsid; log remote/b54/jf54.log; results remote/b54/results/hgf54/jf_G54r). Then:
  `./remround.sh hg_G54r remote/b54/results/hgf54/jf_G54r /home/joe/dev/hifipushie/workspace/checklists/garrett_hair.json hg_G51r`
  and tmp/strip.py (run from $W with `uv run python`): `strip.py <pairs dir> <out.png> front three_quarter profile
  back nape__back` = ref | result x0.84 rows.
- Best so far: G53r's top / sides / back (styles/g_G53r.json) + G51r's nape. Kept: whorl [182, 30] r 8 cm (on the
  photo's spot; az 180 = midline), look.vary 0.08 (softer lock stripes), lift f/t/s/b/n 14/12/20/18/10 mm, lay
  .45/.5/.4/.35/.5, sides out .06.
- Open, worst first: (1) nape: hard dark cut + drooping fringe + a stray vertical strand down the neck centre; nape
  stand-off 5 / 9.3 mm; the fade knob is all-or-nothing (density .4 = bald band): needs a real length taper toward
  the nape line, not a density cut. (2) Whorl: a tight point, the photo's is broad with scalp showing: no thinning
  option (a whorl density / part halo would serve). (3) Profile ledge where the lifted top meets the sides; "seam"
  pale top vs darker back. (4) Temples should read more silver. Direction MAJORs: disputed (settled with Joe).
- Every round goes to NICO-TOP (Joe's rule 2026-10-15): one folder per submit, detached, as many variants per batch
  as useful. Queue waits 50-90 min; render ~15 min per job.

## 2026-10-15 ~20:00 (hair-garrett successor 4)
- Measured targets from the photo crops (G53r pairs, scratch tmp/whorlmeas.py, templemeas.py, stepmeas.py):
  whorl scalp show = warm (skin) pixels in the crown__back crop: photo 1.14 % of hair px, centroid (271, 259), spread
  sd 25 x 19 px (~7 x 5 mm) vs G53r 0.16 %. Temples (lower 3/4 of the temple crops, neutral hair px): photo L* 45.0 /
  46.4, light share (L* > 55) 0.27 / 0.21, chroma 2.9 / 4.4; G53r L* 42.7 / 44.1, light 0.09 / 0.17, chroma 4.7 / 4.8.
  Profile's lower band (sides above the ear) L* photo 54.9 vs ours 36.1: the sides read silver in the photo. Back view
  L* photo 35-36 vs ours 42-43 (our back is too LIGHT, not darker). Profile ledge / seam: my outline and row-L* metrics
  did not separate photo from ours (internal edges, not the silhouette): judged by the review's MAJOR only.
- Cause of the bald nape band (G52r / G53r): fade.length 0.004 makes those locks < 8 mm, and grow() never grows a lock
  under 8 mm (`s[-1] < 0.008: continue`): the fade's band had no locks at all, only the thinned even layer.
- New groom options (hair_loose / hair_strands / hair.weights, tests in test_hair_loose.py): fade.taper (m; length AND
  lift ramp to `floor` x over `taper` above the nape line, line jittered `rough` m, density to `density` only over the
  lowest third, locks kept >= 9 mm), whorl.thin / thin_radius (Gaussian root thinning at the whorl, locks + even layer),
  loose.blend (region transitions x wider about the same middles; 1 = old weights exactly).
- Cherry-picked bef0229c (remote.sh per-commit archive) and 01917898 (one Blender per job, pack_model --stage).
- G55r = G54r + nape length 12 mm, fade {taper .025, floor .35, density .75, rough .004, front kept}, whorl thin .55 r
  12 mm, blend 1.6, grey sides / temples .55, sideburns .5, back .04. G56r = G55r + blend 2.2, whorl thin .7 r 15 mm,
  grey sides / temples .65, sideburns .6, taper .03 floor .3. Targets: nape stand-off 9.3 +- 3 mm with no bald band or
  stray strand; whorl warm share ~1 % near (271, 259); temple L* 45-46, light share .2-.27; no ledge / seam MAJOR.
- Found while checking the builds: G54r had NO locks at the back centre below z -0.023 m (head-centre frame): the
  nape's 6 mm length (and the fade's) are under grow()'s 8 mm floor, so the whole nape was even-layer children copying
  the back's longer guides (the drooping fringe / stray strands). G55r / G56r (taper, nape 12 mm): 208 back-centre
  locks down to z -0.101, all >= 9 mm; 2091 locks vs 1707.
- Submitted hgf5556 (remote/b5556/, both jobs packed with `--stage _g3_hg_h6` after a local stage.ensure: 125 MiB
  each; remote/mkjob.sh takes STAGE=). Chained detached: offload wait, then remround G55r and G56r (prev hg_G53r),
  logs tmp/rr_G55r.log / rr_G56r.log, flag tmp/rr_5556.done. G54r's remround is chained too (tmp/rr_G54r.log).
- STATE: hgf54 + hgf5556 queued. NEXT: tables + reviews; strip.py ref | result crops; keep the variant that hits the
  targets, revert any regression.
- G54r (G53r + G51r's fade): nape 4.8 / 9.3 FAIL, coverage behind 4.44 % FAIL, bald rectangle still there (its 8 mm
  fade locks are under the grow floor too). Review FAIL.
- G55r / G56r (hgf5556, 81 min incl. queue; packed stage worked): EVERY measured item PASSES on both, nape and
  coverage behind for the first time. G56r: nape 9.0 / 9.3, coverage behind 0.41 %, front 14.6, top 14.1, crown 13.9,
  sides 12.5, back 9.9, L* 43.0 / 42.4, grey .495 / .466. My measures (G56r | G55r | photo): whorl scalp share 1.30 % |
  0.66 % | 1.14 %, its centroid (263, 301) | (265, 305) | (271, 259) = ~42 px LOW; temple L* 46.9-48.9 | 45.6-46.7 |
  45.0-46.4, light share .23-.32 | .18-.24 | .21-.27; back view L* 42.5 | 41.3 | 36.8 (ours too light).
  My look (scratch strip: ref | G56r | G55r): bald band GONE, dense hair to a soft taper; scalp now shows at the
  whorl. Still wrong: nape ends in a V point (hairline.nape_v 8 mm; the photo's is near-horizontal) with spiky tips
  and a few strays below it; the whorl is a tight spiral with a SATURATED PINK spot (photo: low-contrast thinning);
  front-top visor / ledge in profile is unchanged by blend 1.6 / 2.2 (it is the front's lift + 45 mm length, not the
  region weights); back reads uniformly light (photo darker at crown and nape).
  Review FAIL on both (34-35 MAJOR lines incl. disputed direction / hairline / skin ones). On my targets: (1) nape
  PASS on numbers, review MAJOR still (V point, strays); (2) whorl scalp share PASS on numbers, review MAJOR (pink,
  tight, ~4 deg low); (3) ledge / seam FAIL (unchanged); (4) temples PASS on numbers (review wants softer edge).
- KEEP G56r (styles/g_G56r.json) as the new best.

## Handover 2026-10-15 ~23:00 (hair-garrett successor 4 -> next; 70-tool-call clock)
- Best: hg_G56r. Code on hair-heads2: fade.taper, whorl.thin / thin_radius, loose.blend (tests in test_hair_loose.py),
  cherry-picks of bef0229c + 01917898. Jobs: STAGE=_g3_hg_h6 remote/mkjob.sh <model> hg_h6 <job> packs the built stage
  (run tmp/ensure_stage.py hg_h6 through run.sh first, from a clean tree at the commit you submit).
- NEXT round, one batch, each with its target: (1) nape: hairline.nape_v 0.008 -> 0 (photo near-horizontal), taper
  rough .004 -> .002; target: review no V / strays, nape stand-off stays 9.3 +- 3. (2) whorl: at el 30 -> ~34 (centroid
  42 px low), thin .7 -> .5 and look.scalp_tint up so the spot isn't pink; target scalp share ~1.1 %, centroid within
  15 px of (271, 259). (3) front visor: front length 45 -> ~35 mm and/or lay .45 -> .6 at the front only; target: no
  ledge MAJOR with front stand-off >= 11.5. (4) back too light (L* 42.5 vs 36.8): a darker back / nape (grey back 0
  and a per-region darkening, which doesn't exist yet: look.seen is global).

## 2026-10-16 (hair-garrett successor 5): the checklist passed a crew cut; texture items added
- Coordinator's read of G56r (all old items pass, review FAIL): a BRISTLY CREW CUT (short straight uniform bristles,
  dark / light striping) where the photo's hair is longer, lies down and sweeps, tips flow and clump; a stiff front
  visor; a dark blotch at the front-top hairline; back too light / uniform; nape V; hard lined hairline edge.
- PROCESS: the checklist measured stand-off, coverage, colour, lines, never the strand texture. New tool
  spikes/hair_garrett/texmeas.py <pairs dir> (ref | res crops, hair px = neutral + textured, eroded): lay (strand angle
  to the image horizontal, coherence-weighted), coh (structure tensor at 4 px), len (p75 of skeletonised light-ridge
  pieces), band (DoG 3-10 L* std = lock striping), edgec (DoG 1-4 std in the 25 px under the hair line), Lmean.
  Measures that did NOT separate photo from ours (dropped): autocorrelation length along strands (2-5 px both),
  orientation spread in 32 px windows, sparse-tail width of the hairline (7 vs 8 px).
- Photo | G56r (new checklist items, targets = photo +- tolerance, in workspace/checklists/garrett_hair.json):
  lay_top: 3q top-front 17.1 | 58.9, profile top-front 31.4 | 60.4, hairline 17.8 | 52.3 deg (tol 12).
  strand_length: 3q 52 | 11, profile 62 | 10.5, back 62 | 11 px (min 30).
  flow_coherence: 3q .75 | .52, profile .74 | .51, back .75 | .51, top-front .80 | .67 (min .70).
  striping (band): top-front 3.68 | 4.45, profile top-front 3.33 | 4.18, hairline 3.20 | 4.26 (tol .3).
  hairline_edge (edgec): hairline 2.83 | 3.49, temples 2.94 / 2.71 | 3.00 / 3.28 (tol .3).
  back_lightness: back 34.8 | 42.3, crown 34.6 | 40.1, nape 35.4 | 42.6 L* (tol 3).
- Causes found (geometry, spikes scratch tmp/blotdbg.py: lock points by (az, el) over the front hairline):
  every lock's `lift` is reached within 3 cm of arc (clear = lift * ss(s / 0.03)), so a 45 mm lock lifted 14 mm spends
  most of its length rising: a standing bristle. The stand-off should come from layers (`body` x layer rank), the
  lock lying (`lay`). The front flow {"from": crown, bias} points FORWARD-DOWN at the hairline (away from the crown,
  laid in the forehead's near-vertical tangent plane: the bias's y is mostly projected out there, only z survives);
  G56r's bias z .6 + 14 mm lift = the visor; fade.front.reach (.01) is what stops forward tips: dropping it with lay
  .75 draped 90 locks up to 25 deg down the forehead. The front locks on his right go to his left (bias x .9), so the
  hairline at az -30..-10 is covered only by the roots' first stretch: root_dark (.5 default) + the dark under layer
  show there = the dark blotch (hypothesis; G57r lowers root_dark, G58r combs the front up and back over it).
- Round G57r / G58r (one batch hgf5758, remote/b5758/, chain.sh: remote.sh -> offload wait -> remround both, prev
  hg_G56r; flag tmp/rr_5758.done). Both = G56r + top length 60 mm, lift top 8 mm, lay top .75, body per region
  (front / top 14, sides 8, back 10, nape 8 mm), front length 52 mm, lay .55, lift 12 mm; hairline.nape_v 0; fade.rough
  .002; whorl at [182, 34], thin .5; look.scalp_tint .5 (pink whorl), root_dark .3, variation .2 (lock lightness:
  striping), seen x .82 with grey top / front .18 -> .32, back / nape 0 (a darker back without a new per-region option:
  the darker base carries the back, more grey hairs keep the front's L*). G58r also: front bias [.5, 1.5, 2.5] (up and
  back over the hairline: 8 locks dip under it vs 87 at G56r-like settings without reach), strands.clump .25,
  variation .1.
- STATE: hgf5758 queued on NICO-TOP. NEXT: texmeas on pairs_hg_G57r / G58r + remround tables + reviews.
- CORRECTION: strand_length photo 52 / 62 vs ours 11 px was a COLUMN MISREAD (cut on a fixed-width table). Real: photo
  11-22 px, ours 10-19 px: the ridge-piece length does NOT separate them. Item kept as unmeasured (status in the
  checklist); visible length is the review's until a better measure. The other five items were read from full tables.
- G57r / G58r (hgf5758, 45 min incl. queue). Photo | G56r | G57r | G58r:
  lay_top (3q top-front / profile top-front / hairline, deg): 17/31/18 | 59/60/52 | 62/62/53 | 48/68/41: FAIL all;
  G58r's front-up-and-back is the only move that lowered it (3q, hairline).
  flow_coherence (3q / profile / back / 3q top-front): .75/.74/.75/.80 | .52/.51/.51/.67 | .57/.54/.52/.71 | .56/.52/.52/.68:
  FAIL (whole views unchanged by clump .25).
  striping band (3q top-front / profile top-front / hairline / profile): 3.68/3.33/3.20/3.58 | 4.45/4.18/4.26/4.46 |
  4.96/4.51/4.35/4.86 | 4.92/4.53/4.33/4.80: REGRESSED (grey hairs .18 -> .32 on a darker base = more white-on-dark
  contrast; the review agrees: "near-white strands over dark streaks").
  hairline_edge edgec (hairline / temples): 2.83/2.94/2.71 | 3.49/3.00/3.28 | 3.88/3.95/3.04 | 3.63/2.83/2.81: G58r
  temples PASS, hairline FAIL.
  back_lightness L* (back / crown / nape): 34.8/34.6/35.4 | 42.3/40.1/42.6 | 37.3/36.2/35.4 | 37.3/36.2/35.4: PASS both
  (seen x .82, back grey 0).
  Old items: stand-off front 11.4 / 11.2 vs 14.5 FAIL (G56r 14.6: REGRESSION from front lift 14 -> 12 mm and the
  up-and-back comb), back G57r 8.9 FAIL / G58r 9.1 PASS, top / crown / nape PASS, coverage PASS; colour_front G57r L*
  43.8 PASS (G58r's colour rows came out n/a: cmp.py did not write them, unexplained).
  Review FAIL both (MAJOR lines 35 / 31; G56r 34). Hair MAJORs on G58r: colour too light and contrasty (all views);
  "reads as fur / bristle: short thick white dashes on a dark brown base"; strands "thick, flat, ribbon-like with dark
  outlines"; white halo line on the top silhouette; nape a hard bristle row (no V now, but blunt); sides flare like a
  helmet; front: "points down onto the forehead / bowl fringe" on one view, "lifts" wanted.
  My look (scratch cmp.png, ref | G56r | G57r | G58r): the front-top dark blotch is GONE in both (root_dark .5 -> .3,
  and on G58r the front combed up over the bare stretch); nape V gone; back darker and closer; whorl less pink. G58r's
  top-front shows the first lying, sweeping strands; still a bristle texture everywhere else.
- Verdict: FAIL. Keep G58r as the base for the front / back / nape / blotch fixes, but NOT its grey .32 (revert to .18
  with the darker base, or lighten the base less) and NOT its front stand-off (front lift back to 14 mm or body front up).
- The biggest remaining gap is the STRAND RENDER, not the groom: the review's "thick white dashes / ribbon strands with
  dark outlines" and our coherence .52 vs .75 are the per-strand look (strands.thickness .7, fine_alpha .3, the grey
  share as pure white strands, root_dark / depth giving each strand a dark core). Test thinner strands with more count
  and a grey that is mid-grey, not white (look.grey #9c9791 is light), against the band / coh items.

## Handover 2026-10-16 (hair-garrett successor 5 -> next; 70-tool-call clock)
- Best: G58r for blotch / nape / back L* / top-front lay; G56r for front stand-off and colour contrast. Neither passes.
- New checklist items (workspace/checklists/garrett_hair.json): lay_top, flow_coherence, striping, hairline_edge,
  back_lightness (measured: spikes/hair_garrett/texmeas.py <pairs dir>; print the FULL table, never cut columns),
  strand_length (unmeasured). gatetable.py does not read them yet (rows n/a): run texmeas beside remround.
- Geometry check without renders: scratch tmp/blotdbg.py <model> (locks over the front hairline by az / el and those
  dipping under it): front flow {"from"} points forward-down at the hairline; fade.front.reach is what holds tips back.
- NEXT round (one batch): G59r = G58r + grey top / front .18 (striping), front lift .014 / body front .016 (stand-off
  14.5), look.grey darker (mid-grey, e.g. #8a8681) and strands.thickness .7 -> .5 with count 360k -> 480k (bristle /
  ribbon look; check the 12 GB cap); G60r = G59r + root_dark .15, depth .3 (dark strand cores). Targets: band <= photo
  + .3, coh >= .70, lay hairline <= 30, stand-off front >= 11.5, back L* within 3.

## 2026-10-16 (hair-garrett successor 6): lay as a groom lever, render lever, A / B / C batch
- Merged origin/main (game-camera fix b32d303f etc.).
- NEW groom options (hair_loose, test_lift_profile_lies_down_along_the_lock): `lift_ramp` (m, per region; arc to full
  lift, default .03 = before), `lift_fall` (0..1: lift given back toward the tip), `body_along` (0..1: body x layer
  reached gently along the lock, not only on descent: the height of a short top from lying layers). Defaults grow
  identical locks. Tried and dropped: a `settle` pull toward the clearance: no effect, the locks already hug the
  clearance floor (lay .75 presses them down), so the lock's height profile IS the clearance profile.
- spikes/hair_garrett/laygeo.py <model> [patch.json ...]: lay / stand-off / front-reach on the lock geometry, no render
  (silhouette-band image angle in ortho yaw 45 / -90, p90 height over the front hairline, locks dipping > 5 deg below
  the front line). Calibration: stand-off G56r 14.5 / G58r 11.4 vs rendered 14.6 / 11.2 (good). Image lay G56r 25 / 16,
  G58r 41 / 40 deg vs RENDERED 59 / 60 and 48 / 68: G56r's curves already lay low, yet rendered 59: most of the measured
  lay gap is in the strand RENDER (short dashes read as random orientation, coherence .52), not the groom. G58r's
  front-up-and-back + top flowing sideways (bias x 1.0) made the curves themselves steep (in profile a sideways flow
  shows only its rise: the vertical dashes of the profile crop).
- Groom A (G59a): G58r + front / top flow from the crown forward (bias [.1, 0, 0] / [.1, 0, -.3]), lift front .006 /
  top .004, lift_ramp .02, body_along 1 front / top, body front .014 / top .014, fade.front.reach .01 (the limit stays:
  without it 74 locks draped up to 24 deg down the forehead). Geometry: lay 20 / 17 deg (photo 17 / 31), stand-off
  16.6 mm (14.5 +- 3), dips 0 (G58r 3). lift_fall not used (tips falling lowered the stand-off; body_along carried it).
- Render B (G59b): G58r + grey top / front .32 -> .18, look.grey #9c9791 -> #8a8681, strands.thickness .7 -> .5,
  count 360k -> 480k, root_dark .3 -> .15, depth .5 -> .3. C (G59c) = A's groom + B's render.
- gatetable.py now measures the texmeas items on the LOOK pairs (one row per crop); remround runs it after mksheet.
  colour_front stays n/a on G58r: cmp.py prints no view-0 colour line for it (view 0 hair mask?), unexplained.
- Batch hgf59 on NICO-TOP (remote/b59/, chain.sh -> remround x3 vs hg_G58r, flag tmp/rr_59.done).
- RESULTS hgf59 (~75 min incl. queue; tables out/table_hg_G59{a,b,c}.md, reviews out/review_hg_G59*). G58r | A | B | C:
  lay_top 3q / profile / hairline: 48/68/41 | 56/58/54 | 47/68/40 | 55/58/53 (photo 17/31/18): FAIL all; A's groom made
  3q and hairline WORSE. coherence (3q / profile / back / 3q top): .56/.52/.52/.68 | .55/.52/.49/.66 | .56/.51/.48/.67 |
  .53/.49/.45/.65: FAIL, no lever moved it. striping (3q top / pro top / hairline / profile): 4.92/4.53/4.33/4.80 |
  5.16/4.48/4.77/4.78 | 4.43/4.14/4.52/4.69 | 4.66/3.68/4.41/4.88: B best, still FAIL. hairline_edge (hl / temples):
  3.63/2.83/2.81 | 3.85/3.44/3.45 | 3.26/2.54/2.45 | 3.75/2.94/3.30: B best (temples PASS). back L* (back / crown /
  nape): 37.3/36.2/35.4 | 31.5/28.3/30.5 | 34.1/31.9/33.9 | 27.8/23.2/28.6: G58r / B PASS, A / C too DARK (FAIL).
  stand-off front 11.2 | 17.2 | 11.2 | 17.2 (14.5 +- 3: A / C PASS) but top 16.4 / crown 16.4 FAIL on A / C (12.7 / 10.9);
  temple_corners A +23 mm, C +21 mm FAIL; coverage_behind A 2.19 %, C .99 % FAIL. grey_mix B .327 / C .228 FAIL (G58r n/a).
  Reviews: all FAIL (MAJOR lines A 35, B 41, C 38; G58r 31). A: "top combed forward and down toward the brow, reads as a
  fringe; reference swept BACK and slightly to his left"; front edge a brim / cap peak; sides 1.5 cm out. B: helmet
  (low flat top, bell sides), strands "painted, scratchy streaks", hard hairline edge, M-shape / temple recession and
  sideburn missing (the last are hairline items, unchanged since G56r).
- My look (ref | G58r | A | B | C, top-front 3q and profile crops): A / C radiate from a visible crown point and come
  forward-down into a bowl fringe with a hard ledge; strands still read vertical. B ~ G58r, slightly finer and less
  contrasty. No variant shows the photo's long, soft, back-sweeping strands.
- LESSONS: (1) laygeo's silhouette-band image angle said A lies at 20 / 17 deg; the render read 56 / 58. The proxy only
  sees the top silhouette; the crops are dominated by the camera-facing slope, where a forward flow from the crown
  runs toward the viewer = vertical in the image. Do not trust laygeo's img3q / imgpro as lay until it measures the
  crop's own region (project the texmeas crop box). Stand-off and dip proxies DID calibrate. (2) The photo's top is
  combed BACK (slightly to his left), not forward from the crown. (3) Coherence / lay of the rendered crops did not move
  with groom or strand thickness: the dash texture is in how strands are built (short segments, clump structure), the
  next lever to study, e.g. strands.clump / tips / segment length, not grey or thickness.
- KEEP / REVERT per item: KEEP B's render (grey top / front .18, look.grey #8a8681, thickness .5, count 480k, root_dark
  .15, depth .3): striping and hairline_edge improved, back L* still PASS; its grey_mix FAIL (.327) needs the target
  checked. REVERT A's groom (forward flow, body_along top): lay, top / crown stand-off, temples, coverage, back L* all
  worse. The lift options stay in the code (defaults = old locks, tested). Best now: G59b (styles/g_G59b.json).

## Handover 2026-10-16 (hair-garrett successor 6 -> next; 70-tool-call clock)
- Verdict FAIL (all three). Best = G59b (G58r groom + finer, mid-grey render).
- NEXT round (one batch): G60 = G59b + front / top flow combed BACK and a little to his left (e.g. front bias
  [.3, 2.0, .3] from the crown, top [.3, 1.5, 0]) with the lying profile (lift front .008 / top .005, lift_ramp .02,
  body_along front / top .6, body front .016 / top .012), fade.front.reach .01; check laygeo stand-off 14.5 +- 3 and
  dip5 ~0 first, and top / crown stand-off <= 12.7 / 10.9 + 3. A second variant on the strand build (clump, tips,
  segment length) for coherence. Hairline M-shape / temple recession / sideburn (review MAJORs every round) is a
  separate hairline item, not lay.

## 2026-10-16 (hair-garrett successor 7): what LAY measures (calibrated), the gap is real, G60 batch
- Coordinator: two lay measures disagreed by ~35 deg (laygeo 16-25 vs render 56-60): settle the measure before grooming.
- spikes/hair_garrett/laycal.py. `synth`: grey strand patches at KNOWN image angles 15 / 30 / 60 / 85, texmeas `lay` |
  windowed `flow` (48 px doubled-angle resultant, weighted by its length):
  long strands 18.6/32.3/60.4/81.1 | 17.7/32.2/60.5/84.3; clumped locks 16.1/33.2/58.6/83.5; SHORT DENSE DASHES (8-16 px)
  14.9/30.0/60.0/83.8 (exact); isotropic dashes 46.8 (coh .31, R .10); dots = strands end-on 45.8 (coh .19, R .05).
  So texmeas lay is right whenever there IS a direction, short dashes included; texture without direction reads ~46,
  never "standing" (90), and shows as coh < .35 / R < .15 (our renders: coh .55-.70: they have a direction).
- `strands <model> <count> <outdir> [patch.json ...]`: the model's EVALUATED strands (hair.job + hair_strands.strands_of_model:
  Blender geometry, no render, ~20 s warm, CPU), every segment projected through the FITTED review cameras into the gate
  crops (v1 az 30 el 60 85 mm, v2 az 45 el 58 85 mm, v0 az 0 el 38 95 mm, as mksheet), front-most only (2 px z-buffer,
  1.5 mm), length-weighted |angle|; plus a FLAT raster of them (lines, per-strand grey) measured by texmeas.
  G59b (3q / profile / hairline): evaluated geometry 51 / 61 / 41, flat raster 50 / 68 / 44, EEVEE render 47 / 68 / 40,
  photo 17 / 31 / 18 (lay) = 15 / 31 / 17 (flow). The flat raster of the real strands looks like the render.
  => the render measure is VALID and the ~30-37 deg gap is real geometry. laygeo's img3q / imgpro were wrong twice over:
  an orthographic silhouette band, and LOCKS (guides) instead of the strands (G59b locks through the real cameras
  38 / 39 / 29: hair_even's interpolated children run 12-22 deg steeper than their guides). Use `laycal strands` as the
  pre-render lay check; laygeo stays for stand-off / dips (those calibrated).
- Where the steepness is (crops): the profile's lower half = the SIDES combed down (vertical); the front hairline =
  strands rising straight back from the line (back-combed reads vertical from the front). Photo, signed dominant angle
  (+ = rising to the right): 3q -11, profile -11, front +1: the front top lies level and runs back (slightly falling),
  the front hairline hair runs SIDEWAYS. Ours G59b -49 / +76 / -26.
- Geometry sweep on the evaluated strands (flat-raster lay 3q / pro / hl; laygeo stand-off; all dip5 0), base = G59b +
  lift front .008 / top .005, lift_ramp .02, body_along .6, body front .016 / top .012, fade.front.reach .01:
  i1 front bias [.3,2,.3] top [.3,1.5,0]: 35/67/42, 15.0 mm | i3 front [.4,3,.8] top [.4,3,.3]: 35/51/47, 13.8 |
  j1 i3 + front [1.5,2,.6] top [.8,3,.3] sides [0,2,-.3]: 32/56/37 | j2 j1 + lift_ramp .01 + lay .5: 41/62/42 (worse) |
  j3 j1 front [2.5,1.5,.6]: 33/56/35 | k1 i3 + front [2.5,1.5,.6]: 32/53/35, 15.1 mm (BEST: sum over photo 54 vs G59b 96) |
  k2 k1 + sides [0,1.6,-.2]: same as k1. s1 (G59b + clump .6, tips .6, length front .06 / top .072): 56/68/48 (no lay
  change, as expected); s2 = s1 + even .5: 52/59/44. k1s = k1 + s1: 32/52/35. (all from=[215,42])
  Profile stays ~52 against 31 in every variant: the sides' downward comb and the level run-back over the top are not
  reached by flow bias alone (next lever: the side region's flow / lay, and front lift kept level instead of following
  the scalp).
- Batch hgf60 (remote/b60/chain.sh, one submit, 12 GB): (i) hg_G60k1, (ii) hg_G60s1, (iii) hg_G60k1s, remround vs
  hg_G59b, flag tmp/rr_60.done. Styles in styles/g_G60*.json.
- Hairline M-shape / temple recession / sideburns NOT done this round (budget): still review MAJORs; hairline_centre
  +3.0 mm and temple_corners +6.8 mm FAIL on G59b are the measured rows to start from.
- RESULTS hgf60 (~60 min incl. queue; tables out/table_hg_G60{k1,s1,k1s}.md, reviews out/review_hg_G60*). G59b | k1 | s1 | k1s:
  lay_top 3q / profile / hairline: 47/68/40 | 34/57/35 | 53/68/44 | 33/58/35 (photo 17/31/18, pass <= 29/43/30): FAIL all,
  k1 the first real move in four rounds. PREDICTION HELD: laycal strands said k1 32/53/35, s1 56/68/48 (rendered 34/57/35,
  53/68/44): the evaluated-strand flat raster predicts the render within ~1-4 deg; use it before every render.
  coherence (3q / profile / back / 3q top): .56/.51/.48/.67 | .52/.49/.43/.67 | .60/.56/.51/.69 | .53/.51/.46/.65: FAIL; s1
  (clump .6, tips .6) the only one up. hairline_edge hl: 3.26 | 3.42 | 2.53 PASS | 3.37. back L* (back / crown / nape):
  34.1/31.9/33.9 | 27.7/23.2/28.2 FAIL | 34.2/32.3/33.9 | 28.6/24.8/28.6 FAIL. temple_corners +6.8 | +21.7 | n/a | +21.9 (FAIL);
  coverage_behind .13 | 1.41 FAIL | .19 | 1.55 FAIL; colour_front L* 38.5 | 34.0 FAIL | 37.7 | 33.7; stand-off: k1 / k1s
  front 13.2 PASS (G59b 11.2 FAIL), sides 11.2 PASS, nape 13.6 FAIL. Reviews all FAIL, MAJORs G59b 41 | k1 35 | s1 33 | k1s 34
  (k1: sides flare like a helmet, colour split dark top / light sides, step from the front of the top to the crown;
  s1: flat cap with a blunt fringe edge, top / side layer step, a dark shelf of vertical strands at the front).
- My look (ref | G59b | k1 | s1; 3q top-front, profile top-front, 3q head): k1's top runs more across and back (better),
  but a dark root band / brim sits along its front hairline and the temple corner is cut back; s1 ~ G59b, a little softer.
  Profile top-front still vertical in all three. None reads like the photo.
- Cause read (HYPOTHESIS, not tested alone): k1 / k1s share with G59a (last round) the LIFT BUNDLE (lift_ramp .02,
  body_along .6, body front .016, fade.front.reach .01) and all three have the dark back (L* 23-31), temple corners
  +21-23 mm and coverage_behind 1-2 %; G59b / s1 (no bundle) do not. The flow is the lay lever; the bundle is the cost.
- KEEP / REVERT: KEEP k1's FLOW (front {"from":[215,42],"bias":[2.5,1.5,0.6]}, top bias [0.4,3.0,0.3]): lay -13 / -11 / -5.
  REVERT the lift bundle (back L*, temples, coverage). s1: keep clump .6 / tips .6 candidates (coherence +.04-.05,
  hairline_edge PASS) but REVERT its length change (top .072 / front .06: lay 3q +6) -- untested apart, check on laycal.
  Best stays G59b for the gate; k1 is the lay lead.

## Handover 2026-10-16 (hair-garrett successor 7 -> next; 70-tool-call clock)
- Verdict FAIL (k1, s1, k1s). The lay measure is settled: texmeas lay is valid, the gap was real geometry, and
  `laycal.py strands <model> 120000 <outdir>` (20 s warm per variant + 50 s hround build) predicts the render's lay
  within ~4 deg. laygeo's img3q / imgpro are WRONG (locks, ortho band): use laygeo only for stand-off / dips.
- NEXT round, one batch, every variant screened on laycal strands first:
  (a) G59b + k1 flow ONLY (no lift bundle): expect lay ~k1 and back L* / temples / coverage back at G59b; check stand-off
      front (G59b 11.2 FAIL vs 14.5 +- 3) with laygeo; if short, raise lift front alone, not the bundle;
  (b) (a) + clump .6 / tips .6 (no length change);
  (c) the profile: ~55 in every variant is the SIDES combed down and the front top following the scalp; try sides flow
      more back with less lay on the sides, screened on laycal before rendering.
- Hairline M-shape / temple recession / sideburns: still not done. Rows: hairline_centre +2.8-3.4 mm (tol 2), temple_corners
  (G59b +6.8, tol 6); review MAJORs every round. Independent of lay: do it in the same round.
- Models hg_G60{i1,i3,j1,j2,j3,k1,k2,s1,s2,k1s} in workspace (styles/g_G60*.json); flats in $HG/laycal/.

## 2026-10-16 (hair-garrett successor 8): the pre-render SCREEN (calibrated), lever log
- spikes/hair_garrett/screen.py <model> <outdir> (driver $HG/scr.sh <round>...: hround build from hg_h6 + styles/g_<round>.json,
  then the screen; ~2.5 min a variant, no render). The model's evaluated strands (full count, hair.job) drawn as a FLAT
  raster (optical density: width max(2r, one render px), the strands job's scalp hp_density x look.scalp_tint as the
  root-shadow tint, head z-buffer from the scalp grid on 3 px cells) through the gate cameras, measured with the GATE's
  own code: stand-off = hair_read.hairness + outline_rays per fitted view, median; hairline = hlinetrace's cast of the
  hair / skin boundary vs the photos' parser line, per |az| bin; coverage = hcover's magenta test on the flat ID raster
  (magenta = density x 1.0), share over the render's figure area (constant: the flat has no body); lay = laycal strands.
- CALIBRATION (flat | render): stand-off front / sides / nape G59b 10.9/9.5/9.6 | 11.2/8.9/9.9, k1 12.9/12.8/13.4 |
  13.2/11.2/13.6, s1 11.3/9.5/9.4 | 11.6/9.4/10.1 (within ~0.6 mm, k1 sides +1.6); hairline_centre (flat - 1.9 mm bias,
  per bin G59b flat 4.7/5.0/5.8/8.9 vs render hlinetrace 2.6/3.3/4.2/6.8) 2.9/2.6/2.7 | 3.0/2.9/3.4; temple az-30 bin
  7.0/7.2 | 6.8/6.7; coverage_behind .20/1.49/.33 | .13/1.41/.19 (flat reads +0.1-0.15: pass at <= 0.65);
  coverage_above .03/.26/.03 | .01/.18/.01; lay as successor 7 (1-4 deg).
- FINDING: k1's temple_corners +21.7 was a BIN ARTEFACT, not a regression: gatetable averages the |az| 30-40 and 40-50
  bins, and the 40-50 bin (where the photo's line runs down the temple toward the sideburn, ours ~+37 mm) only exists
  when the render's parser finds > 3 points there (G59b render: none, so +6.8 = bin 30 alone; k1: 6.7 and 36.7). The
  az-30 bin is unchanged (6.8 -> 6.7). The flat finds the 40-50 gap on EVERY variant (+35-38 mm): a real, constant miss
  (no hair coming down the temple side), reported apart as temple_side. k1's real costs: coverage_behind and nape.
- PITFALL: laycal / screen `patch.json` deep-merged into spec["hair"] in memory does NOT regrow the locks (they are
  stored in the spec; groom_hair regrows them): ten patched screens came out identical to the base. Variants must be
  BUILT (hround / scr.sh). (Successor 7's i1..k1 numbers were from built models: valid.)
- LEVER LOG G61 (each = G59b + k1's flow (front bias [2.5,1.5,.6], top [.4,3,.3]) + ONE lever; screen numbers: stand-off
  front / sides / back / nape mm | hairline_centre / temple az30 mm | coverage_behind % | lay 3q / profile / hairline deg;
  photo lay 17 / 31 / 18):
  G59b       10.9 / 9.5 / 9.4 / 9.6  | +2.9 / +7.0   | .20  | 50 / 68 / 44
  k1 (built) 12.9 / 12.8 / 13.8 / 13.4 | +2.6 / +7.2 | 1.49 | 32 / 53 / 35
  a  flow    9.4 / 9.2 / 9.9 / 9.6   | -7.8 / -12.4  | .20  | 50 / 59 / 39   (flow alone: profile -9, but the front falls
             over the forehead 8 mm: flow is NOT the 3q lay lever)
  +lift .008/.005 (al)  7.2 / 8.3 / 8.9 / 9.6 | -8.6 / -13.4 | .17 | 50 / 60 / 37   (front stand-off down)
  +lift_ramp .02 (ar)   10.6 / 12.2 / 13.1 / 12.9 | -8.6 / -12.1 | 1.11 | 51 / 62 / 41  (= THE coverage_behind and
             back / nape stand-off cost of k1)
  +body_along .6 (ab)   14.2 / 11.4 / 12.2 / 11.1 | -4.5 / -7.8 | .73 | 48 / 51 / 40  (front stand-off PASS; some coverage)
  +fade.front.reach .01 (af) 7.9 / 9.2 / 9.9 / 9.6 | +1.0 / +5.3 | .18 | 21 / 46 / 27  (= THE LAY LEVER: 3q -29, hairline
             -12, hairline back in tolerance; front stand-off drops)
  +body front .016 (ad), sides lay .75 (ps), sides flow [0,2.5,-.2] (pf), sides lift .012 (pl), front / top lay .9 (pt):
             no effect beyond noise (sides lift: sides stand-off -1.7). The profile's sides do not answer to sides lay / flow.
  So successor 7's "the flow is the lay lever, the bundle is the cost" was wrong on both halves: the lay came from
  fade.front.reach, the coverage / back from lift_ramp; flow alone drops the front onto the forehead.

## Handover 2026-10-16 (successor 8, reconstructed)
Successor 8 was stopped past its tool-call clock with no handover; rebuilt from $HG/screen/scr_hg_*.json and styles/.
- STATE: NO screened variant passes. Nothing rendered since G60. The G63 sweep (d1 d2 d4 d5 d6) was written
  (styles/g_G63d*.json) and WAS running (scr.sh pid alive at restart; `pgrep -f screen` misses it while hround builds:
  check `pgrep -af "scr.sh|hround|screen.py"`). Successor 9 started a duplicate by mistake, killed it within seconds.
- Targets (screen.py): stand-off front / top / crown / sides / back / nape 14.5 / 12.7 / 10.9 / 12.6 / 12.1 / 9.3 +-3;
  hairline_centre 0 +-2, temple az30 0 +-6; coverage_behind <= 0.65 flat; lay 17.1 / 31.4 / 17.8 +-5.
- G62 (each = G61a (G59b + k1 flow) + body_along .6 front/top + fade.front.reach, plus one extra):
  (cols: stand-off f/t/c/s/b/n | hc / tc | cov_behind | lay 3q / profile / hairline)
  c1 reach .01            12.9/16.1/16.5/11.4/12.4/11.3 | +2.0 / +7.1 | .73 | 30 / 40 / 34
  c2 = c1 without body_along.top: IDENTICAL to c1 (body_along.top does nothing; front is the one that counts)
  c3 c1 + body.sides .012 : = c1 (sides +0.3) -> body.sides is dead
  c4 c2 + lift_ramp.sides .02: 15.1/16.2/16.5/13.3/14.1/13.4 | +2.6/+7.3 | 1.49 | 37/58/39 (ramp again = coverage + lay cost)
  c5 reach .02            13.9/16.2/16.5/11.4/12.4/11.3 | +0.8 / +6.2 | .73 | 32 / 45 / 33
- Best so far by item: G61af (reach .01 alone) has the best lay 21/46/27 (3q PASS, profile +15, hairline +9) and
  coverage .18, but front stand-off 7.9 (-6.6) and sides 9.2 (-3.4). body_along .6 buys the front stand-off (12.9-14.2)
  but costs the lay (+9 3q vs af), lifts top / crown to 16+ (+3.5 / +5.6 FAIL), and coverage_behind .73 (FAIL).
  So: reach and body_along fight over the lay; reach .02 on top of body_along gains only 1-5 deg.
- Lever effects (summary): fade.front.reach = lay (3q / hairline) + drops the front; body_along.front = front / top /
  crown stand-off + coverage_behind cost + lay cost; lift_ramp = coverage_behind + back / nape cost; flow = profile lay
  a bit but drops the front onto the forehead; body.sides, body_along.top, sides lay / flow: dead. temple_side +38 is
  constant on every variant (no hair down the temple side; no lever tried yet reaches it).
- NEXT: run G63 (body_along .3 with reach .01 / .02 = d1 / d2; lift.front .014 instead of body_along = d4 / d5; d6 = d4 +
  lift.sides .024 for the sides stand-off): the question is whether lift.front restores the front stand-off WITHOUT
  body_along's top / crown / coverage cost. The profile lay (+9..15 everywhere) has no lever yet.

## 2026-10-16 (successor 9): G63, the region-mean pitfall, G64
- G63 (screen; cols as above): af = reach .01 alone for reference
  G61af reach .01                 7.9/10.5/10.0/9.2/9.9/9.6   | +1.0/+5.3 | .18 | 21/46/27
  d1 body_along .3 + reach .01    9.9/13.2/13.1/10.6/11.2/10.4 | +1.5/+5.5 | .46 | 24/42/29
  d2 body_along .3 + reach .02    11.0/13.3/13.1/10.6/11.2/10.4| +0.3/+7.5 | .46 | 31/51/32
  d4 lift.front .014 + reach .01  10.3/12.4/10.2/9.3/9.9/9.6  | +1.2/+5.3 | .18 | 25/45/30
  d5 lift.front .014 + reach .02  10.9/12.7/10.2/9.4/9.9/9.6  | +0.7/+4.9 | .18 | 32/53/34
  d6 d4 + lift.sides .024         10.4/12.4/10.2/9.7/10.2/9.8 | +1.2/+5.3 | .18 | 25/44/30
  -> reach is NOT monotonic: .02 is worse than .01 on every pairing (+6..9 deg 3q). lift.front buys +2.4 mm front for
  +4 deg 3q, no coverage cost. lift.sides barely moves the sides stand-off (+0.4).
- PITFALL (hair_loose.by_region): a per-region dict gives the regions LEFT OUT the MEAN of those given, not the default.
  {"front": .6, "top": .6} for body_along put .6 on sides / back / nape too: that is where G61ab / G62 / G63d1's
  coverage_behind (.46-.73) and top / crown / back stand-off cost came from, not from the front. Name every region.
  (lift_ramp {"sides": .02} in c4 = .02 everywhere = the same as ar.) G64e7 / e8 retest body_along front-only.
- G64 (base d4 = af + lift.front .014 unless named; screen/tab.sh <variants> prints these rows):
  e1 lift_fall front .5           10.3/12.1/10.2/9.2/9.9/9.6  | +1.2/+5.3 | .18 | 27/47/31  (lift_fall: dead)
  e2 lift.front .02 + fall .5     14.1/14.8/10.2/9.4/9.9/9.6  | +1.8/+6.6 | .18 | 35/47/41  (front PASS, lay +10)
  e3 af + reach .006              7.0/10.1/10.0/9.2/9.9/9.6   | +0.9/+5.6 | .18 | 19/41/26  (BEST LAY so far: 3q PASS)
  e4 lift_ramp front .012         12.8/12.7/10.2/9.2/9.9/9.6  | +3.0/+7.4 | .18 | 37/49/47
  e5 lift_fall front+top .5       10.3/11.8/9.6/8.9/9.6/9.6   | = e1
  e6 length.front .065            = d4 exactly (front length is set by fade.front.reach: tips end reach past the line)
  e7 af + body_along front .6 ONLY 11.7/13.3/10.2/9.4/9.9/9.6 | +2.0/+7.0 | .18 | 28/45/33  (front PASS, NO coverage
     cost once the regions are named; lay +7)
  e8 af + body_along front+top .6  12.9/16.1/16.5/10.0/10.2/9.6 | .30 | 29/41/34 (top .6 = top / crown +6: the old cost)
  -> Front stand-off and lay are COUPLED through every front lever tried (lift, ramp, body_along: ~+1 deg 3q per
  +0.4 mm). reach: none 50, .006 19, .01 21, .02 ~30 deg 3q (U-shaped). Profile lay never under 41 (photo 31).
- G65 (base af = G61a + reach .01; f2.. change reach):
  f1 reach .006 + body_along front .6 10.6/13.1/10.2/9.2/9.9/9.6 | +2.4/+7.0 | .18 | 28/42/34
  f2 reach .004                    6.3/10.1/10.0/9.1/9.9/9.6   | +1.3/+5.8 | .19 | 18/38/27  (best lay; front -8)
  f3 reach .008                    7.4/10.3/10.0/9.2/9.9/9.6   | +1.0/+5.3 | .18 | 20/44/27
  f4 reach .006 + back .3          6.9/10.4/10.0/9.1/9.9/9.6   | +1.2/+5.0 | .18 | 20/45/26  (back: dead)
  f5 reach .006 + stiff top .25 / front .3  8.1/10.0/...       | 35/59/27  (low stiff: worse, gravity hooks)
  f6 reach .006 + body_along front .9 12.7/14.4/10.2/9.2/...   | +2.8/+7.4 | .18 | 31/42/40
  -> reach is monotonic below .01 (.004 best), None jumps to 50 (another code path). body_along.front buys the front
  stand-off at ~+1.3 deg 3q / mm, same exchange rate as lift. The profile lay sits at 38-45 whatever the front does:
  it is the top-side strands (flat: they arc down the side of the top), G66 tries the top flow bias.
- G66 (base f2 = af with reach .004):
  g1 reach .002                    6.0/10.1/10.1/9.1/9.9/9.6 | +1.2/+6.4 | .18 | 17/36/26
  g2 top flow bias [.4,3,-.5]      6.6/... | 18/42/26 (down: worse)
  g3 top flow bias [.4,4.5,.3]     6.5/10.3/10.2/9.1/9.9/9.6 | +1.4/+5.4 | .18 | 17/33/26  (PROFILE LAY PASSES: the top's
     back bias IS the profile lever; 3q and profile both in tolerance for the first time)
  g4 out.sides .15                 = f2 (dead)
  g5 body_along front .6 + lay.front .9   10.0/13.1/... | 28/39/35 ; g6 ba .9 + lay.front 1.0  11.9/14.2/... | 32/41/42
     (lay.front does not break the coupling)
  STILL FAILING on the best (g3): front stand-off 6.5 (photo 14.5), sides 9.1 (12.6), hairline lay 26 (18).
- G67 (base g3; h2.. on h1 = g3 + reach .002):
  h1 reach .002                    5.9/10.1/10.2/9.1/9.9/9.6   | +1.2/+5.9 | .18 | 17/31/26
  h2 top bias [.4,6,.3]            6.0/... | 17/29/27 (saturates past 4.5)
  h3 body_along front .6           9.6/12.8/10.5/... | +2.7/+7.2 | 28/35/37 ; h4 lift.front .014  7.6/11.8/... | 23/33/31
  h5 front bias [2.5,3,.6]         5.3/... | +2.2/+6.8 | 19/32/33 (front combed back: hairline lay worse)
  h6 length.sides .025             5.9/10.1/10.2/11.5/11.1/11.1 | +1.2/+5.9 | .16 | 17/32/26  (SIDES PASS: sides
     stand-off is the sides LENGTH, not lift / body / out. BEST: everything passes except front stand-off 5.9 vs 14.5
     and hairline lay 26 vs 18)
- G68 (base h6):
  i1 body_along front .4           8.6/11.9/10.4/11.5/11.1/11.1 | +2.3/+7.1 | 24/35/33
  i2 + lift.front .02              11.9/16.7/11.3/... | 39/39/51
  i3 front bias [2.5,.5,.6]        6.1/10.1/10.2/11.5/11.1/11.1 | +1.0/+5.4 | .16 | 15/32/24  (BEST: hairline lay +6)
  i4 lay.front .95 = h6 ; i5 messy.front .05 = h6 (dead) ; i6 ba .6 + messy .05 9.5/... | 28/36/37
  -> STUCK on the front stand-off: five levers (lift, lift_ramp, body_along, lay.front pressing, lift + body_along) each
  raise it only by steepening the 3q / hairline lay at ~1.3-2 deg per mm; none gives 14.5 mm at 17 deg.
- G69 (base i3):
  j1 front bias [2.5,0,.6]         6.3/10.1/10.2/11.5/11.1/11.1 | +1.1/+5.3 | .16 | 15/32/23  (BEST overall)
  j2 fade.front.width .01 / j3 density .5 / j4 both: hairline_centre -> 0 (+0.1 / -0.1 / -0.3), no stand-off, no lay
  j5 body.front .03                = i3 (body.front dead)
  j6 body_along front .3           7.6/11.2/10.4/... | +2.0/+6.6 | 21/32/28 (half step: +1.5 mm for +6 deg 3q)

## Handover 2026-10-16 (successor 9)
- VERDICT: FAIL, no variant passes the screen; nothing rendered (rule: render only a screened pass). 59 tool calls, 42
  variants screened (G63-G69), all levers logged above.
- BEST = G69j1 (styles/g_G69j1.json, model workspace/hg_G69j1, built): passes stand-off top / crown / sides / back /
  nape, hairline centre +1.1, temple az30 +5.3, coverage_behind .16, lay 3q 15 / profile 32. FAILS: front stand-off 6.3
  vs 14.5 (-8.2), hairline lay 23 vs 18 (+5.2, at the edge). temple_side +38 constant (no lever reaches it).
  Recipe from G61a: fade.front.reach .002, flow.top.bias [.4,4.5,.3], flow.front.bias [2.5,0,.6], length.sides .025.
- The levers that WORKED: reach (lay 3q / hairline, down to .002), top flow back-bias (profile lay), sides LENGTH
  (sides / back / nape stand-off), front flow less back (hairline lay). Dead: lift_fall, length.front (reach sets it),
  back, out.sides, messy.front, lay.front, body.front, body.sides, lift.sides (weak), fade.front width / density.
- STUCK (gates rule: 3+ approaches): front stand-off vs lay. lift, lift_ramp, body_along (front only), lay pressing
  and their combinations all raise the front only by steepening the 3q / hairline lay (~1.3-2 deg per mm). The photo's
  14.5 mm at 17 deg needs a front that is long and lying: with reach .002 the front-fade tips end 2 mm past the line,
  so the front zone has no length to build height from. Candidate NEXT (new capability, not a slider): a front zone
  whose locks keep their length (reach applied only to the hairline row, the rest of the front at length.front) with
  body_along front-only layered on; or measure whether the photo's front stand-off is the top's mass seen from the
  front (then the top's length / body_along.top named-only, not the front, is the lever). Coordinator / Joe call.
- PITFALL found: by_region gives regions left out the MEAN of those given (name every region).
- Tooling: screen/tab.sh <variants> prints one row per screened variant.

## Successor 10 (2026-10-16)
- Merged origin/main (hides, sim-key fix, game camera fix, game-distance gate). Hair tests green, one file per process.
- by_region FIX (hair_loose.by_region, the top-lay branch, _lengths): regions left out take the parameter's DEFAULT,
  not the mean of the given ones. Test test_regions_left_out_take_the_default. Scan of 6135 specs / styles
  (workspace/*/spec.json, hair_garrett/styles, examples, spikes): partial dicts in G60-G63 (body_along / lift_ramp
  {"front","top"} or {"front"}: those rounds' "front-only" body_along and lift_ramp reached sides / back / nape too,
  so their dead-lever verdicts are UNRELIABLE), old styles iE/iF/iG (length {"nape"}: nape length everywhere), and
  four family-head workspace specs (lay {"sides": .3} = .3 everywhere; names in workspace/private_notes/) were rewritten
  value-preserving (lay .3 named on every region). G64-G69 name every region: unaffected.
  STATE: fix + test in. NEXT: re-screen G69j1 (G69j1f), validate the front stand-off item.
- Re-screen of G69j1 under the fix (hg_G69j1f): identical numbers (front 6.3 / top 10.1 / crown 10.2 / sides 11.5 /
  back 11.1 / nape 11.1, hc 1.1, tc 5.3, ts 38.4, cov .16, lay 15 / 32 / 23).
- FRONT STAND-OFF ITEM VALIDATED (scratch s10/frontdiag.py <model> <out>: each view's front-region rays, grazing
  point az / el, stand-off, ours vs photo, + overlays fd_*.png). The front rows come ONLY from view 1 (3q, grazing
  |az| ~36, the forehead corner) and view 2 (profile, grazing |az| ~6, the forehead); view 0 gives none (its outline
  grazes the sides / top). So it is NOT the top's mass seen from the front camera. Profile el 30-45 / 45-55: ours
  6.6 / 8.7 vs photo 17.2 / 14.8 mm; 3q 2.5 / 5.2 vs 14.1 / 16.4. On the profile overlay the photo's front locks stand
  up and FORWARD over the receded front (a forelock ~1 cm over the forehead); ours end at the line, close to the
  skull. Real front-height gap: the item stands.
- NEW: fade.front.row (m): the reach cut only within `row` of the line; the front behind it keeps its length
  (test_front_reach_row_keeps_the_front_length). Screens G70a (row .012), G70b (row .012, front 35 mm,
  body_along front .5), G70c (row .02, front 40 mm, body_along .5, lift front 14 mm).
  STATE: G70a-c screening. NEXT: best of them + G69j1 in ONE NICO-TOP batch (b70: pairs + magenta + game 1 m / 3 m).
- TEMPLE_SIDE ITEM CHECKED (no lever built): it is view 0's |az| 40-50 bin, ours - photo median z of the hair / skin
  line. G69j1f per view (ours | photo, mm): view 0 bin 40 1745.0 | 1706.6 (the +38); view 1 (3q, the view that faces
  the temple) bin 40 1745.0 | 1745.6 (+-0.6: AGREES), bin 50 1739.1 | 1706.4; view 2 bin 40 1744.5 | 1749.6, bin 50
  1738.3 | 1724.7. So the +38 is where the photo's line turns DOWN the temple toward the sideburn: in the front view
  that near-vertical stretch grazes the camera and lands in bin 40, in the 3q view in bin 50. A median z per az bin
  of a near-vertical line measures where in the bin the descent falls, not a height. The item as written does not
  measure "temple height". Proposal: replace it with the |az| at which the line crosses a fixed z (e.g. 1730) in view
  1, ours vs photo (the descent's position: it looks ~5-10 deg further forward on the photo).
- G70 screens (stand-off f/t/c/s/b/n | hc tc ts | cov | lay 3q / profile / hairline; targets 14.5/12.7/10.9/12.6/
  12.1/9.3, lay 17 / 31 / 18 +- 5):
  G69j1f 6.3/10.1/10.2/11.5/11.1/11.1 | 1.1 5.3 38.4 | .16 | 15/32/23  FAIL front, lay hairline
  G70a   8.6/10.7/...                  | -9.2 -9.5    | .17 | 50/57/39  (long front falls over the line: hc -9)
  G70b  11.0/12.8/...                  | 0.9 7.1      | .16 | 29/47/31
  G70c  14.0/14.7/10.5/11.6/11.1/11.1 | 2.0 5.9 39.0 | .16 | 34/48/36  PASSES every stand-off; FAILS all three lays
  The row capability gives front height (14.0) without the hairline coverage breaking, but the coupling holds:
  the kept front length stands up STEEP (+13 to +18 deg on all lay items). Front height is no longer stuck; lay is.
- b70 batch on NICO-TOP (hgf70, remote/b70/, chain.sh RS="G69j1 G70c"): pairs + magenta + game set
  (views g1, g1y45, g1y90, g1y180, g3, g3y45 size 384 ss 1). G70c is in as the other side of the trade, so the look
  decides which error shows. Sheet script s10/gamesheet.py <out> <models...> (photo scaled to game px/m).
  STATE: hgf70 running. NEXT: remround tables + reviews, game sheet, MAJORs classified game-visible / close-up-only.
- b70 / hgf70 DONE (2 jobs, ~6.5 min each on NICO-TOP, game frames 118 s for 6 views incl. load). Gate tables
  ($TOUT/table_hg_G69j1.md, table_hg_G70c.md), reviews ($TOUT/review_hg_<m>/review.md), pairs ($TOUT/pairs_hg_<m>/),
  game sheet $TOUT/game_hgf70.png (rows g1, g1y45, g1y90, g1y180, g3, g3y45; ref | G69j1 | G70c), 1 m crop
  game_hgf70_1m.png. CAVEAT: the reference column is scaled by the photo's mm/px at the head and reads ~1.2-1.3x
  larger than ours: check the scale (frames' mm vs the stage camera) before the next sheet.
  RENDER ITEMS, G69j1 | G70c: stand-off front 6.5 FAIL | 14.1 PASS (others pass both); lay 3q / profile / hairline
  17.0 / 42.8 / 23.4 PASS (+-12) | 40.6 / 56.9 / 41.2 FAIL; hairline_centre +2.5 | +3.2 FAIL; temple_corners +7.1 |
  +21.2 FAIL; colour_front L* 32.6 | 34.5 vs 42.4 FAIL; grey_mix .15 | .22 vs .47 FAIL; flow_coherence .48-.61 |
  .49-.69 vs >= .7 FAIL (4 views); striping FAIL on 4 views both; hairline_edge 3.16 | 3.21 vs 3.13 FAIL;
  back_lightness 34.2 / 31.9 PASS both.
  REVIEW (blind) MAJORs, both FAIL, with my game-distance class from the 1 m / 3 m sheet:
  GAME-VISIBLE: (a) texture = white speckle / needle noise, not strands (coherence + striping agree); (b) colour
  darker, browner than the photo's silver salt-and-pepper, temples not lighter (colour_front, grey_mix agree);
  (c) no sideburn / temple too bare in front of the ear (profile and 3q at 1 m: obvious); (d) silhouette: sides
  and back flare (helmet / mushroom), back slab with a blunt hem; (e) hard, high, straight front hairline.
  CLOSE-UP-ONLY (recorded, not blocking): crown whorl centred / starburst and the crown seam line, the dark band
  at the hairline roots, the bristly hem detail. G70c adds a game-visible dark streak on top at the front (g1).
- VERDICT: FAIL. G69j1 stays the best (G70c buys front stand-off with lays +23..+25 and a dark top streak).
  The numbers that still fail are the RENDER items (texture, colour, sideburn) more than geometry: those are the
  game-visible ones.

## Handover 2026-10-16 (successor 10)
- Done: by_region fix + test (G60-G63 "front-only" verdicts unreliable), front stand-off item validated (real gap,
  forehead rays in views 1-2), fade.front.row capability + test (front height reachable: G70c 14.0), temple_side item
  shown to measure the line's descent position, not a height, b70 rendered with the game set (hgshots g<m>[y<deg>]).
- NEXT, game-visible first: (1) strand texture / coherence (speckle; look.variation, clump, fine_alpha; striping
  item); (2) colour + grey mix (seen lighter, grey share .15 -> .47); (3) sideburn / temple coverage in front of the
  ear (hairline.sideburns .022 is too short or the temple points too far back; a temple_side item measured as the
  descent azimuth in view 1 first); (4) side / back flare (lift.sides .02, back .018 are the suspects). Front height
  with row only if a lay-preserving comb is found (row + lay.front .9 + top flow back: untested).
- Fix the game sheet's reference scale first (CAVEAT above).

## Successor 11 (2026-10-16): game-sheet scale, new shape items, groom geometry + colour
- GAME SHEET SCALE (s11/gamesheet.py; scratch): the photo is now scaled by INTEROCULAR (bisenet eye centroids on the
  full frontal picture vs on the first model's g1 tile; one factor for every row). The frames' mm at the head centre
  is NOT the error source (cameras 1.7-2.8 m away: eye-plane vs centre depth only 2-3 %). Measured: photo IO 224.5 px
  = 63.2 game px at the mm scale vs ours 68.5 px -> photo x1.084 (the old sheet showed the photo ~8 % too SMALL).
  With the eyes matched, the photo's head + hair mass still reads larger than ours: that part is real proportion
  (head / hair size per interocular), not the sheet.
- NEW SCREEN ITEMS (screen.py): temple_descent = view 1, first 2-deg |az| bin from 30 out whose line median is under
  z 1730 (ours | photo; replaces temple_side, which measured where a vertical stretch falls in a bin); width_front
  +40/+60/+80 mm over the head centre (view 0 silhouette, head + hair, mm); hem z / soft / spread (view 2, 40-90 mm
  behind the centre: the hair's lowest edge, 0.8 -> 0.2 fall, p90-p10 of the edge height). tab.sh prints them.
  G69j1f: descent 65 | 51 deg (FAIL: our temple line descends 14 deg too far back), widths 170/139/86 | 174/146/90
  (ours NOT wider: the "helmet flare" is not a width excess at these heights), hem z 91 | 92, soft 6.6 | 8.2,
  spread 74 | 62.
  STATE: items in. NEXT: G71 screens (front forward lay on row, temple line forward + sideburns, grey + seen colour).
- G71 screens (cols: stand-off f/t/c/s/b/n | hc tc | descent ours/photo | lay 3q / profile / hairline):
  G71a G70c + front bias forward [2.5,-1.5,.6]        14.0/14.4/... | 1.9 6.5 | 65/51 | 34/47/37 (forward comb: lay unchanged)
  G71b a + lift.front .008 + body_along .3          9.1/10.6/... | 0.0 4.6 | 63/51 | 35/50/33
  G71c b + bias [1.5,-3,.3]                          9.2/... | -2.9 6.9 | 63/51 | 36/48/38
  G71d b + lay.front .9                              = b (lay.front dead again)
  G71t1 G69j1 + temple line forward (42.5-67.5 deg: 1739/1729/1716/1706/1699/1693 mm) + sideburns .03
                                                     5.9/10.1/10.0/11.5/11.0/11.2 | 1.1 5.6 | 53/51 PASS | 15/35/23
  G71t2 steeper line (1737/1722/1708/1699/1692/1687) + sideburns .036
                                                     6.4/10.0/9.9/11.9/11.0/10.9 | 0.8 5.4 | 51/51 PASS | 16/35/24, cov .24
  -> FRONT: the kept-length front's lay (34-36 deg 3q vs 17) does NOT respond to the comb direction (forward bias),
  lift, body_along or lay.front: it comes with the LENGTH (G69j1's short front lays at 15). Forward over-and-down needs
  a new capability (a bend along the lock: rise for the first cm, then lie forward), not these sliders.
  TEMPLE: the descent item passes with the line moved forward (t2: 51 = photo).
- G72 (screen, then the batch): a = t2 + colour (seen [.34,.326,.317] = L* +5, grey #999692 = +6, grey shares front .45
  top .35 sides .75 back .4 nape .2 temples .75 sideburns .7; photo light share .47 vs ours .15, L* 42.4 vs 32.6;
  chroma 4.1 vs 4.9, hue 66 vs 65: NOT browner by measure, the brown read is darkness); b = a + G70c's row front at
  28 mm, body_along .3, lift .01 (a middle trade); c = a + fade.taper .045 (hem softness 5.5 vs 8.2 mm).
- G72 screens: a 6.4/10.0/9.9/11.9/11.0/10.9 | hc .8 tc 5.4 | descent 51/51 | lay 16/35/24 | FAIL front, hairline lay
  b 9.8/11.3/10.2/12.0/11.0/10.9 | hc 1.5 tc 6.0 | 51/51 | lay 22/41/26 | FAIL front (-4.7), profile lay (+10), hairline (+8)
  c (taper .045) = a with sides stand-off -1.3 and hem softness unchanged (5.4 vs photo 8.2): taper does not soften
  the hem edge; dropped. Widths stay 170/140/85 vs photo 174/146/90 (ours a little NARROWER: no flare excess measured).
- b72 on NICO-TOP (hgf72, remote/b72/, RS="G72a G72b", same views as b70 incl. the game set).
  STATE: hgf72 running. NEXT: remround tables + reviews, s11/gamesheet.py (interocular) ref | G69j1 | G72a | G72b.

## Handover 2026-10-16 (successor 11)
- VERDICT: FAIL so far (screen): no variant passes front stand-off AND the lays. Renders of G72a / G72b are queued
  on NICO-TOP (hgf72, queued 20+ min behind other batches at handover); chain remote/b72/chain.sh (client pid in
  `offload status`) runs the remround tables + blind reviews itself and touches tmp/rr_72.done.
- Done: (1) game sheet scale fixed by interocular (s11/gamesheet.py: photo x1.084; the photo was SMALLER, and with
  eyes matched its head + hair mass still reads larger: real proportion). (2) Front: forward comb / lift / lay.front
  on the kept-length front do not lower its lay (G71a-d): lay comes with the length -> needs a new capability (a lock
  that rises then bends to lie forward), G72b is the middle trade (front 9.8, lay 22/41/26). (3) Temple: temple_descent
  item (view 1, |az| of the line crossing z 1730) replaces temple_side; the line moved forward + sideburns .036 passes
  it (51 = photo 51) at no lay / coverage cost (G71t2). (4) Flare / hem: width_front and hem items measure ours a
  little NARROWER (170/140/85 vs 174/146/90) and the hem at the photo's height; no width flare to fix; hem softness
  5.5 vs 8.2 mm and fade.taper does not move it. (5) Colour: measured not browner (chroma / hue match), darker; G72
  sets seen L* +5, grey +6, grey shares up (front .45 top .35 sides .75 back .4 nape .2): verify on hgf72's cmp.
- NEXT: when tmp/rr_72.done exists: read $TOUT/table_hg_G72a.md / G72b, review_hg_<m>/review.md; then
  `./run.sh $HG/s11/gamesheet.py $HG/s11/game_hgf72.png hg_G72a hg_G69j1 hg_G72b` (crop rows 0-1212 for the 1 m sheet)
  and classify MAJORs game-visible / close-up-only; colour_front / grey_mix from cmp_hg_G72a.txt (if short: colour_step).
  Then the front bend capability (rise then lie forward), screened on lay + stand-off together.
- Privacy: tracked notes no longer name family heads; one older commit SUBJECT on this branch (91de24ef "profover:
  ...") still names one: rewording needs a history rewrite of unpushed commits: coordinator's call.

## Successor 12 (2026-10-16): bend capability, head vs hair proportion
- BEND (src hair_loose.py `groom.loose.bend`, commit 68e1fd59): a per-region lock PROFILE: rise straight for `rise` m
  (leaning `up` 0..1 to the scalp normal; no gravity, no lay on the way up), bend by `angle` deg toward the comb over
  `arc` m, then lie with its own `lay` (replaces the region's lay after the bend) and the region's stiff. Bend locks are
  resampled every 4 mm (the 2 cm resample turned the bend into a chord). Test tests/test_hair_loose.py::
  test_bend_rises_then_lies_over measures on synthetic ball-head locks: height at the bend 12 +- 2.5 mm, angle 90 / 60
  +- 12 deg (60 measured with lay 0 + stiff 1: lay 1 presses any lie flat onto its height, as it should), after-bend
  elevation |.| < 15 deg, zero-rise regions bit-identical, plain front lock < 6 mm at the same arc.
- HEAD vs HAIR PROPORTION (coordinator's item 3; s12/iomm.py + s11/ioprobe.py on hg_G72b, view 0 fitted camera):
  photo eye-mask centroid IO 224.5 px; ours projects 227.9 px (eye_front, cornea apex) / 237.5 (eye centres) in the
  SAME fitted camera: ours only 1.5 % wider at the eye plane. The game sheet's x1.084 is mostly PERSPECTIVE: the game
  camera stands 1 m from C - 4 cm, the eyes 86 mm in front of C -> magnified ~9.4 % against the outline's plane; the
  photo camera (2.77 m) magnifies them only 3.2 %. Matching by interocular blows the photo's OUTLINE (head + hair, near
  C's depth) up by ~6 %: that is the "photo's head and hair still read larger". The head's outline is matched by the
  fitted camera (block-in), so the HEAD is not bigger (eye spacing 1.5 % wider is head-shape, for the coordinator).
  What is real and mine: the hair is a little SMALLER than the photo: stand-off front 9.8 vs 14.5, top 11.3 / 12.7,
  back 11.0 / 12.1, sides 12.0 / 12.6; widths +40/+60/+80 170.7 / 140.1 / 87.3 vs 173.7 / 145.9 / 90.2 (-2..-4 %).
  Sheet fix: scale the photo per DEPTH (outline at mm@C, K = 1; the face K = (Zc/Zeye)_game / (Zc/Zeye)_photo ~ 1.06),
  or judge outline rows at K = 1 (NOIO=1).
- BEND SCREEN (s12/scr_G73..76.log, screen/log_G7[3-6]*.txt; base G72b: front 9.8, lay 22.1 / 41.3 / 26.5 vs photo
  14.5 / 17.1 / 31.4 / 17.8). VERDICT FAIL: no variant passes front stand-off AND the lays. The bend buys height
  (front 14.0-16.6 PASS) but every bend variant's lays are WORSE than G72b's:
  | round | change | front | lay 3q / profile / hairline |
  | G73a-d | rise .012-.016, up .7-.8, no from | 9.9-11.3 | 27-33 / 38-40 / 38-46 (rising hairline row = bristles) |
  | G74a-d | + from .012-.015, rise .018-.022 (+ top .006) | 12.1-14.1 | 35-50 / 40-42 / 46-62 (the lie hooks DOWN the forehead: the front comb from the crown points down it) |
  | G75a-d | + toward [1,-.3,.2] for ALL bend locks | 16.2-16.6 | 56-63 / 65-75 / 52-57 (the top's bend locks turned sideways too) |
  | G76a-d | toward per region {front: ..} | 12.3-14.1 | 39-47 / 47-58 / 44-54 |
  Seen on the G76 rasters (s12/cmp_G76.png): the lie-over tops now arc sideways as wanted, but below them a band of
  vertical RISING shafts shows (nothing covers them from the front) and the hairline row's short rises hook. In the
  photo the lie OVERHANGS forward past the roots and hides the rise. Capability additions this round (all tested):
  bend.from (rise ramps in behind the line), bend.toward (world lie direction, per region).
- NOT LAUNCHED: the NICO-TOP bend batch (coordinator item 4): the screen fails, so a batch would render a known FAIL.
  hgf72 (G72a done, G72b rendering at handover) is the chain's own; its tables / reviews land at tmp/rr_72.done.
- NEXT (successor 13): (a) when tmp/rr_72.done exists: G72a/b render items (colour L*, grey mix from cmp_hg_G72*.txt;
  coherence / striping), reviews classified game-visible vs close-up-only; the helmet read: compare top curvature and
  hem line SHAPE (screen's widths / hem items) before calling it texture (texture -> hair-cards thread).
  (b) bend: make the lie COVER the rise: a forward overhang (toward with more -y, longer after-bend length: lie length
  >= rise + the from band) and NO bend on the hairline row (bend weight 0 under `from`, not a short rise that hooks:
  make `from` gate the bend itself, rise_b = 0 there). Also check whether the hair_even strands (interpolated between
  locks) reproduce the vertical shafts: measure lay per object (screen prints hair_even / hair_under). Screen only
  front + lays; then ONE batch (--stage _g3_hg_h6, remote/b72/chain.sh as the template, own folder b7x) with the best.
  (c) gamesheet: scale the photo per depth (outline K = 1), see the proportion note above.
- PRIVACY: branch commit 91de24ef's subject names a family head. Not rewritten (coordinator). The MERGE to main must be
  squashed with a GENERIC message; branch subjects never reach the public repo.
- STATE: bend capability on branch (68e1fd59 + from + toward), screen FAIL, no batch launched. NEXT: (b) above.
- hgf72 LANDED (07:14, $0; tables out/table_hg_G72a|b.md, reviews out/review_hg_G72a|b/review.md): VERDICT FAIL both
  (G72a 38 MAJOR lines, G72b 28). COLOUR OVERSHOT: G72's raise (seen L* +5, grey +6, grey shares up) made it too
  LIGHT: cmp_hg_G72b view 1 L* photo 34.1 | ours 41.2, light share .26 | .48; view 2 39.4 | 38.2 (ok); back_lightness
  photo 34.8 | ours 51.8 (crown-back 34.6 | 49.6). Every review pair says "too light / silvery white". colour_front and
  grey_mix rows are n/a in the table (cmp didn't write them: run colour_step). Coherence .48-.63 vs >= .7 FAIL,
  striping 3 of 4 FAIL. Review MAJORs by cause: colour (all views); sides / back stand-off + flare ("helmet", "skirt to
  mid-ear", back 150 vs 117 px behind the ear: the reviewers see SILHOUETTE flare at the sides / back although
  width_front at +40..+80 mm measures us narrower: those items sit ABOVE the ear; add a width item at ear height and
  a back stand-off item behind the ear in view 2); top / crown seam (two flows meeting); hard hairline edge; nape hem
  bristly. Game-distance classification NOT done this session (gamesheet not run): next step.
- NEXT first: revert the colour raise toward G69j1 (seen L* target from view 1: -7; light share .26), add the
  ear-height width / behind-ear stand-off items, then (b) bend overhang.

## Successor 13 (2026-10-16): colour by region, ear-height items, bend gate, depth-scaled game sheet
- COLOUR READ CORRECTED: cmp_hg_*.txt prints `ours | picture` (the picture's numbers are constant across rounds). The
  handover's "view 1 photo 34.1 | ours 41.2" was read backwards: view 1 is ours 34.1 vs photo 41.2 (ours DARKER by
  mean, but the mean is shadow-heavy), view 2 ours 39.4 vs 38.2 (ok), back_lightness ours 51.8 vs 34.8 (too LIGHT),
  light share view 1 top .459 vs .221, view 2 back .532 vs .223. The game-distance review and the reviewers all say
  "nearly white / silvery": the overshoot is the GREY MIX (G72 raised back 0 -> .4, nape 0 -> .2, top .18 -> .35),
  not a uniform -7 L*. G77/G78 colour (between G69j1 and G72b per region, from those numbers): seen .315 (G69j1 .294,
  G72b .34), grey #918d89, grey top .22, front .35, sides .65, back .10, nape .05, temples .65, sideburns .6. Back
  share target .223 interpolates to grey ~.14 and back L* 34.8 to ~.01: .10 between. Needs the render to measure.
- NEW SCREEN ITEMS (spikes/hair_garrett/screen.py, e0ae1a7f): width_front at C +0 / -20 / -40 mm (ear height),
  back_extent +0 / -20 / -40 mm (profile view: how far the silhouette reaches behind C), hem_soft with a tolerance
  (+- 2.5 mm, flat). On G72b they FAIL as the reviewers saw: width +0 199.0 vs photo 186.9, -20 191.4 vs 183.4;
  back extent 114.0 / 115.1 / 111.7 vs 109.4 / 108.9 / 104.7. (+40..+80 widths pass: the flare is at ear height.)
- FLARE (G77, s13/scr_G77.log): sides / back lift .02 / .018 -> .012 (G77b, d) kills the flare (width +0 186.9, back
  extent PASS) but the stand-off rays' median falls to 8.3-8.7 vs 12.6 / 12.1 (FAIL); sides / back lay .6 / .5 + out
  .03 (G77c) changes nothing. The flare is the LOWER part of the side locks: G78a-d try lift_fall (the lift given
  back toward the tip) to keep the high stand-off and pull the ear-height silhouette in.
- BEND GATE (src hair_loose.py, 1e8446d4): bend.from now gates the bend: roots under BEND_GATE (.35) of the ramp get no
  bend at all and lie as plain locks (a short rise bent by the full angle was the hairline row's hook); test
  test_bend_from_gates_the_bend (hairline-row locks identical to the no-bend groom).
- GAME SHEET BY DEPTH (s13/gamesheet.py + s13/gameround.sh): the photo is scaled at the head centre's depth (K = 1:
  the hair outline to scale); the label prints K_face (1 m 1.060, 3 m 0.998: the face is nearer both cameras, the
  1 m game camera magnifies it 6 % more than the 2.77 m photo camera). DEPTH=face scales by K_face; IO=1 is the old
  interocular match. gameround.sh writes the 1 m / 3 m pairs and runs the blind review on them
  ($TOUT/review_<m>_game; ERROR file when pairs are missing).
- BEFORE (G72b) game-distance review: 17 game-visible MAJORs (out/review_hg_G72b_game/review.md): hairline reads too
  high / temples bare (the photo's front mass overhangs the forehead: the bend overhang item), sides puffed at temple
  height (the flare), colour nearly white, grainy surface / no comb direction ("gravel", "coiled"), flat top, a ragged
  strip in front of the ear, squarish back. Skin MAJOR -> other stage.
- G78 / G79 SCREENS (s13/scr_G78.log, scr_G79.log; screen/log_G7[89]*.txt):
  - lift_fall did NOTHING on sides / back (G78a, c identical to G72b): lift_ramp (default 3 cm) is longer than those
    locks (2.5 / 1.5 cm), so the fall never starts. With lift_ramp .008 (G79a) the lift lands lower: sides / back
    stand-off up (14.4 / 13.4) and the flare WORSE (width +0 197.5, back extent 116-117). Not the lever.
  - FLARE FIX = less root lift + shorter back: G78d (lift sides .016, back .015, back length .012) passes width +0 /
    -20 (192.8 / 189.0 vs 186.9 / 183.4), back extent +0 / -20 / -40 (110.9 / 111.4 / 108.6 vs 109.4 / 108.9 / 104.7),
    sides 9.7 PASS, back 8.7 vs 12.1 FAIL (-0.4 past tol), hem_soft 4.4 vs 8.2 FAIL. G79b (= G78d, back lift .018):
    back 9.5 PASS, width +0 193.4 FAIL (+0.5 past), back extent -40 FAIL (+0.7 past), hem_soft 4.5 FAIL. Both keep
    G72b's front 9.3 FAIL and lays 22 / 42 / 26.5 (profile, hairline FAIL). Both rendered in hgf79.
  - BEND OVERHANG FAILS AGAIN (G78e-h: front length .05-.06, rise .012-.016, from .010-.015, toward forward
    [.6..1, -.8..-1, -.1..-.2], angle 110-120): front stand-off only 10.2-10.5 (the gate takes the rise off the first
    rows, so less height than G74-G76) and lays 52-58 / 56-58 / 40-50 (front region 69-74 deg in 3q).
  - INTERPOLATION IS NOT THE CAUSE: per object, hair_even 43-49 deg vs hair_under 25-31; with the even layer on the
    nearest guide (strands.even_guides 1, G79c) or 2 (G79d) the even lays are the same (46-48). The even children copy
    the BEND GUIDES' own shape; the under layer (1.6 cm) is too short to reach the bend. The upright band is the
    guides' rise itself, seen past a lie that is too short / too high to cover it. Next idea (not tried): the rise
    lower and shorter (rise <= .008) with a longer, flatter lie (lay 1, angle 140+, after-bend length >= 3 cm) so the
    lie sits in front of the rise from the front camera; or drop the bend and get front height from body_along.
- hgf79 LANDED ($0, NICO-TOP; tables out/table_hg_G78d|G79b.md, reviews out/review_hg_<m>[_game]/review.md, 1 m / 3 m
  sheet out/game_hg_G78d.png = photo at head-centre depth | G78d | G72b). VERDICT FAIL both.
  | model | game-visible MAJORs (1 m / 3 m) | close-up MAJORs | table PASS / FAIL | L* v1 / v2 (photo 41.2 / 38.2) |
  | G72b (before) | 17 | 27 | 12 / 13 | 34.1 / 39.4 |
  | G78d | 16 | 26 | 7 / 18 | 31.2 / 28.5 |
  | G79b | 16 | 34 | 9 / 17 | 30.0 / 28.4 |
  Gone at game distance: "sides puffed above the ears" (the flare fix reads) and "hairline too high". Left, by cause:
  (1) SURFACE / CONTRAST: "speckle noise, not hair", "curly / wiry", "white flecks on near-black" in every view, flow
  coherence .49-.64 vs >= .7: the grey strands are near-white over a near-black base. The MEAN L* is now too DARK
  (31 / 28.5) while the reviewers still say "too white": the fault is the VALUE RANGE between the grey and dark
  strands, not the mean. CAUTION: cmp says G78d's shadow / highlight L* are BOTH under the photo's (v1 18.9 / 43.5
  vs 28.3 / 54.1; v2 17.5 / 39.1 vs 24.3 / 53.1): the whole range sits low, yet the eye sees white flecks on black.
  The flecks are thin single strands (sub-pixel at 1 m), so area statistics miss them. Next: measure the fleck
  contrast first (strand-scale L* p95 - p5 on a 1 m crop, ours vs the photo), then lift the base (seen up, shadow
  L* +8) and calm the grey strands' value against it; don't darken the grey by eye. (2) FLAT TOP / no front lift (front stand-off 9.3 vs 14.5; the bend screens still fail the lays).
  (3) comb direction unread (follows (1)). (4) G78d close-up: back slab / ragged hem at jaw level behind the ear
  (profile), a dark blotch at the front-centre crown, straight temple edge.
- STATE: G78d = best (flare fixed, game MAJORs 17 -> 16, FAIL). Code: screen items e0ae1a7f, bend gate 1e8446d4.
- NEXT (successor 14): (a) value range: grey hex + seen from the cmp shadow / highlight rows, screen nothing (colour
  needs a render): ONE batch, 2 variants. (b) front lift without the bend's band: body_along / lift on front only,
  or a lower shorter rise with a long flat lie (see the G78 / G79 note). (c) G78d's back slab: back length / hem.

## Successor 14 (2026-10-16): the outline TRACED from the photo, scope split (strand-render / cards), colour by measure
- SCOPE (coordinator, A): the game asset is CARDS. Speckle, flecks and strand contrast at 1 m are strand-render
  effects the card pipeline replaces (hair-cards thread): review items of that kind are listed as "strand-render /
  cards", outside this thread's gate count. The groom's COLOUR is still fixed by measurement (the cards bake from it).
- TRACE (B; src hair_loose.py `groom.loose.trace`, spikes/hair_garrett/fronttrace.py + mktrace.py): the photo's hair
  outline through the fitted cameras, per outline ray (hair_read.outline_rays on the photo's frame, views 0 / 1 / 2):
  the skull edge's scalp point (az, el) and the stand-off there; the same rays on screen's flat raster of ours. Locks
  rooted in `trace.regions` are HELD at the traced height where they pass over the traced area (Gaussian `sigma` deg),
  layered (`under`), reached over `rise` m, the hairline row lying (`from` m). The heights are SOLVED, not swept:
  mktrace's fixed-point step h_cmd *= h_photo / h_ours per ray (clipped .6..1.8), against the screen's own outline.
  Per-ray read of G78d (s14/trace_G78d.json): front deficit is at the far temple-front corner in the 3/4 view (az 322,
  el 35-52: photo 13-16 mm, ours 5-9) and the profile's hairline (el 27-36: the photo's front edge stands 11-17 mm
  off the forehead, ours never meets the backdrop there); back: 3/4 view back-side (az 133) photo ~20 vs ours ~10,
  profile back-centre (az 166) photo 3-5 vs ours 6-10 (the back is too FULL at the centre, too thin at the sides).
- SCREENS (styles/g_G80*.json, screen/log_G80*.txt; stand-off front / back, lays 3q / profile / hairline):
  | G78d (before) | 9.3 F / 8.7 F | 22.3 / 42.0 / 26.5 |
  | G80a/b rise .008 | 11.2 F / 8.7 F (b: 11.6 P, back samples) | 32.7 / 46.0 / 50.8 |
  | G80f-i rise .025, from .01, under .6 | 9.4-9.7 F / 10.1-10.2 P | 22.3 / 42.3 / 28.7 (= G78d) |
  | G80k-m hairline row held (from 0) + dense front edge | 10.0-10.8 F | 41-49 / 59-64 / 48-52 (bristles) |
  | G80n (G80i + one solve step) | 11.6 P / 10.5 P | 28.0 / 44.6 / 37.2 |
  | G80q-s (2nd step, from .02 / .03, under .4) | 11.4-11.9 / 10.8-10.9 | 24.7-27 / 42-44 / 34.8-39.6 |
  | G80u (G80r + hem taper / rough, messy front .05) | 11.8 P / 10.8 P | 26.1 / 43.6 / 37.3 |
  Every stand-off row and the width / back-extent rows PASS from G80n on (G80u: width +80 97 vs 90 +-6, 0.5 over);
  lays FAIL and are worse than G78d at the hairline (+11 deg): height gained over a 2.8 cm lock is rise you can see
  from the front. The profile lay's excess is the SIDES (share .46-.48 at 51 deg), not the front, in every variant.
  hem_soft does not move with fade taper / rough / density (4.2-5.2 vs 8.2): not the lever, unexplained.
- COLOUR (D; G78d cmp: mean L* 31.2 / 28.5 vs 41.2 / 38.2, shadow 18.9 / 17.5 vs 28.3 / 24.3, highlight 43.5 / 39.1
  vs 54.1 / 53.1, light share .18 / .12 vs .48 / .42, back light share .01 vs .43 / .22, L_sd matched 11.0 vs 11.6):
  the whole range sits low and the grey share is low, not a too-wide range. G81a = G80u + seen x1.5 linear
  ([.383 .367 .357]) + grey x1.15 (#9b9692); G81b = seen x1.8 ([.418 .400 .389]), grey kept; both: grey front .55,
  top .30, sides .75, back .22, nape .10 (between G78d and G72b per region by the light-share rows).
- BATCH hgf81 (remote/b81/chain.sh, RS="G81a G81b"): gate renders + game set, then remround / gameround vs hg_G78d.
- hgf81 LANDED ($0, NICO-TOP; out/table_hg_G81a|b.md, out/review_hg_G81[ab][_game]/review.md, 1 m / 3 m sheet
  out/game_hg_G81b.png = photo | G81b | G78d). VERDICT FAIL. Game-visible MAJORs, split per the coordinator's scope:
  | model | shape | colour | strand-render / cards | total | render stand-off front / back / nape | lay hairline (render) |
  | G78d (before) | 8 | 3 | 4 | 15 (+ skin) | 9.2 F / 8.9 F / 5.9 F | 26.5 P |
  | G81a | 9 | 6 | 2 | 17 | 12.1 P / 11.2 P / 5.9 F | 36.5 F |
  | G81b | 6 | 6 | 3 | 15 | 12.1 P / 11.0 P / 8.5 P | 35.2 F |
  Render tables: G81b every stand-off row PASSES (first time: front 9.2 -> 12.1 vs 14.5). Shape MAJORs left on G81b:
  hairline a hard flat cut-out, little top volume / no front lift (still seen: the trace's +3 mm doesn't read as the
  photo's forelock projection), temple a hard step, outline flat front + bulging rear crown, back / nape boxy and too low.
  The "back slab hanging to jaw level" item of G78d is gone; the low back remains.
- COLOUR OVERSHOT (my fault: two changes on one row). Base lift + grey shares together: light share .70-.76 vs .47
  (top .80 vs .22, sides .95-.98 vs .59), view 0 mean L* 47.4 vs 42.4, shadow 36.8 vs 30.7. And back .22 against sides
  .75 made a HARD SEAM behind the ear (all three reviews). Next: G78d's grey shares back, ONLY seen lifted (x1.35 linear:
  view 0/1 shadow then ~+6 L*), back / sides shares within .3 of each other; one change per row, measured.
- STATE: best SHAPE = G80u geometry (G81b without its colour); best COLOUR = G78d's. Code: trace f2f87255, test 7e49f110.
- NEXT (successor 15): (1) colour as above (G82 = G80u geometry + G78d grey + seen x1.35), screen nothing, one batch.
  (2) the hairline lay (35 vs 17.8; the traced height costs ~10 deg there): the photo's front edge stands as a projected
  forelock; the trace holds locks only radially. Try a hold whose target is the traced outline POINT (profile view: the
  hair's 3D edge on the midline plane) so the front locks run forward over the line, not up. (3) hem_soft never moved
  (4.2-5.2 vs 8.2): read how screen.hem measures before trying more fade keys. (4) Hand to the cards pipeline only once
  shape MAJORs are low: they are 6 now; propose it to the coordinator, don't export.

## Successor 15 (2026-10-16): colour by seen alone, the seam diagnosed, forward hold, hem item fixed
- Merged main 1547b2ed; hair tests all pass (pytest per file; test_hair_lift / strands / tied run as scripts).
- SEAM behind the ear is NOT the grey map. Lock grey by (|az|, el) is continuous in G78d and G81b (sides .70-.74 ->
  back .22-.29 over |az| 80-180 at blend 2.2, the step to 8 neighbours p90 .05), and lock DIRECTION is continuous
  across the back (s14/seam.py: jump to neighbours 3-9 deg, ~20 only at the whorl). The render's block (rear view: a
  horizontal edge at the whorl's height across the width plus a band at the left side, tone AND direction) is born
  in the strand children (even layer / under layer in Blender), not in the locks: a strand-render item. The cards
  bake grey from the locks (hair_cap.strand_grey), so it should not carry over to cards. Unlocated: a next step
  is the child curves' hp_gr / direction read back from the Blender geometry (no render).
- whorl.spiral 70 -> 120 (G82d) changes NOTHING in the screen (identical to G80u): the key doesn't reach the locks.
- FORWARD HOLD (src hair_loose `trace.forward`, test test_trace_forward_leans_the_front_hold_over_the_hairline):
  the hold's push leans forward along the scalp by forward x the root's front weight. Screens (lay 3q / profile /
  hairline, target 17.1 / 31.4 / 17.8; front stand-off 14.5):
  | G80u (before) | 26.1 / 43.6 / 37.3 | 11.8 |
  | G82b forward .6 | 20.7 / 37.4 / 42.8 | 12.5 |
  | G82c forward 1.0 | 18.5 P / 35.0 P / 42.8 F | 12.4 |
  3q and profile lays PASS for the first time; the HAIRLINE lay gets worse (+5.5): FAIL. Leaning the push forward
  doesn't make the hairline row lie across. Next: read the per-region hairline numbers (front vs top share).
- HEM_SOFT read the wrong thing: the photo's "hair" is the parsing net's probability, ours was strand coverage.
  screen.py now runs the same net on our flat image ("hem_soft (net, as the photo)"). G80u: 13.5 against 8.2. Ours
  is too SOFT, the opposite of the old row (4.9). The fade isn't too hard, it's too wide or thin. Untouched.
- COLOUR: G82a = G80u + seen x1.35 linear ([.364 .349 .339]), G78d grey; G82e = x1.7 ([.407 .390 .379]). Estimate
  from L* = 116 Y^(1/3) - 16: G78d's 31.2 needs ~x1.9 linear for 42.4, so x1.35 likely lands ~36. The bracket
  measures it.
- BATCH hgf82 (remote/b82/chain.sh, RS="G82a G82e G82c"; launched detached 2026-10-16, $0 NICO-TOP): gate renders +
  game set, then remround / gameround vs hg_G78d (tmp/rr_G82*.log, tmp/rg_G82*.log, out/game_hg_G82*.png).
- Not done: shape items (4) unmeasured this session (hairline cut-out, temple step, profile top curve, boxy back).
- STATE: best geometry G82c (G80u + forward 1.0) on 3q / profile lays; colour pending hgf82. Code a9b85ad0, 371141b1.
- NEXT: (1) read hgf82: pick seen by L* / light share (interpolate between x1.35 and x1.7). (2) the hairline row's
  lay. (3) hem: the net says too soft; narrow the fade taper. (4) the seam in strand children. (5) shape items.
  Shape MAJORs are still 6 and the hairline lay still fails, so it's not time to hand over to cards.

## Successor 16 (2026-10-16): the hairline lay is not the hairline row; a per-side lean passes all three lays
- hgf82 read (gate tables, same cameras): colour_front L* / light share: G82a (seen x1.35, no forward) 40.6 / .431,
  G82e (seen [.407 .390 .379]) 43.3 / .549, G82c (x1.35 + forward 1.0) 38.0 FAIL / .361. The forward hold darkens
  the front read by 2.6 L*. back_lightness FAILs in all three (43.9 / 47.0 / 43.9 vs 34.8: the back is too LIGHT,
  and more seen makes it worse); game reviews call the hair too light and contrasty (white flecks on black speckle),
  so the front's low L* is not "too dark overall". Pick: seen [.4098 .3926 .3815] (G82a x1.125; slope 64 L* and 2.8
  share per unit seen from G82a -> G82e: est. L* ~40.9, share ~.49 on the forward-hold geometry).
- WHICH LOCKS MAKE THE HAIRLINE CROP'S LAY (spikes/hair_garrett/hlrow.py, G82c, by strand root distance behind the
  line): 0-10 mm 6% of visible length (27-29 deg), 10-20 mm 18% (33-36), 20-30 mm 21% (44.5), 30-45 mm 36% (47.8),
  45+ 18% (31.5). The crop is made by roots 20-45 mm back, where the trace hold is full (trace.from 0.03) and the
  forward lean acts: not the hairline row. orgrid.py (signed orientation, 4x4 windows): the photo's front is a DOME
  (his right side +25 / +37 deg rising to the image right, centre +9 / +14, his left -18 / -22, coherence .77); our
  render's left side (his right) was vertical (-88 / +84, coherence .2-.4), his left already matched (-13 / -21).
- Flow bias does nothing there (front bias x 2.5 -> 4: 43.0; top bias x 0.4 -> 2: 45.0, profile FAIL): the hold
  decides the path. src: trace.forward takes a world direction [x, y, z] or per side {"left", "right"} (blended over
  az +-10; test_trace_forward_per_side_sweeps_across). Screens (lay 3q / profile / hairline; target 17.1 / 31.4 /
  17.8 +- 5):
  | G82c forward 1.0 | 18.5 P / 35.0 P / 42.8 F |
  | G83L1 all [.8 -.6 0] | 35.0 F / 46.3 F / 27.1 F |
  | G83S1 right [.8 -.6 0] (over the top) | 27.6 F / 36.6 P / 31.3 F |
  | G83S3 right [-.8 -.6 0] (down to his right temple) | 17.6 P / 35.8 P / 24.8 F |
  | G83S5 right [-1 -.4 0] | 17.6 P / 35.3 P / 23.6 F |
  | G83S6 right [-1.1 -.7 0] | 17.2 P / 35.1 P / 22.6 P |
  The lay is axial, so +x and -x read the same angle in the front view; the paths differ (over the top crosses
  into the 3q crop, down the temple doesn't).
- HEM (net soft, target 8.2 +- 2.5; G82c 13.7): fade.taper .045 -> .027 12.6, .015 9.7 P, .012 11.7 (not monotonic:
  the per-lock rough jitter); rough .006 -> .003 13.0; floor .3 -> .15 13.4. Taper .015 taken; spread grows 98 ->
  107 (photo 61.5): the edge's height varies more behind the ear, next item for the hem.
- SHAPE items measured (G84b screen, ours | photo, mm): widths at z +80 98.2 | 90.2 (+8: the flat / wide top the
  reviews call boxy), z 0 192.8 | 186.9, z -20 189.3 | 183.4 (sides flare +6); back_extent at z -40 108.6 | 104.7
  (+3.9: the boxy low back), 0 / -20 +1.5 / +2.8; M shape (temple - centre) 0.1 | -3.9; temple_side (az 40, uncal.)
  +35. The hairline_edge row PASSES (2.34 <= 3.13) while every review calls the edge hard: that checklist item is
  incomplete (gates rule) and needs a measure the eye agrees with before any change. Not changed this round.
- BATCH hgf84 (remote/b84/chain.sh, RS="G84b G84a", NICO-TOP, $0): G84b = G82c + forward {"left": 1.0, "right":
  [-1.1, -0.7, 0]} + fade.taper .015 + seen [.4098 .3926 .3815] (screen: 17.6 P / 35.5 P / 22.2 P, hem_soft 9.6 P,
  hairline_centre 1.6 P); G84a = same with right [-.8 -.6 0] (24.7 F). Styles in $HG/styles/g_G84*.json.
- hgf84 RESULT (gate renders, $0): G84b | G84a: hairline lay 22.4 P | 22.35 P (G82c 47.4, G82a 37.4), 3q 23.9 P |
  24.0 P, PROFILE 45.2 F | 45.7 F (G82c 45.2: the screen's 35 doesn't predict the render's profile lay; calibrate),
  colour_front L* 43.0 P | 42.7 P, grey_mix .533 P | .516 P, standoff_front 17.8 F | 18.1 F (14.5; G82a 12.1: the
  lean lifts the front), back_lightness 47.4 F (34.8), hairline_centre +3.4 F, temple_corners +17.8 F, hairline_edge
  1.97 P. Reviews: pairs 33 | 32 MAJORs, game 18 | 18. G84b pairs by scope (32 + 1 skin): SHAPE / GROOM 21 (sides
  puff, flat top, long behind the ear and nape, squared back, nape flare, hard hairline / temple edges x6, temple
  step, a SWIRL / fan from a point at the front top (pairs 8, 9, profile: likely the per-side lean diverging at
  az 0, NEW), whorl pinched x2, crown stubble), COLOUR 4 (too light / silver sides, a pale band, flat nape),
  STRAND-RENDER 7 (dark blocks and the crown seam, dark smears).
- My look at the 1 m sheet (out/game_hg_G84b.png): LIGHTER than G78d and the photo (the photo is mid-dark grey);
  the profile's dark rear block and seam are unchanged; flat top, hard hairline. The colour row PASSES while every
  review says too light: colour_front (one front crop) is an incomplete item. Raising seen was the wrong lever; the
  next colour row needs a whole-head / sides L* item from the photo before any change, and seen back toward G78d.
- STATE: code fc9b6830 (trace.forward per side). Best for lays: G84b (hairline and 3q pass in render, profile fails).
  Hem: taper .015 (screen 9.6 P; render review still says long / ragged behind the ear: spread 107 vs 61.5).
  Shape MAJORs 21, so NOT time for the cards handoff.
- NEXT: (1) colour: add the whole-head L* item (sides, back at game distance), revert seen toward G78d; (2) the
  front swirl from the lean: give the blend over the centre more width (az +-10 -> +-25) or lean the left side the
  same way; check standoff_front; (3) calibrate the screen's profile lay against renders (35 screen vs 45 render);
  (4) shape: wide top (+8 mm at z +80), low back (+3.9 at z -40), length behind the ear, a hairline-edge measure the
  eye agrees with; (5) the strand-render blocks / seam (children).

## Successor 17 (2026-10-16): comparable counts, profile screen, colour item, front lean, hem, hairline edge
- COUNTS: the "shape 21 (was 6)" compared two different reviews (21 = the 12-pair close-up review by hand; 6 = the
  1 m / 3 m game review). Same prompts and pairs in both rounds (remround.sh / s13/gameround.sh unchanged, 12 pairs,
  same names). One counting rule now: spikes/hair_garrett/count_review.py (first sentence of each MAJOR; order skin
  (OTHER STAGES) / strand / direction / colour / shape). Re-counted:
  | review | G78d | G81b | G84b |  (shape / colour / direction / strand, hair total)
  | pairs | 11 / 10 / 3 / 2 = 26 | 19 / 17 / 4 / 2 = 42 | 15 / 10 / 5 / 2 = 32 |
  | game  | 9 / 5 / 1 / 1 = 16 | 6 / 6 / 1 / 2 = 15 | 8 / 5 / 2 / 1 = 16 |
  So G84b is NOT a shape regression of 6 -> 21: game shape 6 -> 8 (+2: radial stripes = the new swirl, jagged strip
  in front of the ear), pairs shape 19 -> 15.
- STATE: counts comparable. NEXT: profile screen calibration.
- PROFILE SCREEN CALIBRATED: the screen's lay used 120k strands; the render uses strands.count (480k). At 120k the
  under layers show through the flat raster and the profile crop's sides (lower right quadrant, 0.9 of its hair px:
  photo 46 / render 69 / flat-120k 54 deg) read flatter. laycal.strands(count=0) = the spec's count; screen.py uses
  it (~20 s a variant). Also: head occlusion is now a z-buffer of the head surface (LAYCAL_HEADOCC=0 = old normal
  test; it changed the profile by only -0.5). Screen (full count) | render, 3q / profile / hairline:
  | G84b | 20.7 / 43.0 / 21.9 | 23.9 / 45.2 / 22.4 |
  | G82a | 29.1 / 52.8 / 38.7 | 26.8 / 53.8 / 37.4 |
  | G78d | 26.5 / 53.5 / 26.5 | 27.7 / 55.1 / 26.5 |
  | G82c | 22.3 / 44.1 / 49.9 | 25.1 / 45.2 / 47.4 |
  profile within 2.2 deg (was 10-13 low), 3q within 3.2, hairline within 2.5.
- STATE: screen predicts the render's lays. NEXT: colour_regions item, front lean, hem, hairline band.
- COLOUR ITEM: hair_read now reports each view's median L* by region (`L_by_region`, cmp "L* by region"); gatetable
  item colour_regions (checklist) rows per view 0 / 1 and region. Averaged over views 0-2 it PASSED on G84b (top 39.1 |
  35.6, sides 45.0 | 44.4): the profile view reads darker than the photo (front 31.4 | 38.9, sides 37.7 | 41.7) and
  cancelled the front / 3q views' too-light top (v0 43.5 | 36.7, v1 41.2 | 33.9) and sides (v1 48.8 | 44.8). Per view it
  fails where the reviews say. back_lightness (back crops) 47.4 | 34.8. Change: seen x0.81 ([.332 .318 .309], from
  successor 16's slope 64 L* a unit seen: -5 L* on the lit views), toward G78d's .315.
- HAIRLINE EDGE MEASURE (spikes/hair_garrett/edgewidth.py; checklist hairline_band): per column of the hairline__front
  crop, the px from 90 % to 10 % of the column's hair cover (skin -> hair Lab axis). photo 11 px, G78d / G84b 4 px with
  86-88 % of columns a "cut" (< 6 px), agreeing with every review; texmeas' hairline_edge (passes) is incomplete. The
  photo's edge is long leading strands lying over the skin; ours a dense mat ending in short spikes. Lever: fade.front
  .reach .002 -> .006 (tips lie further over the line; hairline_centre is +3.4 mm high, so the same direction).
- FRONT: trace.forward_blend (deg, default 10) widens the per-side blend at the centre: the swirl / fan at the front
  top is the two sides' diverging leans meeting over 20 deg. Screen (full count) 3q / profile / hairline, stand-off front:
  G84b 20.7 / 43.0 / 21.9, 12.3 | G85a blend 25: 20.0 / 42.8 / 20.2, 12.4 | G85b blend 25 + lean x0.6: 22.4 / 45.0 /
  26.0, 12.4 | G85c blend 40: 19.8 / 42.9 / 19.8, 12.5. Taken G85c. NOTE the screen's front stand-off does NOT see the
  render's lean lift (G84b render 17.8 vs screen 12.3; G84a 18.1 vs 12.1; G82c forward 1.0 12.8 vs 12.4): uncalibrated
  for the per-side lean, so the fan's removal is a bet that the render's +5 mm is the fan standing up.
- HEM: fade.taper_from (deg, default 100): where the taper starts; 75 takes it round behind the ear (backw was 0 at
  |az| < 100, so the sides' full .025 hung there).
- SCREENS G86 (G85c +): G86a = taper_from 75 + reach .006 + seen x0.81, G86b = taper_from 75 + seen. 3q / profile /
  hairline, front stand-off, hairline_centre, hem net spread: G85c 19.8 / 42.9 / 19.8, 12.5, 1.7, 107.5 | G86a 19.3 /
  42.7 / 19.6, 12.6, 1.0, 109.2 | G86b 18.8 / 42.9 / 19.6, 12.5, 1.7, 111.0. taper_from did NOT move the hem: dropped.
- HEM DIAGNOSED (screen.hem now prints z by 10 mm column, 40 mm behind the centre first): the HARD edge matches the
  photo (ours 23 / 89 / 99 / 105 / 87 / 77 mm under the centre, photo 29 / 88 / 98 / 100 / 92 / 76). The NET edge (the
  thin strands) reaches 179-187 mm under the centre at 70-90 mm behind: stray / flyaway strands hanging down the neck
  (the reviews' "jagged spikes to jaw level"). The row compares net 107 with the photo's 61.5: the lever is the strays
  at the nape (strands.stray .9 / flyaway .024 have no region scope yet), not the cut. Not changed this round.
- BATCH hgf86 (remote/b86/chain.sh, RS="G86c G85c", NICO-TOP): G86c = G85c (G84b + forward_blend 40) + fade.front
  .reach .006 + seen [.332 .318 .309]; G85c isolates the blend. Styles $HG/styles/g_G86c.json, g_G85c.json.
- HANDOVER (successor 17, 70-call clock): hgf86 was queued 50 min behind projskin's rs_r7 and is RUNNING at the stop
  (chain detached: remote/b86/chain.sh -> remround / gameround vs hg_G84b, then tmp/sum_86.txt = hairline_band
  (edgewidth) + count_review.py pairs / game counts for G86c, G85c, G84b; tmp/rr_86.done when finished). The 1 m sheet
  will be out/game_hg_G86c.png (photo | G86c | G84b). NOT YET JUDGED: no verdict on G86c.
- Row status going in (G84b render): PASS hairline lay 22.4, 3q 23.9, hem_soft, colour_front, grey_mix. FAIL profile
  lay 45.2 (31.4; the screen now predicts it within ~2: no screened variant reaches it, G85c 42.9), standoff_front 17.8
  (screen blind to it), back_lightness 47.4 (34.8), colour_regions per view (v0 top +6.8, v1 top +7.3, v1 sides +4.0),
  hairline_band 4 px (11), hem net spread 107 (61.5; strays down the neck, not the cut).
- NEXT: (1) read tmp/sum_86.txt + out/table_hg_G86c.md (colour_regions rows, back_lightness, standoff_front, lays) and
  LOOK at out/game_hg_G86c.png before the numbers; count with count_review.py only. (2) If the front stand-off is still
  +3: the lean itself lifts it in the render while the flat doesn't see it: find why (render outline vs flat outline at
  the front, same camera) before more front changes. (3) Hem: a nape scope for strays / flyaways (strands.stray .9,
  flyaway .024 are global), measured on screen.hem net cols. (4) Profile lay 43 vs 31.4: the sides combed down make it
  (lower-right quadrant 69 vs photo 46); a sides flow more back, screened at full count. (5) back_lightness: if seen
  x0.81 leaves the back > 38, the back's own grey share (groom.grey.back) is the next lever.
- STATE: code 35aeda81 + this note. hgf86 running.

## Successor 18 (2026-10-18): skin tone on hair sheets, the unrecorded G87 length screens
- PICKED UP: commits 280fed90..d4330973 (lenmeas.py, flowtrace.py, groom.loose.comb_trace) were a successor that hit the
  usage limit before writing notes. Its G87a-e were built and SCREENED ($HG/screen/log_G87*.txt) but never recorded:
  a = G86c + comb_trace (the photo's traced flow), b = a + lengths front .044 / sides .045 / back .03 (photo visible runs
  44-45 mm vs ours 23-26), c = b + front traced, d / e = c + sides / back lay .8 / .9, lift .008 / .005. Kept (code is
  opt-in: comb_trace only acts when set).
- SKIN TONE (Joe 2026-10-18: "last one I saw he was very dark-skinned", out/game_hg_G86c.png). NEW skintone.py <model>
  [views=] [tag=]: median Lab in the skin thread's boxes (forehead / cheek_R / cheek_L, MediaPipe on the photo, same
  code as spikes/projskin/skincheck.py; the photo values reproduce the skin thread's to 0.2 L), on photo | our tile,
  pass |dL| <= 5; the skin thread's garrett_g14 render printed beside; hair_front = info. G86c v0: forehead 59.6 vs photo
  75.8, cheek_R 46.2 vs 63.0, cheek_L 39.9 vs 53.9 (-14 to -17 L; the skin thread's render 77.9 / 62.0 / 52.6).
- CAUSE, measured (local light renders, v0 512 px, 60k strands; hgshots skin=<json> NEW: the stand-in skin's keys
  replaced): sun 0 + variation .3: no change; tone melanin 0 / blood .1 (albedo ~ the projskin stack's own base
  [.83 .73 .67]): +2.5..3.5 L only; shading subsurface 0 / specular: no change. The procedural tone is ALREADY the
  stack's base colour (tone_rgb(G86c's tone) = [.83 .72 .65]). The gap is the LIGHT: hair sheets use stage.photo_light
  (FRONT_LIGHT re-balanced, PBR Neutral, exposure -0.55); the skin thread renders under skin_project.stage_light (the
  fitted SH light, Standard, 0 EV). Under the hair light, skin of the right albedo reads ~1 EV dark, while the hair's
  colour rows pass: the hair's look.seen (.33) was calibrated UP into a dim light (about 2x its albedo).
- LIGHT FIX, measured (local v0 512 px): hgshots ev=<stops> NEW (added to every view's exposure). ev +1.0: forehead
  80.5 | 75.8, cheek_R 66.3 | 63.0, cheek_L 58.6 | 53.9 (tone melanin 0 / blood .1; +3..+5 L: PASS at the edge; the
  model's own tone is ~3 L darker, so ev 1.0 with the model's tone lands ~0..+2 L). Hair goes ~1 EV lighter with it, so
  the hair's colours are rescaled by 0.5 in LINEAR (sRGB x 0.73): seen [.332 .318 .309] -> [.242 .232 .226], grey
  #918d89 -> #6a6764. The model's own skin (no skin= override): the stand-in tone is the stack's base colour already.
  RULE from here: every Garrett hair render passes ev=1.0 with the rescaled colours, and skintone.py runs on every sheet.
- LENGTH SCREENS (full count, calibrated lays 3q / profile / hairline; G85c 19.8 / 42.9 / 19.8, target profile 31.4):
  | G87a comb_trace | 21.2 / 48.2 / 19.1 | hem_soft net 12.8 F |
  | G87b + lengths .044/.045/.03 | 32.6 / 51.5 / 36.8 | stand-off sides 20 back 22 |
  | G87c + front traced | 35.5 / 51.8 / 40.4 | |
  | G87d / e + sides lay .8 / .9 | 44.3 / 66.1 / 36.4, 44.5 / 66.2 / 36.3 | |
  | G87f = G86c + lengths .044/.045/.03 (no trace) | 30.6 / 49.3 / 37.1 | hem net soft 6.3 P |
  | G87g = G86c + lengths .036/.035/.02 | 24.0 / 47.4 / 26.4 | hem net soft 8.3 P, stand-off sides 17.6 back 16.7 |
  The traced comb did NOT improve any lay (profile +5 worse); longer strands worsen every lay in proportion to the
  length (they show more of the comb's direction error). Length and direction are coupled: length can't be raised to
  the photo's runs (44-45 mm) without the direction field right first.
- BATCH hgf88 (remote/b88/chain.sh, RS="G88a G88b", PREV=hg_G86c, args ev=1.0): G88a = G86c + rescaled colours (THE
  re-skinned G86c), G88b = G87g + rescaled colours (mid lengths, to measure length with lenmeas on the render).
  Styles $HG/styles/g_G88*.json. The chain adds skintone rows to tmp/sum_88.txt.
- hgf88 RESULT (NICO-TOP, $0). SKIN (skintone, G88a): v0 forehead 79.4 | 75.8, cheek_R 65.7 | 63.0, cheek_L 58.1 | 53.9,
  v1 forehead +3.8, cheek_L +4.7: ROW PASS (+3..+5 L, a* +5..+7: a little light and pink; the skin thread's render is
  +2 / -1 / -1 L). My look at out/game_hg_G88a.png (photo | G88a | G86c): the face now reads the photo's lightness
  (G86c's ruddy-dark face is gone); slightly peachy-pink; the bare shoulders are a flat peach (no shirt on the stage).
  A further ev 0.8 would centre the tone (~16 L / EV here) but moves the hair too: left at 1.0.
- HAIR under the new light (G88a, table_hg_G88a.md): colour_regions v0 PASS (front 34.8 | 37.1, top 33.4 | 36.7, sides
  49.6 | 46.6), v1 top 41.1 | 33.9, sides 52.7 | 44.8, back 50.4 | 39.0 FAIL; back_lightness 44.8 | 34.8 FAIL;
  colour_front 38.2 | 42.4 FAIL (now too dark; it was the light-dependent single crop). Lays 3q 23.2 P, hairline 21.1 P,
  profile 45.9 F (31.4). Stand-offs all PASS. hairline_band (edgewidth) med 6 px (G86c 5, photo 11), cut share .44 (.83).
  The back / sides are +8..+11 L too light in every light: groom.grey.sides .57 / back .34 is the lever (not seen).
- LENGTH (lenmeas sline p75, photo | ours): G88b (lengths .036/.035/.02) 3q 168 | 116 (G86c 117), profile 167 | 116
  (112), temple his-left 217 | 146 (127), back 149 | 176 (159), crown-back 182 | 187 (167). Mid lengths moved the
  temples +19 px and over-lengthened the back; the top / front runs did not move (they are the comb's direction, not
  the length). Not adopted.
- REVIEWS: none this round. bin/review exits 3: "You've hit your weekly limit, resets Oct 19, 1pm (America/Denver)".
  The pairs / game pairs are on disk (out/pairs_hg_G88[ab], out/gpairs_hg_G88[ab]): re-run remround's / gameround's
  review lines after the reset, count with count_review.py. No MAJOR count for G88; last counted: G86c game 16 (shape 8,
  colour 5, direction 3), pairs 29; G84b 16, G85c 14, G78d 16.
- PLATEAU (plain): game-visible hair MAJORs have sat at 14-16 since G78d (successors 14-17, ~12 rounds). Rows that never
  pass by any screened lever: profile lay (42-48 vs 31.4), hairline band (4-6 px vs 11), back lightness (+10 L), strand
  run length (115 vs 167 px; longer strands make every lay worse). The strand groom has plateaued on the comb-direction
  field: length, profile lay and the front lean all trace back to it, and comb_trace (the photo's flow) did not fix it.
- HANDOVER (successor 18). STATE: code 715cb590 + skintone fix; G88a = G86c re-lit (ev 1.0, seen [.242 .232 .226], grey
  #6a6764) is the current best and the sheet to show; every hair render from now passes ev=1.0 and these colours, and
  runs skintone.py. NEXT: (1) after the review reset, review G88a pairs + game pairs (count_review.py); (2) back / sides
  lightness: groom.grey.sides / back down toward the v0 photo values (measured row: colour_regions v1, back_lightness);
  (3) the decision Joe asked about: strands vs cards for Garrett (see PLATEAU).

## hair-cards round 6 (2026-10-15 evening, fresh session)
- b11's export had died when the old session stopped; it was rerun with b11chain.sh (export, then offload with
  TIMEOUT=240, detached with setsid). Batch hc-b11a.
- FOUND (bake): texels inside a coverage card's opaque core but between drawn strands had tone 0. tn2 = m / cov with
  m = 0, and the solid fill only reaches texels where alpha <= 0.5. Those texels drew dark dashes, so the side of the
  head read as brush strokes (b10). Fix: tone / root / flow at those texels come from the nearest drawn strand.
  Also: a strand is drawn on a card only if IN_SHARE 0.6 of its points lie inside the card (36-41% of layer-2 points
  fell outside: fragments); segments running more across than along the card (SIDEWAYS 0.5) are skipped. Offline
  preview: bake/bk1.py old|new on bake/cut_now.pkl. In b12, not in b11.
STATE: b11 queued (review c7 when it lands); bake fixes committed for b12. NEXT: c7 review, then b12 with the fixes plus the worst MAJOR.
- FOUND (fit): a clump's centre line is the mean of its strands, and it jumps wherever one starts or ends. 74 of 154
  tail cards kinked 45-130 deg in their last 20% (the crumpled-paper tail ends, b12 back view), and 43 of 190 head
  cards at their staggered roots. Fix in hair_cards._clump: Gaussian-smoothed, sigma 1 station where the strands
  are full and 4 where few run, padded by carrying each end straight on. With mode "nearest", sigma 6 was worse:
  squashed end stations gave random tangents. Kinks are now 16 tail / 6 head (bake/loops2.py <out pkl>).
  test_centre_line_does_not_kink_where_strands_end.
- Own look at b12 (local, bake fixes only): the tail from the back is wide flat ribbons with a card looping over the
  tie; dark thick wires in L3 hanging singles; a crumpled bottom (above); the crown still carries a dark row of loops.
- Review c7_b11 (offload, blind; review/c7_b11): FAIL with 29 MAJORs, the same families as c6. Crown crest (4 regions);
  colour too light (4: L* 34.7 vs 31.7 measured); tail: crumpled lower half, blocky chips at the tips, smeared swirl
  texture with black slits, ribbons splaying to the right, a flag shape; head reads as flat ribbons with smeared bands;
  part a smudge; temple fragments and specks; side sheet over the temple; nape broken into jagged cards.
- Fixes since (b14): the crest was three FREE halo flyaways (off_head, rooted in the mass at 84 mm) that the crown
  rule exempted. Now FLY_CROWN_FREE 0.06 applies to them (bake/flyc.py, bake/topsil.py: L3 at the crown 99 -> none).
  Card gain 2.85 -> 2.5 (setgain.py; the L* measure). A strand's card-frame coordinates are median+Gaussian smoothed
  along the strand: nearest-station switches made jumps (bake/jumps.py: tail 0.8% of segments -> 0.35%). The
  polyline closest-point projection was WORSE (medial-axis switches on the inside of bends): reverted.
- New rule (Joe, via coordinator): ALL renders go to NICO-TOP (offload.sh). The laptop is only for small check crops
  and ID passes. The local layer-isolation render (layers.sh) was stopped.
- Face wisps: the cards' pictures are drawn at FACE_ALPHA 0.55 (c7: solid pale ribbons; 4 hairs a texel wide each).
  This edit landed while the b14 exports were starting: b14a has it for sure, b14 maybe (check the face islands' alpha).
  b14a = ANISO 1 (square texels), to test the stair steps across the flow on the side of the head.

## Handover 2026-10-15 night (hair-cards agent, round 6; stopped at the 100-tool-call rule)
Branch worktree-agent-a54a66de6d6970c0b. Commits this round: bake tone fill between strands + IN_SHARE / SIDEWAYS
(5c6f5677); _clump centre-line smoothing (c94c3ac1); ENV_PCT 90 (no visible effect: the head cards were not over the
radial envelope; topsil.py); FLY_CROWN_FREE + smoothed strand card coords (7f6e7723); FACE_ALPHA 0.55 (fc1004ce).
hc_s2 hair.export.card_gain = 2.5 (store history).
- IN FLIGHT (detached, nothing to babysit): b14 (all the above) and b14a (the same + ANISO 1, square texels) are exported
  (exp/b14, exp/b14a) and queued as ONE offload, batch hc-b14 (out/off_b14.txt; TIMEOUT 240). c8.sh waits for its
  DONE, then writes review/c8_b14 and review/c8_b14a (crops, measure.txt, review.md via rv.sh) and touches
  review/c8.done. NEXT: read both review.md files (MAJOR count, VERDICT); check v0 colour L* in measure.txt
  (target 31.7); compare b14 and b14a on the side-of-head / tail stair steps and keep the better ANISO.
- Still open, worst first (from c7 + my own look at b12/b13): tail (flat ribbons with gaps from behind, crumpled
  lower half: the centre-line kinks are fixed in b14, unreviewed; blocky rectangular tips; ribbons splaying to the
  right that read dark; a card looping over the tie, the U at the tie in back view); head texture (smeared horizontal
  bands: b14 / b14a test); part a smudge, not a crisp dark line; temple specks / fragments in front of the ear;
  a side sheet over the temple (screen-left in the front view); nape under the tail broken into jagged dark cards.
  Tail card GEOMETRY is wider than the strands (bake/tailw.py: 108 vs 90 mm at mid-height), so the narrow, gappy tail
  is the cards' PICTURES (sparse strands, edge fade, DENSITY 0.55), not their placement.
- Tools (bake/): loops2.py <out.pkl> (cut from in_hero.pkl + centre-line kink stats), loops.py, jumps.py <pkl> [s]
  (card-frame coordinate jumps), flyc.py / crown2.py / topsil.py (cards over the crown, front-view top silhouette),
  tailv.py / tailw.py (tail cards' coverage and width), bk1.py old|new (offline atlas preview). hx.py takes aniso=.
- RULES now: ALL renders go to NICO-TOP (offload.sh <job> <renders.json> <exp dirs>, its own folder, detached; batch
  several candidates per submit). The laptop is only for small crops and ID passes. CPU cap: 10 cores for all agents.
STATE: c7 FAIL (29 MAJORs); b14 / b14a queued with an auto-review (c8). NEXT: read c8, fix the worst MAJOR (tail
pictures / density), loop; re-seat on tp_k19 only when near a PASS.

## hair-cards: shared card pictures (2026-10-15 late, hair-cards agent, round 7: the change of approach for the SURFACE)
Why: c5-c7 failed on the same card-surface faults (smeared bands, no fine strands, blocky tips; 27-29 MAJORs) while the
big read was close. MEASURED (bake/texd.py <exp dir>: texels per mm along / across per layer from the GLB's UVs):
b11 (unique islands, ANISO 2) layer0 0.79 / 0.43, layers 1-3 ~1.4 across / 0.72 along; b14a (ANISO 1) 0.5-1.0 square.
One 2048 x 1024 block shared by ~500 unique islands cannot do better than ~1.3 texel/mm (cards' world area ~1.6 m2
incl. layers): a hair is ~0.08 mm, so each texel averaged ~12 strands = the smear. Not a tuning problem.
- NOW (hair_clumps.bake_tiles, default TILES 24; S["bake_tiles"] = 0 restores unique islands): as studios do (Epic's
  Hair Card Generator texture groups, "Num Textures" << cards; clump tile libraries). Cards are grouped by class
  (head / tail / face / fly) x coverage-or-upper, k-means on (3 log length, log width), tiles per group ~ sqrt(area);
  each cluster's medoid (among its clusters' denser half by strand count) is baked at a fine SQUARE texel
  (TILE_ANISO 1); every card of the cluster wears that island; tint = its own strands' mean tone / the tile's
  (0.7-1.4, multiplied into tone_k = the vertex colour). Skyline packing for <= 64 islands (shelves wasted the space
  under the tallest island). Texel: b15 2.7 (coverage, DENSITY 0.55) / 4.3-6.6 texel/mm (upper layers), 0.22 mm.
- Fine texel exposed the groom's sparseness (a 3 cm clump has 300-900 strands drawn 1 texel wide: mostly holes), so a
  tile's strands are drawn as children ("kids": offset across ~ card width / strands, depth jitter, tone x 0.88-1.12)
  until widths sum to KID_COVER 1.4 x the card width; each child ends up to KID_TIP 30% early, so the TIP is a feathered
  fringe in alpha, not a cut block (the blocky tips of c7).
- Known: one tile (a tail card near the tie) has crossing strands (kinked clump chosen as medoid): pick medoids by
  straightness if it shows. Bottom quarter of the bake block unused (the tallest tile sets the texel).
- b15 (24 tiles, KID_COVER 1.4) and b15b (16 tiles, KID_COVER 2.0; texel 3.0-7.7/mm) queued on NICO-TOP as batch
  hc-b15; c9.sh writes review/c9_b15, review/c9_b15b. hx.py takes hk.<CONST>=<v> (any hair_clumps constant).
STATE: tiles built + tested (test_shared_tiles...); b14/b14a (hc-b14) and b15/b15b (hc-b15) both queued.
NEXT: read c8 + c9 reviews; if tiles beat unique islands on lock texture / tips, keep and fix the next MAJOR family.
- c8 EMPTY, CAUSE (coordinator caught it): hc-b14 never rendered. NICO-TOP fetched the repo bundle expecting fc1004ce's
  archive (sha 59a515a8) and got a872d5b5's (b6a4cb16): submitting hc-b15 from the SAME worktree while hc-b14 was still
  queued replaced the served repo.tar.gz, so the queued job's download failed its hash. c8.sh then hid it (crops.py
  `|| continue` on missing renders, no ERROR). FIX: cr.sh <round> <off file> <tags> (replaces c8.sh / c9.sh) writes
  review/<round>_<tag>/ERROR on missing renders or an empty review; b14re.sh resubmits hc-b14 only after hc-b15's
  DONE. Root cause fixed on main bef0229c (remote.sh serves repo_<sha>.tar.gz per commit), cherry-picked here as a3d89c8e
  (taken whole: it also carries main's ram_gb <= 12 cap). b14re.sh still serialises; harmless. cr.sh's ERROR file stays.
STATE: hc-b15 queued (b15 / b15b, tiles); hc-b14 resubmit chained after it; cr.sh c9 / c8 review each on landing.
NEXT: read c9 (tiles) + c8 (unique islands), fix every independent MAJOR in one round, grouped by cause.

## Handover 2026-10-16 (hair-cards agent, round 7; stopped at the 70-tool-call rule)
Branch worktree-agent-a54a66de6d6970c0b, not pushed. Commits: a872d5b5 bake_tiles (shared pictures), a3d89c8e
(main's remote.sh per-commit archive, cherry-picked), the wisp fix below, notes.
REVIEWS (all FAIL; review/<r>_<t>/review.md, pair_0..7; lines naming MAJOR): c8_b14 24, c8_b14a 28 (unique islands),
c9_b15 26, c9_b15b 30 (tiles 24 / 16). (ERROR files there are empty: crops.py's stderr; empty = fine.)
- Texture family, mentions of smear / brush / no strands / texture: b14 6, b14a 8, b15 3, b15b 5. Tiles help, which
  supports the texel hypothesis. But b15 is not a clear win on the count: the wisps vanished (below), and the crown
  and holes got more mentions. Keep tiles (24, b15). ANISO 1 (b14a) is not better than 2 for unique islands.
- My look, front pair_6 ref | b14 | b15 (bake/cmp_tail_b14_b15.jpg): b15's side hair is smoother and darker, but its
  face-framing wisps are GONE. Cause: at 0.22 mm texels a lone hair at 0.45-0.55 alpha disappears. FIXED in b16: face /
  fly tiles get child hairs (KID_WISP 0.7, kid_max 3 fly / 6 face) at WISP_ALPHA 0.9.
- In flight: hc-b16 (b16 = b15 + the wisp fix) on NICO-TOP via b16chain.sh; cr.sh c10 writes review/c10_b16.
Remaining MAJOR families in c9_b15, grouped by cause (geometry, not texture; unchanged by tiles):
  1 CROWN: cards flip up into a loop at the front of the crown; white slivers between top cards; the part is crossed
    or unreadable. Look at the top-layer cards' normals and bend at the crown (bake/crown2.py, flyc.py).
  2 TAIL: pinched to a point at the tie (the reference is broad from the tie), separate flat ribbons splaying right,
    shredded and blocky lower third, sawtooth ends. Card ends are cut square in GEOMETRY: taper hw to ~0 over the last
    15% of each card, and fan the tail's root cards wider at the tie (bake/tailw.py: 108 vs 90 mm, mid-height only).
  3 SIDE BANDING: hard light / dark bands between stacked layers from temple to tie. Per-card tint (0.7-1.4) on
    stacked cards plus hard layer edges: clamp tint to 0.85-1.15 on head cards and widen EDGE_FADE for upper layers.
  4 HAIRLINE / EAR: dark card ends on the forehead at the temples; the ear left fully exposed (the reference covers its
    back half). Side cards need more stand-off over the ear.
  5 SILHOUETTE: no frizz or flyaways over the crown (FLY_CROWN_FREE removed them for b12). Retry with the tile wisps.
STATE: tiles in (b15 = 26 MAJOR mentions); b16 (wisp fix) queued with the c10 review. NEXT: read c10; fix families
2 and 3 (geometry taper, tint clamp) and 1 (crown) in one round, then judge again.

## hair-cards round 8 (2026-10-16, game distance; resumed session, ran beside the round-7 agent's last steps)
- hc-b15 had rendered (out/s_hc_s2_b15R_*, b15bR_*); only the DONE line and the reviews were missing (the session
  died). c9 reviews: b15 26, b15b 30 MAJOR lines (the round-7 handover above has the families). hc-b14 was
  resubmitted by the round-7 agent (c8_b14 24, c8_b14a 28).
- GAME-DISTANCE judging (gates.md): spikes/haircards/shots.py views g<m><view> (g1v0, g3backl: the game camera at
  1 / 3 m from the head centre, vertical fov 59, size=1080 = the centre columns of a 1920x1080 frame, native pixels;
  vN = the photo camera's direction, under its photo light). spikes/haircards/gsheet.py <out.png> <tags>: photo
  (scaled to the same px/m from the fitted camera's f / depth) | strand groom | cards, rows g1v0 g1v1 g1v2 g1backl
  g3v0 g3backl, plus the measures; gpairs.py <dir> <tag> [sheet col]: blind-review pairs (rv.sh). Batch hc-g1
  (strands gS, b15, b15b, b14a), sheet /mnt/data/hifipushie/haircards/game/gm_g1.png (+ .json measures).
- MEASURED at 1 m, hair pixels (strand id mask on the photo; each render's own id mask), L* units:
  coherence (structure tensor): photo 0.79-0.82, strands 0.81-0.84, cards 0.78-0.84 = equal: the cards read as
  COHERENT hair, not needles. Fine band (DoG 0.8-2.5, speckle / needles): photo 3.0-3.3, strands 2.9-4.4 (the
  needle look; 4.35 front), cards 2.2-2.4 = smoother than the photo. Lock band (DoG 2.5-8): photo 4.8-5.2, strands
  5.6-6.6, cards 5.8-7.0 = TOO STRIPY at lock scale (the "flat painted bands" / side banding). Card hair area is
  ~65-75% of the strand groom's in every view (lost wisps, flyaways, tail bulk). L*: cards 31-32 front (photo 27).
- g1_b15 blind review (review/g1_b15, against the photo for v0-v2, the groom for the back): FAIL, 21 hair MAJORs, the
  reviewer marked EVERY one visible at its size (1 m and 3 m). Game-visible, grouped by cause:
  1 CROWN: white slivers / holes along the top, a looped flap, a hard dark rim (1 m all views; a lump at 3 m).
  2 WISPS: no face-framing locks (1 m, 3 m); b16 (round 7's wisp tiles) is the fix in test. b14a (unique islands)
    keeps them: the tile path lost them.
  3 TAIL: thin paddle / strip from the front (vs the photo: also the groom's own bulk), blunt sawtooth ends (1 m
    profile), separate dark straps splaying right and gaps (1 m and 3 m back).
  4 SURFACE: flat painted bands, bark-like stripes (1 m 3/4 + profile) = the lock-band measure above.
  5 HAIRLINE / NAPE: hard dark-rimmed hairline, dark marks on the temple skin, a dark jagged mass behind the ear.
  6 SILHOUETTE: cap-tight, ears exposed (vs the photo; partly the groom).
  7 NECK NOISE: grainy dithered dark speckle on the neck / back under the tail (1 m back). Not in the strand render.
    Untested guess: the cards' shadows (dithered render method, low samples) or nape fuzz cards. Test next: one back
    view with card shadows off.
  Close-up-only: none new; the c9 close-up MAJORs are mostly these families again.
- FIXED for b17 (29d1c1d5): clump card GEOMETRY tapers over its last 15% to 0.12 of its width (TIP_TAPER / TIP_FLOOR;
  test_clump_cards_taper_to_a_point_not_a_square_end); tile tint clamped 0.85-1.15 on head / tail cards (TINT_RANGE;
  face / fly keep 0.7-1.4).
- IN FLIGHT: b17chain.sh (export exp/b17, waits for hc-b16, ONE offload hc-b17: b17 std + game views, b16 game
  views), then game/gm_g2.png (gS, gb17, gb16, gb15), review/g2_b17 (game, blind) and review/c11_b17 (close-up).
STATE: cards are coherent and not needly at 1 m (the target), but FAIL on geometry families 1-7, all game-visible.
NEXT: read g2_b17 + c11_b17 (does the taper kill the sawtooth, the clamp lower the lock band toward 5?); then the
crown (family 1: top-layer card normals / bend at the front of the crown, bake/crown2.py) and the neck-noise test.
- Handover (round 8, stopped at the tool-call clock): b17 exported (exp/b17); hc-b17 QUEUED on NICO-TOP (busy), its
  client and b17chain.sh run detached and write game/gm_g2.png (+ gm_g2.txt measures), review/g2_b17 (game, blind) and
  review/c11_b17 (close-up), then review/g2.done. Nothing to babysit. The 1 m verdict went to the coordinator.
STATE: b15 FAIL at game distance (21 visible MAJORs); b17 (taper + tint clamp + b16's wisp tiles) in the queue.
NEXT: read gm_g2 (lock band toward the photo's ~5? sawtooth gone? wisps back?) + g2_b17; then crown (family 1) and the
neck-noise test (one back view, card shadows off).

## hair-cards round 9 (2026-10-16, fresh session after the round-8 handover; game-distance families)
hc-b17 sat QUEUED on NICO-TOP the whole round (busy with other batches): gm_g2 / g2_b17 / c11_b17 not read yet. Work done
on the laptop with measures (no renders), scripts in /mnt/data/hifipushie/haircards/:
- crownprobe.py <model> <glb>...: rays from the scalp centre through ~2400 scalp directions (within 5 deg of a lock root):
  card alpha coverage (1 - prod(1 - a)), the outer card's vertex normal facing, its height off the scalp, and the GAP
  from the outer opaque card to the next one under it, per region; crown gaps attributed to export layers.
  b15 / b17: NO scalp holes over the crown (coverage 1.00, 0% < 0.5; the only "holes" are the forehead rim at az ~0,
  el 11-46 = bare skin under the swept-back front, expected); NO card normals face in (exported normals are radial,
  n.out >= 0.95). So the crown's "white slivers / holes" are NOT gaps to the scalp and NOT flipped normals: they are the
  render BACKDROP seen between cards that stand off each other (sliver pixels = the backdrop's 219 grey, the brightest
  in the crown). Crown: outer card p90 18 mm off the scalp, outer->next gap p90 9.2 mm, 38% of crown rays gap > 4 mm.
- FIX 1 (a3a193ef, test_head_layers_lie_close_over_frizzy_clumps): head layer offsets use the clump's normal spread
  capped at HEAD_SN_MAX 3 mm (layer_offset; tails keep theirs). b18: crown gap p90 9.2 -> 7.1, rays > 4 mm 38 -> 31%,
  top-front p90 9.4 -> 4.8, top-back 5.9 -> 4.0; sides / back unchanged in height (no volume lost).
- Remaining crown gaps: outer = layer1 (mid) cards over layer0 AND layer2 = mid cards bent UP by their clumps (the
  "looped flap"). The groom itself has a frizz-loop halo dome over the crown (bake/crown_gS_b15.png: gS | b15 at 1 m).
  ENV_PCT 75 (b18e) does NOT fix it (crown > 4 mm 34%) and shrinks the sides 2 mm: rejected.
- FIX 2 (in test as b19): CROWN_LOOP: head strands rooted over the crown whose chord < 0.6 x length are left out of the
  head cards (crown_loops; test_crown_loops_found_straight_hair_kept). Numbers below.
- NECK NOISE: test pass wired (blender_scene hair_glb_look card_shadow False; shots.py shadow=0); b18chain renders
  g1backl with and without card shadows and prints the skin fine-band L* std under the hair (gm_g3.txt "neck").
- SILHOUETTE (silh.py <tags>: widths at 20..140 mm below the vertex, 1 m, photo segmented as dark-or-coloured against its
  neutral backdrop; game/silh_*.png masks): front g1v0, mm:
    depth      20   40   60   80  100  120  140
    photo     114  148  169  177  205  213  215
    strands   129  159  185  201  203  201  194
    cards b15 118  154  176  186  185  182  191
  The crown is NOT narrow: cards = photo +/- 7 mm at 20-60 mm. At ear height (100-140) the photo is 205-215 (incl. the
  tail showing beside the neck), strands 194-203, cards 182-191: cards lose 10-20 mm to their groom (ENV_PCT 90 cap +
  ENV_UNDER on the sides), and the GROOM is 2-21 mm under the photo at ear level. GROOM ITEM for the coordinator (th_W18
  / hc_s2 approved: not changed here): side fullness over / behind the ear, ~+10-20 mm total width at ear height.
- HAIRLINE (hairline.py: L* of hair within 3 px of the face skin minus hair 6-15 px in, upper half; dark marks = skin
  within 12 px of hair under the skin's p5 - 10): g1v0 strands +17.8 (a light, see-through hairline), b15 +1.5, b14a
  +4.4; g1v1 strands +19.0, b15 -1.1. Temple marks g1v1: b15 5.1% vs strands 0.6%. = the hard dark rim, measured.
  Cause not fixed: alpha-tested cards can't show skin between sparse hairs; the fix to try is a lighter, sparser root
  picture on hairline cards (hairline cards' first BASE_IN mm drawn at the strands' skin-blended tone, alpha under the
  cutoff in gaps) and no strand_shade darkening at roots that sit on the outside at the hairline.
- b19 (CROWN_LOOP 0.6, exp/b19, crownprobe): crown rays gap > 4 mm 31 -> 25%, but the crown's outer card height p50
  9.3 -> 2.2 mm (the cap is now the outer surface over much of the crown: the crown FLATTER, ~7 mm lower) and the gap p90
  stays 9.1 (layer1 over the cap). Mixed: NOT adopted. CROWN_LOOP is 0 (off) in the code; b19 waits for a render beside
  b18 (hx.py hk.CROWN_LOOP=0.6 re-exports it) before any verdict. Likely better: keep loop strands for the picture but
  fit the mid-layer centre line on the clump's non-loop strands only (height kept, flap gone).

## Handover 2026-10-16 (hair-cards agent, round 9; stopped at the 70-tool-call rule)
Commits: a3a193ef (HEAD_SN_MAX layer cap), e35ce7ea (card_shadow test pass), + this one (CROWN_LOOP, off; notes).
IN FLIGHT (detached, nothing to babysit): hc-b17 still QUEUED on NICO-TOP; its b17chain.sh writes game/gm_g2.png,
review/g2_b17, review/c11_b17. b18chain.sh waits for off_b17 DONE, then ONE offload hc-b18 (b18 game set + g1backl with
shadow=0), then game/gm_g3.png + gm_g3.txt (measures, silh, hairline, "neck" lines) and review/g3_b18 (blind, game);
review/g3.done when finished. `offload wait hc-b18` to chain on it.
STATE: crown faults measured (backdrop between stand-off cards, not holes / flipped normals); b18 cuts crown gaps
(p90 9.2 -> 7.1); silhouette short at ear height (cards -10..-20 mm vs groom, groom -2..-21 vs photo); hairline rim
measured (cards +1.5 vs groom +17.8 L*). Not judged on renders yet: everything waits on NICO-TOP.
NEXT: (1) read gm_g2 / g2_b17 (taper sawtooth, clamp band vs 4.8-5.2, wisps) and gm_g3 / g3_b18 (crown slivers, neck
line gb18 vs gb18ns: if the no-shadow std drops toward gS, the noise is card shadows -> cast shadows from a coarser
proxy or a shadow-only alpha with a lower cutoff; else nape fuzz cards); (2) crown: mid-layer centre line from non-loop
strands (above); (3) sides at ear height: per-region envelope (ENV_PCT 97 for el < 30) to win back the 10-20 mm;
(4) hairline root picture (above). Groom item for the coordinator: side fullness at ear height.

## hair-cards round 10 (2026-10-16, fresh session; hc-b17 / b18 still queued on NICO-TOP)
- EAR-HEIGHT WIDTH, measured geometrically (/mnt/data/hifipushie/haircards/silhgeo.py <tag> [hk.X=v]: export, then front
  widths of the strands (1 mm bins, coverage > 7%) and of the cards (alpha > 0.5 samples), no render; it matches the
  render silhouettes within ~6 mm). g0 (= b18 code) at 100/120/140 mm under the top: strands 203/199/206, cards
  191/188/187. THE ENVELOPE CAP IS NOT THE CAUSE: uncapped (ENV_PCT 100, ENV_UNDER 0) +2-3 mm only. Cause: the head's top
  card sat at its clump's mean + 0.6 x spread, the outer strands ~2 spreads out. Per side (-x / +x): head strands p99.7
  +-93..96, cards +-88..93; the +x excess at 140 (strands +111) is the TAIL beside the neck and flyaways (tail strands
  +104, singles +104), not the head.
- FIX (card_offset / side_weight, SIDE_EL 20-40 deg, SIDE_OUT_PCT 90, SIDE_ENV_PCT 99): on the sides the head's layers
  move out TOGETHER until the top one lies on the clump's p90 outer strands; the envelope there is p99. s4: cards
  195/192/187 (-x half 95/94/90 vs strands 98/97/95: within 3-5 mm; +x 100/98/97 vs 105/102/111: the tail). Top layer
  alone moved (s3): same width but side rays gap > 4 mm 12.5 -> 16.0%; together (s4) 14.3%, back 18.4 -> 17.9%.
  Crown untouched (identical crown numbers). Test test_side_head_layers_reach_clump_outer_strands. Not met: within 5 mm
  at 140 on +x (the tail); next lever there = the tail's own outline, not the head.
- TEMPLE "DARK MARKS" WERE THE BROWS: marks.py <tag> <view> (game/marks_gb15_g1v1.png) puts b15's 5.1% on the brows and
  the far brow tail, dark skin the cards' hair came within 12 px of. hairline.py now drops marks that are dark in the
  strand groom's frame too (ctl=gS): b15 0.0% (g1v0, g1v1), gS 0.6%. The visible temple fault is HAIR: dark scribbled
  face wisps / hairline-card roots at the temple and forehead edge (same crop), i.e. the rim below.
- HAIRLINE ROOTS (bake, card "edge" = majority lock at_hairline, or face): over HL_SOFT 10 mm from the root the picture
  fades in from HL_ALPHA 0.45 of its alpha, the depth shade goes to 0 at the root, tone x (1 + HL_LIFT 0.35). Texture
  pass (atlasdiff.py s4 h1, same layout): 4129 texels change (0.10% of the atlas), over the 0.33 cutoff 88 -> 74%,
  base colour L* over the cutoff 51.3 -> 54.8 (the depth part acts in the shader, not in base colour). Whether that
  reaches the groom's +18 L* edge needs b19's frames (hairline.py; variant with HL_LIFT 0.6 / HL_ALPHA 0.35).
- b19 READY, NOT LAUNCHED (the brief: read b17 / b18 first): exp/b19 (= HEAD d440d4e9 code) and exp/b19h (HL_LIFT 0.6,
  HL_ALPHA 0.35; atlasdiff b19 b19h: over cutoff 71 -> 64%, L* 56.8 -> 58.8); b19_renders.json (gb19, gb19h game set,
  gb19ns = g1backl without card shadows); b19chain.sh waits for review/g3.done, offloads ONE batch, writes
  game/gm_g4.png + gm_g4.txt (silh, hairline with the gS control, silhgeo widths, neck std) and review/g4_b19 (blind,
  every fault with its distance class), review/g4.done (review/g4.ERROR if frames are missing).

## Handover 2026-10-16 (hair-cards agent, round 10; stopped at the 70-tool-call rule)
Commits: b018aa1a (side layers to the clump's outer strands, card_offset / side_weight + test), d440d4e9 (hairline
roots; temple-marks finding), + this notes commit. Scratch tools new this round: silhgeo.py, silhdiag.py, marks.py,
atlasdiff.py; hairline.py now takes ctl=gS.
IN FLIGHT: hc-b17 still QUEUED on NICO-TOP (behind the skin batch); b18chain.sh detached behind it (writes gm_g3,
review/g3_b18, review/g3.done). Nothing of b19 is running.
STATE: (1) ear-height width: the envelope cap was NOT the cause; fix in, -x side within 3-5 mm of the groom; FAIL on +x at
140 mm (cards 97 vs strands 111: the tail beside the neck + flyaways, not the head). (2) hairline: roots sparser /
lighter in the texture (measured in texture space only); temple marks = brows (metric fixed, cards 0.0%). Render
verification of both waits on b19.
NEXT: when review/g3.done: read gm_g3 / gm_g3.txt / review/g3_b18 + gm_g2 / g2_b17 / c11_b17 (taper, tint clamp 4.8-5.2,
wisps, crown gaps, neck: gb18 vs gb18ns std); revert losses; a neck fix if the no-shadow view clears the noise; re-export
b19 / b19h if code changed (silhgeo.py b19 export=1; b19h with hk.HL_LIFT=0.6 hk.HL_ALPHA=0.35), commit, then
`setsid nohup ./b19chain.sh > out/b19chain.log 2>&1 &`. Tail width: the tail's own outline (spread / top-layer offset
on the side facing out), measured with silhgeo. offload.sh still packs without --stage: add --stage _g3_hc_s2 per
RESTART.txt (after a local stage.ensure) before launching.

## hair-cards round 11 (2026-10-16, fresh session; b17 / b18 read, b19 launched)
- READ gm_g3 (gS, gb18, gb17, gb15) + g2_b17 + g3_b18 (blind, game distance). g3_b18: FAIL, 26 hair MAJORs, ALL
  game-visible (1 m or 3 m; none close-up-only). Families: tail (thin from the front, flat paddle / slab in 3/4 and profile,
  jagged comb ends, short vs the groom), no face-framing wisps / temple volume + no centre part (also the groom: it is
  swept back; the photo has a centre part = GROOM items for the coordinator), crown loop card standing over the scalp
  (backdrop under it, 1 m all views, a bump at 3 m), stiff dark strings in front of the ear, neck haze (1 m + 3 m),
  colour (vs the photo: lighter / ashier = the groom's colour too; vs the groom: darker, contrasty).
- KEPT (no losses): b17 taper + tint clamp, b18 HEAD_SN_MAX. Lock band (DoG 2.5-8) g1v0 photo 5.49 / gS 6.29 / b15 5.96 /
  b17 5.56 / b18 5.86; g1v1 5.25 / 6.14 / 6.51 / 6.45 / 6.40; g1v2 5.35 / 5.56 / 6.30 / 6.24 / 6.14: the clamp lowered it
  0.06-0.4 but the TARGET 4.8-5.2 is NOT met (FAIL; the groom itself is 5.6-6.3). Sawtooth: still "jagged comb-like ends"
  in profile and back (FAIL; the taper alone doesn't do it). Crown: b18 back view no longer "blotchy" (g2's MAJOR), the
  front loop card remains (b17 = b18 at 1 m: a raised flap at the top front).
- NECK = CARD SHADOWS (confirmed): gb18ns (cards cast no shadow) is clean (crop: gS | gb18 | gb18ns). neck.py <tags>
  (skin under the tail, g1backl): skin L* gS 63.3, gb18 58.2, gb18ns 63.9; fine-band std 1.07 / 1.19 / 1.13 (fine std
  does NOT see it: the haze is a broad darkening). Hair L* 39.6 / 31.3 / 34.6: card self-shadow is ~3 of the cards'
  8 L* "darker than the groom". FIX (7fb76afc): game look `card_shadow: "proxy"` (blender_scene._card_shadow_proxy;
  shots.py shadow=proxy): the cards cast no shadow, a shadow-only copy (same mesh) casts from the atlas alpha at 1/4 size,
  cut 0.2 (an engine's shadow LOD). Target: skin L* >= 62 with the shadow kept as a soft darkening.
- WISPS measured (wispL.py <tags>: hair pixels below the brows in front of the ear, g1v1): gS 2175 px L* 54.2; b17 / b18
  560 px L* 38.6; b15 95 px L* 11.4 (b16's wisp tiles helped, not enough). FIX: face cards WISP_LIFT 0.4 (tone x 1.4,
  depth shade off: dep = 1) and WISP_KIDS_FACE 10 hairs a picture (was 6).
- TAIL OUTLINE (TAIL_OUT 1.0: tail layers out together to the clump's p90 outer strands, like the head's sides):
  silhgeo front +x at 140 mm 97 -> 100 (strands 111): FAIL by 11 mm; profile unchanged (264 vs 308 at 140: the tail's
  back reach is 43 mm short in geometry). Next lever: a tail-specific SIDE_OUT_PCT (97) and SIDE_OUT_MAX over 12 mm.
- b19 batch (ONE offload hc-b19, --stage _g3_hc_s2 now packed by offload.sh): gb19 (all of the above, proxy shadows),
  gb19h (+ HL_LIFT 0.6 / HL_ALPHA 0.35), gb19c (+ CROWN_LOOP 0.6: silhgeo ear width 195 -> 187 at 100 mm, a loss to
  weigh against the crown flap), gb19sd (b19, default shadows: g1v1, g1backl), gb19ns (b19, no shadow). b19chain.sh writes
  game/gm_g4.png + gm_g4.txt (incl. neck.py, wispL.py) and review/g4_b19, review/g4.done.
- b19 RESULTS (hc-b19 on NICO-TOP; game/gm_g4.png + gm_g4.txt; review/g4_b19 blind): FAIL, 19 hair MAJORs (b18's g3:
  26; different reviewer runs, so the drop is partly noise), ALL game-visible: 15 at 3 m, 4 at 1 m only, 0 close-up-only.
  Left at 3 m: tight cap / no side volume, ears exposed (GROOM item: the groom is 2-21 mm under the photo); no
  face-framing locks; crown arc / loop (front) + notched crown gaps (back); tail a flat fanned sheet with blunt clumped
  ends, detached dark ribbons on the right; near-black nape wedge behind the ear; neck haze. 1 m only: streaky card
  planes, the hairline patchy with a dark top rim.
- SHADOW PROXY: NO EFFECT (gb19 proxy = gb19sd default shadows: skin L* 57.9 vs 58.1; gb19ns 63.9; the crops look the
  same). So the haze is NOT hair-scale alpha in the shadow map: any card shadow does it (the soft sun's penumbra over
  the neck, resolved at 24 samples). The strand groom casts almost none (gS 63.3 = no shadow). REVERTED (no dead code).
  Next to try: the light's shadow settings in the game look (sun angle / filter / jitter, more samples on one test view)
  or a cheap test of card_shadow off for the hair object, judged as a game-look choice by the coordinator.
- WISPS: WISP_LIFT works on tone: g1v1 wisp L* 38.6 -> 49.6 (groom 54.2), the reviewer now calls them light stray
  lines (MINOR, 1 m only). WISP_KIDS_FACE 10 did NOT add area (571 vs 560 px; groom 2175): the missing area is
  geometry (face-framing LOCKS to the jaw; the groom's own wisps are long), not hairs per picture. Kept both.
- HAIRLINE: rim - inner g1v0 +2.1 -> +5.0, g1v1 0.0 -> +3.2 (groom +17.8 / +19.0). b19h (HL_LIFT 0.6, HL_ALPHA 0.35)
  rendered the SAME rim numbers to 0.1 as b19 (GLBs differ): the stronger setting does nothing visible at 1 m. Defaults kept.
- CROWN_LOOP 0.6 ADOPTED (gb19c): the knob over the 3/4 crown is gone; the front still shows an arc with backdrop under
  it; front widths at 1 m kept (191 at 100 mm, 197 at 140). Hairline rim g1v1 +6.1.
- TAIL_OUT kept: front width at 140 mm 192 -> 194 (render), geometric +x 97 -> 100 vs strands 111 (FAIL by 11 mm).
- Tooling: offload.sh's stage pack ran under plain python3 (no hifipushie module): the job synced the stage on the
  machine instead (+~3 min, harmless). Fixed: `capped uv run --project $W python ... --stage _g3_hc_s2`.

## Handover 2026-10-16 (hair-cards agent, round 11)
Commits: 7fb76afc (wisps lit, TAIL_OUT, the shadow proxy), notes, + this one (proxy reverted, CROWN_LOOP 0.6 on).
Nothing in flight. Scratch new: neck.py, wispL.py (both <tags>).
STATE: b19 FAIL, 19 game-visible MAJORs (15 at 3 m). Wins kept: wisp tone, crown loop, tail out, hairline +3-5 L*.
NEXT: (1) neck haze: the game look's shadow settings (not the cards' alpha); (2) the tail as one rounded rope
(profile: flat fanned sheet; detached right ribbons = tail clumps' outer layer stand-off); (3) nape wedge behind the
ear (L* of the nape cards vs the groom); (4) front crown arc; (5) groom items for the coordinator: side volume over the
ears, face-framing locks to the jaw, centre part, colour.

## hair-cards round 12 (2026-10-16, fresh session; b20 batch, game/gm_g5.png, review/g5_b20)
- RESULT: FAIL, 21 game-visible hair MAJORs (14 at 3 m, 7 at 1 m only, 0 close-up-only); g4_b19 had 19 (15 at 3 m). Same
  prompt / settings as g4. Reviewed gb20 (b19c + face cards 6 mm + edge normals + game shadow map).
- NEW TOOLS (scratch /mnt/data/hifipushie/haircards): tailx.py <tags> (tail cross-section strands vs card GLB: sd major x
  minor, roundness, r97, angular fill, facing |n . radial|), wedge.py <tag> <view> <others> (darkest hair blob L*),
  nape.py <tag> <view> <x> <y> (GLB verts under a pixel: n . to-eye), tailprof.py (ID-pass tail outline: does NOT work
  on gS, its ID pass isn't hair-red). shots.py flat=1 + params {"flat": 1}: unlit albedo game pass (laptop OK, 8 s).
  shots.py shadow=game[:mm[:filter]] -> light keys shadow_res / shadow_filter (blender_scene._light_rig: EEVEE
  shadow_maximum_resolution / shadow_filter_radius = a game cascade's texel + PCF).
- (1) SHADOW: game practice = alpha-TESTED shadow casting at the card cutoff (UE masked; HDRP Alpha Clip Threshold
  Shadow), PCF-filtered at a cascade texel, contact shadows; written into shading.py's hair_cards notes. Our
  game_material is already a binary alpha cut, so the grain is not alpha hashing. Skin L* under the tail: gS 63.3, no
  card shadow 63.9, default 58.1, game 4 mm / filter 2 58.8, game 8 mm / filter 3 59.8. Target >= 62: FAIL (+1.7 best).
  The reviewer still calls it a dark dithered smear at 3 m. Next: the EEVEE soft-sun penumbra over thin cards
  (sun angle 3 deg; shadow ray / step count) or a judged game-look choice by the coordinator: card shadows off at
  game distance (hair shadow LOD), contact only. Keep shadow=game:8:3 for game sets (most game-like, best number).
- (2) TAIL: measured, the cards ARE already a round bundle in geometry and normals (tailx at 40-200 mm from the tie:
  roundness strands 0.66-0.79 / cards 0.69-0.72, r97 within 5 mm, fill 0.88-1.0, facing 0.83-0.90). So "a flat fanned
  sheet / curtain" is NOT the card distribution. Profile crops: the cards' tail juts ~50 px further back at the bottom
  and misses the groom's in-curl of its lower third; ends blunt. Edge-rounded normals (EDGE_ROUND 1: each card edge
  gets the cylinder's normal there) did nothing visible: reverted to 0 (knob kept). Next: the tail's lower third
  follows the mean (fit end_share 0.08) and loses the curl: fit the tail cards per wave phase lower down / shorter
  end clumps; then a tube judged in profile against the groom.
- (3) WISPS: face cards half width 3.5 -> 6 mm: wisp area g1v1 534 -> 1403 px (groom 2175), L* 52.8 (groom 54.2). KEPT,
  but the reviewer now calls them PALE grey/blonde ribbons in front of the ear (a 3 m MAJOR): WISP_LIFT 0.4 x wider
  cards = bright planks. Next: WISP_LIFT 0.2 and FACE_ALPHA down, measured against the photo's cheek L* not the groom's.
- (4) STRIPING: band g1v0 6.25 -> 6.38, g1v1 6.16 -> 6.23, g1v2 6.00 -> 6.11, back 5.17 -> 5.10 (target 4.8-5.2): FAIL.
  TINT_RANGE 0.93-1.07 (gb20t) gave the SAME band to 0.04: per-card tint does not drive the lock bands. Edge normals
  don't either. Left: the atlas tiles' own contrast (tile picture variety: 24 tiles, depth shade baked in) and layer
  order (coverage layer showing through the top layer's gaps). Next: band of the atlas tiles alone (flat pass, one
  tile everywhere) to split picture vs geometry.
- (5) NAPE WEDGE: traced. Flat albedo there L* 51.4 (normal); lit 7.6; no card shadow 8.1; groom 33.5. So LIGHTING, not
  albedo or card shadow. nape.py: the visible verts are TAIL cards (y +0.14 m) whose shading normals turn from the eye
  (n . to-eye -0.10, 68% < 0): the tail's neck-facing side. backscatter 1.0 (gb20w) 7.9, edge normals 7.5: FAIL. The
  notes' wrap diffuse ((N.L + 0.45) / 1.45, 0.55 of the shadow) is NOT in blender_cards.game_material (Principled, no
  wrap): the in-Blender game look is darker on the far side than the engine we describe. Next: wrap diffuse in
  game_material (a Translucent lobe weighted to the wrap, or a shader-to-RGB-free mix), then re-measure the wedge.
- Groom items (unchanged, coordinator's): side volume over the ears, centre part, colour (lighter / greyer than the
  photo at 3 m), face-framing locks to the jaw.

## Handover 2026-10-16 (hair-cards agent, round 12)
Commits: dc4ef7a7 (b20 tooling + changes) + this one (EDGE_ROUND off, shading shadow note, notes). Nothing in flight.
STATE: b20 FAIL, 21 game-visible MAJORs (14 at 3 m). Kept: wider face cards (area x2.6), shadow=game:8:3 for game sets.
NEXT: (1) wrap diffuse in game_material (nape wedge + dark ribbons), (2) wisp tone down (pale ribbons), (3) tail's
lower-third curl in profile, (4) striping: split atlas vs geometry, (5) neck smear: sun penumbra / shadow LOD decision.

## hair-cards round 13 (2026-10-16, fresh session; coordinator's five decisions; b21 batch, game/gm_g6.png, review/g6_b21)
- (1) WRAP DIFFUSE in blender_cards.game_material (c0f4e91a): the notes' max(0, (N.L + 0.45) / 1.45). Principled keeps
  Lambert + the shadow map; the rest of the wrap (wrap - max(0, N.L)) is added per sun as emission, albedo x sun
  irradiance / pi x lift, unshadowed (light through hair). Suns (hp_sun*) are copied into the material before EVERY
  frame (blender_cards.set_wrap_lights; views re-aim the suns). params "wrap": w (0 = plain Lambert). TEST
  spikes/haircards/wraptest.py (one card, albedo 0.5, one sun, no world, EXR): ratio to N.L = 1 at N.L 0.71 / 0.17 /
  0 / -0.20 / -0.34 / -0.45 / -0.77 = 0.799 / 0.430 / 0.318 / 0.173 / 0.075 / 0 / 0 vs the formula 0.798 / 0.430 /
  0.310 / 0.173 / 0.074 / 0 / 0: PASS (lit radiance 0.4788 vs 0.5 x 3 / pi = 0.4775, so the calibration is right).
  Deviation from the notes: "keep ~0.55 of the shadow map" is not in (the lift is unshadowed, the Lambert part fully
  shadowed): nodes can't read one sun's shadow term. Test gotcha: an image made by images.new + pixels renders
  transparent in EEVEE (alpha cut); load it from a PNG file like the GLB's atlas.
- (2) HAIR SHADOW LOD (shading.py hair_cards notes, with the engine mapping: UE per-LOD Cast Shadow, Unity LOD Group
  renderers Cast Shadows Off at LOD1+, HDRP contact shadows in the Volume, Godot cast_shadow per visibility range):
  LOD0 (1 m) cards cast alpha-tested at the cutoff + contact shadows; 3 m+ no card shadow. Game render: shots.py
  shadow=game* views g3* get card_shadow False (view key; blender_scene sets visible_shadow on hp_card objects per
  frame); shadowlod=0 keeps them. EEVEE 5.1 has no contact shadows: the stage's horizon scan (fast GI) is the
  stand-in for the screen-space contact term.
- (3) TAIL lower third, measured in PROFILE against the strands (new scratch tailside.py <tags>: side-view coverage
  raster, 10 mm bands under the tie, visible back edge at 7% / 50% coverage + weighted p97 / mean / p3): b20's cards
  are NOT further back than the groom anywhere (lower third: visible back edge -10.1 mm at 7%, -4.3 at 50%; the
  geometry ends no lower). The round-12 read ("juts ~50 px further back") came from the 3/4 v2 camera, not the side
  plane. What IS off: the bottom 30-40 mm stop short of the groom's curl (back edge at 170 mm: -28 at 7%) and the
  bottom front edge doesn't swing forward (190 mm: +12 mm). TAIL_END knob (fa8d2283; default 0.08): b21e = 0.03, the
  cards run on into the curl: lower-third back edge -3.6 mm at 7% (max 0), +2.3 at 50%; front edge at 190 still +11.8.
- (4) WISPS: WISP_LIFT 0.4 -> 0.2 in b21 / b21e (measured in the batch: wispL.py, groom L* 54.2, b20 52.8).
- (5) STRIPING split: b21u = b21 with the atlas colour made uniform (alpha-weighted mean RGB, alpha kept: same
  coverage). If its lock band stays near b21's: geometry (normals / layer order); if it drops to ~4.8-5.2: the pictures.
- b21 batch (ONE offload hc-b21, b21chain.sh, MAIN = gb21e): gb21e (all, 6 views), gb21 (TAIL_END 0.08), gb21nw (wrap
  off: g1v1, g1backl), gb21u (uniform atlas: 4 x 1 m), gb21L0 (card shadows kept at 3 m). Same review prompt as g4 / g5.
- b21 RESULTS (hc-b21, 10 min on NICO-TOP; game/gm_g6.png + gm_g6.txt (+ gm_g6_first.txt: the chain's first sheet call
  died on gb21u, which has no 3 m frames; b21chain.sh fixed, b21post.sh reran sheet / pairs / review); review/g6_b21,
  MAIN gb21e, same prompt / settings as g4 / g5): FAIL, 29 game-visible hair MAJORs (25 at 3 m, 4 at 1 m only, 0
  close-up-only); b20 had 21. The colour fault ("too light / grey vs the dark brown") is now counted in 4 regions.
- NAPE (wedge.py, b20's darkest blob, g1backl; groom 33.5): b20 7.3 -> gb21 22.1 / gb21e 23.0 (wrap), wrap off gb21nw
  8.2: the wrap is the lever, +15 L*; still 11 short (FAIL). The reviewer still calls a dark ragged block behind the ear
  (1 m only). Next: the notes' "0.55 of the shadow" term (not in nodes) or the wrap applied to the card's back side.
- SHADOW LOD (neck skin L*, groom 63.3 / 63.2): 3 m gb21 (no card shadow) 64.0 vs gb21L0 (kept) 59.7: PASS at 3 m.
  1 m (LOD0 casts, by decision) 59.4. The reviewer still lists "grainy speckle on the upper back" at 3 m (region 4).
- STRIPING (gsheet band, DoG 2.5-8; target 4.8-5.2): gb20 6.38 / 6.23 / 6.11 / back 5.10 -> gb21 5.49 / 5.26 / 5.62 /
  4.29, gb21e 5.83 / 5.66 / 5.49 / 4.33. So most of the lock banding was LIGHTING (the far side of every card went
  black under Lambert), not the pictures or the tint. gb21u (uniform atlas) frames exist (1 m only) but its band was not
  measured: gsheet needs the 3 m frames; next session: a 1 m-only band read of gb21u vs gb21 to split what is left.
- WISPS (wispL, groom g1v1 54.2 / g1v0 46.2): gb21 53.3 / 41.3 (b20 52.8 / 35.5): the wrap lifted them more than
  WISP_LIFT 0.2 took off; the reviewer still calls them pale beige ribbons (3 m). Next: WISP_LIFT 0 with the wrap, and
  narrower / darker face cards; judge against the photo's temple, not the groom's.
- TAIL: gb21e (TAIL_END 0.03) vs gb21: reviewer still "flat paddle / blunt comb ends / dark crunchy patch mid-tail".
  Geometry matches the groom's side profile within ~4 mm; the read is the cards' planar picture + ends, not the reach.
- HAIR L* (gsheet): gb21 36.3 / gS 32.1 / photo 41.2 at g1v1; the wrap brightened the cards past the groom (colour
  MAJORs). Kept the wrap (it is the spec); next: tone the albedo down by the wrap's average lift.

## Handover 2026-10-16 (hair-cards agent, round 13; stopped at the 70-tool-call rule)
Commits: c0f4e91a (wrap diffuse + shadow LOD + wraptest), fa8d2283 (TAIL_END), a18f4cce + this (notes). Nothing in flight.
STATE: b21 FAIL, 29 game-visible MAJORs (25 at 3 m) vs b20 21. Wins measured: nape +15 L*, lock band -0.6 to -0.8
(near target), 3 m neck skin = groom. Losses: hair too light (wrap lift on an albedo tuned for Lambert), wisps paler.
NEXT: (1) albedo down by the wrap's mean lift (hair L* back to the groom's 32), (2) WISP_LIFT 0 + darker face cards,
(3) band of gb21u at 1 m, (4) nape: wrap on the back side / shadow leak, (5) tail ends + mid-tail dark patch.
Scratch new: tailside.py <tags>, b21chain.sh, b21post.sh, neck.py NV=<view>.

## hair-cards round 14 (2026-10-16, fresh session; b22 batch, game/gm_g7.png, review/g7_b22)
- RESULT: FAIL, 21 game-visible hair MAJORs (15 at 3 m, 6 at 1 m only, 0 close-up-only); b21 had 29. Same prompt /
  settings as g4-g6 (b22chain.sh). Against the groom, colour is now a MINOR in both groom pairs ("close to the groom",
  "slightly darker, no highlights"). Against the photo it is still a MAJOR in 4 pairs ("too light / grey vs the dark
  warm brown"): that is the GROOM's colour (cards' chroma / hue = the groom's to 0.5 C* / 2 deg), the coordinator's item.
- TOOLS (spikes/haircards + scratch): colour.py <tag> (hair L* / C* / hue on the COMMON mask of both ID passes, and
  the albedo factor k that brings the cards' mean L* to the groom's through Blender's AgX curve: out/agx_ramp.png, an
  AgX'd grey ramp, no render). gsheet.py draws a blank cell for a tag's missing frame (1 m-only tags). hx.py gain=
  (hair.export.card_gain) and hc.<CONST>= (hair_cards constants). Flat passes per triangle range (shots.py only=
  [[start, count]] from the export json "layers"; core = cap range's last fixed_parts.core tris) = the ID trace.
- (1) COLOUR: wrap's mean lift measured 1.28 (gb21 / gb21nw, g1v1 and g1backl). k to the groom on gb21e: 1 m
  0.79-0.90 (mean 0.84), 3 m 0.88-0.94. b22 card_gain 2.5 -> 2.10 (x 0.84): g1v1 L* 31.9 (groom 32.2) PASS; g1v0 33.3 /
  34.1, g1backl 35.0 / 36.2; but 3 m now dark: g3v0 33.6 / 36.3, g3backl 36.2 / 39.4. The model under-predicted the
  darkening (k after = 1.02-1.17, the spec doesn't scale but AgX's shoulder does). b22k (1.95, the full wrap lift) is
  darker everywhere: rejected. Next: gain ~2.25 (between, per colour.py on gb22: 1 m k 1.02-1.13) if 3 m matters more.
- (2) WISPS: WISP_LIFT 0 + gain: wisp L* g1v1 53.4 -> 41.6 (groom 54.2), g1v0 41.1 -> 36.3 (groom 46.2): now DARKER
  than the groom; the reviewer calls them "thin, stiff, dark" cards in front of the ear (1 m only, was pale ribbons at
  3 m). Area unchanged (1436 px vs groom 2175). The fault is shape (stiff planks standing off), not tone. Next:
  WISP_LIFT ~0.15, and fewer / thinner / closer-to-the-cheek face cards.
- (3) STRIPING: gb21u (uniform atlas) band 4.92 / 5.03 / 5.27 / back 3.53 vs gb21 5.49 / 5.26 / 5.62 / 4.29: the tile
  pictures add 0.2-0.6, the rest is geometry / light. b22 band 5.61 / 6.02 / 5.80 / 4.45 (target 4.8-5.2): FAIL, UP
  from gb21e (5.83 / 5.66 / 5.49); the darker albedo didn't shrink it. Hairline rim also fell: rim-inner g1v1 +3.6
  (gb21e +6.5, groom +19): HL_LIFT's light roots darkened with the gain. Next: HL_LIFT up to keep the rim; band
  needs the tiles' contrast (gb21u says ~0.4 of it) plus the geometry part, not tone.
- (4) NAPE: shadow_leak (game_material param, the notes' 0.55 shadow keep: Principled x (1 - leak) + leak x Lambert
  unshadowed in the wrap emission; wraptest lit PASS) changed NOTHING at the nape (b20 blob gb22 19.7 / gb22sk 18.5,
  groom 33.5; neck numbers identical): the nape hair is not in the shadow map's shadow, it faces away from the sun
  (wrap 0 under N.L -0.45). Preview limit noted in the param doc: the leak also scales world ambient. Flat pass: the
  dark serrated block behind the ear is ALBEDO (dark in flat): layers 0 / 1 head cards under the tie, the deep-shaded
  underside of the picture. The reviewer: "dark spiky saw-tooth fringe" (1 m MAJOR x2). Next: lighten the depth shade
  on the underside of nape head cards (or HL-like soft roots at the nape hairline), not lighting.
- (5) TAIL: dark mid-tail patch TRACED and FIXED: flat passes per range (layers 0-3 clean, the cap range's tail CORE
  dark): the core tube's square ragged end showed through the thinning cards. CORE_SHARE 0.2 -> 0.5 (ends inside the
  cards) + CORE_TAPER 0.25 (closes to a point): gone in flat (fb22) and no reviewer mention of a dark patch. Tail ends:
  TIP_TAPER_TAIL 0.3 + TIP_FADE_TAIL 0.12 (alpha fade under the cutoff): the reviewer still says "blunt comb-like",
  "cut square, jagged comb-tooth" (3 m MAJOR), and the groom pair now says "thin and straggly". Tail SHAPE (paddle /
  volume) is the bigger fault.
- Kept in b22: gain 2.10, WISP_LIFT 0, TAIL_END 0.03, tail tips, core 0.5 / 0.25 (exp/b22, hx.py hc_s2 exp/b22 gain=2.10
  hc.CORE_SHARE=0.5 hc.CORE_TAPER=0.25 hk.WISP_LIFT=0 hk.TAIL_END=0.03 hk.TIP_TAPER_TAIL=0.3 hk.TIP_FADE_TAIL=0.12).
  Module defaults unchanged (b21 behaviour) until the coordinator approves.

## Handover 2026-10-16 (hair-cards agent, round 14; stopped at the 70-tool-call rule)
Commits: ad80a61d (tail tips, shadow_leak, gsheet, colour.py), f8bab542 (core knobs, wraptest leak) + this (notes).
Nothing in flight. STATE: b22 FAIL, 21 game-visible MAJORs (15 at 3 m) from 29. Colour vs groom matches at 1 m (3 m
-3 L*); mid-tail dark patch gone. NEXT: (1) gain ~2.25 (3 m), HL_LIFT up (hairline rim), (2) face cards: shape, not
tone (WISP_LIFT ~0.15, closer to the cheek), (3) nape: underside depth shade of head cards under the tie (albedo),
(4) striping: tile contrast (~0.4) + geometry, (5) tail shape / volume (paddle) before ends. Scratch: b22chain.sh,
b22exp2.sh, b22_renders.json, colour.py, gsheet_lite.py. Note: an earlier mis-run (tesshair7's shots.py picked by
run.sh's _find for a bare "shots.py") rewrote out/s_hc_s2_v0/v1/v2.png and right.png (strand groom, same model).

## hair-cards round 15 (2026-10-16, fresh session; b23 batch, game/gm_g8.png, review/g8_b23)
- DEFAULTS (coordinator): b22's values are the module defaults now (hair_cards CORE_SHARE 0.5, CORE_TAPER 0.25;
  hair_clumps TAIL_END 0.03, TIP_TAPER_TAIL 0.3, TIP_FADE_TAIL 0.12; blender_cards SHADOW_LEAK 0.45 = game_material's
  default) and hc_s2's spec carries hair.export.card_gain 2.10 (history v6): exports no longer need command-line knobs
  (hx.py hc_s2 <dir> = b22 + this round). Hair tests, one file per process: all pass (test_face_wisp_cards_are_lit_and_lighter
  wants WISP_LIFT > 0: 0.15 now, item 5).
- Scratch fix: env.sh's _find now looks in spikes/haircards before spikes/tesshair7 (a bare "shots.py" resolved to
  tesshair7's, the round-14 mis-run).
- (1) 3 m COLOUR: NOT the cards. gsheet own-mask L* 1 m -> 3 m (gm_g7): photo 42.0 -> 40.4 (g1v0 / g3v0), cards gb22
  33.3 -> 33.5, strand groom gS 35.2 -> 39.6. The cards hold their L* with distance like the photo; the GROOM gets ~4 L*
  lighter at 3 m (its sub-pixel strands drawn wider: the light front hairs cover more of each pixel). So "3 m dark vs the
  groom" is the groom's render, and a per-LOD gain would be wrong (no engine does it; the photo says distance-invariant).
  Mips checked anyway (numpy box chain of exp/b22's atlas, cutoff 0.33): alpha coverage x1.00 / 1.02 / 1.04 / 1.05 /
  1.06 to mip 4 (x1.20 at mip 7), colour over covered texels within 1% (basecolor is dilated under alpha 0): no mip
  darkening. Coverage-preserving mips (shading.py notes already ask for them) stay the engine instruction.
- (2) NAPE: NAPE_LIFT (hair_clumps.bake_tiles: head cards rooted under the head centre and beside / behind it get tint
  x (1 + 0.6), NAPE_BAND / NAPE_Y smoothstep ramps). First try (y ramp from the centre back) left the dark serrated
  marks behind the ear untouched (flat g1backl: NAPE_LIFT 0.6 and 1.2 identical, b23 / b23n); NAPE_Y now starts 25 mm
  in front of the centre. Measured in the batch (wedge.py + crops).
- (4) TAIL measured before changing (tailx.py b22, slices along the tail axis): cross-section matches the groom within
  ~10% (sd 18.7 x 13.3 vs 18.5 x 14.6 at 40 mm, 27.2 x 19.9 vs 29.6 x 19.5 at 200 mm; roundness 0.69-0.73 vs 0.66-0.79;
  r97 3-5 mm short). The 3 m crops: the groom's tail is wavy, curling, ragged-full at the end; the cards' a smooth
  straight sheet ending in aligned tapered points (the "comb"). Change: TAIL_END_JIT 0.15 (each tail card ends at its
  own share: staggered ends); b23t = TIP_TAPER_TAIL 0.15 (less point per card). The wave itself is not in the cards.
- (5) WISPS: WISP_LIFT 0.15, FACE_PER 4 -> 6 (b23 face/L0 60 cards), FACE_YO 0.5 (face card layers half as far off
  their clump's centre).
- (6) HL_LIFT 0.35 -> 0.8.
- (3) STRIPING: per-layer frames in the batch (gb23cap / gb23layer0..3, 1 m, lit, own id masks: layerband.py).
- b23 batch (ONE offload hc-b23, 23 min on NICO-TOP; b23exp.sh + b23chain.sh + b23mk.py; game/gm_g8.png + gm_g8.txt,
  review/g8_b23, same prompt / settings as g4-g7): FAIL, 24 game-visible hair MAJORs (15 at 3 m, 9 at 1 m only, 0
  close-up-only); b22 had 21. Colour is no longer a MAJOR in any pair. New or louder: "thin cap / scalp through the
  cards / forehead open" (3 m, photo pairs), "narrow silhouette", "tail short, stops at chin" (photo pairs: the groom's
  own length), "crown flap" at the upper left (3 m, groom pairs), speckle on the neck / back (1 m).
- Numbers b22 -> b23 (groom): hairline rim-inner g1v1 +3.6 -> +7.4, g1v0 +5.5 -> +6.2 (+19 / +17.8): better, still
  FAIL. Wisp L* g1v1 41.6 -> 45.3 (54.2), g1v0 36.3 -> 37.3 (46.2); wisp area 1436 -> 1314 px (2175): the face
  cards still read as "stiff straight strips" (1 m, 3 pairs). Band g1v0 / g1v1 / g1v2 / back 5.61 / 6.02 / 5.80 / 4.45
  -> 5.67 / 5.71 / 5.61 / 4.36. Hair L* = the groom's at 1 m (k 1.00-1.03 except g1v2 1.18).
- (3) STRIPING BY LAYER (layerband.py, each range alone, own id mask, 1 m, g1v0 | g1v1): cap 5.05 | 6.81, layer0
  5.51 | 5.63, layer1 6.54 | 5.90, layer2 8.05 | 6.43, layer3 (singles) no pixels. The TOP layer (layer2, 64 head
  cards) stripes most, then layer1; the coverage layer0 is near the target. Not fixed this round: next is layer2's
  per-card normal / tint spread (fewer, wider, lower-contrast top cards or its tint range narrowed), measured the
  same way.
- (2) NAPE: FAIL. wedge blob gb22 19.7 -> gb23 18.6, gb23n (NAPE_LIFT 1.2) 18.6: the lift does not reach the dark
  marks even with NAPE_Y (the cards drawing them are probably not "head" cards rooted low: cap range or tail /
  hairline cards). Next: flat pass per range (shots only=) at g1backl to name the range, then lift THAT.
- (4) TAIL: TAIL_END_JIT and b23t (TIP_TAPER_TAIL 0.15) change nothing measurable (cross-section, side profile within
  1-2 mm of b22; lower-third back edge -19.3 / -18.3 vs -19.0 mm). The reviewer: "flat broad sheet, repeating diagonal
  streaks", "spiky ends", "straight stringy sheets" vs a wide WAVY mass. The miss is the wave (cards follow straight
  clump centre lines) and the bottom 150-180 mm (back edge -33 mm: the curl), not the width.
- (1) 3 m colour: see above (the groom brightens at 3 m; cards and photo don't). No change made.

## Handover 2026-10-16 (hair-cards agent, round 15; stopped at the 70-tool-call rule)
Commits: b0f91ab8 (b22 values as defaults + round-15 knobs), 05af25b8 (NAPE_Y), notes. Nothing in flight.
STATE: b23 FAIL, 24 game-visible MAJORs (15 at 3 m) vs b22 21. Wins: hairline rim, wisp tone, band at g1v1 / g1v2,
colour off the MAJOR list. No effect: NAPE_LIFT, tail end jitter / taper. Defaults now = b23 (exports need no knobs).
NEXT: (1) the nape: name the dark marks' triangle range by flat passes per range, (2) striping: layer2 (top) first,
(3) tail wave / curl (cards along the clump's wavy centre line, not a straight one), (4) crown flap upper left (new at
3 m), (5) neck speckle at 1 m (shadow leak / dithering?). Scratch: b23exp.sh, b23chain.sh, b23mk.py, layerband.py.

## hair-cards round 16 (2026-10-16, fresh session; coordinator's gate change; b24 batch, game/gm_g9.png, review/gg9_b24)
- GATE SCOPE (coordinator): the cards gate is CARDS vs the STRAND GROOM at 1 m / 3 m; the photo stays on the sheet as
  context only, photo-vs faults the groom shares go to the coordinator's groom list. Rule written in gates.md "Source-asset
  scope" (59debb1e). Scratch: gpairs_g.py <dir> <sheet> <cards col> (groom gS = the reference in all six rows), rvg.sh <dir>
  (the scoped review prompt: "cards reproducing the strand groom shown as the reference").
- (1) BASELINE b23 vs the groom (review/gg8_b23, no new render): FAIL, 24 game-visible MAJORs (19 at 3 m, 5 at 1 m only,
  0 close-up-only). By cause: colour flat, the groom's light / blonde strands lost (4: front, 3/4, profile, front 3 m);
  face wisps darker, fewer, shorter than the groom's (4); crown card standing off / faceted crown outline (4, upper left
  in back 3/4, top in profile); tail narrower / straighter / shorter / pointed ends / detached strips (4); nape fragments
  + neck speckle (3); hairline strips, no centre part (2); ears bare (1). Note the groom DOES show a part and blonde
  highlights: these are now cards faults, not photo faults.
- (5) NAPE TRACED: flat passes per triangle range at g1backl (flatr.sh <exp> <view> name=start,count ...; b23 ranges:
  cap, layer0 halves, layer1 halves, layer2, layer3, then layer1's head end 12982+686 and hanging/L1 13668+3446): the dark
  serrated marks behind the ear are drawn ONLY by HANGING (tail) layer-1 cards; head cards draw none. That's why
  NAPE_LIFT (head cards only) changed nothing in round 15. Fix: NAPE_LIFT also lifts tail cards by the same root test.
- (3) TAIL WAVE: tail / face cards' centre line = the mean of their strands by station, which straightens a wavy lock
  (phases differ) and smooths the curl (sigma 4 where few run). hair_cards._medoid_line: the line moved onto the clump's
  long strand nearest the mean (offset held before its root / past its end, sigma 1). MEDOID_TAIL / MEDOID_FACE = 1.
  tailside.py (no render): lower-third back edge b24m0 (medoid off) -19.3 mm, b24 -14.1 mm; mean -5.6 -> -0.5 mm; at
  150-160 mm -34 / -33 -> -22 / -17 mm. Better, not closed (the curl's outer strands stand further back than any medoid).
- (4) WISPS: FACE_END 0 (face cards run to their longest strand: wisps stopped at the jaw), WISP_LIFT 0.15 -> 0.5 (round
  15 measured +3.7 L* for +0.15; the groom's wisps are +9 L* over b23's), medoid curve. Tris 23268 -> 23720 (+2%).
- (2) STRIPING: TINT_TOP (0.93, 1.07) for the top head layer (was TINT_RANGE 0.85-1.15), measured per layer in the batch.
- (7) CROWN FLAP: flats show broad layer-1 / layer-2 head cards arcing over the upper-left crown with scalp under them;
  not changed this round (no time).
- b24 RESULT (ONE offload hc-b24, ~45 min incl. queue; b24chain.sh / b24mk.py / b24exp.sh; game/gm_g9.png + gm_g9.txt;
  review/gg9_b24 = cards vs the GROOM): FAIL, 20 game-visible MAJORs (13 at 3 m, 7 at 1 m only, 0 close-up-only) vs the
  b23 baseline 24 (19 at 3 m) under the same groom-scoped prompt. Remaining by cause: crown card plate / arched card at
  the upper left + shards at the top front (5, the biggest: 3 m in three views); tail straight / flat / ribbon strips
  flaring right / folded flap at its end (5); no centre part + dark flat top "helmet" (2); the groom's light streaks
  lost (1 side, plus in tail / crown faults); wisps short / sparse (3); hairline pale blotches (2, new: HL_LIFT 0.8 +
  WISP_LIFT 0.5 drew pale patches at the left forehead); neck / back speckle + nape stubble (1).
- Numbers b23 -> b24 (groom): nape wedge L* 18.6 -> 32.9 (33.5) PASS: tracing to hanging/L1 was right. Wisp L* g1v1
  45.3 -> 50.9 (54.2), g1v0 37.3 -> 44.4 (46.2); wisp AREA g1v1 1314 -> 1004 px (2175; b24m0 = 1314: the medoid line
  pulled the face cards onto one strand, narrower spread). Hairline rim-inner g1v1 +7.4 -> +8.6, g1v0 +6.2 -> +8.2 (+19 /
  +17.8). Layer2 band g1v0 8.05 -> 8.23, g1v1 6.43 -> 5.97 (whole hair 5.67 / 5.71 -> 6.27 / 5.28): TINT_TOP is not the
  striping's lever (the tile pictures / card geometry are). Hair L* at 1 m now LIGHTER than the groom (k 0.83-0.89 at
  g1v0 / g1v1 / g1backl, 3 m within 5%): b24m0 is the same, so it's the nape lift on tail cards + TINT_TOP, not the
  medoid; next round: lift only the cards the trace named (hanging/L1 rooted at the nape), not every tail card in the band.
- My look (pair_1 / pair_3): the neck speckle is plain at 1 m (dithered shadow under the tail); the groom's light
  streaks (crown, tail) are what the cards lose most; the tail reads lighter and flatter than the groom's.
- New groom-vs-photo items for the coordinator: none new; the scoped review sent nothing to OTHER STAGES.

## Handover 2026-10-16 (hair-cards agent, round 16; stopped at the 70-tool-call rule)
Commits: 59debb1e (gates.md source-asset scope), ec33a4d0 (medoid tail / face, FACE_END, WISP_LIFT 0.5, TINT_TOP),
the NAPE_LIFT-on-tail commit, notes. Nothing in flight. STATE: b24 FAIL, 20 game-visible MAJORs vs the groom (13 at 3 m);
groom-scoped baseline b23 = 24 (19). NEXT: (1) crown plate upper left (flats: broad layer-1 / layer-2 head cards arcing
over the upper-left crown with scalp under them: name the cards by range, then hold them under the envelope or drop
them), (2) light streaks: the groom's highlight strands per card tile (tile pictures average them away), (3) tail:
ribbon strips flaring right (tail L2 / L3 singles?) + folded flap at the end; curl back edge still -17..-22 mm at
150-160 mm, (4) wisp area (MEDOID_FACE 0.5?), hairline pale patches (HL_LIFT / WISP_LIFT down a step), (5) neck speckle
(shadow dithering of alpha-hashed cards on the skin), (6) the 1 m L* overshoot (narrow the tail nape lift to the traced
cards), (7) part line. Scratch: gpairs_g.py, rvg.sh, flatr.sh, b24*.

## hair-cards round 17 (2026-10-16, fresh session; b25 batch, game/gm_g10.png, review/gg10_b25)
- New measures (no render): crownx.py <tags> (scratch): per card (connected triangles of the GLB) the area of its
  alpha > 0.5 samples standing > 3 mm over the head + tail strands' p97 radius (3-deg direction bins) over the top
  (elevation > 20), per range the area > 5 / 8 mm from any strand point, and FOLDS (edge-adjacent triangles of one card
  turned > 120 deg). streak.py <tags> (frames): light-streak spread p95 - p50 L* and DoG detail std inside each render's
  own hair mask (g1v1 / g1v2 / g1backl / g3v0), a part dip at g1v0's top band, skin grain (DoG 0.6-1.5) under the tail
  at g1backl.
- BASELINE streak.py (gS | gb23 | gb24): p95 - p50 g1v1 21.9 | 10.4 | 13.0, g1v2 17.7 | 8.5 | 12.1, g1backl 14.6 | 9.6 |
  10.8, g3v0 26.9 | 11.7 | 15.6; median L* g1v1 30.6 | 32.2 | 35.4. The groom = a DARKER mass with light strands far over
  it; the cards = a lighter, flat mass (half the streak spread). Part dip g1v0 3.5 (col 245) | 2.0 | 2.6 (col 285: not at
  the groom's part). Skin grain g1backl std 0.31 | 0.42 | 0.42, skin L* 66.0 | 61.4 | 61.0 (the cards' shadow).
- (2) CROWN PLATE traced (crownx b24): ONE card stands off over the top, layer-1 card 133 (tri0 12398, 133 mm, arcing
  front -> over the pole -> back, az 7..341, el -4..87), 1.46 cm2 > 3 mm off; 37% of its vertices sit on NaN envelope
  bins: near the pole the 3-deg (az, el) bins are slivers with < 20 strand points, so _under_envelope never held it.
  Not a normal flip (no inward normals), not a stood-off layer. Fix: envelope() falls back to uniform cells on the unit
  sphere (~6 then ~12 deg). b25: 1.05 cm2 (partly closed; the rest not traced yet).
- (3) TAIL FLAP traced: hanging/L0 card 201 (60 mm wide at the tail's curl, z -90..-150 mm) has 10-11 folded triangle
  pairs; its strip's edges swap sides over ~30 mm: a half-turn TWIST of the frame where the curling line passes its core
  ("outward" swings round), not an in-plane bend (BEND_HW did nothing for it). Fix: TWIST_HANG 10 deg / station for
  hanging cards (hair_cards._clump twist=). Ribbons: HW_PER_STRAND 0.6 mm half width per running strand for tail cards
  (a few outer strands wore an 18 mm dense-tile ribbon).
- (1) colour: NAPE_LIFT on tail cards only for layer 1 (the traced range); TINT_TOP back from (0.93, 1.07).
- (4) streaks: TINT_TOP (0.85, 1.35): the top layer may run lighter than its tile, not darker; b25t = (0.85, 1.15)
  control, b25s = TINT_RANGE (0.85, 1.35) too (every head / tail card). Part: not changed (no time).
- (5) MEDOID_FACE 0.5 (b24 1.0 cut wisp area 1314 -> 1004 px), HL_LIFT 0.8 -> 0.5 (pale forehead blotches).
- (6) neck speckle: traced in the batch: b25 g1backl with shadow filter 6 (gb25sf) and with no card shadow (gb25ns).
- (3) after TWIST_HANG (crownx b25): folded pairs over all cards 74 -> 28, folded cards 31 -> 8; tail card 201 10 -> 6
  pairs (still folded, less). The crown card 133 standoff 1.46 -> 1.05 cm2. (crownx's "cap" row now shows 3.9 cm2 > 3 mm
  over the top: the cap's alpha in the new atlas, at scalp level under sparse crown strands. A measurement artefact,
  not a plate; exclude the cap next time.)
- b25 RESULT (ONE offload hc-b25, 6 jobs; b25exp.sh / b25mk.py / b25chain.sh; game/gm_g10.png + gm_g10.txt + geo_b25.txt;
  review/gg10_b25 = cards vs the GROOM): FAIL, 30 game-visible MAJORs (25 at 3 m, 5 at 1 m only, 0 close-up-only), up
  from b24's 20. NEW and the loudest: pointed card tips stand up out of the silhouette at the FRONT TOP / over the left
  forehead ("cat ears", pairs 0 / 1 / 2 / 4, 3 m; plain in pair_1). Still there: no centre part / dark cap, flat colour
  without blonde streaks (all six pairs), short / sparse wisps, the tail narrow / straight / in strips with a detached
  dark strand at frame-right, nape shards, neck grain, crown planks / jagged top edge.
- Numbers b24 -> b25 (groom): 1 m L* k (cards -> groom) g1v0 0.83 -> 0.91, g1v1 0.84 -> 0.96, g1backl 0.89 -> 0.98
  (the overshoot is gone; g1v2 1.02 -> 1.14 and 3 m 1.04-1.12 now a little dark). Nape wedge 32.9 -> 29.8 (33.5): giving
  the lift to tail layer 1 only cost 3 L*. Wisp area g1v1 1004 -> 1564 px (2175), g1v0 4998 -> 5100 (7214); wisp L*
  g1v0 44.4 -> 40.2 (46.2). Hairline rim-inner +8.1 / +8.7 (+17.8 / +19). Layer-2 band g1v0 7.96 / g1v1 6.10.
  Streaks p95 - p50: g1v1 13.0 -> 13.2 (gS 21.9), g3v0 15.6 -> 17.4 (26.9). Part dip 2.5 (3.5, at another column).
- TINT_TOP / TINT_RANGE up to 1.35 changed NOTHING: gb25, gb25t and gb25s are identical to 0.1 L* in every metric. The
  per-card tint (a card's mean strand tone / its tile's) never reaches 1.15, so the clip is not what holds the streaks
  back. Streaks need light strands INSIDE the tile pictures (or a per-card tone from its lightest strands), not the tint.
- (6) NECK SPECKLE TRACED: the cards' SHADOW on the skin. No card shadow (gb25ns): skin grain std 0.29, skin L* 65.9 =
  the groom's 0.31 / 66.0; with it (gb25) 0.42 / 61.1; a wider shadow filter (game:8:6, gb25sf) is worse (0.46). The
  groom casts almost no shadow there. Coordinator decision: a game's card shadow (shadow LOD at 1 m, a shadow-only alpha
  read at a coarse mip, or contact shadow only), or accept the groom's render as unshadowed.
- CAT EARS, partly traced (no render): crownx says TWIST_HANG is not it (b25tw0 = b25 over the top); MEDOID_FACE 1
  (b25mf1) cuts the top's standing-off area 4.9 -> 3.2 cm2 (b24 1.6), so MEDOID_FACE 0.5 (face lines half-way between
  the clump mean and a strand) is one cause; the envelope fallback is the other candidate. crownx does not single out
  the ear cards: they need a flat ID pass at g1v1 per range.

## Handover 2026-10-16 (hair-cards agent, round 17; stopped at the 70-tool-call rule)
Commits: 831bb630 (envelope fallback, nape lift on tail L1 only, TINT_TOP, HW_PER_STRAND, BEND_HW, MEDOID_FACE 0.5,
HL_LIFT 0.5), 793d63dd (TWIST_HANG), notes. Nothing in flight. STATE: b25 FAIL, 30 game-visible MAJORs (25 at 3 m) vs
b24 20: WORSE, because of new front-top "cat ears". The colour regression is fixed; the speckle is traced to the card
shadow; the tint lever for the streaks is ruled out.
NEXT: (1) cat ears: flat passes per range at g1v1 (flatr.sh b25 g1v1 ...), then A/B MEDOID_FACE 1 and the envelope
fallback off (b25mf1 exported). If nothing better comes up, return MEDOID_FACE to 1 and get the wisp area some other
way (FACE_PER). (2) streaks: light strands in the tiles (strand_tones' spread kept in the bake) and not the tint.
(3) the neck shadow: the coordinator decides. (4) the nape wedge is back to 29.8: NAPE_LIFT 0.8 for tail L1.
(5) tail card 201 still has 6 folded pairs: TWIST_HANG 6. (6) the part: still untouched.
Scratch: crownx.py, c133.py, c201.py, streak.py, b25*.

## hair-cards round 18 (2026-10-16, fresh session; b26 batch, game/gm_g11.png, review/gg11_b26)
- (1) CAT EARS NAMED (flat passes per range at g1v1, flatr.sh): they are the CAP (tris 0-3700), not a card layer. A/B:
  MEDOID_FACE 1 (b25mf1) and ENV_FALLBACK 0 (b25ef0, new knob) both still have them; b24 has none; TWIST_HANG 0 (b25tw0)
  has them; BEND_HW 0 (b25bh0) has NONE. Cause: BEND_HW narrowed layer-0 head cards at their bends, so cap vertices had
  no card within CAP_REACH / CAP_FAR and cap_under_cards left them at the MASS height: two points standing up. (Round
  17's crownx "cap" 3.9 cm2 row was this, not an artefact.) BEND_HW -> 0 (it never touched the tail flap). The strand
  part then made the same fault again (a cap knob at the front top: the part gap leaves cap vertices uncovered), so the
  structural fix: hair.CAP_BARE_FLOOR, a cap vertex with no coverage card in reach lies on the scalp (b26 cap flats at
  g1v1 / g1v0 clean, t18/b26flat3.png). Envelope fallback and MEDOID_FACE 0.5 kept (crown plate stays held).
  The review still names ONE dark jagged tuft above the top-left crown at 3 m (pair 0): not traced yet (a card, not the cap).
- (2) CARD SHADOW from a coarse mip (coordinator decision): blender_cards.SHADOW_MIP 16: the shadow pass (Light Path Is
  Shadow Ray) reads the cut coverage (alpha > cutoff) box-averaged 16 x 16 texels as a soft opacity (transparent
  shadows). Unit test spikes/haircards/shadowmip_test.py: a striped card's floor shadow std 0.42 -> 0.08 at the same mean.
  Shading notes (shading.py hair_cards "shadows") rewritten with the Unreal / Unity HDRP / Godot mapping. RESULT on the
  head: FAIL, it does not take the grain: skin under the tail g1backl grain / L* = mip 1 0.44 / 61.9, mip 16 (gb26) 0.42 /
  61.5, mip 32 0.44 / 62.0, no card shadow 0.29 / 66.2; groom 0.31 / 66.0. So the speckle is NOT the alpha's detail: it
  is the shadow map itself (shots shadow=game:8:3: 8 mm texels, filter 3, dithered transparent shadows over many
  overlapping cards) and its mean darkening (-4.5 L*). Next: a softer / wider-filtered hair-only shadow (filter at the
  texel of a coarse cascade, or the shadow_leak raised for the skin under hair), or contact-shadow-only at 1 m too;
  measure grain + L* against 0.31 / 66 for each.
- (3) STREAKS: hair_clumps.TILE_TONE_POOL 1: a tile's child hairs draw their tone ratio from the per-strand mean tones of
  every card wearing the tile (ratio p5 / p50 / p95 / p99 0.58 / 0.99 / 1.43 / 1.60, 21 tiles). Control b26tp0 (pool
  off): frames differ but every metric is equal to 0.01: NO measurable effect. Streak spread p95 - p50 g1v1 gS 21.9 |
  b25 11.6 | b26 14.2, g3v0 26.9 | 17.4 | 19.8: the gain is from the other b26 changes (cap / part / bends), not the pool.
  The tile's strands are not where the light streaks are lost: a per-card tone from its lightest strands, or more
  tiles for the top layer, are the next candidates.
- (4) PART: hair_clumps.strand_part reads the part from the strands (top roots, el > 35, first 3 cm sweep x share >= 0.35:
  hc_s2 has 1505 +x / 984 -x votes, a clean split at x = 0, spikes/haircards/partprobe.py) and wins over the spec's
  default line (hc_s2 has no parting: the default line sat at x = 3 cm). Result: FAIL, part dip g1v0 gS 3.5 | b25 2.5 |
  b26 1.1 | b26pt0 (strand part off) 2.9, all at col ~283 (the groom's at 245). The split leaves a gap but the cards
  over it don't sweep away from it; the review still says "no part, dark cap" (3 m). Not kept as a win; keep the code
  (it's what exposed the cap knob) but the part needs the cards' ROOT ends turned away from the line, not just a split.
- (5) NAPE_LIFT 0.8: wedge 29.8 -> 30.2 (groom 33.5), small. TWIST_HANG 6. The detached dark strand at frame right:
  not traced (the review: "a large clump swings out to the right at tie height + 100 px", pair 3).
- b26 RESULT (ONE offload hc-b26, 6 jobs, NICO-TOP; b26mk.py / b26chain.sh; cards vs the GROOM): FAIL, 17 game-visible
  MAJORs (14 at 3 m, 3 at 1 m only, 0 close-up-only) vs b25's 30 and b24's 20: the best count so far. Remaining by
  cause: top dark / flat / no blonde streaks (5), no part / dark cap (2), wisps few / short / faint (3), tail narrow /
  strips / blocky ends / detached clump (4), dark tuft over the top-left crown (1), crown blotches (1), neck speckle (1).
  Hairline rim-inner g1v1 +9.7 (+19), wisp area g1v1 1566 px (2175).

## Handover 2026-10-16 (hair-cards agent, round 18; stopped at the 70-tool-call rule)
Commits: f0c2449b (SHADOW_MIP + ENV_FALLBACK knob), 22823757 (TILE_TONE_POOL), 8f9b6496 (BEND_HW 0, strand_part,
NAPE_LIFT 0.8, TWIST_HANG 6), 267d977d (strand part first), a815a680 (shading notes), 9c07ce81 (CAP_BARE_FLOOR), notes.
Nothing in flight. STATE: b26 FAIL, 17 game-visible MAJORs (14 at 3 m) vs the groom, best so far; cat ears gone (cap).
NEXT: (1) the card shadow: coarse mip did nothing, the grain is the shadow map's (try filter / leak / contact-only at
1 m, measure vs 0.31 / 66); (2) streaks: tone pool did nothing measurable; try a per-card tone from its lightest strands
or top-layer tiles; (3) part: turn the cards' roots away from the strand part (sweep), measure the dip at the groom's
column; (4) the dark tuft over the top-left crown (flat pass per layer at g1v0); (5) tail detached clump (pair 3).
Scratch: r18a-f.sh, b26mk.py, b26chain.sh, t18/ (flat sheets, partprobe.py), shadowmip_test.py.

## hair-cards round 19 (2026-10-16, fresh session; b27 batch launched: game/gm_g12.png, review/gg12_b27)
- (1) SHADOW PROXY (coordinator decision): hair_cards.shadow_proxy (card triangles sampled into a 4 mm grid, closed 4
  voxels, holes filled, eroded 4 mm in, blurred 1.2 voxels, marching cubes step 2: ~9k tris on hc_s2, 0.6 s), written
  by export_hair beside each GLB as `<name>_hair_<tier>_shadow.obj` (Y-up), named in extras hifipushie_hair.shadow_proxy;
  hair_glb_look imports it shadow-only (blender_cards.shadow_proxy: camera / diffuse / glossy / transmission rays off),
  the cards' visible_shadow off; the per-view shadow LOD toggles the proxy instead of the cards. shots.py proxy=0 = the
  old card shadow. Shading notes (shading.py hair_cards "shadows") now lead with the proxy + Unreal / Unity / Godot.
  LOCAL PROOF (g1backl 1080, 8 samples, b26 + its proxy, t19/l19_neck.png): the proxy casts and the cards don't (frame
  diff proxy vs cards 0.45 mean, the shadow's outline changes), BUT skin grain / L*: cards 0.65 / 63.1, proxy 0.65 /
  62.9, none 0.29 / 66.7. FAIL on the target: the grain is NOT the dithered cards, it is EEVEE's shadow-ray noise on
  any shadowed skin (STAGE_EEVEE shadow_ray_count 4 + step 16: cards 0.41, proxy 0.42, same for both). And the target
  0.31 / L* 66 is an UNSHADOWED skin: the groom casts no shadow at all (blender_strands.py: the groom object's
  visible_shadow = False). Any honest hair shadow will read darker than the groom there. Coordinator call: shadow the
  groom too (fair A/B), or judge the neck with both unshadowed; and raise shadow_ray_count for game renders.
- (3) PART: hair_clumps._part_root (PART_ROOT_REACH 0.03): a head card rooted within 3 cm of the strand part gets a
  Hermite lead-in from the part's edge (PART_GAP off), leaving sideways, into its own start. Flat g1v0 part dip 1.75
  (off, b27p0) -> 1.93 (on, b27p), col 256 (groom 3.5 at 245): moves the row, but little. Kept (on). Flat
  t19/part_flat.png: the cards' top is a flat mass, the groom's a dark V where both sides sweep down; and a dark knob
  over the top-left crown in both (the tuft, (6), still untraced).
- (2) STREAKS, traced: the groom's light streaks are its HIGHLIGHT RIBBONS (blender_strands hair colour: cells ~4 mm
  across (hp_ch) / ~15 mm (hp_cb), ~40% of cells over the threshold, half their strands up to +60% value, a sine along
  the length), coherent over several mm. The tile tone pool (round 18) lit single 0.2 mm hairs, which a 1 mm pixel
  averages away (why b26tp0 = b26). Also: the cards' strand_tones passes sun_x 0 (the groom adds the locks' strands.sun,
  +-0.2 on ~180 locks, to the ribbon pick): small. New lever: hair_clumps RIBBON_W / RIBBON_SHARE / RIBBON_GAIN, bands
  across each tile picture lighten half their hairs. Flat proof (g1v1 / g3v0 p95-p50): off (b27p) 11.3 / 15.1, share 0.4
  gain 0.6 (b27) 10.6 / 13.5 (p50 +1.5): WORSE, it lifts the mass, not streaks -> default 0. b27s = share 0.15, gain 1.2:
  r19e.sh measures it and the batch's main export is b27s only if its g1v1 spread beats b27p's by >= 0.5 (out/b27main).
- (4) tail, (5) wisps, (6) tuft: not reached this round.
- BATCH (r19e.sh -> b27chain.sh; ONE offload hc-b27, exports b27p / b27s): gb27 = main export (proxy on), gb27r0 (ribbons
  off, if main is b27s), gb27pc (proxy off: cards cast), gb27ns (no shadow); sheet game/gm_g12.png, review
  review/gg12_b27, done flag review/g12.done (ERROR file review/g12.ERROR). offload.sh now ships *_shadow.obj.

## Handover 2026-10-16 (hair-cards agent, round 19; stopped at the 70-tool-call rule)
Commits: e2e341ac (shadow proxy, part roots, ribbons), ribbons default 0, notes + shading notes. IN FLIGHT: r19e.sh
(b27s export + flat proof, then b27chain.sh: the NICO-TOP batch and the review vs the GROOM). Wait with
`/mnt/data/hifipushie/bin/offload wait b27`, then read review/gg12_b27 and game/gm_g12.txt; count the MAJORs (b26 17).
STATE: shadow proxy works as plumbing but does NOT reach the groom's neck numbers (the groom casts no shadow; the grain
is EEVEE shadow-ray noise). Part lever moves its row a little (1.75 -> 1.93). Ribbons 0.4 / 0.6 dead (worse).
NEXT: (1) coordinator: groom shadow on for the A/B, or both off; shadow_ray_count 4 in game renders (STAGE_EEVEE);
(2) streaks: if b27s failed its proof, try ribbons on the top layer only (head L2) and pass the locks' sun into
strand_tones; (3) part: the dark V needs the top cards to bend DOWN away from the line (not only start at it): measure
how many cards got a lead-in (c["part_root"]); (4) tail width / strips / blocky ends / pair-3 clump; (5) wisps; (6) the
top-left tuft (flat pass per layer at g1v0, it shows in t19/part_flat.png).
Scratch: r19a-e.sh, proxytest.py, glbmesh.py, b27mk.py, b27chain.sh, t19/.

## hair-cards round 20 (2026-10-16, fresh session after round 19's handover)
- b27 main = b27p: ribbons share 0.15 / gain 1.2 (b27s) flat g1v1 spread 11.67 vs 11.30 (+0.37 < 0.5): DEAD, ribbons stay 0.
- GROOM SHADOW, corrected: round 19's note was wrong. `visible_shadow = False` in blender_strands is the SCALP tint
  object, not the groom. The groom curves DO cast, but Blender's material default `use_transparent_shadow = True`
  (checked: 5.1.2) plus a 1 mm default shadow texel (light shadow_maximum_resolution 0.001) under 0.07 mm dithered
  strands (fine_alpha 0.5, tip alpha) cast ~nothing. Coordinator decision (a): shots.py `gshadow=opaque` ->
  blender_scene.hair_look sets the strands visible_shadow and their materials' transparent shadow OFF. Decision (b):
  shots.py `rays=<n>` (default 4) = scene.eevee.shadow_ray_count for groom AND cards; recorded in shading.py
  hair_cards "shadows". Old gS frames also predate the game-camera fix (framing differs from the card frames).
- PART (flat g1v0 part dip, groom 3.5): PART_GAP 4 mm 1.93, 8 mm 2.70, 12 mm 3.16, 16 mm 3.52; PART_ROOT_REACH 5 cm
  adds nothing over 3 cm. Default now 16 mm. CAUTION: the number reaches the groom's but the crops (t20/part.png)
  show NO dark V yet: the cards' top still reads as a flat mass. Judged in the batch (gb28).
- TUFT (6), traced (t20/tuft.png, flat g1v0 per layer of b27p): the top-left knob is head layer-1 cards (a dark knob)
  plus a layer-2 card rising above the dome. crownx: they do NOT stand off the strands' p97 envelope, so the groom has
  strands there (its frizz), which it draws as fine translucent flyaways and the cards as an opaque clump. Fix
  direction (not done): top-of-head cards from sparse / frizz clumps become thin low-alpha wisps or are dropped.
- BATCH hc-gs (gschain.sh, after hc-b27): gSo (groom shadow ON, all 6 game views = the NEW reference), controls at
  g1backl gSt (transparent strand shadow, rays 4) / gSof (opaque + 0.25 mm texel), cards gb27x (b27p, rays 4) and gb28
  (b28i = PART_GAP 16 mm, all views). Out: t20/neck.txt, game/gm_g13.png, review/gg13_b28 (vs gSo).
- b27 READ (game/gm_g12.txt, review/gg12_b27 vs the OLD unshadowed groom gS): FAIL, 19 MAJORs (b26 17). Neck g1backl
  grain / L* (rays 1): gS 0.31 / 66.0, gb27 proxy 0.42 / 60.8, gb27pc cards cast 0.44 / 62.0, gb27ns none 0.29 / 66.2.
  Lit part dip gb27 1.75 at col 283 (gS 3.51 at 245): the part is still at the wrong column in the lit frame. MAJORs
  by theme: face-framing wisps missing / short / grey (4), crown a dark helmet with a broken top silhouette, notches,
  tuft (4), tone darker / cooler, no blonde streaks (4), ponytail narrow, no wave, cut-off ends, smeared sheet (4), a
  thick dark detached arching strand right of the tail (2), neck speckle (1), card strips with dark edges on the crown.

## Handover 2026-10-16 (hair-cards agent, round 20; stopped at the 70-tool-call rule)
Commits: 8146dca9 (rays=, gshadow=opaque), shading notes (rays 4), PART_GAP 16 mm, these notes.
IN FLIGHT: hc-gs (gschain.sh, ONE offload): gSo = groom with its shadow ON at all 6 game views (the NEW reference),
gSt / gSof controls, gb27x (b27p at rays 4), gb28 (b28i, PART_GAP 16 mm). Wait `/mnt/data/hifipushie/bin/offload wait
hc-gs`, then review/g13.done (or g13.ERROR); read t20/neck.txt, game/gm_g13.txt, review/gg13_b28 (vs gSo).
STATE: b27 FAIL (19 MAJORs). Ribbons dead. Part lever reaches the groom's number flat (3.52 vs 3.5) but shows no V.
Groom-shadow cause found (transparent strand shadow + 1 mm texel), fix plumbed, not yet seen.
NEXT: (1) neck: is gSo's neck shadowed now (L* < 66)? if gSo ~ gSt the opaque switch is not enough: use gSof's 0.25 mm
texel for the source; then gb28 vs gSo grain / L*. (2) part: if gb28's lit dip is still at col 283, the cards' part
line (strand_part) sits 3.8 cm off the groom's visible part: trace the column, not the gap. (3) tail (narrow, strips,
cut ends, the detached arching strand) and the wisps (most MAJORs); (4) tuft: thin / drop top cards from frizz clumps.

## hair-cards round 21b (2026-10-18, fresh session; round 21 died on a usage limit with no commits)
- r21 left only scratch (t21/: gshprobe.py, neck.txt, streak.py): nothing in the repo to finish or revert.
- GROOM SHADOW still OFF in the source frames: gSo (gshadow=opaque) reads EXACTLY gS (neck g1backl L* 66.0 / p10 56.8
  / fine 0.31 both; part dip 3.51 both), gSof (+ 0.25 mm texel) = gSt. The switch reaches the strands (probe: the
  CURVES objects carry hp_strands, visible_shadow True) but sub-texel 0.07 mm strands still cast nothing in EEVEE's
  virtual shadow maps. So gSo = the old unshadowed reference; the card proxy's neck shadow (L* 60.7) is a known
  difference the source lacks (decision for the coordinator: a groom shadow proxy, e.g. the cards' own shadow proxy
  under the groom, if the source should be shadowed).
- b28 READ (review/gg13_b28 vs gSo): FAIL, 25 MAJORs (b27 19, b26 17; 3 of b28's are 1 m only). Look-first (my own
  read of pair_1 / pair_3 before the review): agreed. Crown lower and flat with spikes at the top front, no visible part,
  face-framing wisps short / grey, darker flatter tone without the light streaks, tail narrower / shorter with blunt
  striped ends, two dark ribbon cards arching out right of the tail (back 3/4, still there at 3 m), nape stubs.
  PART_GAP 16 mm: lit part dip 3.44 at col 259 (b27 1.75 at 283, groom 3.51 at 245): the number moved, the reviewer
  still sees no part. Not reverted (no measure got worse); judged with the crown below.
- NEW MEASURE cardsil.py <src> <frames> <glb tags> (no render): the cards' alpha samples projected with the game
  frames + the body = the figure; DEFICIT px (groom figure the cards miss) and EXCESS px by thirds of the figure's
  height. Calibrated on b28i against its render: top-band deficit g1v0 3245 vs 3136 rendered, g1v2 2822 vs 2658,
  g1backl 1991 vs 1905. b28i top-band deficit 8058 px (sum of the three 1 m views); excess ~0 (the ribbons right of
  the tail lie INSIDE the groom's figure: its flyaways; they are a width / opacity fault, not a placement one).
  Deficit maps (t21b/sil_b28_*.png, blue): a 10-20 px (~10-20 mm) band over the WHOLE crown: the top layer sits at its
  clump's mean (+ <= 3 mm, HEAD_SN_MAX) under the ENV_PCT 90 cap, the sides already sit on their outer strands
  (SIDE_OUT_PCT, SIDE_EL 20-40 deg). Lever: the side placement further up (SIDE_EL) / the cap (ENV_PCT).
  STATE: r21a.sh sweeping c1 SIDE_EL 60-80, c2 85-90, c3 ENV_PCT 97, c4 c2 + SIDE_OUT_MAX 20 mm -> t21b/crown.txt.
  Target: top-band deficit -40% with excess < 200 px and no crownx far cards. NEXT: the best on a flat render.
- CROWN sweep (t21b/crown.txt), top-band deficit px g1v0 + g1v2 + g1backl: b28i 8058; c1 SIDE_EL 60-80 6543 (-19%);
  c2 85-90 6534 (saturates: same as c1); c3 ENV_PCT 97 7943 (-1%: the cap is not what holds the top down); c4 c2 +
  SIDE_OUT_MAX 20 mm 6456 but a new far card (299, 1.15 cm2 > 8 mm off every strand). c1 costs 0.27 cm2 standing > 3 mm
  off the envelope over the top (b28i 0). Short of the -40% target: the rest of the band is the groom's translucent frizz
  halo (fg threshold counts it) that cards are not meant to copy. c1 kept as the base, not yet a default.
- RIBBONS right of the tail traced (t21b/ribbon_trace.png: b28i flat g1backl, all | layer3 only | layer2 only): NOT fly
  cards (layer3 draws ~nothing at the cutoff) but top-layer (layer2) TAIL cards arcing out from the tie; card 345 is
  0.77 cm2 > 8 mm from every strand (crownx far). STATE: r21c.sh on c1: d1 MEDOID_TAIL 0.5, d2 TAIL_END 0.08, d3 both
  -> t21b/tail.txt (far area per range, low-band deficit must not grow).
- TAIL sweep (t21b/tail.txt, top.txt; on c1): d1 MEDOID_TAIL 0.5 (all tail layers): layer2 > 8 mm off 0.77 -> 0 but the
  profile figure deficit +957 px (the tail's kick / wave is the medoid's): rejected. d2 TAIL_END 0.08: far card 345
  still there (0.90): rejected. NEW knob MEDOID_TAIL_TOP (the top tail layer only): e1 0.5: layer2 > 5 mm 10.96 ->
  2.30 cm2, > 8 mm 0.77 -> 0, figure deficit +0.7% (profile -49, back +69); e2 0.0: 0.92 cm2 but back +190. Kept e1.
- DEFAULTS (committed): SIDE_EL (60, 80), MEDOID_TAIL_TOP 0.5. b29 = these.
  STATE: b29chain.sh (ONE offload hc-b29): export b29, 6 game views gb29, sheet game/gm_g14.png (gSo, gb29, gb28),
  cardsil rows in game/gm_g14.txt, pairs review/gg14_b29, then review/g14.done (or g14.ERROR). NEXT: blind review.
- b29 READ (game/gm_g14.png, tiles review/gg14_b29, blind SUBAGENT reviewer, not bin/review: counts are not strictly
  comparable with b26-b28's): FAIL, 19 MAJORs (b28 25 by bin/review). Rendered figure deficit vs gSo at 1 m (4 views):
  b28 17458 -> b29 15917 px (-9%); top band 10499 -> 8687 (-17%); profile mid band +338 (tail). LOOK-FIRST (mine, ref |
  b29 | b28, t21b/ref_b29_b28.png): the back of the crown is a little fuller; the DARK LOCK ARCHING OFF THE RIGHT OF THE
  TIE IS STILL THERE (the reviewer names it at 1 m and 3 m). So MEDOID_TAIL_TOP fixed what crownx measured (layer-2
  area off every strand) but not the visible lock: that lock lies NEAR strands (the groom's flyaways there) and is a
  card too wide / opaque for the 2-3 hairs it stands for. Lesson: the measure must be the visible fault; trace by the
  frame box (cardsil box=<view>:x0,y0,x1,y1, done for b28i: layer-2 tail cards 345 / 340 / 331 / 326 / 322 dominate the box
  at 630-685, 455-570 in g1backl, but the box also catches the tail's edge: narrow it to 645-685, 470-545).

## Handover 2026-10-18 (hair-cards agent, round 21b; stopped at the 70-tool-call rule)
Commits: notes; hair_clumps SIDE_EL (60, 80) + MEDOID_TAIL_TOP 0.5 (new knob, top tail layer only) = b29.
Scratch: cardsil.py (figure deficit / excess vs the groom without a render, + card trace by frame box), r21a-d.sh,
b29chain.sh, t21b/ (crown.txt, tail.txt, top.txt, sil_*.png, ribbon_trace.png, ref_b29_b28.png).
STATE: b29 FAIL, 19 MAJORs (subagent reviewer). Nothing in flight.
NEXT: (1) the stray dark lock right of the tie: trace it with a NARROW box (cardsil box=g1backl:645,470,685,545 on b29)
plus a flat only=<that card's tris> render; lever = a tail card's width / alpha follows the strand count still running
at each station (HW_PER_STRAND exists: check it reaches layer 2's sparse arcing strands), or drop top-layer cards whose
clump is under N strands. (2) hairline: skin band + pale flat strips above the forehead (HL_ALPHA / HL_LIFT / root fade)
and NO visible part (3 rounds of PART_GAP moved the number, never the look). (3) crown spikes (top-front, all views).
(4) tail texture: smeared sheet + swirl, blunt ends; right side volume over the ear in the front view.
(5) groom shadow: gSo == gS (the opaque switch casts nothing: sub-texel strands); coordinator decides whether the
source gets a shadow caster.

## hair-cards round 22 (2026-10-18, fresh session; coordinator: groom shadow yes, levers judged by the tile of the fault)
- (1) THE DARK LOCK off the right of the tie, traced (cardsil box=g1backl:645,470,685,545 on b29 + flat renders per layer,
  t22_lock_trace.png): NOT one stray card. Layer-0 card 230, layer-1 299 / 300 and layer-2 322 / 331 / 345 are the tail's
  right-edge clumps; their frame faced "outward" from the tail core, i.e. sideways (+x), so from the back AND the front
  they were seen EDGE-ON: thin dark arching ribbons where the groom shows a broad rounded bulge (t22_lock_b29.png).
  NEW knob hair_cards.PCA_FRAME (hanging = tail / face cards): the card's width turns onto its clump's cross-section major
  axis where the section is flat (anisotropy ramp 0.3-0.7, smoothed as a doubled angle; then the TWIST_HANG limiter).
  Tile (t22/lock_flat_b29_p1.png, flat g1backl, b29 | PCA_FRAME 1): the arching ribbons are GONE and the right bulge is a
  filled mass like the groom's. Figure deficit vs gSo (geofig, 1 m views): b29 13191 -> p1 11826 px (-10%; profile mid
  1453 -> 667), excess <= 34 px a view; 0.5 worse on the back (2078 vs 1623). KEPT: PCA_FRAME 1.0 default.
- GROOM SHADOW (coordinator: yes): gproxy.py builds the groom's caster with the cards' own recipe (hair_cards.shadow_proxy)
  from its head + tail strands (10.6k tris, voxel 4 mm, inset 4 mm); shots.py gproxy=<obj> -> blender_scene imports it
  shadow-only (blender_cards.shadow_proxy). Lever proof (local 540 px, gS vs gSc, t22/gproxy_zoom.png): the neck under the
  tail takes the shadow (crop mean 146 -> 141 /255) and the tail's inner strands self-shadow. The new reference is "gSc".
  STATE: committed with PCA_FRAME; NEXT: hairline, part, then one batch b30 (+ gSc 6 views) on NICO-TOP.
- FRONT TOP sweep (r22c.sh, on PCA_FRAME 1 = p1; geofig vs gSo, 1 m, t22/geofig_q.txt; flat tile t22/front_q.png p1 | q1 | q2 | q3):
  q1 PART_GAP 6 mm (16 in b28 / b29): top-band deficit g1v0 2650 -> 1960 (-26%), g1v1 2322 -> 1695 (-27%), g1v2 2411 ->
  1656 (-31%), back 1261 -> 1153; back low band +266 px (watch). Tile: the front top is fuller and rounder, the right spike
  smaller. The 16 mm gap left a bare band ALONG THE PART, which over the top of the head IS the silhouette: the crown
  deficit was mostly the part gap, not the envelope caps (21b's SIDE_EL / ENV_PCT chased the rest). KEPT (default 6 mm).
  q2 HL_LIFT 0.15: no change in the flat tile at 540 px (tone only, geometry identical): lever not proven, NOT shipped.
  q3 HEAD_SN_MAX 8 mm: top band +6% worse: rejected.
  STATE: b30chain.sh (ONE offload hc-b30): b30 = PCA_FRAME 1 + PART_GAP 6 mm, gSc (groom + gproxy caster) 6 views,
  neck / part t22/neck.txt (gSo, gSc, gb29, gb30), sheet game/gm_g15.png (gSc | gb30 | gb29), pairs review/gg15_b30.
- b30 launched 11:2x (hc-b30 queued on NICO-TOP behind rs_r9 / x62 / dgrr: the chain runs on by itself and writes
  review/g15.done; then a blind subagent review of review/gg15_b30 tiles 0-5 (gSc = the reference) is still owed).
  NOT tried this round (budget): (3) the part as a SCALP TINT (a dark line painted on the head under the part, and under
  the hairline: the cards' skin gap) instead of more card geometry; (5) tail texture (smear / blunt ends); hairline pale
  strips (HL_LIFT is tone only: prove it on a LIT local 540 px frame, not the flat one, before shipping).
- b30 READ (game/gm_g15.png; tiles review/gg15_b30 vs gSc; blind SUBAGENT reviewer, images only, gates brief): FAIL,
  13 MAJORs (b29 19, same kind of reviewer): front 1 m 3, 3/4 1 m 3, profile 1 m 2, back 3/4 1 m 3, front 3 m 1, back
  3/4 3 m 1. LOOK-FIRST (mine, before the review; t22/look_b30.png = gSc | b30 | b29, back and front top): the dark lock
  arching off the tie is GONE and the bulge right of the tie is a filled rounded mass like the groom's; the reviewer no
  longer names it. NEW in its place: dark leaf-shaped shards / gaps between broad tail cards near the tie ("torn leaf
  cards", 3 m): PCA_FRAME turns cards to face the camera broadly, so their own picture gaps and shapes show. Front top:
  a little fuller, still ragged / spiky and lower than the groom; part still not seen; hairline skin gaps + flecks remain.
  Numbers vs gSc (img rows, rendered): figure deficit 1 m b29 -> b30: front 3702 -> 2676, 3/4 3402 -> 2485, profile 5761
  -> 3985, back 3120 -> 2396 (-26..-31%); excess 113-327 px (mid band). Part dip (streak.py): gSo 3.51, gSc 3.29, b29
  2.85, b30 2.02 (weaker, as expected from the 6 mm gap; the reviewer saw no part in either).
- GROOM SHADOW measured (t22/neck.txt, g1backl neck common px): gSo L* 66.2 / p10 56.8 -> gSc 62.6 / p10 49.4 (the
  groom now casts); cards b29 64.7 / 56.3, b30 64.6 / 56.1: the cards' neck is now LIGHTER than the source (p10 +6.7).
  Speckle unchanged (0.31 -> 0.34). gSc is the reference from now on (its frames in out/, s_hc_s2_gSc_*).

## Handover 2026-10-18 (hair-cards agent, round 22; stopped at the 70-tool-call rule)
Commits: PCA_FRAME 1.0 (hair_cards: hanging cards' width on the clump's flat section) + groom shadow caster (shots.py
gproxy=, blender_scene groom_proxy; scratch gproxy.py builds exp/gshadow/groom_shadow.obj); PART_GAP 6 mm; notes.
Scratch: r22a-c.sh, b30chain.sh + b30_renders.json (the gSc reference render job), t22/ (geofig_p / geofig_q, neck.txt,
lock / front / look tiles), t22_lock_b29.png, t22_lock_trace.png.
STATE: b30 FAIL, 13 MAJORs (b29 19): the first drop after three flat rounds. Nothing in flight.
VERDICT (look-first): converging where a lever fixed a CAUSE seen in a tile (edge-on frames, the bare part band), not by
counted measures. Cards are not hopeless, but the tail's surface (smear, leaf shards, blunt ends, short at the back) and
the front hairline are now the bulk, and both are PICTURE / ALPHA faults, not placement.
NEXT, in order: (1) tail: the leaf shards near the tie (trace them in g1backl with cardsil box= as in r22; likely layer-1/2
cards whose picture gaps now face the camera: denser tile / KID_COVER for tail, or the TWIST limiter after PCA), tail
length at the back (-30 px: TAIL_END / TAIL_END_JIT), blunt ends. (2) hairline skin gaps + flecks and the part: a scalp
tint (dark under the part line and the hairline band on the head's texture) is the untried lever; HL_LIFT must be proven
on a LIT local frame. (3) crown flaps at the top front (trace the standing cards with crownx.py). (4) face wisps short /
pale strips (FACE_END, WISP_LIFT). (5) cards' neck now lighter than the shadowed groom (proxy inset / SHADOW_LEAK).

## hair-cards round 23 (2026-10-18, fresh session; order: tail surface, hairline / part, crown flaps, face wisps)
- (1) TAIL LEAF SHARDS traced (t23/bk_flat_lit_b30.png: b30 g1backl flat albedo | lit): the dark leaf-shaped shards between
  the tail cards near the tie are LIT ONLY (the flat albedo has none). Not the cards' cast shadow either
  (t23/bk_shadow_AB.png: gSc | b30 lit | b30 shadow=0: same shards). Winding agrees with the vertex normals (t23/wind.py:
  1.2% opposed in b29 and b30 alike). Cause (inferred): PCA_FRAME turns a card's plane up to 90 deg off the outward frame,
  so from outside the tail the camera sees its BACK, and a double-sided card's back is shaded with the flipped normal
  (inward: dark). NEW knob hair_cards.PCA_MAX (deg, 90 = round 22's unlimited turn).
  STATE: r23c.sh: u1 PCA_MAX 45, u2 60, u3 FREE_END 0.03 (tail ~30 px short at the back) -> lit g1backl / g1v1 local
  1080 + t23/geofig_u.txt. NEXT: tile ref | b30 | u1 | u2 of the tie.
- TAIL sweep READ (t23/tie_u.png, t23/back_u_s.png: gSc | b30 | u1 PCA_MAX 45 | u2 60 | u3 FREE_END 0.03, lit g1backl 1080
  local; t23/geofig_u.txt): u2: the big dark leaf shards near the tie are gone (a few small flecks left), the tail reads as
  one surface; the right bulge stays a mass. u1: shards gone too but a NEW dark edge-on wedge at the tail's bottom left.
  Back figure deficit b30 1805 -> u2 1957 px (mid band 348 -> 498: the bulge a little narrower), 3/4 front 2051 -> 2033.
  u3 FREE_END: geometry IDENTICAL to b30 (dead lever for this tail: the hanging cards' end is set elsewhere). KEPT
  PCA_MAX 60 default (the fault seen in the tile is gone; the +150 px is the cost, watched).
- TAIL TONE (t23/lstat.py, L* in a tail box g1backl 570,440,690,620 incl. some background): gSc mean 36.1 / p10 15.2,
  b30 45.0 / 27.7, u2 46.6 / 28.7; crown box: gSc 52.3, b30 59.2. The cards are ~7-10 L* lighter and lack the dark depths
  now that the groom casts (gSc). Candidate: the cards' SHADOW_LEAK (0.45, tuned against the unshadowed groom).
  STATE: r23e.sh renders u2 at shadow_leak 0.3 / 0.1 (g1backl, g1v0). r23d.sh: hairline h1 CAP_BASE_IN 0, h2 CAP_PART_CUT
  0.3, h3 HL_LIFT 0.1 (lit g1v0).
- HAIRLINE levers DEAD at 1 m front (lit g1v0 local 1080, t23/hl_h2.png gSc | b30 | h1 | h2 | h3): h1 CAP_BASE_IN 0, h2
  CAP_PART_CUT 0.3, h3 HL_LIFT 0.1 each differ from b30 only by the local-vs-offload noise (~800 px > 12 levels, the
  same box for all three), and h1 vs h3 by 62 px. So the pale strips / skin gaps at the hairline are neither the cap's
  base nor the hairline cards' tone. A box trace (cardsil box=g1v0:450,380,495,460) is useless there: it counts every card
  the box's rays cross at all depths (the cap 28.6k samples, layer 0 12k, 1 8k, 2 5.9k). NEXT: trace by a flat ID render
  per layer (flatr.sh ranges: cap = tris 0-3219, layer 0 from 3220 ...) and look at which layer is the pale strip.
  The knobs stay at their old defaults (CAP_BASE_IN 0.25, CAP_PART_CUT 0.8).
- TONE lever DEAD: shadow_leak 0.45 -> 0.3 / 0.1 on u2 moves the tail box < 1 L* (46.6 -> 46.3 / 45.8), crown 0.1 L*. The
  cards' ~7-10 L* surplus over gSc is ALBEDO (the lit hair is not in the map's shadow), i.e. card_gain (hair.match_cards
  measured it against the UNSHADOWED groom look; gSc's strands self-shadow). NEXT: re-measure card_gain against gSc.
  STATE: b31chain.sh launched 11:43 (ONE offload hc-b31: b31 = PCA_MAX 60, all else b30; sheet game/gm_g16.png gSc | gb31
  | gb30, pairs review/gg16_b31, review/g16.done).
- HAIRLINE PALE STRIPS traced (flat g1v0, u2: t23/hl_flat3.png all | cap only | no cap): the cap alone has a clean dark
  hairline and NO pale strips; the pale beige strips over the temples / forehead sides are CARDS (non-cap). Without the
  cap the mid-front shows bare skin under the part: the cap is what covers it. w1 WISP_LIFT 0.15 (0.5): flat front
  795 px moved, the strips a little less pale but still broad beige bands (t23/wisp_flat3.png u2 | w1): not a visible
  fix, NOT kept. So they are broad, opaque face / hairline cards lying flat on the forehead (shape, not tone).

## Handover 2026-10-18 (hair-cards agent, round 23; stopped at the 70-tool-call rule)
Commits: hair_cards.PCA_MAX 60 (new knob, the PCA turn held off the outward frame); hair_strands CAP_BASE_IN / CAP_PART_CUT
(knobs, old defaults, proved dead at 1 m); notes. Scratch: r23a-e.sh, b31chain.sh + b31_renders.json, hx.py (hs.<CONST>),
t23/ (tile.py <out> <view> <box> <tags>: native crops side by side; lstat.py: L* in a box; wind.py: winding vs normals;
tie_u / back_u_s / leak / hl_h2 / hl_flat3 / wisp_flat3 tiles; geofig_u.txt).
STATE: b31 (PCA_MAX 60, all else b30) QUEUED on NICO-TOP as hc-b31 (11:5x); the chain writes game/gm_g16.png, pairs
review/gg16_b31 (0-5) and review/g16.done by itself. The blind review of b31 is OWED (bin/review from 2026-10-19 13:00 MT,
else a fresh subagent: images only, gates brief, gSc = the reference).
VERDICT (look-first, local tiles only): the tail's dark leaf shards near the tie are fixed in the tile (they were the BACKS
of PCA-turned cards, shaded with the flipped normal). Still wrong, by size: the cards are ~7-10 L* lighter than gSc with
no dark depths (albedo / card_gain, not shadow), broad pale face / hairline cards at the temples, the ragged spiky crown
top, no part, tail short / blunt (FREE_END is a dead lever here).
NEXT, in order: (1) read b31 (review). (2) card_gain re-measured against gSc (hair.match_cards on the shadowed groom): the
biggest visible difference left at 1 m and 3 m. (3) the temple pale strips: trace which cards (flat ID render per card
range, cardsil only counts all depths) and narrow / thin them (FACE_PER, FACE_ALPHA, WISP_KIDS_FACE). (4) tail length:
find what ends hanging cards (hair_clumps end_share for tails, not hair_cards.FREE_END). (5) crown flaps, part.

## hair-cards round 24 (2026-10-18, fresh session; Joe: only what's left to get Tess game-ready; the assembly agent takes the best build)
BEST CARDS FOR EXPORT: b32 = code at 4352c62a + hc_s2's spec (/mnt/data/hifipushie/haircards/exp/b32/hc_s2_hair_hero.glb, hero 23.8k
  tris). Through export_asset: set hc_s2 hair.export.tier "hero" first (EXPORT_CARDS default cuts 12000 tris, see (6); untested).
- (1) b31 (hc-b31, PCA_MAX 60) still in the offload queue at 11:57 (chain b31chain.sh alive; review/g16.done not yet).
  (2) card_gain: r24a.sh k1 gain 1.5 / k2 gain 1.25 (default 2.10 on hc_s2) -> lit g1backl / g1v0 / g1v1 local 1080; target
  gSc tail box (g1backl 570,440,690,620) L* 36.1 / crown 52.3 (u2 46.6 / 59.2-ish). (3) temples: flatr.sh u2 g1v0 per layer
  (L0-L3 ranges from the b31 report) to see which layer the pale strips are. (4) tail end: r24b.sh t1 = hair_clumps TAIL_END 0
  + TAIL_END_JIT 0.05 (FREE_END was dead: the tail cards end at hair_clumps.TAIL_END 0.03 + up to 0.15 jitter).
  STATE: r24a, flatr, r24b queued on the local heavy slot. NEXT: read k1 / k2 L* + tiles.
- (2) GAIN READ (t24/gain_back.png, t24/gain_front.png: gSc | u2 (gain 2.10) | k1 1.5 | k2 1.25, lit local 1080; t23/lstat2.py =
  L* over hair pixels only, L* < 78): tail back g1backl 570,440,690,620: gSc 28.1 | u2 37.0 | k1 29.3 | k2 25.5; head back
  450,300,700,430: 34.1 | 36.4 | 29.1 | 25.4; 3/4 tail g1v1 634,486,718,606: 35.3 | 38.3 | 30.3 | 26.3; 3/4 crown 470,375,610,440:
  33.9 | 33.6 | 28.4 | 25.9. So the surplus is the TAIL's (+9 back, +3 3/4), the head cards are within ~2 L*: a global gain
  overshoots the head by 5. NOT kept. New knob hair_clumps.TAIL_TONE (tail cards' tone x, default 1.0): r24c tt1 0.75.
- (3) TEMPLE STRIPS traced (t24/temple_layers.png, flat g1v0 per layer of u2): the pale bands at both temples are all in
  LAYER 0 and are the face-framing cards (face/L0: 60 cards; WISP_LIFT x1.5 tone, no depth shade, half width 6 mm); layers
  1-3 have none. r24d f1 = FACE_PER 3 (narrower clumps) + WISP_LIFT 0.15.
  STATE: r24b (t1 tail end), r24c (tt1 tail tone), r24d (f1 face cards) chained on the local heavy slot; b31 still queued.
- (4) TAIL END: t1 (TAIL_END 0 + TAIL_END_JIT 0.05) NOT kept: at g1backl the tail is no longer than u2's (gSc's ends at the
  same height: length was not the fault, the ends' look is), +1.7 L*, broader flat bottom (t24/tail_t1_tt1.png).
- (2b) TAIL_TONE 0.75 KEPT (t24/tail_t1_tt1.png gSc | u2 | t1 | tt1): tail back 37.0 -> 30.5 (gSc 28.1), 3/4 38.3 -> 31.4
  (gSc 35.3), head box unchanged 36.4 (gSc 34.1). The pale tail panels are gone in the tile.
- (3b) TEMPLES: f1 FACE_PER 3 + WISP_LIFT 0.15: 119 face cards (+870 tris), left band still broad: NOT kept. f2 WISP_KIDS_FACE 4
  + WISP_ALPHA 0.7 (same tris): left temple sheet see-through strands, right strip thinner (t24/temple_f2_zoom.png gSc | gb30
  | f1 | f2): KEPT (WISP_ALPHA also applies to fly cards; test_face_wisp updated).
- (5) crown flaps / part: no change this round (crownx on tt1: no top card > 8 mm off; the spiky top is card ends in the
  outline, layers 1-2, t24/temple_layers.png).
- b32 (defaults at 4352c62a), all 6 game views LOCAL 1080 (offload b31 was still queued after 1 h: killed, b31 = u2 locally).
  Before / after tiles t24/ba_<view>.png (gSc | gb30 | b32). Blind subagent review (images only, review/r24_b32/<view>.png
  ref | result): FAIL, 22 MAJORs over 6 regions (g1v0 5, g1v1 3, g1v2 3, g1backl 3, g3v0 3, g3backl 2; b30 baseline under
  bin/review was ~20). Biggest by size: (a) tone flat, no blonde highlight streaks / clump contrast (every view; the
  reviewer calls it "too dark": the MEAN matches gSc, p90 is 7-10 L* short: the fault is missing highlights, not level);
  (b) torn / spiky crown silhouette + no centre part (front, 3/4, side, still at 3 m); (c) dark shards under the tie and a
  blunt shredded tail bottom; plus the upper-left forehead pale sheet (still MAJOR at 1 and 3 m) and face wisps now thin
  / grey (f2 made them fainter at 3/4: the reviewer wants thicker, warmer wisps to the jaw).
- (6) EXPORTABILITY (exa.py hc_s2 exp/asset_b32, export_asset role hero, lods, no preview; 721 s; out/exa_b32.log): runs
  end to end, GLB + LOD1-3 written, hair_cards budget 11996 of 25000, alpha cutoff 0.33 from EXPORT_CARDS. BUT export_asset
  cuts the hair at hair.EXPORT_CARDS triangles 12000 (tier None): 574 cards, 826 dropped, card_width 43 mm, NOT the judged
  23.8k hero build. Set spec hair.export.tier = "hero" (hair.py: budget = ex["tier"] or triangles) before the RC export
  (untested). LODs: hair 11996 -> 5324 at LOD1 and stays 5324 at LOD2 / LOD3 (whole layers dropped once, then nothing).

## Handover 2026-10-18 (hair-cards agent, round 24; stopped at the 70-tool-call rule)
Commits: hair_clumps.TAIL_TONE (0.75), WISP_KIDS_FACE 4, WISP_ALPHA 0.7 (4352c62a), test updated, notes. Scratch: r24a-g.sh,
exa.py (export_asset check), t23/lstat2.py (L* over hair pixels), t24/ (gain / tail / temple / ba_ tiles, ba/ crops),
review/r24_b32 (blind pairs). Nothing in flight (b31 offload chain killed: superseded).
VERDICT (look-first, t24/ba_*.png): b32 is better than b30 on the tail (tone near gSc, no pale panels or leaf shards in the
lit tail) and the left temple (see-through instead of an opaque sheet). It still reads as cards at 1 m and 3 m: flat tone
with no highlight streaks, spiky crown outline, no part, blunt tail bottom, shards under the tie. Blind review FAIL (22 MAJOR).
NEXT, in order: (1) highlights / clump contrast: gSc's p90 is 45-49 vs ours 37-38 in every hair box: the atlas's per-card
light streaks (look highlights / variation, TINT_TOP), measured as p90 and p10 per box, not the mean. (2) export: set hc_s2
hair.export.tier "hero" and re-run exa.py (confirm 23.8k hair, LOD steps). (3) crown outline + part (layers 1-2 card ends
in the top silhouette; the cap has a clean outline). (4) the face wisps: warmer / thicker at 3/4 (WISP_LIFT, FACE_END) without
the temple sheet coming back. (5) tie shards.

## hair-cards round 25 (2026-10-18, fresh session; Joe: only what's left for Tess / Garrett game-ready; b32 -> Tess's RC)
BEST CARDS FOR EXPORT: b33 = hair_clumps defaults at this round's last commit (= b33c: TONE_CONTRAST 2.2, _DARK 1.3, _TAIL 3.5,
  TAIL_ROOT_LIFT 0.6, TIP_FADE_TAIL 0.3) + hc_s2's spec (/mnt/data/hifipushie/haircards/exp/b33c/hc_s2_hair_hero.glb, hero 23.8k).
  EXPORT SETTINGS: spec hair.export = {"tier": "hero"} (else EXPORT_CARDS cuts 12000 tris), export_asset(role="hero", lods=True);
  alpha_cutoff 0.33, shadow_proxy on. LODs now come from the card TIERS rigged or not (asset.py, this round): hair 23844 /
  12496 / 8246 / 2498 tris at LOD0..3 (t25/tiers.py; budgets hero hair_cards 25000 / 12500 / 8250 / 2500). Not yet run
  through a full export_asset with the tier set (exa.py with tier hero: ~12 min heavy).
- (1) HIGHLIGHTS MEASURED (t25/hl.py: Lab over hair pixels L* < 78 per box, local 1080 game renders): the deficit is CONTRAST,
  not level or hue. gSc | b32: back tail p10 14.7 | 21.9, p90 45.1 | 37.6; back head p10 20.5 | 25.4, p90 48.1 | 44.3; 3/4 tail
  p10 21.9 | 24.0, p90 49.1 | 38.2 (L* > 50: 9.0% | 0.3%); front crown p90 60.2 | 43.6. Top-10% pixels' hue 65-66 deg both,
  chroma 12-14 both: the streaks are lighter strands of the same hue. Streaks (runs over the box's p75) 2 px wide every 4 px
  in gSc, ours 1 px every 12-33 px. So ours has half the p10..p90 spread (~15 vs ~30 L*) at the same mean.
  NEW knob hair_clumps.TONE_CONTRAST (default 1.0): head / tail card pictures' hair tones x k about each island's median
  (both ends move, the mean stays). r25a: c16 = 1.6, c22 = 2.2, c16r = 1.6 + RIBBON_SHARE 0.3 (views g1backl, g1v1, g1v0).
- (2) CROWN traced: cardsil.py gSc lb32 b32: no card stands OUTSIDE the groom's figure at the top (excess 0 / 76 px top
  band), the top band is DEFICIT (1878 / 1585 px at g1v0 / g1v1): the torn outline is the dark slab card tops left
  between gaps, not cards sticking out (t25/crown_front.png). r25b: flat per-layer g1v0 (cap / L0 / L1 / L2) to see whose.
- (5) LODs: export_asset used the groom's card TIERS (main / npc / far = budgets hero hair_cards 12500 / 8250 / 2500) only
  when RIGGED; unrigged it fell back to dropping whole layers once (11996 -> 5324 flat). asset.py: tiers unrigged too.
  r25c (t25/tiers.py): hair.export_cards per tier, triangles per tier (the cap alone is 3220: far 2500 may not fit).
  STATE: r25a / r25b / r25c chained on the local heavy slot. NEXT: read c16 / c22 tiles + hl.py.
- (1b) CONTRAST READ (t25/c_back.png, t25/c_v1.png: gSc | b32 | c22 | c16r; hl.py): c16 head back spread p10..p90 18.9 ->
  24.8 (gSc 27.6), streak gap 12 -> 5 px (gSc 7); c22: head back p10 21.1 p90 50.4 (gSc 20.5 / 48.1), L*>50 10.9% (gSc 7.4,
  b32 1.9): the back of the head now shows light / dark strands in the tile (VISIBLE, kept as the base). The TAIL barely
  moves (back tail p90 37.6 -> 41.3 at 2.2, gSc 45.1; 3/4 tail 38.2 -> 41.4, gSc 49.1); c16r (+ RIBBON_SHARE 0.3) no better
  than c22 at the tail. Front crown p10 dropped (12.3 -> 7.1: darker, gSc 19.9): watch the front.
  NEW knobs: TONE_CONTRAST_TAIL (r25d c22t: tail 3.5), TAIL_ROOT_LIFT / TAIL_ROOT_LEN (tail roots under the tie lit, depth
  shade off: r25e e1 0.6), e2 = TIP_FADE_TAIL 0.3 (0.12: the blunt shredded tail bottom).
- (2b) CROWN per layer (t25/crown_layers.png, flat g1v0 L0 | L1 | L2; NB these frames may be round 24's u2, flatr re-runs
  them for b32): L0 covers the sides only (scalp bare over the top, the cap carries it) + the pale left-forehead sheet
  (face/L0); L1 = hairline cards with dashes over the forehead top; L2 = two hooked flaps up at the top left / right =
  the spikes in the outline. Not changed this round (crownx: no top card > 8 mm off the strands; the hooks lie in the
  groom's frizz band).
  STATE: r25b (flat), r25c (tiers), r25d (c22t), r25e (e1, e2) chained locally. NEXT: read, pick b33, review side by side.
- (1c) c22t (TONE_CONTRAST_TAIL 3.5): tail p90 back 44.8 (gSc 45.1), 3/4 44.9 (49.1), streak gap 20 -> 7 px (gSc 4): KEPT.
  e1 TAIL_ROOT_LIFT 0.6: the under-tie shards barely lighter (t25/e_zoom.png): marginal, kept in b33 only because b33c had it.
  e2 TIP_FADE_TAIL 0.3: finer, wispier tail ends: KEPT. TONE_CONTRAST_DARK 1.3: c22's front darks came back up (front crown
  p10 7.1 -> 12.1; gSc 19.9). b33c (all of these; hl.py): head back p10 / p50 / p90 24.4 / 41.0 / 50.5 (gSc 20.5 / 33.0 /
  48.1), tail back 24.5 / 36.3 / 46.0 (gSc 14.7 / 25.8 / 45.1): highlights now there, but the MEAN is +8-10 L* light (the
  darks are short now, not the lights). Front crown unchanged (12 / 23 / 43 vs 20 / 32 / 60: the front is dark L1/L2 cards).
- SIDE-BY-SIDE BLIND REVIEW (one fresh subagent, review/r25_sbs/<view>.png = ref | X | Y, order shuffled, key.txt): b33c
  closer in 6 regions (3/4 tone + tail; back tone, under the tie, ear wisps; side tone), b32 closer in 1 (back: tail length /
  taper), same in 12. Remaining in both: jagged notched crown, no centre part, front too dark / no blonde streaks over the
  top, face wisps short / grey, ponytail ends blunt (not wavy), dark comb marks behind the ear (nape), holes in the tail.
  Tiles: t25/b33_front.png, b33_v1.png, b33_back.png, b33_side.png (gSc | b32 | b33c).

## Handover 2026-10-18 (hair-cards agent, round 25; stopped at the 70-tool-call rule)
Commits: TONE_CONTRAST (+ _DARK, _TAIL), TAIL_ROOT_LIFT / LEN, TIP_FADE_TAIL 0.3 as defaults (= b33); hair tier LODs unrigged
(asset.py). Scratch t25/ (hl.py highlight stats, pair.py tiles, tiers.py, tiles), r25a-g.sh, review/r25_sbs. Nothing in flight.
VERDICT (look-first): b33 is better than b32 at the back and 3/4 (light / dark strands through the head and tail, finer tail
ends); the front is unchanged and still the weakest view (dark, jagged crown, no part). Still reads as cards at 1 m.
NEXT, in order: (1) the tone MEAN: b33 is +8-10 L* light at the back (darks short): lower the tail / head base a little
(TAIL_TONE 0.75 -> ~0.65, or TONE_CONTRAST_DARK 1.3 -> 1.8 at the back only) measured by hl.py p10 / p50. (2) the front top:
L1 / L2 cards there are dark (front crown p50 23 vs 32) and hook up at the outline (t25/crown_layers.png): lift the front-top
cards' tone (like HL_LIFT) and pull the two L2 hooks under the envelope; the part needs the cards' roots turned away from the
line. (3) full export_asset with hair.export.tier "hero" (exa.py) to confirm LOD0..3 = 23.8k / 12.5k / 8.2k / 2.5k, check each
LOD at its game distance. (4) the nape comb marks behind the ear, holes in the tail. Test update: tests/test_* for the new
knobs not added (defaults only).


## hair-cards round 26 (2026-10-18, fresh session; Joe: only what's left for Tess / Garrett game-ready; RC review MAJORs: crown spike, hairline)
BEST CARDS FOR EXPORT: b34 = hair_clumps / hair defaults at this round's commit (= r26 g2: TAIL_TONE 0.62, TONE_CONTRAST_TAIL
  4.5, TONE_BACK = TONE_FRONT 0.85 (every head card x 0.85), hair.CAP_RELAX 60) + hc_s2's spec
  (/mnt/data/hifipushie/haircards/exp/g2/hc_s2_hair_hero.glb). EXPORT SETTINGS: spec hair.export = {"tier": "hero"},
  export_asset(role="hero", lods=True); alpha_cutoff 0.33, shadow_proxy on (exa26.py injects the tier; full run exp/exa34).
- (0) LOOK at b33c front (t25/b33_front.png, crop of g1v0 top): the crown's top is a flat dark block with a hooked flap at
  the right; the forehead top is a dark band with scalp between cards and no part; a pale sheet lies flat on the left
  forehead; a broad dark lock beside the face on the right (the RC's minor). Still the weakest view.
- NEW knobs (hair_clumps, defaults off): HOOK_RISE (m: a head card that comes down from its highest point and rises again
  by more than this ends at its low point: the hooked top flaps), TONE_BACK / TONE_FRONT / TONE_POS_Y (head cards' tint by
  their roots' y: back down for the +8 L* mean, front-top up for the dark front crown).
  r26a: d1 TAIL_TONE 0.6 + BACK 0.8 + HOOK 4 mm; d2 TAIL 0.55 + BACK 0.75 + FRONT 1.25 + HOOK; d3 TAIL 0.65 + BACK 0.85 +
  TONE_CONTRAST_DARK 1.8 + FRONT 1.25 + HOOK (views g1backl, g1v1, g1v0). exa26.py = exa.py with tier hero injected.
  STATE: r26a running locally. NEXT: hl.py d1-d3 vs gSc / b33c, crown crop.
- (1) r26a READ (hl.py; t26 tiles): TAIL_TONE 0.6 brings the tail mean down (back p50 36.3 -> 31.2, 3/4 37.7 -> 32.2; gSc
  25.8 / 34.8) but the streak share with it (L*>50 4.2% -> 1.2%). TONE_BACK by ROOT place is the wrong key: the back of the
  head is covered by cards rooted at the FRONT (strands run from the hairline over the top to the tie), so d2/d3 (FRONT 1.25)
  made the back head LIGHTER (p50 41 -> 44, L*>50 11 -> 32%) and the front crown box did not move (p50 23 in all: the front's
  dark is shading, not albedo). HOOK_RISE 4 mm cut 70 head cards, all L0 (strands rising to the tie at the nape), and left
  the front hooks as they were: DEAD, stays off.
  r26b: wisps w1 WISP_ALPHA 0.9 + WISP_KIDS_FACE 3, w2 + WISP_ALPHA 1.0 + WISP_LIFT 0.8 (wisps stop at the jaw: thin tips
  under the cutoff?). r26c: e1 TAIL_TONE 0.62 + all head cards x 0.85 (TONE_BACK = TONE_FRONT); e2 + TONE_CONTRAST_TAIL 4.5;
  e3 e1 + ENV_PCT 80 (front top outline). STATE: r26b / r26c chained locally.
- (3) WISPS r26b (t26 tiles w_v1 / w_v0: gSc | b33c | w1 | w2): w2 (WISP_ALPHA 1.0, WISP_KIDS_FACE 3, WISP_LIFT 0.8) shows a
  little more of the cheek / pre-ear locks, still grey-pink and thin, nowhere near gSc's golden locks to the collarbone.
  Marginal: not a default yet.
- (1) TONE r26c (hl.py): e1 (TAIL_TONE 0.62, every head card x 0.85) back head p50 41.0 -> 37.1 (gSc 33.0), tail 36.3 ->
  31.6 (25.8), but L*>50 at the tail 4.2 -> 1.4%; e2 (+ TONE_CONTRAST_TAIL 4.5) tail 33.4 / 3/4 35.1 (gSc 34.8) with the
  streaks back (3.0%, gap 5): KEPT as the tone base. e3 ENV_PCT 80: no change anywhere (cards sit under the 90th already).
- (2) FRONT CROWN TRACED (flat g1v0 per range, b33c: t26/flat.png cap | L1 | L2 | L3): the "flat spike / block" on top of
  the front outline is the CAP (the sunk mass: a flat-topped, notched block standing over the top); L1 and L2 each have one
  hooked flap at the top right; L3 (flyaways) nothing there. NEW knob hair.CAP_SMOOTH (deg, gaussian over the mass cap's
  height, 0 = off). r26d: f1 6 deg, f2 12 deg. hx.py / exa26.py take hh.<CONST>.
- (2b) CAP_SMOOTH (r26d f1 6 / f2 12 deg): NO change (the card export's cap is reshaped after, by cap_under_cards). NEW knob
  hair.CAP_RELAX (iterations: the card cap's radius relaxed over its mesh, only ever lowered, after cap_under_cards):
  r26e g1 20 / g2 60 with the e2 tone. Flat cap g1v0 (t26/g_cap.png b33c | g2): the notched flat block is now a round dome;
  lit front (t26/g_v0.png): the centre block on the outline is gone. Cost: at 3/4 (t26/g1_v1.png) a top-layer card's edge
  shows as a ledge over the crown where the cap no longer backs it. KEPT (60).
  HOOK_RISE again on layers >= 1 only (HOOK_LAYER_MIN, r26f h1 2 mm: cut 55 L1 cards): the two hooked flaps unchanged
  (t26/h_v0.png): DEAD, off. The hooks are not "down then up" cards; they need their own trace (per-card id at the pixel).
- SIDE-BY-SIDE BLIND REVIEW (one fresh subagent, review/r26_sbs/<view>.png = gSc | X | Y shuffled, key.txt): FRONT closer =
  g2 (b33c "a flat rectangular block sticking up at the centre of the crown"; g2 "a hooked flap on its right"); 3/4 same
  (g2: flaps / spikes forward at the front top; b33c: the block; b33c's tail tone slightly closer); BACK same. Both: MAJOR
  torn / hooked top outline, tail texture "dark smeared slabs", no part + hard dark hairline; minor: stringy temple wisps
  (not wet clumps), dark ticks behind the ear, chopped tail ends; "no broad dark lock beside the face" in either.
  -> b34 = g2 (the RC's crown "flat spike" = the cap block: removed; the hooks remain).
- (4) FULL EXPORT (exa26.py, b34 settings, tier hero injected; exp/exa34, out/exa34.log, 584 s on the local heavy slot):
  hair LOD0..3 = 23844 / 12496 / 8246 / 2498 tris (budgets hero hair_cards 25000 / 12500 / 8250 / 2500: all inside);
  LOD0 total 73857 of 100000; LOD1 38483, LOD2 26737, LOD3 18733. NB lashes stay 4880 at EVERY LOD (LOD3: a quarter of
  its triangles are lashes): an asset.py LOD gap for the lashes part, not hair. The GLBs: hc_s2.glb 22 MB, LOD1-3 2.2 / 1.7 /
  1.2 MB. NOT DONE: each LOD rendered at its game distance (no budget left this round).

## Handover 2026-10-18 (hair-cards agent, round 26; stopped at the 70-tool-call rule)
Commits: HOOK_RISE / HOOK_LAYER_MIN (off: dead), TONE_BACK / TONE_FRONT / TONE_POS_Y (both 0.85 = all head cards darker),
hair.CAP_SMOOTH (off: no effect on the card cap), hair.CAP_RELAX 60 (the crown's flat cap block gone), TAIL_TONE 0.62,
TONE_CONTRAST_TAIL 4.5 = b34. Scratch t26/ (tiles), r26a-f.sh, exa26.py (tier hero injected, hh./hk. constants), hx.py
takes hh.<CONST>, review/r26_sbs. Nothing in flight.
VERDICT (look-first): b34 fixes the RC's front "flat spike" (it was the cap's notched top, now a dome) and brings the back
down ~4 L* (head back p50 41 -> 37, gSc 33; tail 36 -> 33, gSc 26; 3/4 tail = gSc) with the tail streaks kept. Asked 8-10
L*: got ~4 at the head, ~3 at the tail; more costs the streaks (e1). The front is still the weakest view: torn top outline
with two hooked flaps, no part, hard dark hairline, thin grey temple wisps; at 3/4 a top card's edge now shows as a ledge.
The reviewer did not see a broad dark lock beside the face. Still reads as cards at 1 m.
NEXT, in order: (1) the two hooked flaps: trace them per card (id pass at the outline pixel -> card index -> its
strands), then pull those cards under the envelope or drop them. (2) the 3/4 crown ledge after CAP_RELAX: a softer top-card
edge fade or CAP_RELAX ~30. (3) render LOD1-3 (exp/exa34) at their game distances. (4) the part / hairline (dead levers in
round 23: CAP_BASE_IN, CAP_PART_CUT, HL_LIFT), wisps (w2: WISP_ALPHA 1.0, KIDS 3, LIFT 0.8 was marginal). (5) lashes LOD.

## hair-cards round 27 (2026-10-18, fresh session; Joe: only what's left for Tess / Garrett game-ready; best = b34)
BEST CARDS FOR EXPORT: b34 (unchanged so far; see round 26's header for the path and settings).
- (1) HOOKS TRACED (new scratch hooktr.py <tag> <view> boxes: projects every card's alpha>0.5 samples with the shot's
  camera (frames_*.json; NB `dir` there points from the target TO the eye), a z-buffer of card ids, saved
  t27/cardid_<tag>_<view>.npy (IoU-checked against the id pass: outline rows match to 1-2 px); per card at the box: layer,
  pixels, its centre polyline root -> tip, radius from the scalp centre, bends). g2 g1v0: right hook (px 560-576 x 357-372)
  = the ROOT ends of six top cards (L0 48 / 53, L1 125 / 126, L2 190 / 192) rooted at (+33, -28, +78) mm from the scalp
  centre, i.e. on top just left of the part, 2-3 cm behind the hairline; left hook (478-500 x 366-376) = the root ends of
  L0 2 / L1 56 / 57 / L2 138 at (-41, 0, +80). They are NOT down-then-up cards (bends 1-10 deg past the root): the cards
  START 88-92 mm out (L0 88, L1 90, L2 92) over a cap at ~75-78 mm there, first segments bending 10-22 deg (they leave
  sideways, then turn back), and each card's root is a straight-cut edge (ROOT_FADE only 4 mm). Stacked root ends standing
  10-15 mm over the cap = the hooked flaps on the outline. Same cause, likely, for the 3/4 "ledge" since CAP_RELAX lowered
  the cap under those roots (the gap grew).
  r27a (chained locally): LOD shots (exp/lods/hair[_LODn].glb = exa34's character GLBs reduced to the hair node by lodx.py)
  at g2 / g4 / g8 (v0, v1); k1 ROOT_FADE 0.012, k2 ROOT_FADE 0.02, k3 CAP_RELAX 30 (g1v0, g1v1, g1backl).
  STATE: r27a running. NEXT: tiles k1-k3 vs b34 at the hooks / ledge; if root fade doesn't remove the flaps, a root seat
  (the first ~15 mm of a head card eased down to the cap).
- NEW knob hair_clumps.ROOT_SEAT (m, default 0 = off) + ROOT_SEAT_GAP 3 mm: a head card's first ROOT_SEAT from its root is
  eased down (smoothstep, only lowered) to its strands' roots' median radius + the gap: the root ends tuck under the
  mass instead of standing as cut edges over the cap. r27c (after r27b): s1 0.015, s2 0.03, s3 0.03 + ROOT_FADE 0.012.
  LOD shots: exa34's LOD GLBs import every mesh (the body's textures are external): lodx.py also strips the other
  nodes' meshes; r27b re-renders LOD1-3 after r27a. LOD distances from budgets.lod_screen_size [1, .5, .25, .12] (a 1.75 m
  sphere on a 1920-wide, 59 deg vertical frame: LOD1 from ~1.7 m, LOD2 ~3.5 m, LOD3 ~7 m): judged at g2 / g4 / g8, each
  LOD beside LOD0 at the same distance (the pop at the switch).
- (1b) r27a READ (t27/k_v0.png, k_v1.png: gSc | b34 (lg2) | k1 | k2 | k3): ROOT_FADE 0.012 / 0.02 moved 360 / 773 px of
  the front frame (mean |dL| 0.02 / 0.03): the hooks unchanged, DEAD lever for them (the root ends are not what the
  alpha fade reaches; the flap is the cards' geometry). CAP_RELAX 30 (k3): 83 px changed at the front, the 3/4 ledge
  looks the same: no gain, b34 keeps 60. The geometric fix ROOT_SEAT (s1-s3, r27c) has RENDERED but is NOT judged yet.
- (3) LODs AT GAME DISTANCE (t27/lods.png: LOD0 | LODk at g2 / g4 / g8, v1 + v0; t27/lod_atlas.png): MAJOR, export
  fault. The exported LOD1-3 (exa34, asset.export_asset lods=True) do NOT read as the same hair: a bare skin patch over
  the crown, floating bits over the head, a torn / tattered tail, at every distance. The SAME tiers exported by
  hair.export_hair (hx.py tiers=hero,main,npc,far -> exp/tiers27) render whole and close to LOD0 (trmain at g2, trfar at
  g8: same crown, same tail mass). Their caps sit 2-3 mm over the scalp in every tier (capchk.py), so not the cap. Cause
  to confirm: asset.py (~line 2300) exports each LOD tier with its own hair.export_cards into out/_lod<k> and then sets
  tp_["atlas"] = LOD0's atlas; the atlas is NOT tier-independent (md5 of hair_basecolor differs between a hero-only
  export and a 4-tier export), so LOD UVs land on the wrong texels (transparent / wrong tiles): bald crown, torn tail.
  (lodx.py's hair-only extraction is not it: LOD0 through the same path renders like the hero GLB.)
  Fix direction: build all tiers in ONE hair.export_hair call (one atlas, as its docstring promises), and make the
  atlas really shared (export_hair writes each tier's maps over the last: check that each tier's UVs index the final
  atlas), then re-export and re-run this LOD sheet.
- (1c) ROOT_SEAT READ (t27/s_v0.png: gSc | b34 | s1 0.015 | s2 0.03 | s3 0.03 + ROOT_FADE 0.012), front crown at 1 m:
  the geometric fix WORKS on the lever: s1 removes most of the left spiky flap; s2 also flattens the right hook to a small
  lump on the outline, which now reads as a rounder dome (nearer gSc); s3 = s2. Candidate b35 = b34 + ROOT_SEAT 0.03, NOT
  yet a default: 3/4 + back views and a blind side-by-side review still owed (handover NEXT (2)).

## Handover 2026-10-18 (hair-cards agent, round 27; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: still b34 (round 26 header), BUT its LOD1-3 are broken in the character export (above): ship
LOD0 only until the asset.py hair-LOD atlas fault is fixed.
Commits: ROOT_SEAT / ROOT_SEAT_GAP (hair_clumps, opt-in, off). Scratch (copies in t27/): hooktr.py (card-id z-buffer at
outline pixels, per-card polyline), lodx.py (character GLB -> hair-only GLB for shots.py), capchk.py (cap vs scalp per
tier), t27tile.py; r27a/b/c.sh; exp/lods, exp/tiers27, exp/k1-k3, exp/s1-s3. Nothing in flight (r27c finished or
finishing: check t27/r27c.done; no waits left).
VERDICT (look-first): no visible improvement this round. The hooked flaps are traced (root ends of six top cards
standing 10-15 mm over the cap at the front crown) but the alpha lever is dead; the geometric fix (ROOT_SEAT) is rendered,
unjudged. The biggest finding is the LOD export: LOD1-3 read as a different, balding, torn hairdo at their switch
distances, while the same tiers built by export_hair read as the same hair.
NEXT, in order: (1) asset.py hair LODs: one export_hair for all tiers / a truly shared atlas; re-export (exa26.py) and
re-run the LOD sheet (r27b.sh with lodx.py). (2) s2 (ROOT_SEAT 0.03) is the front winner by my look: tile it at 3/4 / back (t27tile.py g1v0 430,335,680,450 2 gSc lg2 ls1 ls2 ls3;
g1v1 430,345,730,500 1.6) and re-trace with hooktr.py; keep ROOT_SEAT only if the flaps go without bare crown.
(3) blind side-by-side review of the winner vs b34. (4) part / hairline, tail slabs (untouched this round). (5) lashes LOD.

## hair-cards round 28 (2026-10-18, fresh session; Joe: game-ready Tess / Garrett; r27's broken hair LOD1-3 first)
BEST CARDS FOR EXPORT: b35 = b34 + hair_clumps.ROOT_SEAT 0.03 (now the DEFAULT) = hair defaults at this round's commit +
  hc_s2's spec; export as b34 (spec hair.export.tier "hero" (exa26.py injects it), export_asset(role="hero", lods=True)).
  Path: /mnt/data/hifipushie/haircards/exp/exa28b/hc_s2.glb (+ _LOD1-3, maps beside them). LODs OK: y (same hair at every
  switch distance, t28/lods.png; minor: a few stray strokes over the crown at LOD1-3 only, below).
- (1) LOD CAUSE CONFIRMED (scratch atlasprobe.py hc_s2 t28/ap: export_cards per tier into its own dir): the hero tier's
  atlas is 2048 x 2048 (tiles + scalp chart in the top 1024 rows, the baked clump tiles (hair_clumps.bake_tiles, cut
  "clumps") stacked UNDER them), main / npc / far have no baked cards: 2048 x 1024, the same top rows (max diff 1/255).
  asset.py pointed each tier's uv (v over a 1024-row atlas) at LOD0's 2048-row atlas: every card read texels twice as
  far down, half of them in the bake block or across it = the bald crown, floating bits, torn tail. export_hair had the
  same fault the other way: each tier wrote its maps over the last, so every GLB but the last tier's wore the wrong atlas
  (r27's main / far looked right only because far was last and main = far's atlas).
  FIX (general): hair.share_atlas(part, files, files0): a tier whose maps are LOD0's pictures, or their top rows, gets its
  v remapped onto those rows (hair_cards.remap_v) and shares LOD0's atlas; a tier whose pictures differ carries its own
  maps (asset: `<hair>_lod<k>_<map>.png` beside the GLBs, the hair material's extensions copied; export_hair:
  `hair_<tier>_<map>.png`). asset's LOD report says "atlas": "LOD0's" | "own". export_hair's first tier is the shared one.
  Test tests/test_hair_lods.py (test_share_atlas: fails on the r27 code: tier uv on LOD0's atlas samples other texels).
  STATE: r28a running (exa26.py hc_s2 -> exp/exa28, lodx -> exp/lods28, glbuv.py -> t28/glbuv.txt, shots g2/g4/g8 _l28*).
  NEXT: LOD sheet LOD0 | LODk at each switch distance.
- (2) LASHES LOD: lods.ribbon_lod (lod_parts(ribbons=...)): the lash ribbons (each a strip of across-pairs, lashes.build)
  thinned by whole ribbons, evenly along the lid, at the head's ratio (budgets lod_ratios head_and_hair: 1 / .5 / .25 / .1),
  the kept ones widened by 1 / ratio (cap lods.RIBBON_WIDEN 3) to hold the dark frame's coverage; vertices kept (face
  shapes and weights index them). 4880 -> ~2440 / 1220 / 488 expected. Test test_ribbon_lod.
  RESULT (r28a, exp/exa28, b34): lashes 4880 -> 2440 / 1216 / 488 at LOD1-3 (LOD3 total 14341). Hair LOD1-3 took the
  OWN-maps path: share_atlas refused on the normal map (0.005% of texels, the tiles' last rows next to the bake block,
  differ by up to 28 levels); now a share of <= 0.1% differing texels still counts as the same picture. (r28a's renders
  never ran: run.sh cds to the worktree, the relative glb paths missed; r28b uses absolute ones.)
- (3) ROOT_SEAT 0.03 vs b34 (t28/s_v1.png 3/4, s_back.png back, s_v0.png front: gSc | lg2 | ls2): 3/4: the flat slab
  standing off the crown top is gone, a rounder dome; back: the same (no bare crown added). BLIND review (fresh subagent,
  t28/blind_*.png, ref | A | B, key t28/blind_key.json: A = ls2): front A slight, 3/4 A clear, back tie. ADOPTED:
  ROOT_SEAT default 0.03 (b35). Reviewer's notes for both: bare scalp at the hairline / temples (ref covered), a ragged
  crown edge and a dark gap behind the tie at the back, a torn, patchy ponytail with dark holes (ref dense, fibrous).
  STATE: r28b running (exa26.py hc_s2 -> exp/exa28b with b35 + the shared-atlas tolerance; lods28b; t28/glbuv_b.txt;
  shots g2/g4/g8 _l28b*). NEXT: LOD sheet; glbuv numbers (LOD1-3 on LOD0's atlas, v remapped).
- (1c) r28b RESULT (exp/exa28b, b35, the fixed export): no "atlas differs" line: LOD1-3 hair on LOD0's 2048 x 2048
  atlas, uv v 0-0.5 (the tiles' rows; glbuv.py, t28/glbuv_b.txt: mean alpha at card centroids LOD1 0.78 / LOD2 0.76 /
  LOD3 0.58 vs r27's broken LOD1 0.57 with v over 0-1). Triangles LOD1-3: hair 12496 / 8246 / 2498, lashes 2440 / 1216 /
  488, totals 36043 / 23073 / 14341. LOOK (t28/lods.png, t28/lodsheet.py: LOD0 | LOD1 | LOD2 | LOD3 at g2 / g4 / g8, 3/4
  + front, head 99 / 51 / 28 px tall): every LOD now reads as the SAME hair: full crown, same mass and tone, tail whole;
  no bald patch, no torn tail. LOD1-2 are even cleaner at the front crown than LOD0 (fewer hooks). Left: (a) a few thin
  dark strokes 1-3 cm OVER the crown at LOD1-3 (absent at LOD0; at 51 / 28 px heads 1-2 px); t28/floatc.py finds no
  piece > 8 mm from the rest at LOD1, 4 small ones at LOD3, so they are cards attached at a root that stand up (likely the
  thin wisp / fly cards of the lower tiers' 'pair' / 'lock' / 'free' cuts); (b) LOD3's tail is spikier (far tier, 2.5k).
  STATE: LODs fixed and shippable. NEXT: trace (a) with hooktr.py on out/s_hc_s2_l28b_LOD1_g2v0.png (card ids at the
  strokes) and drop / tuck those cards in the lower tiers (general: a tier wider than the hero's should not carry fly
  cards that stand off the mass).

## Handover 2026-10-18 (hair-cards agent, round 28; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: b35 = hair defaults at this commit (ROOT_SEAT 0.03 now default) + hc_s2's spec, exported with
hair.export.tier "hero", export_asset(role="hero", lods=True) (exa26.py): exp/exa28b/hc_s2.glb + _LOD1-3. LODs OK: y.
Commits: hair.share_atlas + asset / export_hair LOD atlas fix; lods.ribbon_lod (lashes per LOD); ROOT_SEAT default 0.03;
tests/test_hair_lods.py. Scratch t28/: atlasprobe (ap/), blind.py + blind_*.png + blind_key.json, lodsheet.py, lods.png,
floatc.py, glbuv_b.txt; glbuv.py; r28a.sh (b34, superseded), r28b.sh. Nothing in flight.
VERDICT (look-first): the ship blocker is gone: LOD1-3 read as the same hairdo as LOD0 at their switch distances. b35's
3/4 crown is a rounder dome (blind review: front slight, 3/4 clear win, back tie). Still weak at close range (reviewer,
both builds): bare scalp at the hairline / temples, ragged crown edge and a dark gap behind the tie at the back, a torn,
patchy ponytail with dark holes.
NEXT, in order: (1) the stray strokes over the crown at LOD1-3 (above). (2) Garrett's export through the same path (not
run this round: check his hair LODs share the atlas too). (3) part / hairline coverage (bare temples), (4) tail slabs /
ponytail holes. Lashes' 5699 eyes_mouth_lashes at LOD0 is still over the 5000 hero budget (thin basis): a lash count
call for Joe or the coordinator, not changed here.

## hair-cards round 29 (2026-10-18, fresh session; Joe: game-ready Tess / Garrett; coordinator: fit eyes / mouth / lashes to 5,000)
BEST CARDS FOR EXPORT: b36 = exp/exa29b/hc_s2.glb + _LOD1-3 (b35's hero hair; LOD1-3 without the crown strays; lashes fit
the 5,000 eyes_mouth_lashes budget, 4,995). LODs OK: y for LOD1-2; LOD3 n from behind (bare patch by the tie, below).
- (1) STRAYS OVER THE CROWN at LOD1-3 traced (scratch t29/standoff.py: per LOD, welded hair pieces standing past LOD0's
  outermost hair in their direction from the head centre, top of the head): LOD0 none; LOD1 17 / LOD2 20 / LOD3 8 pieces
  > 6 mm, the worst at the front crown (glTF y 1.655, z +0.08) 26-27 mm past LOD0, 6-8 vertices, uv u 0.438-0.468 (the
  fly tile): POOLED HALO cards (hair_cards.pooled_singles, the lower tiers' halo, 8 single-hair locks a card). The hero
  (hair_clumps) gives no card to a single hair rooted over the crown (FLY_CROWN / FLY_CROWN_FREE) or one that loops
  (FLY_STRAIGHT); the lower tiers had no such rule. FIX (general): hair_cards.halo_card_ok, the hero's rules for every
  tier, applied to the pool before clustering. Test test_halo_card_rules. Back of the head: tail pieces by the tie
  13-47 mm past LOD0 at LOD1-3 (uv u 0.0-0.13), the LOD3 spiky tail; next after the re-export.
  r29a RESULT (exp/exa29a): NOTHING moved (same vertex ids, LOD1 12496): the strays are not pooled. t29/lockat.py (locks
  nearest a point): th59 / th18 / th48 / th15 / th7 / th62, 1-2 hairs, W 1-3 mm, free, rooted 8 cm over the scalp centre
  IN THE MASS (off_head, so not is_single, so not pooled): the lower tiers cut them as thin wisps (2-3 'fly' cards each).
  The hero drops them (FLY_CROWN_FREE). FIX 2: _lock_cards skips any few-hair lock (hairs > 0, not face) failing
  halo_card_ok. STATE: r29b running (exa26.py -> exp/exa29b + t29/eyetile.py -> t29/ea_*; whether it has fix 2 depends
  on when hair_cards was imported: standoff.py says).
  r29b RESULT (exp/exa29b, has fix 2: LOD1 hair 12492): the front-crown strays (uv 0.438, 26-27 mm) are GONE at LOD1-3.
  Left past LOD0 by > 6 mm: side cards over the ears 7-12 mm (lower tiers' wider cards: the outline, fine) and the
  tail by the tie, behind the head (glTF y 1.49, z -0.10..-0.12), LOD1 14-23 mm, LOD2 16-36, LOD3 11-47 mm (8-vertex
  cards, the far tier's 75 mm segments): the spiky LOD3 tail. STATE: r29c running (lodx + shots _l29b* incl. g4backl,
  t29/lods.png). NEXT: look at the sheet; the far tier's tail.
  LOOK (t29/lods.png, LOD0 | LOD1 | LOD2 | LOD3 at g2 / g4 / g8 front, g2 / g4 3/4, g4 back; shots _l29b*): front views:
  the strokes over the crown are GONE at every LOD; LOD1-3 read as LOD0's hair. Left: (a) at the tie, thin spikes
  standing out sideways at LOD1-3 (3/4 views, worst LOD3); (b) NEW TO THE SHEET (first back view of the LODs): LOD3 at 4 m
  from behind shows a BARE SKIN PATCH right of the tie, ~1/4 of the back of the head (the far tier's mass cap / free cut
  not covering there); LOD1-2 backs are fine. Not checked whether r28b had it (no back render then): likely, nothing
  this round touches the far tier's coverage except few-hair locks over the crown.
- (2) EYES / MOUTH / LASHES BUDGET (b35: 5,699 of 5,000 = lashes 4,880 + eyes 795 + teeth_lower 24; teeth / tongue
  are hidden-face dropped). What reads least at 1 m: the LOWER lashes' segments (3 mm, 10 deg curl: 4 quads for a
  straight line) and a few % of whole lashes. CHANGES (general): lashes per-lid `segments`, the lower lid 2 by default
  (lashes.VERSION 21): 4,880 -> 4,280 for Tess; asset.lash_cap (the role's eyes_mouth_lashes budget less eyes / teeth /
  tongue / brows) + lods.ribbon_fit (ribbon_lod at the largest share of whole lashes that fits, widened for coverage)
  after the lash export: Tess's lashes 4,280 -> <= 4,181 (~2% of lashes). Test test_lash_budget_fit.
  RESULT (r29b): log "lashes: 4280 -> 4172 triangles (595 of 610 lashes, widened x1.02) to fit eyes_mouth_lashes 5000";
  budget line eyes_mouth_lashes 4995 of 5000 (was 5699 OVER); LOD1-3 lashes 2088 / 1040 / 420. TILES (t29/eyetile.py
  <export dir> <prefix>: the export GLB re-imported via asset.game frames, face at 1 m (game pixels) + eyes front / 3/4
  / side + mouth; t29/lash_ba.png top = b35, bottom = r29b): no difference I can see at 1 m or close. BLIND review
  (fresh subagent, t29/blind_lash_A/B.png, key blind_lash_key.json: A = after): 1 m none, eyes front none, 3/4 about the
  same, side none: "VERDICT: equivalent". ADOPTED (defaults). The review's SHARED faults (both builds, other
  stages: to the coordinator): at the re-imported GLB the lid rims / inner corners show pink-lilac (the eye's wet /
  caruncle geometry past the lids?), the upper lashes read as a stiff comb from the side (no curl visible), the lash line
  is lost at 1 m. Also seen in the same re-import (not hair-cards' viewer): the hair is ash-grey with a WHITE patch at the
  crown front: blender_game's importer materials, not lodx / game_material; check before anyone judges hair there.

## Handover 2026-10-18 (hair-cards agent, round 29; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: b36 = hair / lashes / asset defaults at this commit + hc_s2's spec, exported as before (exa26.py:
hair.export.tier "hero", export_asset(role="hero", lods=True)): /mnt/data/hifipushie/haircards/exp/exa29b/hc_s2.glb +
_LOD1-3 (LOD0 hair identical to b35; LOD1-3 without the crown strays; lashes fitted). LODs OK: y for LOD1-2; LOD3 n from
behind (bare patch right of the tie at g4 back, t29/lods.png last row), fine from the front / 3/4.
Commits: hair_cards.halo_card_ok (the hero's FLY_CROWN / _FREE / FLY_STRAIGHT rules) on pooled singles AND on few-hair
locks cut as wisps at the lower tiers; lashes per-lid `segments` (lower 2, VERSION 21); asset.lash_cap + lods.ribbon_fit
(lashes fit the role's eyes_mouth_lashes budget); tests in tests/test_hair_lods.py (test_lash_budget_fit,
test_halo_card_rules). Budget: eyes_mouth_lashes 4995 of 5000 (was 5699); blind review of the lash tiles: equivalent.
Scratch t29/: standoff.py (LODk pieces past LOD0's hair), lockat.py (locks nearest a point), eyetile.py (export GLB
re-imported: 1 m + eye / mouth close-ups), lash_ba.png, blind_lash_*, lods.png; r29a/b/c.sh. Nothing in flight.
VERDICT (look-first): the crown strays are fixed and the eye / mouth group fits its budget with no visible change.
LOD3's back has a bald patch beside the tie (a ship fault for a far LOD seen from behind) and LOD1-3 have thin spikes
sideways at the tie. LOD0's own faults (bare temples / part, ragged crown edge, dark gap behind the tie, patchy tail) are
untouched this round. bin/review was not usable (CLI after 2026-10-19 13:00 MT): reviews were fresh blind subagents.
For the coordinator (other stages): in the re-imported GLB (asset.game) the lid rims / inner corners show pink-lilac,
the upper lashes read as a stiff comb in profile, and the hair renders ash-grey with a white patch at the crown front
(the importer's materials: don't judge hair there).
NEXT, in order: (1) LOD3 back: render exa28b LOD3 g4backl (was it there before?), then trace (standoff.py on the
far tier against the head: the free cut / mass cap near the tie) and fix the coverage. (2) The spikes at the tie at
LOD1-3 (standoff: tail cards by the tie 14-47 mm past LOD0, uv u 0-0.13). (3) Garrett's export through the same path.
(4) Hero: bare temples / part, ragged crown edge, gap behind the tie, tail holes.

## hair-cards round 30 (2026-10-18, fresh session; Joe: game-ready Tess / Garrett; LOD3 back, tie spikes, LOD0 faults)
BEST CARDS FOR EXPORT: b37 = exp/exa30b/hc_s2.glb + _LOD1-3 (hair defaults at this round's commit: CAP_RELAX_FLOOR +
FLY_FAR_TIERS; LOD0 identical to b36). LODs OK: y (LOD3 back covered; blind review: LOD0-2 equivalent to b36, LOD3 better).
- (1) LOD3 BARE PATCH BEHIND (t30/bare.py <glb>...: rays from behind, glTF -z -> +z over the back of the head, '#' where
  the body is hit before any hair): exa29b LOD0 45 bare rays (the nape below the hairline, char's right: legit), LOD2
  51 (same), LOD3 198 (a block over the lower back of the head, x -0.09..0, y 1.44-1.57 = the patch right of the tie).
  The far tier's job cap (hair.job budget far, t30/capfar.py) stands >= 5 mm over the skin there, so the loss is
  later: cards_job lowers the cap under the cards (cap_under_cards, floor = lift = sagitta + 2 mm = 3.2 mm at 14 deg)
  and THEN relaxes its radius (CAP_RELAX 60 iterations, only lowering): at the far tier's 14 deg grid 60 rounds
  diffuse the hairline's dive rows (under the skin) over the whole lower back, so the cap sank under the skin
  (rays met hair 1-18 mm BEHIND the skin there). FIX (general, every tier): hair.CAP_RELAX_FLOOR: the relaxed cap
  never goes under the floor it was given. t30/far1.py (export_cards at a tier, flag off / on, rays vs exa29b's LOD3
  body): far tier bare 198 -> 79 (what's left: the nape below the hairline as LOD0 / LOD2 have it, 3 small spots).
  STATE: r30a running (r30a.sh: exa26 -> exp/exa30a, lodx, shots per LOD incl. g2backl / g4backl / g4backq / g4back /
  g8back, t30/lods_30a.png, t30/bare_30a.txt). NEXT: the tie spikes (2) while it runs.
- (2) TIE SPIKES at LOD1-3 (t30/tiespk.py <glb0> <glbk|npz>...: pieces behind the head by the tie standing > 8 mm past
  LOD0's hair from a point at the tie): exa29b LOD1 47 / LOD2 44 / LOD3 39 pieces; two kinds. (a) FLY-tile cards (uv
  0.44-0.47), thin, 130-160 mm long, 35-80 mm past LOD0: the lower tiers' pooled halo hairs / few-hair wisps on the
  tail. The hero gives no card to a single hair standing > hair_clumps.FLY_FAR (20 mm) off the rest of the hair; the
  lower tiers had no such rule. FIX (general): hair_cards.FLY_FAR_TIERS / drop_far_fly at the end of clump_cards
  (face-framing locks exempt). Test test_far_fly_dropped. t30/far2.py (export_cards at a tier, flag off / on): main
  the 80 / 49 / 47 mm fly spikes gone (47 -> 42 pieces), far likewise (39 -> 36). (b) TAIL-tile cards (uv 0-0.13), 200-260
  mm long, 43-135 mm wide, 25-46 mm past LOD0 just under the tie on the tail's +x side: the lower tiers' wide tail
  cards; NEXT.
  r30a RESULT (exp/exa30a = b36 + CAP_RELAX_FLOOR; the fly fix NOT in it, tiespk unchanged): bare rays from behind
  LOD0 46 / LOD1 54 / LOD2 47 / LOD3 79 (was 198; the rest = the nape below the hairline, as LOD0). LOOK
  (t30/lods_30a.png, LOD0 | 1 | 2 | 3 at g4v0, g4v1, g2backl, g4backl, g4backq, g4back, g8back): the LOD3 bare patch is
  GONE in every back view; LOD3 reads as one even mass. Still: thin spikes over / beside the tie at g4v1 and g4backq on
  LOD1-3 (worst LOD3), a pale chip by LOD3's right temple at g4v0. STATE: r30b running (same chain, fly fix in:
  exp/exa30b, t30/lods_30b.png). NEXT: tiespk on 30b; the tail-tile cards if the spikes remain.
  r30b RESULT (exp/exa30b, both fixes): bare rays from behind LOD0 46 / LOD1 50 / LOD2 47 / LOD3 79; tiespk: the fly
  spikes off the tail (80 / 49 / 47 mm) gone at LOD1-3 (47 -> 42, 44 -> 40, 39 -> 36 pieces). What tiespk still lists:
  the tail-tile pieces' worst points are the tail's TIPS (y 1.35, below its region: a probe artefact, not spikes), two fly
  cards over the left ear (x 0.085, 35 mm past LOD0's cards but within FLY_FAR of the groom's loose strands), and
  tail-tile card ROOTS standing up off the top of the tie at LOD3 (29 mm, y 1.55-1.57): the spikes still seen at g4v1 /
  g4backq on LOD1-3 above the tie. LOOK (t30/lods_30b.png): LOD3's back is covered in every view; the spikes over the
  tie are thinner but still there at g4v1 (LOD1-3) and g4backq (LOD1, LOD3).
  BLIND REVIEW (fresh subagent, t30/blind_A/B.png, rows g4v1 / g4backl / g4v0 x LOD0-3, key blind_key.json: A = b36, B =
  r30b): LOD0-2 equivalent (pixel-near), LOD3 "B clearly better" (A: skin-coloured hole at the crown / tie + a long
  shard right of the tail, both MAJOR; B: covered, a small loop of cards off the tie, MINOR). Shared: a shard right of the
  tail below the tie at LOD1-2 (MINOR), ragged tail lower edge, thin temples. ADOPTED: b37.

## Handover 2026-10-18 (hair-cards agent, round 30; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: b37 = hair defaults at this commit + hc_s2's spec, exported as before (exa26.py: hair.export.tier
"hero", export_asset(role="hero", lods=True)): /mnt/data/hifipushie/haircards/exp/exa30b/hc_s2.glb + _LOD1-3 (LOD0 hair =
b36's; lashes as b36). LODs OK: y, all views incl. 5 back views (t30/lods_30b.png).
Commits: hair.CAP_RELAX_FLOOR (the relaxed card cap keeps the floor cap_under_cards gave it: the far tier's 14 deg cap
sank under the skin over the lower back = LOD3's bare patch); hair_cards.FLY_FAR_TIERS / drop_far_fly (the hero's FLY_FAR
for fly cards at every tier; test test_far_fly_dropped). Scratch t30/: bare.py (rays from behind: skin before hair),
bare_dir.py (top / front / left), capfar.py, far1.py / far2.py (export_cards at one tier, a flag off / on, no full export),
tiespk.py / tiespk2.py (pieces by the tie past LOD0), blind.py; r30a.sh <tag> (export -> lodx -> shots incl. backs ->
lodsheet -> bare). Nothing in flight.
VERDICT (look-first): the LOD3 bald patch is fixed (LOD3 reads as one even mass from behind); the long fly shards off the
tail are gone; small spikes still stand up off the top of the tie on LOD1-3 at 3/4 (tail-card roots). LOD0 untouched:
its torn tail, dark tie area, ragged crown edge and thin temples are what the eye goes to now. (bare_dir.py on LOD0: no
geometric bare scalp from the top or side: the 'bare temples' are see-through / pale cards, not missing coverage.)
NEXT, in order: (1) tail-card roots at the tie on LOD1-3 (tiespk2: tail-tile pieces with their worst point at y 1.55-1.57;
taper / seat their roots into the band like the hero's gather cards (hair_cards clump_cards `gather` hw taper), or start
them under the band). (2) LOD0: tail holes / torn tail, dark gap behind the tie, ragged crown edge, temples (texture /
card opacity, not coverage). bin/review usable after 2026-10-19 13:00 MT.
## hair-cards round 31 (2026-10-18, fresh session; LOD0 the hero view; tail-card roots at the tie on LOD1-3)
BEST CARDS FOR EXPORT: b37 (round 30) until a round-31 build beats it.
LODs OK: y (b37).
- merge origin/main (f01962ee = this branch to round 25, squashed): hair_cards / hair_clumps ours; lashes: main's
  taper_out + our lower-lid segments 2 (VERSION 22); asset: our ribbon-fitted lash LODs (main's thin_strands on the lashes
  NOT also applied: it would thin them twice).
- (1) TAIL-CARD ROOTS AT THE TIE (t31/troot.py <tier> [flag=v]: captures clump_cards' cards in export_cards, the tied
  tail's cards whose first 6 stations' edges stand past b37 LOD0's hair near the tie): the lower tiers' tail cards leave
  the tie at FULL width (half widths 20-30 mm at the root: FREE_SPREAD 3.2 sigma of a clump whose strands fan round the
  band), so the flat root corners stood 15-29 mm up off the round tie. FIX: hair_cards.TAIL_ROOT_HW 8 mm at the root,
  eased to full over TAIL_ROOT_TAPER 50 mm (tier "tie" free locks only, not wisps). Root corners past LOD0 > 8 mm:
  far 11 -> 6, npc 15 -> 9, main 18 -> 13; what remains stands 13-19 mm at only 4-5 mm from the root, hw 8 mm: LOD0's
  own hair is recessed at the tie (its dark gap), so the probe overstates there. STATE: r31a running (t31/r31.sh 31a:
  export -> lods -> shots -> t31/lods_31a.png). NEXT: LOD0 (2) while it runs.
- (0) CROWN CHOPPED OFF (coordinator, after Joe on t28/s_v1.png: "lg2 looks like the hair is chopped off at the top"; item 0
  ahead of the tail). MEASURE t31/crowntop.py <tags> (the figure's top outline per column vs gSc's over its upper 45%):
  ls2 (= b35 = b37 LOD0) g1v0 deficit mean 21.3 px / p90 25 / area 4517, ragged 2.54 (gSc 1.32); g1v1 12.6 / 24 / 3675,
  ragged 2.08 (gSc 0.89). GEOMETRY t31/crownr.py [mod.FLAG=v] (hair_clumps.cut's hero cards, export aborted after the
  cut, vs the head strands' radius from C per 8-deg azimuth bin): cards' max radius short of the strands' p99 by 5.0 /
  7.6 / 9.1 mm (worst 10 / 18 / 17) at el 30-50 / 50-65 / 65-80, even under the p90 at 50-80; no card over el 80.
  Dead levers: SIDE_EL (88, 90), ENV_PCT 97 (nothing moved: the clump's own outer strands are near its mean over the
  crown). CAUSE: ROOT_SEAT (every head card's first 3 cm eased to 3 mm over its roots) over the crown, where nearly every
  card is rooted, plus each card at its own clump's mean. FIX: hair_clumps.CROWN_FILL (opt-in): after the root seat, a
  head card is raised (never lowered) toward the strands' ENV_PCT envelope less ENV_UNDER less CROWN_GAP 2 mm per layer
  under the top, ramped in over el 20-45 deg. crownr: short of p99 3.0 / 2.7 / 2.4 mm (worst 5.7 / 7.7 / 7.0), the top
  layer at the p90. STATE: r31c1 running (t31/r31c.sh c1 hk.CROWN_FILL=1.0: export -> LOD0 shots g1v0/v1/v2/backl ->
  crowntop t31/crown_c1.txt). NEXT: look at it vs gSc / ls2 at the s_v1 framing (hooks back at the front?).
- (1) r31a RESULT (exp/exa31a = b37 + TAIL_ROOT_HW 8 mm; t31/lods_31a.png): the spikes over the tie at g4v1 (LOD1-3) and
  g4backq (LOD1, LOD3) look the SAME as r30b, and the tie's dark band shows more at g2backl LOD1-2 (narrow roots). tiespk2
  on 31a: what stands past LOD0 by the tie is (a) the tail-tile cards' far parts (worst points 8-10 cm back along the
  tail at tie height, the very wide far-tier cards: 132-200 mm wide x 200-260 long, their CORNERS) and (b) two fly-tile
  cards over the left ear (x 0.085, 35 mm). So the spikes are not the root corners. TAIL_ROOT_HW back to 0 (opt-in, kept
  for the record). NEXT for (1): cap a tail card's width at the far tiers (FREE_CLIP x card_width = 91 mm at far) or
  split wide tail cards in two; trace the g4v1 spike with a frame box first.
- (0) r31c1 RESULT (CROWN_FILL 1.0; t31/crown_g1v0.png / crown_g1v1.png: gSc | ls2 | c1): crowntop deficit g1v0 21.3 ->
  16.8 px mean (area 4517 -> 3555), g1v1 12.6 -> 9.7 (3675 -> 2823), ragged unchanged (2.68 / 2.02 vs gSc 1.32 / 0.89).
  LOOK: the 3/4 crown is a little higher, but at the FRONT two flat flaps now stand out at the top corners (left and
  right of the crown, "wings": raised card ends in the air): worse than ls2 at the front. NOT adopted. STATE: r31c2
  running (CROWN_FILL 0.6, CROWN_EL 40: raise only over the top, less of it). NEXT: tile; if the flaps stay, the raise
  must stop short of a card's free end (taper the raise to 0 over its last few cm).
- (0) r31c2 (CROWN_FILL 0.6, CROWN_EL 40) / r31c3 (1.0 + CROWN_END 0.04): crowntop g1v0 20.2 / 16.8 px, g1v1 11.9 / 9.7
  (c3 = c1 to the decimal: the raised free ends are below the ramp, so the flaps are NOT free ends: they are the ROOT
  ends the fill lifts back up after ROOT_SEAT seated them, i.e. the round-27 hooked flaps). Tiles t31/crown4_g1v0.png /
  crown4_g1v1.png (gSc | ls2 | c1 | c2 | c3). BLIND REVIEW (fresh subagent, t31/blind_g1v0.png / blind_g1v1.png, ref | A |
  B, key t31/blind_key.json: A = c1, B = ls2): front B slight, 3/4 B clear, OVERALL B. A: dark slabs up at the top
  corners + a flat chopped edge between them (MAJOR), a notch on the front crown at 3/4 (MAJOR). B: crown lower and
  flatter than the ref (MAJOR), small flaps (MINOR). CROWN_FILL stays OFF (default 0): the measured 22% figure gain is
  bought with flaps.

## Handover 2026-10-18 (hair-cards agent, round 31; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: b37 unchanged (exp/exa30b/hc_s2.glb + _LOD1-3; hair defaults at this commit = b37's: TAIL_ROOT_HW,
CROWN_FILL, CROWN_END all default off). LODs OK: y (b37).
Commits: merge of origin/main (lashes VERSION 22 = main's taper_out + our lower segments 2; asset keeps our ribbon-fitted
lash LODs, main's thin_strands not also applied: check with the game_ready thread that nothing of theirs needs it);
hair_cards.TAIL_ROOT_HW / TAIL_ROOT_TAPER (opt-in); hair_clumps.CROWN_FILL / CROWN_GAP / CROWN_EL / CROWN_END (opt-in).
Scratch t31/: troot.py (tail cards' root edges vs LOD0 by the tie, per tier, no full export), crowntop.py (the figure's
top outline vs gSc per column: deficit / ragged), crownr.py (hero cut aborted after the cut: cards' radius vs the strands'
p90 / p99 per elevation band, flags as hcl.X=v), tile.py, r31.sh <tag> [flags] (the LOD chain, t31/lods_<tag>.png),
r31c.sh <tag> [hk.X=v] (export -> LOD0 1 m shots g1v0/v1/v2/backl -> crowntop). Nothing in flight.
VERDICT (look-first): no build beat b37 this round. The crown IS low and flat at the front (crowntop: 21 px short of gSc
at g1v0, ragged 2.5 vs 1.3), and the cause is now known in numbers (ROOT_SEAT's seated roots + cards at their clumps'
means: 5-9 mm under the strands' p99 over the crown, nothing over el 80 but the cap), but raising the cards brings the
root flaps back. The LOD1-3 spikes over the tie are not root corners (r31a): they are the far tiers' very wide tail cards'
corners and two fly cards over the left ear.
NEXT, in order: (0) crown: raise the CAP (hair cap_under_cards / the mass cap over el 60+) and the layer-0 cards together
with CROWN_FILL but keep each card's first ROOT_SEAT stretch seated (w x ss(s / ROOT_SEAT): its root stays under the layer
above) and try CROWN_FILL on the top layer only; a card over el 80 (the whorl) so the dome's top is hair, not the cap's
edge; judge on crown4-style tiles + blind A/B vs ls2. (1) LOD1-3 tie spikes: the far tiers' tail cards are up to 132-200
mm wide: cap a tail card's width (FREE_CLIP x card_width) or split it; drop / shorten the two fly cards over the left ear
(x 0.085). (2) LOD0 tail holes / ragged lower edge, the dark gap at the tie, temples, the part (not started).
bin/review: its CLI works but is single reference | result (no A/B); use it after 2026-10-19 13:00 MT for per-result
LOOK, fresh blind subagents for A/B.

## hair-cards round 32 (2026-10-18, fresh session; Joe: the crown "chopped off at the top" first; then LOD1-3 tail spikes, LOD0)
BEST CARDS FOR EXPORT: b37 (round 30) until a round-32 build beats it.
LODs OK: y (b37).
- (1) CROWN: hair_clumps.CROWN_SEAT (m, opt-in): CROWN_FILL's raise eases in over a card's first CROWN_SEAT from its root,
  so the root ROOT_SEAT seated stays seated (r31: the fill lifted seated roots = the front-corner flaps);
  CROWN_LAYERS (tuple, from the top: (0,) = top layer only). crownr (short of the strands' p99 at el 30-50 / 50-65 /
  65-80; ls2 5.0 / 7.6 / 9.1, r31 c1 fill-all 3.0 / 2.7 / 2.4): FILL 1 + SEAT 0.03 3.9 / 5.6 / 6.6 (worst 7.8 / 18 /
  16); + top layer only 4.2 / 6.3 / 8.4. The top layer over el 65-80 stays at 85.8 mm (p90 94.3) either way: over the
  crown nearly every top card is within its first 3 cm (rooted there), so a seat of ROOT_SEAT's length keeps most of the
  shortfall. No card over el 80 (the cap is the dome's top). STATE: d1 (FILL 1, SEAT 0.03) and d2 (FILL 1, SEAT 0.012)
  running (t31/r31c.sh). NEXT: tiles vs gSc / ls2 / c1; meanwhile (2) the tail-card width at the far tiers.
- (1) r32 d1 (FILL 1, SEAT 0.03) / d2 (FILL 1, SEAT 0.012): crowntop g1v0 deficit 21.3 (ls2) -> 19.5 / 18.3 px, g1v1
  12.6 -> 11.8 / 11.0, ragged unchanged (2.7 / 2.0). Tiles t32/crownz_g1v0.png / crownz_g1v1.png (gSc | ls2 | c1 | d1 |
  d2): LOOK: no corner flaps like c1, but the top is still the same flat, ragged lid as ls2 (d2 a touch fuller): the
  seat keeps most of the shortfall (the crown's top cards are rooted there). STATE: e1 / e2 running = d2 with the seat
  only for cards rooted in front of C (CROWN_SEAT_Y 0 / +0.03 m): crown-rooted cards raised from their root.
- (2) TAIL WIDTH (t32/tailw.py <tier> [hc flags], t32/tw.sh: every station's edges of the tied tail's cards vs b37 LOD0,
  tail cards' full width): base main 159 cards, width max 73 / p90 55 mm, edges past LOD0 > 8 mm 62, > 15 mm 29; npc 85,
  73 / 56, 35 / 20; far 50, 120 / 107, 29 / 22. (r31's "132-200 mm" was the far tier before FREE_CLIP: today only far is
  that wide.) hair_cards.TAIL_SPLIT_CW 1.0 (opt-in: a hanging clump at a coarse tier split by its OUTLINE width, FREE_SPREAD
  sigmas, not 1.7 sigmas): far 72 cards, width 76 / 64, > 15 mm 22 -> 16; main / npc WORSE (more cards, > 8 mm 62 -> 83 /
  35 -> 52), so TAIL_SPLIT_MIN 0.05 (far only). The worst points (27-44 mm) are the same cards (tt17/20/36, dense L0)
  8-12 cm down the tail at every tier, split or not: the lower tiers' tail hangs OUT past LOD0's, not only corners.
- (1) e1 (d2 + CROWN_SEAT_Y 0: seat only cards rooted in front of C) / e2 (SEAT_Y +0.03 = d2 to the decimal): crowntop
  g1v0 17.5 / 18.3 px, g1v1 10.7 / 11.0. Tiles t32/crownz2_g1v*.png (gSc | ls2 | d2 | e1 | e2): all still the flat ragged
  lid; e1 a little fuller, no c1 corner flaps. crownr with CROWN_LOOP 0: still no card over el 80 (not the loop filter).
  FINDING: the very top of the front silhouette (el 80-90 over C) has NO card; the cap there takes the LOWEST nearby
  layer-0 card less CAP_UNDER (the seated roots), a dip between the crown cards = the "chopped" lid. hair.CAP_TOP_EL
  (opt-in, deg): over it a cap vertex with no card over it takes the HIGHEST nearby layer-0 card's height. STATE: f1 (e1
  + CAP_TOP_EL 70) / f2 (55) running; blind A/B e1 vs ls2 (fresh subagent, t32/blind_g1v*.png, key t32/blind_key.json).
- (2) FREE_CLIP 0.8 (LOD1-3 only: the hero is hair_clumps.cut): main / npc tail width 73 -> 45 mm, edges > 15 mm 29 -> 27
  / 20 -> 17: width is NOT the cause. The same cards stand 27-44 mm past LOD0 at every tier and setting: the lower
  tiers' tail hangs on another line than LOD0's (clump_cards' mean line + yo vs cut's TAIL_OUT layers). NEXT for (2):
  overlay LOD0 and LOD1 tail centre lines (side view) before any width change.
- LASHES vs main's thin_strands (r31 merge note): main's game_ready path thins the lashes per LOD by lods.thin_strands
  (LASH_LODS 0.5 / 0.25 / 0.1, whole lashes); ours does the same job in lods.lod_parts(ribbons=) (ribbon_lod: whole
  ribbons by the LOD ratio, widened) + ribbon_fit to the eyes_mouth_lashes cap at LOD0. Nothing else on main calls
  thin_strands (git grep origin/main: asset.py only): no reliance; the ratios differ (ours = the LOD ratio), say so at
  the merge.
- (1) BLIND A/B (fresh subagent; t32/blind_g1v0.png / blind_g1v1.png = gSc | A | B, key t32/blind_key.json: A = ls2,
  B = e1): front A slightly, 3/4 A clearly, OVERALL A (= OLD). e1: a more ragged top outline (small flaps and notches, a
  jagged slab upper left), a hump toward the back at 3/4. Both: dome lower and flatter than the ref, one dark flap upper
  right, pale temple streaks, the part a dark ragged smudge. e1 NOT adopted.
- (1) f1 / f2 (e1 + CAP_TOP_EL 70 / 55): crowntop g1v0 17.0 / 16.9, g1v1 10.5 / 10.4 (e1 17.5 / 10.7); tiles
  t32/crownz3_g1v*.png: no visible change. CAP_TOP_EL stays off.
- (1) CONCLUSION: every lever that moves the existing cards (fill, seat, cap) buys 3-4 of the 21 px and adds a raggeder
  top. What the eye reads as "chopped": the front outline's top is the part's cards seen END-ON (their straight-cut tops
  as slabs and notches) over a low dip at the part, where the groom's strands rise off the part and arch over. NEXT (new
  geometry, not a tweak): a top COVER row: cards laid along the part front-to-back on the strands' p90 envelope, each
  side's cards leaving the part sideways UNDER it (the hairline row's tile: roots that come in one by one), so the
  outline over el 60-90 is a card's long soft edge, not cut ends; measure crowntop + ragged, tiles, A/B vs ls2.

## Handover 2026-10-18 (hair-cards agent, round 32; stopped near the 70-tool-call rule)
BEST CARDS FOR EXPORT: b37 unchanged (exp/exa30b/hc_s2.glb + _LOD1-3). LODs OK: y (b37). All round-32 flags default OFF
(hair defaults at this commit = b37's).
New opt-in flags: hair_clumps.CROWN_SEAT / CROWN_SEAT_Y / CROWN_LAYERS (with r31's CROWN_FILL), hair.CAP_TOP_EL,
hair_cards.TAIL_SPLIT_CW / TAIL_SPLIT_MIN. Scratch t32/: tailw.py + tw.sh <tag> [hc flags] (tail cards' edges vs b37
LOD0, every station, per LOD tier, no export), blind.py <new> <old> (gSc | A | B sheets + key), crownz*/crownz2/3 tiles;
exa26.py now takes tuple flags. Builds: exp/exad1, exad2, exae1, exae2, exaf1, exaf2 (+ lods*, shots out/s_hc_s2_<tag>_*).
Nothing in flight.
VERDICT (look-first): no build beat b37. The crown is still low and flat with a ragged top (crowntop g1v0 21 px short of
gSc, best variant 17); the blind A/B kept ls2 over the best variant (e1). Moving the existing cards is exhausted: the
next step is a top cover row (see the CONCLUSION above). Tail spikes on LOD1-3: width is not the cause (FREE_CLIP 0.8
narrows main / npc tail cards 73 -> 45 mm and barely moves the stand-off); the same tail cards stand 27-44 mm past LOD0
8-12 cm down the tail at every tier: compare the LOD0 / LOD1 tail lines first. LOD0 items (3) not started. Lashes: no
reliance on main's thin_strands (see above).
Coordinator rule noted: never git push; commits are local only.

## hair-cards round 33 (2026-10-18, fresh session; Joe: the crown "chopped off at the top": a new top cover row; then the LOD1-3 tail line)
BEST CARDS FOR EXPORT: b37 unchanged (exp/exa30b/hc_s2.glb + _LOD1-3; no round-33 build beat it).
LODs OK: y (b37; every round-33 flag defaults OFF, so the defaults at this round's last commit = b37's).
- (1) PART COVER ROW (hair_clumps.PART_COVER = cards per side, opt-in, 0 = off; part_cover()): per side of the part, the
  head strands rooted within COVER_REACH 15 mm of it (over PART_EL) split front to back (root y quantiles) into
  PART_COVER runs; each run one card (fit on its strands, cut to COVER_LEN 70 mm), led in from COVER_OVER 2 mm PAST the
  part line (_part_root got a `gap`: the two sides' covers meet, no dip), raised from its root (COVER_SEAT 12 mm) to the
  head strands' envelope less COVER_UNDER 1.5 mm (the strands rise off the part), width tapered over its last half
  (COVER_TAPER) and its picture's alpha faded over the last 45% (COVER_FADE: soft tips on the side cards, its own tile
  group). Top layer, prio top + 0.5, "cover": True. Test: tests/test_hair_clumps.py::test_part_cover_row_arches_over_
  the_part_with_soft_tips (a dome groom with a centre part: rows both sides front to back, roots on the line, tapered
  tips, the part's top 0 -> 80 mm (no head card within 4 mm of the part without it), under the strands). Commit
  81c1de08. STATE: p6 / p10 (PART_COVER 6 / 10) exporting (t33/r33.sh = r31c.sh, crowntop vs ls2 -> t33/crown_<tag>.txt).
- (2) TAIL LINES (t33/tailline.py <glb0> <glbk...> <png>: side + back views of each LOD's hair, the tail's median line per
  1 cm band below the tie, nape excluded (> 125 mm from the head centre), and its back edge p5): b37 (exp/exa30b)
  t33/tailline_b37.png: LOD1 / 2 / 3's median lines lie on LOD0's within about +-5 / +-8 / +-15 mm (LOD3 zigzags: few
  cards) down the whole tail, side and back; the back edge (p5) of LOD1-3 sits 10-35 mm INSIDE LOD0's 21-26 cm below
  the top (LOD0's fan reaches further back and down). FINDING: the lower tiers' tail does NOT hang on another line; r32's
  27-44 mm stand-off (radial from a head centre, nearest-direction max) is single cards' edges / corners, mostly sideways,
  not the tail's line. Nothing changed for (2). NEXT for (2): the standing cards one by one (standoff.py's pieces).
- (1) p6 (PART_COVER 6: 12 cover cards, all kept: head/L2 73 cards) / q97 (8 per side, raised to the strands' p97,
  COVER_PCT): crowntop g1v0 deficit 21.3 (ls2) -> 20.9 / 20.9 px, ragged 2.54 -> 1.67 / 1.67 (gSc 1.32); g1v1 12.6 ->
  12.6. Tiles t33/cz1_g1v*.png (gSc | ls2 | p6): no visible change. The GLB's hair top near x = 0 rose 1.6472 -> 1.6556
  m (+8.4 mm, b37 exa30b vs p6), the front render's top 0 px. FINDING (the real cause of "chopped"): a card lying
  tangent at the top of the dome is seen EDGE-ON from the front; raising it adds nothing to the front outline. Whatever
  the outline's top is there is a card that stands up (the part cards' ends), hence the slabs and notches. The groom's
  round strands have no edge-on. NEXT: COVER_TILT (deg): the cover card's across direction turned toward the head's
  outward radial (its width reads as height from the front, the upper edge its soft tapered / faded side;
  COVER_SINK 0.5 x hw sin(tilt) moved in so the lower edge tucks into the mass). STATE: t60 (8 / side, tilt 60) / t80
  (tilt 80, p97) queued after q99 (t33/q3.sh).
- (1) q99 (8 / side, p99, COVER_UNDER 0) / t60 (8 / side, COVER_TILT 60): crowntop g1v0 20.9 / 20.9 px, ragged 1.67,
  g1v1 12.6, g1v2 10.1: the SAME numbers as p6 / q97 to the decimal. Tiles t33/cz3_g1v*.png (gSc | ls2 | q97 | t60): no
  change at the outline. Pixel diff q97 vs t60 g1v0: bbox (473, 358)-(639, 549), i.e. only BELOW the outline's top (365):
  the covers change the front hairline / part area, never the crown's top line. FINDING: the front outline's top is not
  over the part at all; it is the crown BEHIND the part (where the hair sweeps straight back to the tie, no part, cards
  running front to back seen end-on from the front: their cut cross-sections are the lid's edge). The cover row (roots
  within 15 mm of the strands' part, which only exists where top roots sweep sideways: the front of the head) cannot
  reach it. r32's "the part's cards seen end-on" was the wrong place.
- (1) (r33 p10 = PART_COVER 10 was killed by the assembly agent's `kill -9 hv.py` at 17:41 (coordinator's note); not
  re-run: superseded by q97 / t60.) No A/B: no tile shows a visible change, nothing to put in front of a reviewer.
- (2) see above: the tail lines agree; nothing changed. (3) not started.

## Handover 2026-10-18 (hair-cards agent, round 33; stopped near the 70-tool-call rule)
BEST CARDS FOR EXPORT: b37 unchanged (exp/exa30b/hc_s2.glb + _LOD1-3). LODs OK: y (b37). All round-33 flags default OFF.
New opt-in code: hair_clumps.part_cover() + PART_COVER / COVER_REACH / COVER_LEN / COVER_HW / COVER_TAPER / COVER_FADE
(own tile group, tip alpha fade) / COVER_OVER / COVER_SEAT / COVER_UNDER / COVER_DRAW / COVER_PCT / COVER_TILT /
COVER_SINK; hair._part_root(gap=); hair.COVER_TIERS {tier: share} (the cover at main / npc / far on the tiles, fewer and
wider: NOT yet run). Test test_part_cover_row_arches_over_the_part_with_soft_tips. Scratch t33/: r33.sh <tag> [flags]
(r31c.sh -> t33/crown_<tag>.txt), tile.py <tags> <out> <views>, tailline.py (LOD tail lines). exa26.py takes dict
flags for hh.*. Builds exp/exap6, exaq97, exaq99, exat60 (t80 was queued, then stopped: nothing in flight). 
VERDICT (look-first): the crown is unchanged: still the low flat lid, 21 px short of gSc from the front. The cover row
works as built (8 mm higher mesh at the part, ragged 2.5 -> 1.7 px from the front) but the part is not where the outline's
top is. NEXT for the crown: measure WHICH cards form the front outline's top (ID-render or project each card's
stations and take the topmost per column), expected = the crown cards behind the part running back to the tie, seen
end-on. Then the same idea moved there: cards standing up (COVER_TILT-like, across direction toward the outward radial)
along the crown's ridge from the part's back end to the tie, or a crown ridge cover generalised from part_cover (strands
rooted along the top ridge line instead of the part). Tail LOD stand-off: single cards (standoff.py pieces), not the line.

## hair-cards round 34 (2026-10-18, fresh session; Joe: the crown "chopped off at the top": measure which cards form the front outline's top, then layer like an artist)
BEST CARDS FOR EXPORT: b37 unchanged until a round-34 build beats it. LODs OK: y (b37).
- (1) CARD-ID PASS (scratch t34/cardid.py <glb> <frames tag> view= layers=<hc_s2_hair.json> out=: no render; every hair
  triangle sampled 16x16 where baseColor alpha > 0.5, projected in shots' frame, z-buffered; per column of crowntop's
  columns (groom top in its upper 45%) the card owning the outline's top pixel; per card layer, root (mm from C), root ->
  tip direction, where along it (s, arc length on its centre line) the outline sits). b37 = exp/hx34b37 (hx.py hero,
  23844 tris = b37's LOD0 hair to the triangle; ID top vs the ls2 render top: median 1 px). t34/id_b37.txt,
  t34/id_b37_g1v0.png / g1v1.png (outline cards coloured, red = our top line, blue = gSc's).
  FRONT g1v0 (212 cols): the CAP 25% (52 cols, the middle of the top: no card above it there), layer2 44%, layer0 22%,
  layer1 5%, layer3 4%. The cards: crown cards rooted at el 60-64, 2-4 cm in front of C, x +-27..37 mm (190, 138, 139, 48,
  125, 53, 126) running straight BACK and down to the tie (dir ~(+-0.1..0.46, +0.86, -0.48)), seen from the front at
  s 0.1-0.3 = 20-60 mm from their ROOT; plus 137 / 4 (rooted el 48, 5 cm in front) at s 0.02-0.2. Outline columns by
  place on their card: root end (s < 0.2) 45%, body 30%, the rest the cap. 3/4 g1v1: root end 21%, body 63%.
  So from the front the top is the scalp cap plus the root ends of crown cards that START on the top of the dome (at
  el 60-70) and leave it backwards: nothing arches over from in front. The groom's strands that cross the top are
  rooted further forward and stand ~20 px (2 cm) higher there.
  STATE: hair_clumps.ARCH (opt-in, cards; arch_row(): head strands whose path reaches ARCH_EL 70 deg with the root in
  front of that top station, split by its x into ARCH runs; a card each from ARCH_START 3 cm past the roots (its start in
  the mass, under the front layers) to ARCH_PAST 7 cm past its top, raised to the strands' p97 envelope (ARCH_PCT) less
  1 mm over ARCH_SEAT 4 cm, tapered + faded tip ("cover": the cover row's tile group)). a10 (ARCH 10) exporting
  (t34/r34.sh = r33.sh). NEXT: card-ID + crowntop + tiles of a10.
- (2) a10 (ARCH 10, first selection: strands CROSSING el 70 with the root in front): "0 strands cross the top". The
  groom's own outline top (t34/strtop.py: head strands projected in g1v0, topmost per column): strands ROOTED near the
  centre line (root x -10..+10 mm, el 62-73, root y 2-3.5 cm in front of C), the outline at their stations 6-12 (24-48 mm
  from the root), standing 17-22 mm above their root's radius; they rise off the scalp, then run back. Our cards leave
  that strip empty (crown cards rooted at x +-27..37: PART_GAP) and seat their roots: the cap is the outline there.
  ARCH reworked: head strands rooted over ARCH_EL 55 within ARCH_X 3 cm of the centre line, ARCH_ROWS 2 by root y, then
  ARCH runs by root x; card from the root to ARCH_LEN 9 cm, raised to p97 over ARCH_SEAT 2 cm. Offline (t34/archq.py on
  the strand dump): 8 cards, their front-view tops 354-367 px vs the groom's strands 353 (b37's cards 365).
- (2) a4 (ARCH 4 = 8 cards, 192 tris): crowntop g1v0 20.9 / ragged 1.64, g1v1 12.6: the SAME as q97; render diff only
  below y 382; card-ID: the outline cards unchanged. The 8 arch cards ARE in the GLB (z up to 95 mm over C, higher than
  any other card) but their atlas tile is EMPTY (alpha 0: t34/atlas_a4_crop.png). Cause (bake): a strand is drawn on a
  card only if IN_SHARE of ALL its points fall inside the card; a 9 cm card over 30 cm strands never passes. FIX: arch
  cards count the share over the card's own length (al <= L), bake on the fitted line (P_fit, before the raise), runs
  split by sweep side (+x / -x / back: a run mixing both sides left its strands 3-4 cm across the card). Offline bake:
  tiles 0 -> 24% of a 512 atlas opaque. SUSPECT: r33's part cover (COVER_LEN 7 cm on long strands) had the same empty
  tiles, so r33's "no visible change" may say nothing about the cover row's idea.
  STATE: b4 (ARCH 4 with the fix, 17 cards) exporting. NEXT: card-ID + crowntop + tiles.
- (2) b4 (ARCH 4 with the fix: 17 arch cards): crowntop g1v0 deficit 21.3 -> 11.9 px (area 4517 -> 2531), top 365 -> 353
  (gSc 346), ragged 2.54 -> 1.83 (gSc 1.32); g1v1 12.6 -> 7.6; g1v2 10.0 -> 7.0. FIRST round to move the front outline.
  Tiles t34/cz_b4_g1v0.png / g1v1 (gSc | ls2 | b4), cz_b4s_g1v2 (gSc | a4 (= b37 look) | b4). LOOK: the top is higher
  but reads as a separate CREST on the dome: chunky ragged lumps with background showing through at the upper left
  (front), and at 3/4 a raised hump / loop over the forehead with daylight under it: the arch at p97 stands off the
  cards below it (they stay at <= p90), so from the side there is a gap. Not adoptable as is.
  STATE: c1 (ARCH_PCT 90, ARCH_SEAT 3.5 cm, COVER_DRAW 1.0 (only the arch uses it: PART_COVER off), ARCH_HW 18 mm) and c2
  (same, ARCH_PCT 94) queued (t34/q3.log). NEXT: crowntop + tiles; A/B the better vs ls2.
- (2) c1 (ARCH_PCT 90, SEAT 3.5 cm, COVER_DRAW 1.0, ARCH_HW 18 mm) / c2 (same, PCT 94): crowntop g1v0 13.1 / 12.6 px
  (ragged 2.64 / 2.71), g1v1 8.1 / 7.7, g1v2 7.4 / 7.1 (b4 11.9 / 7.6 / 7.0; b37 21.3 / 12.6 / 10.0). Tiles
  t34/cz_c1_g1v*.png (gSc | ls2 | b4 | c1), cz_c2_*: c1 / c2 fuller and with fewer holes than b4 from the front; at 3/4
  still a hump / flap over the forehead with background through it (the front row's arch cards rise steeply off their
  roots, nothing under them from the side).
- (3) COORDINATOR'S ONE_NORMAL CHECK (Garrett c5: black crown shards were the back-face normal flip): cherry-picked
  blender_cards.ONE_NORMAL (75b2c6fb, commit here; default 1 = on) and re-shot b37 (n37), c1 (nc1), c2 (nc2) with it.
  crowntop identical to the decimal (the outline is geometry + alpha, not shading). Dark (< 45) px in the head box: front
  1592 -> 1548 (b37), 2343 -> 2048 (c1); 3/4 2515 -> 4131, back 2316 -> 2795 (MORE); tiles t34/on_g1v*.png (ls2 | n37 | c1 |
  nc1): no visible change. On Tess the dark slabs / ragged crown edge are NOT the back-face flip.
- (2) BLIND A/B (fresh subagent, t34/blind/sheet_front.png / sheet_34.png = gSc | A | B, key t34/blind_key.json: A = n37
  (b37), B = nc2): front B "only just" (dome nearly as high, rounder; but a raised crest, a spiky lump upper left, a white
  gap upper right); 3/4 A clearly (B: a bunched hump / flap at the front of the crown, ridged crest, background stripes);
  OVERALL A (= OLD). ARCH not adopted.

## Handover 2026-10-18 (hair-cards agent, round 34; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: b37 unchanged (exp/exa30b/hc_s2.glb + _LOD1-3). LODs OK: y (b37). hair_clumps.ARCH defaults 0
(off), so the defaults at this commit = b37's cards; blender_cards.ONE_NORMAL (cherry-picked) is on for renders.
New: t34/cardid.py (card-ID pass of the outline: which cards, layer, root, direction, s along), t34/strtop.py (which groom
strands make the outline), t34/archq.py / archbake.py (arch cards + their tiles offline, no export), t34/r34.sh (export +
shots + crowntop), t34/shoot.sh <tag> <glb> (shots + crowntop only). Builds exp/exaa4 (empty tiles), exab4, exac1, exac2.
Nothing in flight.
FINDINGS: the front outline's top was the scalp CAP (middle 25%) and the ROOT ends of crown cards starting at el 60-70 off
the centre strip; the groom's top is strands rooted in that strip standing 2 cm off the scalp. The arch row (cards on
those strands, raised to their envelope) is the FIRST change to move the front outline (21 -> 12.6 px deficit) but it
reads as a crest / hump with see-through gaps, and the blind A/B kept b37. Also a bake bug fixed for arch cards: a card
shorter than its strands got an EMPTY tile (IN_SHARE over the whole strand); r33's part cover (7 cm on long strands)
very likely had the same empty tiles, so its "no visible change" was not a test of the idea.
LODs: ARCH is hero-only (LOD1-3 = b37's to the triangle; LOD0 +408 tris): adopting it needs the arch at the tiers too,
or the crown drops at the LOD0 -> LOD1 switch.
NEXT (what would fix it, no more tweaks of these knobs): the crest comes from a thin row of cards standing alone above
cards that stay low. Lift the mass UNDER it with it: the crown cards' roots in the strip (PART_GAP lets them start at
x +-27) and the cap raised to the same envelope over the strip, so the arch lies ON hair, not over air; and the arch's
front row seated longer (its root under the hairline layer). Alternatively hand-placed hero cards along the crown
(artist practice), which our tools can't author yet: a spec list of card paths over the dome would be the general tool.
Re-test the part cover with the tile fix before discarding it.

## hair-cards round 35 (2026-10-18, fresh session; coordinator: FILL THE MASS UNDER THE ARCH as one change, carried to LOD1-3; re-test the part cover)
BEST CARDS FOR EXPORT: b37 unchanged until a round-35 build beats it. LODs OK: y (b37).
- (1) CODE (all opt-in, defaults = b37): hair_clumps.FILL (needs ARCH): (a) a head card whose first PART_REACH runs
  BACK (x share < PART_SIDEWAYS: no visible part behind the front) keeps its root: no PART_GAP cut, no part lead-in, so
  crown cards root in the centre strip like the groom's top strands (diagnostic print "fill: N head cards keep ...");
  (b) hair.cap_fill_arch: after the cap's relax, cap vertices under arch cards raised to the arch surface's height
  (gaussian-weighted, CAP_REACH) less FILL_UNDER 4 mm, eased out to nothing at FILL_REACH 8 deg (only raised);
  (c) the arch's front row (ARCH_ROWS row 0) rises over ARCH_SEAT_FRONT 5 cm (its root at its strands' own height,
  under the hairline layer, longer). hair.ARCH_TIERS {tier: share}: arch_row at main / npc / far with fewer, wider
  cards (COVER_TIERS-style), and the cap fill applies there too. Part cover: P_fit + bake share over its own length
  (r34's arch tile fix, now for the cover). Tests pass (test_hair_clumps 16).
  STATE: f1 (= r34 c2 + FILL + ARCH_TIERS {main 0.6, npc 0.4, far 0.25}) then pc6 (PART_COVER 6 alone) exporting
  (t35/q1.sh -> t35/r35.sh = r34.sh, crowntop vs ls2 -> t35/crown_<tag>.txt). NEXT: crowntop, tiles, LOD tiles, A/B.
- (2) f1 (exp/exaf1): "fill: 88 head cards keep their back-running roots (8 within 15 mm of the centre line)"; cap fill
  raised 698 cap vertices (max 18.6 mm) at LOD0, 978 / 407 / ... at main / npc / far; arch cards at tiers 10 / 10 / 5.
  Hair triangles LOD0 24246, LOD1 12478, LOD2 8248, LOD3 2498. crowntop g1v0 deficit 12.4 px (b37 21.3, c2 12.6), ragged
  1.86 (b37 2.54, c2 2.71, gSc 1.32); g1v1 7.9 (b37 12.6, c2 7.7); g1v2 7.3 (c2 7.1). The outline is c2's; the change is
  UNDER it. Tiles t35/cz_f1_g1v*.png (gSc | n37 = b37 | nc2 = c2 | f1), zoom t35/zz_f1_g1v1.png. LOOK: the 3/4 daylight
  under the arch is gone (the crown reads as one rounded mass, higher than b37); from the front a fuller, higher dome.
  Left: a small blocky ridged lump at the front of the crown at 3/4 (the front arch row's root ends seen end-on).
  BLIND A/B (bin/review-ab ran, but its claude -p hit the weekly limit ("resets 1pm"); its trios t35/ab1/trio_*.png
  went to a fresh blind subagent, key t35/ab1/key.json): front NEW (crown height / fullness much closer; old: low flat
  crown, lumpy crests), 3/4 NEW ("crown height and fullness nearer the reference"; its MAJOR: a blocky lump at the
  front of the crown), OVERALL NEW. STATE: LOD sheet of f1 (t35/lods.sh -> t35/lods_f1.png) and pc6 running; f2 (= f1 +
  ARCH_START 25 mm: the arch's root ends start inside the mass, against the front lump) queued. NEXT: LODs, then adopt.
- (3) LODs f1: t35/lods_f1.png (LOD0 | LOD1 | LOD2 | LOD3 at g2 / g4 / g8, 3/4 and front; t35/lods.sh): the crown keeps
  its height and round top at every tier (ARCH_TIERS + cap fill), no drop at LOD0 -> LOD1; the same hairdo at each switch
  distance. Minor: LOD2 at g2 3/4 shows a few light streaks over the crown (LOD2 is not shown at 2 m); LOD3 tail tips
  as before. LODs OK: y.
- (4) PART COVER RE-TEST with the tile fix (pc6 = PART_COVER 6 alone on b37's defaults, exp/exapc6, 12 cover cards):
  crowntop g1v0 deficit 21.3 -> 14.4 px (top 365 -> 353), ragged 2.54 -> 2.04; g1v1 12.6 -> 8.5; g1v2 7.8. So r33's "no
  change" WAS the empty-tile bug: the cover row does lift the outline once its tiles carry hair. LOOK (t35/cz_pc6_g1v*.png,
  gSc | n37 | pc6 | f1): the covers stand as separate spiky flaps over the part with background between them, front and
  3/4: worse than f1, no fill under them. Not adopted (no A/B: f1 is clearly better on the tile; a cover row would need
  the same fill under it).
- (5) f2 (= f1 + ARCH_START 25 mm, against the 3/4 front lump): the queued waiter never ran it, and the tag "f2" already
  had another round's 17:26 shots in out/ (tag collision: check `ls out | grep _<tag>_` before naming). Re-run as h2
  (exp/exah2, t35/q3.log). STATE: h2 exporting. NEXT: crowntop + tile vs f1; keep f1 unless h2's lump is gone on the tile.
- (5) h2 (f1 + ARCH_START 25 mm): crowntop g1v0 14.4 px (f1 12.4), ragged 2.75, g1v1 8.8, g1v2 7.7; tile t35/cz_h2_g1v*.png:
  the 3/4 front lump is smaller but the top is lower with a small see-through notch. Not better than f1.
- (6) ADOPTING f1 AS DEFAULTS tried and backed out: with FILL = 1 by default, tests/test_hair_clumps.py::
  test_no_card_spans_the_part fails (FILL (a) lets a back-running root keep its root on the test dome's part line, so a
  card spans the part). Defaults left = b37 (all round-35 flags opt-in). Fix before adopting: apply FILL (a) only where
  the strand part has no voters near the root (side_of distance inf, i.e. behind the part's back end), or only above
  the part's back end in y; then re-run the test and f1.

## Handover 2026-10-18 (hair-cards agent, round 35; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: f1 = exp/exaf1/hc_s2.glb (+ _LOD1-3), flags: hk.ARCH=4 hk.ARCH_PCT=94 hk.ARCH_SEAT=0.035
hk.COVER_DRAW=1.0 hk.ARCH_HW=0.018 hk.FILL=1 hh.ARCH_TIERS={"main":0.6,"npc":0.4,"far":0.25} (exa26.py, as t35/q1.sh).
Blind A/B vs b37: NEW front + 3/4 + overall. LODs OK: y (t35/lods_f1.png). NOT yet approved (bin/approve: coordinator /
Joe), and NOT the code defaults (defaults = b37: see (6)).
Numbers (front / 3/4 / side crowntop deficit px; gSc = 0): b37 21.3 / 12.6 / 10.0, c2 12.6 / 7.7 / 7.1, f1 12.4 / 7.9 / 7.3,
pc6 14.4 / 8.5 / 7.8, h2 14.4 / 8.8 / 7.7. Ragged front: b37 2.54, f1 1.86, gSc 1.32.
VERDICT (look-first): f1 is the first crown that beats b37: one rounded, higher mass, no daylight under the arch; left:
a small blocky ridged lump at the front of the crown at 3/4 (the front arch row's root ends end-on), and the outline is
still ~12 px under gSc's from the front. Part cover with working tiles moves the outline too but stands as flaps.
NEXT: (1) make FILL (a) part-safe (see (6)) and adopt f1 as defaults; (2) the front lump: the front arch row's first
cm faded in alpha (COVER_FADE-like at the root) or its root tucked under the hairline layer by an offset, not ARCH_START
(h2 lowered the top); (3) for the remaining 12 px, hand-placed hero cards over the dome (a spec list of card paths)
remain the general tool. Nothing in flight. Scratch t35/: r35.sh, lods.sh, q1.sh, cz_*/zz_* tiles, ab1/ (trios + key).

## hair-cards round 36 (2026-10-18, fresh session; coordinator: f1 part-safe + defaults, the 3/4 front lump, the white crown patch, engine-proof back faces)
BEST CARDS FOR EXPORT: f1 (round 35) until r36d (= the new defaults) is checked against it. LODs OK: y (f1).
- (1) FOUND: round 35's flag `hair_clumps.FILL = 0` was shadowed by the bake's `FILL = 0.82` (packing share) further
  down the module, so FILL (a) (+ cap fill, front-row rise) was ON in every default build since round 35's commit, and
  `hk.FILL=1` in f1 / h2 ALSO set the atlas packing share to 1.0. Renamed `ARCH_FILL`. The part test's failure was not
  FILL (a) (it passes either way on the test dome) but the ARCH row: its runs grouped by sweep (+x / -x / back) took
  strands from both sides of the part. PART-SAFE (round 36): `arch_row(side_of=)` (cut and hair.py's LOD tiers pass it):
  strands whose root has a finite part distance (in front of the part's back end) group by their side, are dropped
  within PART_GAP of the part or sweeping across it; behind the back end (distance inf) the centre strip is used as one,
  as before; ARCH_FILL (a) keeps a root only where side_of's distance is inf. DEFAULTS = f1: ARCH 4, ARCH_PCT 94,
  ARCH_SEAT 0.035, ARCH_HW 0.018, COVER_DRAW 1.0, ARCH_FILL 1, hair.ARCH_TIERS {main 0.6, npc 0.4, far 0.25} (packing
  FILL stays 0.82). test_part_cover_row... sets ARCH 0 (arch cards are "cover" too). Hair tests: 155 passed.
  STATE: r36d (defaults, no flags) exporting (t36/r36.sh). NEXT: crowntop + tile vs f1 (same read = adopt as best).
- (2) r36d (defaults after (1), no flags; exp/exar36d): "arch row: 1032 strands in front of the part's back end (605 at or
  across the part dropped)", 501 -> 15 cards (f1 1106 -> 17); cap fill 475 vertices (f1 698). On Tess the strand part's
  voters reach along nearly the whole centre strip, so "behind the back end" is almost nothing. crowntop front / 3/4 /
  side: 15.6 / 9.4 / 7.7 px (f1 12.4 / 7.9 / 7.3, b37 21.3 / 12.6 / 10.0). LOOK (t36/cz_r36d_g1v*.png, zz_r36d_g1v0.png:
  gSc | f1 | r36d): 3/4 the blocky front lump is GONE (those were the centre strands), but from the front a V notch at
  the part between two lumpy humps; the groom's part is a soft line with no notch in the outline. Worse than f1 front.
  CHANGE: ARCH_PART_KEEP (default 0): in front of the back end strands by the part are KEPT (grouped by side, never
  sweeping across), and each such card STARTS PART_GAP off the part (its first points cut, as the head cards are): no card
  spans or roots on the part, the dome beside the part is kept. ARCH_ROOT_TAPER (step 2, default 0 until tested): the front
  row's root end narrows to a point over it (TIP_FLOOR .. 1, smoothstep), against the end-on square root ends = the lump.
  Tests pass. STATE: r36e (defaults) then r36f (+ ARCH_ROOT_TAPER 0.025) exporting (t36/q1.sh). NEXT: crowntop + tiles vs
  f1, A/B.
- (4 prep) hair-heads2 merged + r59's crown fix (a7618d2d) cherry-picked on a side branch `r36-merge` (worktree
  /mnt/data/hifipushie/haircards/mergewt; not into this worktree yet: builds were running on its code). Conflicts: hair.py
  cap (even-cap floor, then cap_fill_arch), blender_cards (GLTF_SPEC block), tests (both), notes (both). With BACK_FACES the
  tier report's "triangles" counted the backs (test_export_tier_as_an_engine_gets_it: 10568 > npc 8250): now "triangles" =
  card faces (the budgets' unit; doubleSided rasterised both sides too) and "index_triangles" = with the backs. All 161 hair
  tests pass there (env -u PYTHONPATH: env.sh's PYTHONPATH points at THIS worktree's src).
- (3) r36e (defaults: strands by the part kept, cards start PART_GAP 6 mm off it, runs by side): crowntop 16.8 / 9.9 / 8.3
  px; r36f (+ ARCH_ROOT_TAPER 0.025): 17.4 / 10.4 / 8.5 (f1 12.4 / 7.9 / 7.3). LOOK (t36/zz_r36f.png: gSc | f1 | r36e |
  r36f, front row, 3/4 row): both keep the V NOTCH at the part from the front (the side-grouped cards bend away from the
  part: it is the grouping, not the 6 mm gap); at 3/4 the front lump is back in r36e, r36f's taper makes it a smaller,
  softer nub (the taper works on the lump; keep it as a lever). Neither beats f1. CHANGE (default): in front of the back
  end a run per side AND sweep (back-running strands by the part get their own run on each side) -> r36g exporting (t36/q2.sh).
- (5) WHITE CROWN (step 3): named by the assembly r59 (game_ready.md "## r59"): the HAIR material, not the cap mesh: card ORM
  roughness 0.425 under its own floor + the character GLB's default white specular. Its fix (hair.CARD_ROUGH_MIN 0.6,
  CARD_SPECULAR 0.5 x the sheen tint, blender_game reads it) is cherry-picked onto `r36-merge` (8cd7815b), so Tess's cards
  get it here too; no second fix needed. Not re-rendered under the game rig in this round (the assembly owns rc2j).

## Handover 2026-10-18 (hair-cards agent, round 36; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: f1 unchanged = exp/exaf1/hc_s2.glb (+ _LOD1-3), built with round 35's flags (exa26.py as t35/q1.sh).
LODs OK: y (f1). NOTE f1's `hk.FILL=1` ALSO set the bake's packing share to 1.0 (the name collision, (1)), and f1's arch
spans the part, which the code no longer does: f1 is reproducible only from round 35's commit 8e8ba6b4 with its flags.
DEFAULTS at this commit: f1's values (ARCH 4, PCT 94, SEAT .035, HW .018, COVER_DRAW 1, ARCH_FILL 1, ARCH_TIERS) + the
part-safe arch (test_no_card_spans_the_part passes; all hair tests green). They do NOT yet read as well as f1 from the front
(V notch at the part: r36d / r36e / r36f). r36g (side + sweep runs) was exporting at handover: t36/crown_r36g.txt +
`python3 t36/zz.py r36g gSc f1 r36e r36g` -> t36/zz_r36g.png. If r36g closes the notch: A/B vs f1 (bin/review-ab makes the
trios; its claude -p works after 2026-10-19 13:00 MT, else a fresh blind subagent), then LOD sheet (t35/lods.sh).
If not: the honest options are (a) a centre-line run that is allowed over the part only where the groom's own outline has
no dip (measure the groom's top dip at the part, gSc shows a soft one), or (b) ask the coordinator whether the part test's
rule should hold for the top cover row (f1 spanned the part and read better; the groom's part is a line under fuzz).
MERGED at the end of round 36 (git merge r36-merge; the side worktree can go): branch `r36-merge` (worktree /mnt/data/hifipushie/haircards/mergewt) = round-36 step 1 +
merge of hair-heads2 (BACK_FACES etc.) + r59's crown fix; 161 hair tests pass there. Bring it in with
`git merge r36-merge` once no build runs here (conflicts: hair.md only, both appended), re-run tests, then
`git worktree remove /mnt/data/hifipushie/haircards/mergewt`.
r36g (runs per side and sweep, default now): 16.5 / 9.8 / 7.9 px; t36/zz_r36g.png: the notch a little smaller, one stray
flick at the top right; still under f1 from the front. NOT A/B'd (none of r36d-g is a candidate over f1).
VERDICT (look-first): no round-36 build beats f1. The part-safe rule costs the front read (V notch); the root taper softens
the 3/4 lump (r36f) but does not remove it.

## hair-cards round 37 (2026-10-18, fresh session; coordinator: the cover row may span the part where the SOURCE groom shows none)
BEST CARDS FOR EXPORT: r37c (see the round-37 handover; = f1 at 98 % under the current code). LODs OK: not re-checked (f1: y).
- (1) RULE (coordinator, r36's question: YES): cards are judged against their source; Tess's groom shows the part as a soft
  line with no dip, so f1 was right to span it. test_no_card_spans_the_part REPLACED by
  test_no_card_spans_a_part_the_groom_shows (the test groom's bare part line: a measured gap -> no card spans or roots on
  it) + test_cover_row_may_span_a_part_the_groom_does_not_show (a lock combed straight back over the part: no dip -> an
  arch card takes strands from both sides; with PART_VISIBLE 0, the round-36 rule, it doesn't). CODE: hair_clumps.
  part_visible(St, C, side_of) = side_of with distance inf wherever the groom's OUTLINE seen along the part has no notch
  there: one view (up = the mean radial direction of the part-line roots, across = x in that plane), the highest head
  strand point per 2 mm band across (PART_DIP_R); shown = the outline at the part line PART_DIP 3 mm under its height
  PART_DIP_W 12 mm either side, or an empty band over the part line with hair beside (a gap); unmeasurable counts as
  shown. PART_VISIBLE 1 (default) passes it to the arch row (cut + hair.py's LOD tiers) and to ARCH_FILL (a)'s kept roots;
  head cards' PART_GAP cut and side grouping keep the full part. With no shown part over the strip the arch row is round
  35's code path exactly (one strip, runs by sweep -1/0/+1; the per-side start cut never fires) = f1. cut prints "part
  visible: n of m roots on the part show a >= 3 mm notch". PART_DUMP (path) saves the head strands + part for probes.
  MEASURED FIRST (t37/dipprobe.py on t37/tess_part.npz), and why it is the outline, not the surface: Tess's groom SURFACE
  does dip at the part: p90-radius of strand points within 4 mm, vs 12 mm either side: p50 4.0 / p90 11 mm, by root y
  front -> back 3.2 / 4.3 / 4.2 / 4.0 / 4.3 mm, = 0.5 of the hair's depth there (0.72 at the front). A 3 mm surface rule
  (r37a, killed) flagged 640 of 1271 part roots, arch row 31 cards (f1 17). Her OUTLINE along the part: notch p50 -0.5 /
  max 2.0 mm, none >= 3 mm (the crown behind the part stands higher): the coordinator's read (gSc: a soft line, no dip).
  OPEN for the coordinator: the rule reads the outline; a surface trough of ~half the hair's depth along the front half
  of the part is real in the groom (seen from above / 3/4 as a line). If that should count, the cover row must keep off
  the front half of Tess's part (r36's V notch comes back).
  r37a (this rule, first form): "part visible: 128 of 1302 roots", arch row 69 strands "in front", 19 cards (f1 17), fill
  83 (f1 88): NOT f1. Cause: the notch was read at root - side x distance, but side_of's distance is half the gap between
  the two sides' nearest roots, not a length to step: from arch roots 2-3 cm off the part it landed beside it. FIX: the
  notch is computed once per part-line root (distance < PART_GAP) and a query takes its nearest part-line root's
  (t37/notchprobe.py on the dump: 0 of 1129 part roots >= 3 mm, p50 1.2 / p90 2.6). r37a / r37b killed. All 162 hair
  tests green (before the fix; clumps + lods 26 green after).
  STATE: r37c = defaults + hk.FILL=1 (the packing share f1's flag also set), then r37d (+ ARCH_ROOT_TAPER 0.025),
  exporting (t37/q1.sh). NEXT: r37c vs f1 (t37/glbcmp.py: unique verts / tris; crowntop), then review-ab f1 vs r37d.
- (2) r37c (= the defaults at 2af333de + hk.FILL=1; exp/exar37c, exp/lodsr37c): "part visible: 133 of 1302 roots" (p90
  4.7 mm: a few head part roots still read a notch), arch row 41 strands "in front", 18 cards (f1 17), fill 86 (f1 88).
  glbcmp vs f1 LOD0 hair: unique verts 52622 shared of 53675 / 53699, unique tris 75383 of 77248 / 77270 (98 %; the
  extra 20k index tris = BACK_FACES from the merge). crowntop front / 3/4 / side 12.4 / 7.7 / 7.0 px (f1 12.4 / 7.9 /
  7.3). LOOK (t37/zz_r37c.png: gSc | f1 | r37c): r37c reads as f1: one rounded crown, the soft dip at the part like the
  groom's, no V notch; a slightly lower step at the top left from the front; the 3/4 front lump is still there (both).
  = f1 reproduced to 98 %, not bit-exact. STATE: r37d (+ ARCH_ROOT_TAPER 0.025) exporting at handover (t37/q1.sh).

## Handover 2026-10-18 (hair-cards agent, round 37; stopped at the 70-tool-call rule)
BEST CARDS FOR EXPORT: r37c = the hair defaults at commit 2af333de + hk.FILL=1 (exa26.py; t37/r37.sh r37c hk.FILL=1):
exp/exar37c/hc_s2.glb (+ _LOD1-3). Reads as f1 (98 % same geometry, crowntop equal or better) and is built by the
CURRENT code under the source rule, with the merge's BACK_FACES + crown roughness fix. EXPORT SETTINGS: hair defaults +
hair_clumps.FILL = 1.0 (the bake's packing share; f1 had it through the old name collision; 0.82 default). LODs OK: NOT
re-checked for r37c (run t35/lods.sh on it); f1's were y and r37c's tiers come from the same ARCH_TIERS. NOT approved.
TEST: test_no_card_spans_the_part replaced by test_no_card_spans_a_part_the_groom_shows +
test_cover_row_may_span_a_part_the_groom_does_not_show; 162 hair tests green at a0a999f4, clumps + lods green at 2af333de
(run the full hair set once more).
OPEN (coordinator): the rule reads the groom's OUTLINE along the part (no notch on Tess); her groom's SURFACE has a real
trough at the front half of the part (~4 mm, half the hair's depth). If the surface should count, the front half
goes back to r36's V notch.
NEXT: (a) r37d (taper on r37c) finishes on its own: t37/crown_r37d.txt, out/s_hc_s2_r37d_*; tiles `python3 t37/zz.py r37d gSc
r37c r37d`; A/B: `python3 t37/crops.py t37/ab r37c r37d gSc`, then `/mnt/data/hifipushie/bin/review-ab t37/ab1
front=t37/ab/gSc_g1v0.png:t37/ab/r37c_g1v0.png:t37/ab/r37d_g1v0.png tq=..._g1v1 side=..._g1v2 --context "game hair cards
vs their source strand groom" --stage "the crown cards' read vs the groom"` (CLI works after 2026-10-19 13:00 MT; else a
fresh blind subagent). Lump A/B NOT done this round. (b) bit-exact f1: the ~130 part roots that still read a >= 3 mm notch
in the run (the probe on the head-only dump reads none; the run's "up" or roots differ: compare f.view). (c) front deficit
12 px only after (a).

## Garrett cards c1 (2026-10-18, hair-garrett agent; coordinator: strand groom frozen at G88a, game hair = cards from it)
- (1) MERGE: worktree-agent-a54a66de6d6970c0b (hair-cards rounds 6-28: hair_clumps, share_atlas, ribbon_lod, ROOT_SEAT)
  into hair-heads2 (9cd3eb4f). Code auto-merged (hair.py, hair_strands.py, asset.py, lods.py ...); the ONLY conflict was
  this file (both threads appended sections after the common base): both kept, garrett sections first. Tests after the
  merge: test_hair_lods / clumps 17 passed, loose / strands / flow / lift / ear 103 passed.
- (2) Ponytail-specific knobs, read: classify() gives "tail" only to free locks (free > 0.5): a loose groom has no tail
  cards, so TAIL_TONE / TONE_CONTRAST_TAIL / TAIL_ROOT_LIFT / TIP_FADE_TAIL / TAIL_END / MEDOID_TAIL and PCA_FRAME
  (hanging cards) don't act on Garrett. Tess-calibrated knobs that DO act on head cards: TONE_FRONT / TONE_BACK 0.85,
  NAPE_LIFT 0.8 (nape head cards x 1.8 lighter: her nape under the tie), TINT_TOP; card_gain (hair.export.card_gain,
  Tess 2.1) is measured per groom (colour.py k).
- Scratch $HG/cards: run.sh (capped + heavy, haircards scripts), c1a.sh <tag> <gain> [hk.X=v]: hx.py hero cards, then
  spikes/haircards/shots.py of the cards AND the groom at the same cameras / light (NEW shots.py ev=<stops>, 1.0 for
  Garrett): g1v0, g1v1, g1left, g1back, g3v0.
  STATE: c1a (gain 2.1, defaults) running. NEXT: colour rows (p10 / p50 / p90 L*) cards vs groom, gain from colour.py k.
- (2b) c1a = defaults: 0 CARDS, the cap alone (3100 tris). Cause 1: G88a is a SHORT cut (mean lock < MASS_MIN 6 cm) ->
  SHORT_TIERS' per-lock clump_cards, whose strand_grid reads only hair_guides* strands; G88a is an EVEN groom
  (strands.even: hair_even 192k + hair_under 288k, every strand lock 0) -> none. FIX (hair.cards_job): an even groom
  is not "short": it takes the hero tier's clumps cut (hair_clumps), as Tess. Cause 2 (c1b, hh.MASS_MIN=0): 100%
  "hanging" cards: a loose groom's locks are ALL free (1.0, none tied) and every even strand carried lock 0 -> the
  ponytail's tail class (TAIL_TONE .62, TONE_CONTRAST_TAIL 4.5, PCA_FRAME twist, TIP_FADE_TAIL). FIX: hair_clumps.strands
  gives each hair_even* strand its nearest lock's id; hair.cards_job marks a short loose cut's scalp-rooted locks
  "lies" (classify -> head; not face-framing; card_classes reports head). Test test_even_strands_take_the_nearest_
  scalp_locks_class. c1c: 14590 tris (cap 3100, head L0 323 / L1 695 / L2 378 cards), all head.
  STATE: groom renders out/s_hg_G88a_grm_* done; c1c card renders (ev 1.0) running. NEXT: colour rows (gcol.py), tiles.
- (3/4) c1c LOOK (out/sh_c1c.png, groom | cards; NEW $HG/cards/sheet.py, gcol.py): BARE SCALP patches at the back and
  behind the ear (the long-hair cap chart hs.cap_chart reads no hair_even strands: the cap is clear there), dark flap
  cards along the top front, the groom's light-grey sides gone (cards one dark tone). COLOUR rows (gcol.py, common
  mask, groom | c1c p10/50/90 L*): g1v0 19.6/36.9/55.2 | 18.5/34.0/44.0; g1v1 33.1/50.0/58.5 | 26.7/33.4/40.7 (dL50
  -16.6); g1left 27.1/45.6/60.0 | 28.9/39.0/47.6; g1back 28.1/37.4/48.4 | 28.1/40.3/50.5; g3v0 31.9/42.3/53.5 |
  30.8/35.7/43.2. Not black (gain 2.1), but the p90 (the grey) is 10-18 L short everywhere but the back.
  c1a's cap ALONE (the short cut's baked hair_cap chart, every strand + grey by lock) covered fully and kept the grey
  sides, but stood as a tall quiff (raised to the hair's mid height).
  FIX tried: hair.EVEN_SHORT_CAP 1 (an even short groom wears the baked short cap under its clumps cards),
  EVEN_SHORT_LIFT 0 / 1 (cap on the scalp / raised): c1d / c1e. STATE: c1de.sh running.
- (3/4b) c1d / c1e (out/sh_c1de.png: groom | c1a cap only | c1d | c1e): c1d (baked cap ON the scalp) still bare at the
  back / behind the ear (the cap at scalp height sits under the head's skin); c1e (EVEN_SHORT_LIFT 1: the baked cap at
  the hair's mid height + clumps cards) COVERS like the groom, outline close at every view (no quiff: c1a's quiff was
  the short path's own lift without cards over it... same lift here, but its look is now the cards'). Colour rows
  c1e (groom | c1e p50, k): g1v0 37.4 | 39.8 (1.02), g1v1 49.6 | 35.3 (1.90), g1left 42.4 | 39.7 (1.28), g1back 37.4 |
  36.7 (1.06), g3v0 42.8 | 39.1 (1.28). Front / back right; the groom's LIGHT GREY SIDES / TEMPLES (grey .65 by
  lock) are missing: the clumps cut's cards share tiles, one tone for the head. NEW hair_clumps.GREY_TINT (default 0):
  card tint x (1 + k x (its locks' grey - the median card's)). Locks' grey p5 / p50 / p95 .09 / .25 / .64.
  c1f = c1e + GREY_TINT 1.5, c1g = 2.5. STATE: c1fg.sh running.
- (3c) c1f / c1g (GREY_TINT 1.5 / 2.5): NO change (rows identical to c1e within 0.4 L): the knob sits in
  hair_clumps.bake_tiles' tint, which these cards don't reach / show (not traced: budget). Left at 0 (off). The grey
  sides stay the open colour fault: g1v1 p50 35.7 vs the groom's 49.6 (k 1.86), g1left -2.5, front / back / 3 m within
  +3 / -1 / -3.3. NOT near-black: c1e's hair p50 35-40 L* vs the groom's 37-50 (the assembly's black export is their
  colour bug or a missing card_gain: use gain 2.1).
- DEFAULT now EVEN_SHORT_LIFT = 1 (c1e = the defaults at this commit). (4) c1L.sh: all four tiers (export_hair, shared
  atlas) rendered at g2 / g4 / g8 beside the groom; blind review of c1e vs groom tiles ($HG/cards/review/<view>.png,
  left = groom, right = cards) by a fresh subagent.
- (4) LODs (c1L, out/sh_lods.png: groom | hero | main | npc | far at g2v1 / g4v0 / g8v0): hero 14590, main 2384 (cap 2096
  + 288 card tris), npc 1212 / far 668 (cap only). main / npc / far = a TALL SWEPT-BACK POMPADOUR: the coordinator's
  Garrett v4 fault (Joe: "a totally different hairstyle"; the export's default = cap + 96 cards). CAUSE, located: the
  short cut's baked cap RAISED to the hair's mid height (hair_cap.cap_height(chart["lift"]), hair.py ~2813, the
  "cap is the hair's MASS" step) is the pompadour whenever few cards sit over it: c1a (short path, 0 cards) showed
  the same quiff at the hero tier; c1e's hero (same lift, 1396 clumps cards) does not. NOT yet explained why the
  hero's cap reads lower (cap_step? cards hiding it? the lift taken from the cards' top?): trace the cap mesh height
  per tier (hero vs main) over the crown vs the groom's strands' p90 height.
- (4b) BLIND REVIEW (fresh subagent, $HG/cards/review/<view>.png, left = groom, right = c1e): g1back close; g1v0,
  g1v1, g1left, g3v0 not close. MAJORs: colour (dark charcoal vs salt-and-pepper, silver sides / temples gone), front
  hairline an M with a centre notch + dark strands on the forehead, dark spiky shards along the front hairline / temple
  (3/4), top flatter / sides hug (10-15% less height), temple / sideburn bare in profile with loose strands across it,
  ragged dark chunks at the crown edge, specks at the nape.
## HANDOVER (hair-garrett c1, 2026-10-18; stopped at the ~70 tool-call budget)
STATE: branch hair-heads2 = hair-cards merged (9cd3eb4f) + the even-groom fixes (cards_job: even groom not "short";
hair_clumps.strands: even strands take the nearest lock; "lies": a short loose cut's locks are head cards; EVEN_SHORT_CAP /
EVEN_SHORT_LIFT; GREY_TINT knob, off, no effect yet). Scratch $HG/cards: run.sh, c1a.sh <tag> <gain> [k=v] (export +
cards / groom shots at g1v0 g1v1 g1left g1back g3v0, ev 1.0), c1L.sh (tiers at g2 / g4 / g8), sheet.py, gcol.py
(colour rows), review/. Nothing in flight.
VERDICT (look-first): c1e hero reproduces G88a's STYLE (outline, length, receding front, part side) far better than
the default conversion, but is not close in colour and front hairline; the lower LODs are the pompadour.
NEXT, in order: (1) the pompadour at main / npc / far (and any card-poor tier): the lifted cap; measure cap height vs
the groom's strands per tier, then either lift the cap only as far as the cards over it reach (general) or not at all
on card-poor tiers, judged on the c1L sheet. (2) The grey sides: GREY_TINT never reached the render: find where the
clumps cards' per-card tint is applied (bake vs bake_tiles path) and whether the CAP (which carries the grey by
lock) is hidden under dark L1 / L2 cards. (3) Front hairline notch + shards: the hairline cards (HL_*) / PART_GAP on
a receding front. (4) Re-run the blind review (source = G88a) and update the BEST line.

## Garrett cards c2 (2026-10-18, hair-garrett agent, fresh; Joe on v4: "that's a totally different hairstyle": style first at every tier)
- (1) LOD POMPADOUR, measured (NEW $HG/cards/sil.py: hair outline vs the groom per view from the id passes: IoU, area,
  top = p90 over columns of rows the cards' top stands over the groom's, % of the groom's hair height; ex / miss = % outside):
  c1L at g2v0 / g4v0 / g8v0: hero top -1.3 / -2.8 / 0 %, ex 0 %; main +18.7 / +19.4 / +16.7 % (ex 33 / 20 / 7 %); npc
  +20 / +19 / +17 %; far +28 / +26 / +22 % (ex 57 / 39 / 22 %, area 1.3). CAUSES: (a) below the hero tier an even groom
  had NO cards (CARD_TIERS main / npc / far cut per lock with clump_cards, which reads only per-lock guide strands: main
  57 cards / 288 tris, npc / far 0), so the cap was the hair; (b) the even cap's mass lift was ADDED after cap_under_cards
  (over the cards wherever they were few) and on top of whatever height the cap mesh had (far's cap is already the mass:
  doubled). FIX (general): hair.tier_settings(tier, short, even): an even groom is cut by clumps at EVERY tier
  (EVEN_CLUMPS 1); the even cap is SET to the hair's mid height over the scalp (cap_height, not added) BEFORE
  cap_under_cards, which then keeps it under its cards; no bare floor for it (bare_floor=False: c1d's bare patches).
  Tests test_even_groom_is_cut_by_clumps_at_every_tier, test_cap_without_cards_keeps_its_height_when_asked.
  STATE: c2a export (all tiers, GREY_TINT 2.5 with probes, $HG/cards/hxp.py) running. NEXT: sil.py rows per tier, sheet.
- (2) GREY_TINT TRACED (probe $HG/cards/hxp.py on the c2a export, GREY_TINT 2.5): the knob DID reach the cards (bake_tiles
  card grey p5/50/95 .18/.29/.63, tint .66/.93/1.78, tone_k .61/.85/1.63; the GLB's COLOR_0 at the sides .83 -> 1.00, top
  .77 -> .67, $HG/cards/gx.py = COLOR_0 by region), but (a) COLOR_0 clips at 1 (60 % of side vertices at 1.0 in c1g:
  a vertex colour can't brighten past the atlas) and (b) it is the WRONG lever: lighter dark hair is not salt-and-pepper.
  The grey HAIRS were never per region on cards: strand_tones has no grey, and the atlas drew grey hairs by one share for
  every tile (look.grey_share by strand id threshold); only the cap's chart knew the locks' grey. FIX: hair_clumps.
  card_grey (each card's grey share by its strands' locks, the strand look's rule), bake_tiles clusters tiles on it too
  (GREY_TILES 1) and returns B["gshare"] (per atlas pixel: its tile's share), hair_cards.atlas draws the baked rows' grey
  hairs at that share. GREY_TINT stays 0. Test test_card_grey_follows_its_locks. COLOR_0 lever test queued (vc03 = c1e
  with COLOR_0 forced to 0.3, g1v1).
- (3) HAIRLINE measured (NEW $HG/cards/hl.py: front hairline row at 11 columns from the id passes, % of the groom's hair
  height; notch = centre vs +-20 %): g1v0 groom notch -0.7, c1e +4.9 (the M), mean line -11.3 % (the cards' line sits
  higher: a bare forehead band). CAUSE of the notch: G88a's parting is "none" but hair_clumps.cut read a part from the
  strands (PART_FROM_STRANDS: a near-even vote 21.7k / 24.2k) at the centre front and trimmed cards PART_GAP off it.
  FIX: no strand part when the groom has no parting (side_of None).
  STATE: c2a renders queued (c2chain.sh); c2b = these defaults (grey tiles, no emergent part) export next.
- (1b) c2a RESULT (out/sh_c2a_lods.png: groom | c1L main (pompadour) | c2a hero | main | npc | far at g2v0 / g2v1 / g4v0 /
  g8v0; NEW $HG/cards/lsheet.py): every tier has real clumps cards now (hero 1396 cards / 14590 tris, main 677 / 6308, npc
  405 / 3026, far 81 / 992) and the POMPADOUR IS GONE: sil.py top over the groom's at g2v0 / g4v0 / g8v0: main +18.7 /
  +19.4 / +16.7 % -> -1.3 / -2.8 / 0; far +28 / +26 / +22 % -> -2.7 / -2.8 / -5.6; ex (outside the groom) 0 % at every
  tier. Look: all four tiers read as the same short, swept-back, receding cut. Left: the lower tiers sit a little INSIDE
  the groom (miss at g2v1: hero 16 %, main 22, npc 28, far 31 %: thinner over the back / behind the ear), colour (below).
  COLOR_0 lever test (vc03, c1e with COLOR_0 = 0.3): g1v1 p50 35.3 -> 15.1 L*: the render honours COLOR_0 (so GREY_TINT's
  null result was the clip at 1 and the lever being tone, not grey hairs).
  Colour rows c2a (old atlas grey; GREY_TINT 2.5, dropped): groom | c2a p50 (p90): g1v0 36.2 | 36.6 (54.0 | 44.8), g1v1 49.6 |
  37.0 (58.2 | 44.4), g1left 43.1 | 40.0, g1back 37.5 | 35.7, g3v0 42.0 | 37.8. Hairline (hl.py g1v0): notch c1e +4.9 ->
  c2a +3.1 (groom -0.7), mean line -10.3 %.
  STATE: c2b (defaults: grey tiles + no strand part) export / renders queued. NEXT: colour + hairline rows of c2b, review.
- (2b/3b) c2b (defaults: grey tiles + no strand part; out/sh_c2b.png = groom | c1e | c2a | c2b, sh_c2b_lods.png): colour
  UNCHANGED (g1v1 p50 36.5 vs c2a 37.0, groom 49.6; p90 43 vs 58): GREY_TILES is a DEAD LEVER as built (not traced: budget;
  check that atlas()'s `gs > 0` branch runs for the clumps path, that isg on the baked rows survives `lin = base * val * gain`
  / bake tone normalisation, and print the gshare plane's p5/50/95 in the export). Hairline notch c2b +2.8 (c1e +4.9,
  groom -0.7): the strand part removal helped a little; the line is still ~10-14 % high (bare forehead band) and the far
  temple column (-0.4) lost its hair in c2b (29.4 vs 65).
  LOOK (mine, look-first): LODs: style right at every tier now (same short swept-back cut at g2 / g4 / g8). HERO c2a / c2b
  WORSE than c1e: rows of bare-scalp holes at the back and behind the ear, black flaps at the crown, scaly sides. Not shippable.
## HANDOVER (hair-garrett c2, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: commits d8e29b86 (tier_settings: even groom cut by clumps at every tier; even cap SET to mid height then
cap_under_cards with bare_floor False), 463bbef1 (card_grey / GREY_TILES / bake gshare; no strand part when parting none),
notes. Scratch $HG/cards: sil.py (outline vs groom), hl.py (front hairline), gx.py (COLOR_0 by region), lsheet.py (tier
sheet), hxp.py (export with GREY probes), c2chain.sh <tag> (lever test + tiers at g2/g4/g8 + hero at g1/g3).
NEXT, in order: (1) the hero's holes: the c2 cap order (set mid height -> under cards) sinks the cap where cards are sparse;
try keeping the floor at the c1e height where cards are sparse (cap_under_cards floor = max(floor, a few mm), or apply the
under-cards clamp only on tiers whose card share is small) and judge hero (sh_c2b rows) AND tiers (sil.py top <= 0) together;
if two tries fail, restore c1e's order for the hero tier only (keep the clumps cut at every tier: that alone may fix the
pompadour since cards now cover the cap). (2) GREY_TILES dead: trace as above (prove the lever on one tile before a batch).
(3) hairline high / temple: hl.py rows; the cards' front roots sit ~10 % of hair height behind the groom's line.
(4) Blind review vs G88a NOT run this session (budget): run it (bin/review after 2026-10-19 13:00 MT, else a fresh blind
subagent on reference | result pairs, no captions) once the hero has no holes.

## Garrett cards c3 (2026-10-18, hair-garrett agent, fresh; order: hero holes, grey lever on one tile, hairline, A/B vs c1e)
- (1) HERO HOLES, try 1: c2's even cap (SET to the hair's mid height, then cap_under_cards with the floor = `lift`, ~2 mm)
  sank to the scalp wherever a sparse card passed over it: under the head's skin (c1d's fault again) = c2's rows of round
  bare-scalp holes at the back / behind the ear (out/sh_c2b.png col 3-4). NEW hair.EVEN_CAP_KEEP (0.6): the even cap's
  floor under its cards is 0.6 x its mid height (per vertex), held after CAP_RELAX too. Tests clumps 19 passed.
  STATE: c3q.sh queued (c3a = defaults all tiers -> hero g1 views + tiers g2/g4/g8; c3g = hero + hk.GREY_TILES=4).
- (2) GREY LEVER on the texture, measured (NEW $HG/cards/gu.py <exp> [tier]: per region of the GLB, the atlas texels
  under its triangles (12 samples each): L* p50, grey-hair share = L* > 55, COLOR_0): c1e sides 18.0 % / top 17.1 / back
  14.9 / front 16.6; c2b (GREY_TILES 1) sides 26.5 % / top 16.6 / back 12.4 / front 16.9. So GREY_TILES is ALIVE in the
  texture (sides +8.5 pts, back -2.5) but far too weak: the groom's side locks carry grey .64 vs top .22 (3x), and the
  render's side p50 is 36.5 vs the groom's 49.6. Suspect: 24 tiles per group cluster on length / width first, each tile
  draws the MEAN of its cards' grey (side and top cards share tiles). Test c3g (GREY_TILES 4): gu.py sides share up?
  Also the atlas's grey colour is look.grey #6a6764 (L* ~44) x shade x gain: grey hairs are mid grey, not silver.
- (3) HAIRLINE lever queued (c3h: hero + hk.HL_SOFT=0): hairline cards fade their first 10 mm to HL_ALPHA .45 and the
  thin hairs drop under the alpha cutoff, a likely part of the ~10 % high line. hl.py g1v0 decides.
- (1b) c3a RESULT (EVEN_CAP_KEEP .6; out/sh_c3a.png = groom | c1e | c2b | c3a, zz_c3a_crown.png): the HERO HOLES ARE GONE
  (back and behind the ear fully covered; the back reads fuller than c1e, no nape specks). Left: dark flap cards standing
  at the crown's outline (top-left in the back view, top-right in the 3/4), present smaller in c1e: not the cap.
  Colour unchanged (gcol c3a p50 g1v0 39.1 / g1v1 36.6 vs groom 50.0 / g1left 40.0 / g1back 36.7 / g3v0 39.5). Hairline
  hl.py g1v0: notch +2.8, mean line -14.8 % (c1e -11.3): the right temple column (-0.4) 29.4 vs the groom's 98.6 = the far
  temple's lost hair is in c3a too (c1e 62.9). Tiles grey (NEW log line in bake_tiles): cards p5/50/95 .31/.41/.75, tiles
  .34/.42/.74: the tiles DO reach the side cards' share; the atlas draws far less (gu.py sides 26 %): the drawing is the limit
  (isg = id threshold x the depth gate dep .32-.52: only the outer hairs may be grey).
  STATE: c3g (GREY_TILES 4) + c3a tiers + c3h (HL_SOFT 0) renders running. NEXT: tiers sil.py, grey / hairline rows.
- (1c) c3a TIERS (out/sh_c3a_lods.png = groom | c1e hero | c3a hero / main / npc / far at g2v0 / g2v1 / g4v0 / g8v0):
  no pompadour at any tier (sil.py top hero -1.3 / -1.1 / -2.8 / 0 %, main same, npc / far -2.0..-2.8 %, ex 0.0 % at every
  tier and view); same short swept-back cut at every tier. Thinner than the groom (miss at g2v1: hero 16 %, main 21, npc 25,
  far 27 %; c2b the same): the groom's side volume over the ears. GREY_TILES 4 (c3g): NO change (gu.py sides 24 %, gcol
  g1v1 p50 36.1): the tiles already split by grey; the DRAWING is the limit. Probes c3p1 (every tile's grey share forced
  to 1) / c3p2 (+ no depth gate: NEW hair_cards.GREY_DEP0 / GREY_DEPW) running, texture-only (gu.py).
- (3) HAIRLINE lever c3h (hero + hk.HL_SOFT=0): DEAD for the line: hl.py g1v0 identical to c3a to the decimal (notch +2.8,
  mean line -14.8 %; columns 29.4 / 28.0 / 22.4 ...). Either the hairline cards' root fade isn't what sets the line, or the
  tile bake is cached past HL_SOFT (not traced: budget). The line is set by where the front cards' roots sit, not their alpha.
- (2b) GREY max-lever probes (texture only, gu.py): c3p1 (every tile's share forced to 1): sides tex L50 34.3 -> 51.3, grey
  texels 26 -> 45 %, top 17 -> 45 %; c3p2 (+ no depth gate) sides 57.5 / 70 %. So the DRAWING works; the share is drawn
  compressed: idm is not uniform over 0..1, a .74 share drew 26 % grey texels. FIX: NEW hair_cards.GREY_QUANTILE 1: a
  tile's share is drawn as that quantile of the tiles' strand pixels' ids. c3q (defaults: cap keep + quantile) running.
- (4) BLIND A/B, c1e (old) vs c3a (new), fresh subagent, trios ref | X | Y, key review/ab_c3a/key.json (decoded here):
  front OLD, 3/4 OLD, side NEW, back NEW, main 2 m TIE, npc 4 m OLD, far 8 m OLD -> VERDICT TIE. Its MAJORs: c3a black
  shards / dark card backs on the crown's top edge (every hero view), loose dark cards at the nape (back); c1e jagged shard
  tufts at the front hairline, holey edge round the ear. BOTH: thin at the temples / over the ears, the light grey sides
  missing (too dark, uniform). Tiers: it preferred the old (pompadour) tiers at 4 / 8 m as "overvolumed but outline near"
  while c3a's read "receded and thin": the groom's side volume (sil.py miss 21-27 % at g2v1) is the tiers' fault now, not
  the top. Outline changes between levels (consistency) flagged.
- (2c) c3q (defaults: cap keep + GREY_QUANTILE; out/sh_c3q.png = groom | c1e | c3a | c3q): gu.py sides grey texels 26 ->
  31.5 %, top 17 -> 21; gcol p50 vs groom: g1v0 40.3 | 35.6 (+4.8, was +3.5), g1v1 38.6 | 50.0 (-11.4, was -13.4), g1left
  40.8 | 42.3, g1back 37.0 | 37.3, g3v0 41.1 | 41.9 (-0.8, was -2.4). Right way, small; the look barely changes (the silver
  temple / sideburn band is still missing). Kept (default 1).
## HANDOVER (hair-garrett c3, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: commits on hair-heads2 (local, NOT pushed: coordinator rule, never push): EVEN_CAP_KEEP (hero holes fixed), bake_tiles
grey-share log line, hair_cards GREY_DEP0 / GREY_DEPW / GREY_QUANTILE. Scratch $HG/cards NEW: gu.py (atlas grey texels +
COLOR_0 per GLB region), atl.py, hxg.py (force tiles' grey share: GS=), tiles.py (A/B crops), c3q.sh / c3q2.sh / c3h.sh /
c3p.sh, review/ab_c3a (trios, key.json). BEST line updated (top of this file).
LOOK (mine, look-first): hero c3q = c1e's style with full coverage (no holes) but the same three faults the blind reviewer
named: (a) black shards / dark card backs along the crown's top outline (c1e had them smaller), (b) too thin over the
temples / ears (the groom's side volume), (c) the groom's silver sides / sideburns absent: reads as uniform dark charcoal.
Front hairline still high (hl.py mean -14.8 %) and the right temple column bare (29 vs groom 99).
NEXT, in order: (1) the crown shards: find the cards (id pass: dark pixels outside the groom's top outline -> card ids ->
their layer / kind / normal vs view); likely layer-2 cards standing edge-on at the whorl, seen from the back face (dark).
(2) grey sides: the share is drawn now (quantile), but the side tiles' share (~.5-.75) is still less silver than the
strands read; measure the groom's side region's grey-strand share in its own render, then a calibrated gain on the tiles'
share (target gcol g1v1 p50 50 +-3, front not over +3). (3) side volume over the ears at every tier (sil.py miss at g2v1:
target <= 10 %): the cards' lift / the cap's mid height at the sides vs the groom's strands' height there. (4) hairline:
HL_SOFT is dead for the line (c3h identical); the front cards' ROOT positions vs the groom's hairline (hl.py) and the far
temple column. Then re-run the blind A/B (review-ab after 2026-10-19 13:00 MT) with c3q as OLD.

## Garrett cards c4 (2026-10-18, hair-garrett agent, fresh; order: crown shards, grey calibration, side volume, hairline, all tiers + A/B)
- Tess's PART COVER row (round 33, hair_clumps.PART_COVER, opt-in, not judged yet there): a row of cards rooted ON a part
  line. G88a has parting "none" (c2 removed the emergent strand part): nothing to root it on. Not reused; if Tess's
  build wins its A/B, a "crown cover" (the same row rooted on the whorl) is the analogue to try.
- (1) CROWN SHARDS, probed (NEW $HG/cards/shard.py <exp tag>: per card standoff over the cards' own p85 envelope per 4-deg
  bin, outline samples per view (back / side) with layer / normal / atlas lum, shadow proxy vs cards, WINDING): c3q has
  NO card standing out at the back crown (cards > 3 mm out: 7.8 cm2 of 1087, all at the front top az 290-30, max 8 mm);
  the outline samples' atlas colour is NOT dark (dark share 1 %), vertex normals all point out (n.radial p10 .83), the
  shadow proxy sits 1-8 mm inside the cards. FOUND: 1-2 % of card triangles (layer0 2.0 %, L1 1.1, L2 1.0; cap 0) are
  WOUND against their own vertex normals (folds where a card turns over), 134 cards: a double-sided renderer shows
  such a face's BACK from outside and shades it with the flipped normal = lit from inside = black shard. FIX (general):
  hair_cards.WIND_TO_NORMAL 1: mesh() winds every card triangle along its vertex normals. Lever test = c4a.
- (2) GREY: the tiles' shares are drawn now (c3 quantile) but compressed: tiles side .74 / top .41 (1.8x) where the
  locks carry .64 / .22 (2.9x). NEW hair_cards.GREY_SPREAD 2.0: shared tiles' shares x 2 about their median (sides -> ~1,
  top ~.4). Target gcol g1v1 p50 50 +-3 (c3q 38.6), front g1v0 not over +3 of the groom's 40.3.
  (4, read) HL_SOFT is applied only in the per-card `bake` (hair_clumps ~1007), not in shared tiles: dead for the clumps
  path by construction, not a cache.
  STATE: c4a (hero, defaults = WIND_TO_NORMAL 1 + GREY_SPREAD 2) exporting + g1 views (c4a.sh <tag> [hk./hc. k=v]).
- (1b) c4a RESULT (out/sh_c4a.png = groom | c3q | c4a): winding fixed (shard.py: 0.0 % of card area wound against its
  normals, was 1-2 %), but the CROWN SHARDS ARE STILL THERE (back view top-left, profile top-right): winding was not their
  cause. Kept (correct anyway, harmless). Also ruled out: the shadow proxy (c4np = c4a rendered proxy=0: shards
  identical, $HG/cards/c4/zz_np.png), standing cards (none > 3 mm out at the back crown), dark atlas texels on the
  outline (1 %). Lead left (NEW shard2.py): COLOR_0 at the back-left crown (az 90-170, el 40-80) has a p5 of .48 vs the
  cards' .77 median (per-card means all ~.73): a few dark VERTICES per card (roots / an end?) -> next: print which vertex
  rows (along) carry col < .55 and whether they sit at the outline there; also try the cards' alpha < .5 fringe (the
  probes counted only alpha > .5 samples: a dark semi-transparent tip fringe would be missed).
- (2b) GREY_SPREAD 2 (c4a): texture sides grey texels 31.5 -> 38 %, tex L50 45 (gu.py); render g1v1 p50 38.6 -> 39.5 (groom
  50.0), p90 45.8 -> 48.4 (58.1); front g1v0 +5.6 (was +4.8, limit +3: slightly over), g3v0 +0.1. Right way, too small:
  the grey hairs' COLOUR is the limit now (look.grey * (0.6 + 0.4 shade) in hair_cards.atlas: mid grey, not the groom's
  silver). Kept (default 2). NEXT: a grey-hair lightness lever (the strand look's grey vs the atlas's), measured on g1v1.
- (3/4) SIDE VOLUME = HAIRLINE: NEW miss maps ($HG/cards/c4/miss_c3q.png, groom id mask minus cards'): the missing 12-25 %
  is a band along the hair's INNER edge (front hairline, temples, sideburn in front of the ear, behind the ear), plus a
  1-2 px outer rim. Not bulk volume over the ears. c4b (BASE_IN 3 mm, the opaque core nearer the root): hl.py and sil.py
  IDENTICAL to the decimal (like HL_SOFT in c3h): the id pass's outline is the cards' GEOMETRY, so picture levers can't
  move it. The cards' geometry stops short of the groom's hairline: the cut drops / the roots sit behind the edge
  strands. NEXT: per hairline column, the groom's edge strands' roots vs the nearest card's root (hair_clumps.cut: which
  edge strands get no card: MIN_STRANDS, IN_SHARE, fly rules) and the cap's own hairline cut.
  STATE: c4L (all four tiers at the c4 defaults) exporting / rendering; A/B vs c3 (c3q hero, c3a tiers) next.
- (5) c4L = all four tiers at the c4 defaults (exp/c4L, tris 14570 / 6130 / 2958 / 1024). bin/review-ab ran its tiles but its
  reviewer hit the weekly limit (until 2026-10-19 13:00 MT): fallback fresh blind subagent on its trios (review/ab_c4L,
  key.json): front / 3/4 / side / back TIE, main 2 m NEW, npc 4 m NEW, far 8 m NEW ("lighter, greyer") -> VERDICT NEW
  (tiers), TIE (hero). BEST line updated. Its MAJORs, both builds: no silver sides; flat / low front top; black shard flaps
  at the crown and back crown; stray dark strands at the temples / round the ears; temples / sideburns thin, the hair over
  the ear stops high.
## HANDOVER (hair-garrett c4, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: commits on hair-heads2 (local, NOT pushed): hair_cards.WIND_TO_NORMAL 1, GREY_SPREAD 2; notes. Scratch $HG/cards NEW:
shard.py (standoff / outline / atlas lum / proxy / winding per card), shard2.py (COLOR_0 at the back-left crown), c4a.sh
<tag> [k=v] (hero + g1 views), c4L.sh (all tiers + views), c4/miss_c3q.png (miss maps), review/ab_c4L.
LOOK (mine, look-first): c4L reads as c3q with slightly greyer sides; same faults. The crown shards are the most visible
artefact and are NOT winding, proxy, standing cards or atlas colour: unexplained after 4 probes.
NEXT, in order: (1) shards: shard2.py lead (dark COLOR_0 vertices .48 at the back-left crown: which rows; and the alpha
< .5 fringe the probes skipped); if a render test is needed, delete card groups by layer from the GLB (layer0 / 1 / 2 at
az 90-170) and render g1back to find the layer. (2) hairline / temples / sideburns = card GEOMETRY stops short (picture
levers HL_SOFT, BASE_IN dead by construction): find the groom's edge strands that get no card in hair_clumps.cut and the
cap's hairline cut. (3) silver: grey-hair COLOUR in hair_cards.atlas (look.grey x (0.6 + 0.4 shade)) vs the strand look;
target gcol g1v1 p50 50 (c4a 39.5). (4) Re-run review-ab after 2026-10-19 13:00 MT.
## Garrett cards c5 (2026-10-18, hair-garrett agent, fresh; order: crown shards, hairline, silver, all tiers + A/B)
- (1) CROWN SHARDS = the preview's BACK-FACE NORMAL FLIP. Bisect ($HG/cards/strip.py <src> <dst> <tri ranges>: a GLB copy with
  triangle ranges collapsed; bis.sh <glbs>: g1back + g1left): no hair / cap only: none; ANY single card layer alone (L0, L1, L2,
  each with the cap) or any layer removed: the shards stay at the same place -> location, not a layer. shadow=0 (cards cast
  none): still there. flat=1 (albedo unlit): GONE -> lighting, not the picture or the vertex colour (the dark COLOR_0 lead was
  a red herring). The GLB's shading data is clean (sh3.py / sh4.py: unit normals and tangents, tangent = dP/du, handedness
  consistent, N.radial p5 .83 in the region). Cause: Blender (like glTF's own doubleSided rule) REVERSES the shading normal on a
  face seen from behind; a card at the back crown's outline, lying on the head, is seen from below its plane past its edge, so
  it was shaded with a normal pointing INTO the head: unlit = black. The export's shading notes already say "two-sided with ONE
  normal for both faces"; the preview material didn't. FIX (general, every card render): blender_cards.ONE_NORMAL 1:
  game_material shades with Normal x (1 - 2 Backfacing) (Principled, translucent backscatter, the wrap term). c4L re-rendered
  (out/s_hg_G88a_c5n_*): shards gone at back, profile and 3/4. NOTE for engines: a strict glTF viewer flips back-face normals
  (spec) and WILL show the shards; the engine material must honour the notes (Unity HDRP double-sided normal mode "None",
  Unreal: no flip for two-sided). Winding (c4) stays correct and harmless.
  STATE: ONE_NORMAL committed. NEXT: silver (GREY_LIFT trials c5g1-3 running), then the hairline.
- (3) SILVER: NEW hair_cards.GREY_LIFT (grey hairs' colour x this; default 1 = unchanged). gcol (dL50 vs the groom) with
  ONE_NORMAL shading: c4a re-rendered (c5base) front g1v0 +7.2 / 3/4 g1v1 -10.1 / profile -0.7 / back -0.3 / g3 +0.5;
  GREY_LIFT 1.6 (c5g1) +14.5 / -2.7 / +6.2 / +5.6; 2.2 (c5g2) +20.7 / +3.4 / +11.8 / +10.5 / +13.8. The lift moves every view by
  the SAME ~7 L*: the 3/4 deficit is not the albedo. The groom itself is 50 at 3/4 vs 42 in profile and 37 at the back: a
  VIEW-dependent highlight (the strands' BSDF sheen toward the key), which profile / back (already matched) don't see. Not
  adopted (default 1). Lead: the preview's game_material ignores the GLB's own specular (KHR_materials_specular .5,
  anisotropy .7; preview Principled specular .25, isotropic); the 3/4 silver is the anisotropic highlight. And the front's
  +7 is CONTRAST (groom p10 18.8 vs ours 36.5: no dark gaps between the front's strands), not level.
- (2) HAIRLINE probe (hlp.py <dir> [hk.k=v]: hero export with hair_clumps.cut's strands / cards dumped; hla.py: per
  hairline-lock strand, points > 2.5 mm off every card ribbon by fifth of length): front 711 strands, 0.8 % in no card, off-card
  by fifth .05 .06 .04 .13 .57; temples / sideburns L 2940 (8.6 % no card) .19 .11 .10 .21 .72, R 2732 (1.5 %) ... .77; BEHIND
  THE EARS L 1653 / R 1720: 64 / 68 % in NO card (mean off 73 %). Hairline strands 9-20 mm long. Causes: (a) head cards end where
  .35 of their strands still run (the tips = the band past the hairline), (b) fit() drops cards under 1 cm: the short
  converging clumps behind the ears. NEW levers hair_clumps.HEAD_END (.35) and FIT_MIN_LEN (.01). Trial c5h1 = .12 / .005.
- (2b) c5h1 (HEAD_END .12, FIT_MIN_LEN .005; c5h.sh <tag> [hk.k=v] = hlp dump + g1 views): DEAD LEVERS. No-card shares
  identical (behind ears 63.6 / 68.0 %), tips' off-card share .57 -> .52 front only; id-pass miss vs the groom unchanged
  (g1v0 44.3 -> 43.8 %, g1v1 40.3 -> 40.1, g1left 21.8, g1back 11.8). So the behind-ear strands are lost BEFORE fit's length
  test: _clump returning None (min_share .5) or crown_loops (check which), and the tips are off the card ACROSS it (fan past
  the p90 half width), not past its end. Levers left at their old defaults (.35 / .01: no change to the build).
## HANDOVER (hair-garrett c5, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: commits on hair-heads2 (local, NOT pushed): blender_cards.ONE_NORMAL 1 (DEFAULT: fixes the crown shards in every card
render), hair_cards.GREY_LIFT 1 (lever, off), hair_clumps.HEAD_END .35 / FIT_MIN_LEN .01 (levers, defaults unchanged). The
cards GEOMETRY / atlas are unchanged from c4L, so the BEST build is still c4L's GLBs; only the preview shading changed (re-render).
Scratch $HG/cards NEW: strip.py + bis.sh (layer bisect), sh3.py / sh4.py (shading data), hlp.py + hla.py + c5h.sh (hairline
probe), c5g.sh (grey trials), exp/bis, exp/c5g1-2, exp/c5h1, c4/miss_cap_g1left.png.
LOOK (mine): c4L under ONE_NORMAL (out/s_hg_G88a_c5n_*) reads as a clean short grey crop at the back / profile / 3/4: the
black flaps are gone. Still: thin temples / sideburns and bare behind the ears, the 3/4 sides not silver, a flat front.
NEXT, in order: (1) behind the ears: in hair_clumps.cut print per hairline strand why it got no card (crown_loops vs
_clump None (min_share) vs PART_GAP continue); fix that; then the tips ACROSS the card (spread 90 -> 97 for clumps holding
hairline strands, or a hairline edge row). Measure with hla.py + the id-pass miss (hairline band). (2) silver at 3/4: the
preview's game_material should read the GLB's specular / anisotropy (KHR_materials_specular .5, anisotropy .7) instead of its
own .25 isotropic Principled; measure gcol g1v1 (c5base -10.1) with profile / back held. (3) front contrast (p10 18.8 vs
36.5). (4) Re-export all four tiers, A/B vs c4L with bin/review-ab (CLI after 2026-10-19 13:00 MT). Note the A/B baseline:
c4L must be re-rendered with ONE_NORMAL, or the A/B judges the shading fix, not the build.
## Garrett cards c6 (2026-10-18, hair-garrett agent, fresh; order: export back faces, behind-ear cut, GLB highlight in the preview, front contrast, all tiers + A/B)
- (1) EXPORT BACK FACES (coordinator: the shard fix must hold in ANY engine; a strict glTF viewer flips back-face normals of a
  doubleSided material). NEW hair.BACK_FACES 1 (default) + hair.back_faces(): every card triangle is followed, inside its
  layer's range, by its back = the same corners reversed (same vertices, the SAME outward normal, tangent, sign); the cap keeps
  one face; the material is doubleSided FALSE (asset.write_glb looks "double_sided"); CARD_RECIPE_FACES says so (single-sided,
  back-face culling). Preview honours it: blender_scene hair_glb_look passes the imported material's use_backface_culling into
  blender_cards.game_material ("cull"; shadows still from both faces). Test tests/test_hair_back_faces.py.
  COST: vertices UNCHANGED (hero 16115: the back shares them), index triangles x~1.8: hero 14570 -> 26040 (cards 11470 x 2 +
  cap 3100). Budgets (budgets.json, MetaHuman counts VERTICES): hero 25k default / 15-50k range -> inside the range; a culled
  back face costs a cull test, not shading (the real card cost is overdraw, unchanged).
  CHECK (plain viewer = blender_cards flip_back 1, i.e. ONE_NORMAL off; $HG/cards/c6r.sh, glbck.py): c4L shows the black crown
  shards again (back / profile / 3/4), c6a has none: out/c6_flip_ab.png (top c4L, bottom c6a). glbck: c6a doubleSided False,
  88 % of triangles have their reversed twin, verts 16115 = c4L.
  STATE: committed. NEXT: (2) the behind-ear strands with no card.
- (2) BEHIND-EAR STRANDS, why ($HG/cards/why.py <dir> [hk.k=v]: cut instrumented, each strand's fate, stops after the cut): hairline
  strands front 711 (705 card), temple L 2940 (253 clump_none), BEHIND EAR L 1653 (1051 clump_none), R 1720 (1169), temple R
  2732 (20). ALL losses are hair_cards._clump returning None, and over the whole head 42,760 of 192,008 strands (22 %, all
  head, length p50 11 mm) had no card. Cause: _clump needs >= 4 STEP (4 mm) stations where half the clump's strands run =
  strands >= ~12 mm; Garrett's side / nape hairs are 9-11 mm. (First tried: split failed clumps in two (hair_clumps
  SPLIT_DEPTH 4 / SPLIT_MIN 6, kept as default, harmless): behind ears 1051 -> 880, not the cause.) NEW lever
  hair_clumps.MIN_STATIONS (passed to _clump's new min_stations): at 3 with FIT_MIN_LEN .006 every hairline strand has a card
  (behind ears 0 % no card; hla.py mean off-card 73 % -> 15 %). c6b (hero, these two): 19280 unique triangles (c6a 14570),
  verts 23143 (16115), with back faces 35460 index triangles. Look (out/c6_sheet_b.png groom | c6s | c6b): behind the ear a
  little fuller in profile; small. The tips past the cards' sides: off-card share in the last fifth still .41-.76 (not done).
- (3) GLB HIGHLIGHT IN THE PREVIEW: NEW blender_cards.GLTF_SPEC 1 (default): game_material reads the GLB's own
  KHR_materials_specular (factor 1 = IOR level .5: the old .25 WAS the GLB's .5), its colour, the ORM roughness (G; p50 .51)
  and KHR_materials_anisotropy (strength x flow.B along flow.RG in tangent space, uv tangent from the mesh's UV map);
  blender_scene hair_glb_look parses the GLB and passes them. Applied (render diff +5 mean on the hair, bright p99), but the
  3/4 silver does not move: gcol g1v1 dL50 c5base -10.1 -> c6s -9.7; spec doubled + white tint (c6s2) -9.0. With c5's albedo
  lift (all views +7 alike) that rules out albedo AND the highlight. The cards cover 62 % of the groom's hair area at 3/4
  (7241 / 11717 px): the silver is the side / top VOLUME the cards don't have (where the groom's sides catch the key), not
  shading. Left there.
- (4) FRONT CONTRAST: crop out/c6_front_crop.png (groom | c6s): the groom's front has dark gaps between strands (p10 18.8),
  ours a flat mid grey (36.6) and a few dark stray strands over the centre front; the groom's front also stands taller.
  The atlas already carries the depth shade (aux_shade in the preview would double it). Trial c6c = c6b + hc.SHORT_DEPTH .2
  (the depth shade's floor for short-cut strands, .45).
- (4b) c6c (c6b + hc.SHORT_DEPTH .2): gcol IDENTICAL to c6b to the decimal: dead lever for this cut (SHORT_DEPTH is the
  short-tile path's). Front contrast NOT fixed this session.
- (5) DEFAULTS now hair_clumps.MIN_STATIONS 3, FIT_MIN_LEN .006 (with BACK_FACES 1, GLTF_SPEC 1). RISK: a shared default:
  other grooms' short clumps (Tess's) now make cards too; not checked on Tess. If her A/B or RC regresses, set MIN_STATIONS 4
  / FIT_MIN_LEN .01 for her (back to known good). STATE: c6L = all four tiers + c4L re-rendered with the same shading
  (tag c6o*), $HG/cards/c6L.sh.
- (5b) A/B c6L (MIN_STATIONS 3 + FIT_MIN_LEN .006 + SPLIT_DEPTH 4 + back faces, all tiers) vs c4L RE-RENDERED with the same
  shading (c6o*: ONE_NORMAL + GLTF_SPEC, so the A/B judges the build): review-ab's CLI is out until 2026-10-19 13:00 MT,
  so a fresh blind subagent on hand-made X/Y trios (review/ab_c6L, key.json, tiles.py): front OLD, 3/4 TIE, side OLD
  (old's sideburn runs lower), back OLD (new: a flap at the top-left crown, narrower), 2 m TIE, 4 m OLD, 8 m OLD ->
  VERDICT OLD. My look-first read agreed on the back (a crown-edge bump in the new); behind the ear only a little fuller.
  And the extra short cards cost: unique triangles npc 2958 -> 6062, far 1024 -> 2500 (over the crowd range).
  REVERTED to the known good cut: MIN_STATIONS 4, FIT_MIN_LEN .01, SPLIT_DEPTH 0 (levers kept). The reviewer's MAJORs (both):
  thin temples / above the ears (reads narrow), spiky dark front hairline, too dark / no silver at the sides, back texture a
  uniform curly carpet (not swept-back direction), stray wisps round the ears.
- (5c) c6M = all four tiers at the reverted defaults + BACK_FACES: geometry identical to c4L (glbck: same verts / unique tris);
  index triangles hero 26040, main 10164, npc 4704, far 1380 = inside every role's budget range (hero 15-50k, main 6-20k,
  npc 2-8k, crowd 300-1500); vertices unchanged. BEST line updated (c6M).
## HANDOVER (hair-garrett c6, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: commits on hair-heads2 (local, NOT pushed): hair.BACK_FACES 1 + back_faces() (test tests/test_hair_back_faces.py),
asset write_glb looks "double_sided", preview honours the GLB's culling, blender_cards.GLTF_SPEC 1 (the GLB's specular /
colour / ORM roughness / anisotropy in the preview), hair_clumps MIN_STATIONS / SPLIT_DEPTH levers (off), _clump min_stations.
BEST = exp/c6M. Scratch $HG/cards NEW: glbck.py (doubleSided / verts / twins), why.py (each strand's fate in the cut), c6r.sh
(render a GLB: default params = ONE_NORMAL off, a plain viewer), c6h.sh / c6x.sh (hero trial), c6L.sh (all tiers + c4L
re-rendered as c6o*), out/c6_flip_ab.png, c6_sheet_b.png, c6_front_crop.png, review/ab_c6L.
LOOK (mine): the export fix holds (a plain viewer shows c4L's shards, none on the back-faced GLB). Otherwise c6M looks as c4L.
Still: thin temples / no hair above the ears, the 3/4 sides not silver, a flat dark-flecked front, a uniform back texture.
FINDINGS that redirect: the 3/4 silver is NOT albedo (c5) and NOT the highlight (c6: GLB spec / aniso / doubled white spec
moved g1v1 -10.1 -> -9.0): the cards cover only 62 % of the groom's hair area at 3/4: it is the missing side VOLUME. The
behind-ear "no card" is short hairs (9-11 mm < 4 stations x 4 mm); giving them cards (MIN_STATIONS 3) made the back worse.
NEXT, in order: (1) side volume above the ears / temples: the cards' outer envelope vs the groom's at the sides (sil.py
miss maps, card_offset / _under_envelope / SIDE_ENV_PCT), not more short cards. (2) Short hairs as SHORT tiles on the cap
(the cap's own picture) rather than cards, if the behind-ear patch matters. (3) Front: dark flecks = stray card edges /
dark strands at the hairline; front gaps (groom p10 18.8 vs 36.6; SHORT_DEPTH is dead here). (4) review-ab CLI after
2026-10-19 13:00 MT for the next A/B.

## hair-cards round 38 (2026-10-18, fresh session)
BEST CARDS FOR EXPORT: r38a (/mnt/data/hifipushie/haircards/exp/exar38a/hc_s2.glb + hc_s2_LOD1-3.glb; hair-only
lodx copies in exp/lodsr38a/) = f1 EXACTLY (every unique vertex and triangle of LOD0-3, glbcmp) + the merge's BACK_FACES.
EXPORT SETTINGS: the hair defaults at commit b5e5f064 (PART_DIP_WHOLE 1, PART_VISIBLE 1, ARCH 4 ...) + hair_clumps.FILL = 1.0
(exa26.py hc_s2 <out> hk.FILL=1; role hero, lods=True). LODs OK: y (t38/lods_r38a.png, g2 / g4 / g8 x front / 3/4 / back).
NOT approved yet (bin/approve: coordinator / Joe). Known faults (blind review, both r37c/r37d = this geometry): 3/4 front
lump, jagged dark V at the part from the front, a layered ridge in profile, crown ~12 px low at its shoulders from the front.
- (0) COORDINATOR DECISION on r37's open question: KEEP THE OUTLINE RULE. The part counts as shown only where the
  groom's OUTLINE dips (part_visible); the surface trough along the front half of Tess's part does not count. Reason:
  game readability is silhouette, and f1 (whose cover row spans her part) beat the alternatives in the blind review.
- (2) WHY THE RUN READ ~130 NOTCHED PART ROOTS AND THE PROBE NONE: the probe was wrong, not the run. The PART_DUMP npz
  stores St["Q"][:, ::2] and t37/notchprobe.py handed that to part_visible, which takes [:, ::2] again: the probe
  saw every 4th strand point, the run every 2nd. With the run's sampling (t38/np2.py) the dump reads 114 of 1129 head
  part roots >= 3 mm, p90 4.7 mm = the run's line (133 of 1302: + non-head roots). The real fault: per root the
  notch is NOISE around the threshold. t38/np3.py (top per 2 mm band = max or a high quantile; points every 1st / 2nd
  / 4th of the dump): >= 3 mm at 114 / 0 / 389 roots for the max, 342 / 304 / 493 for q .995, 348 / 243 / 0 for q
  .98; the median stays 1.2-2.3 mm. The outline is ONE view along the part, so roots differ only by where the part
  line sits across it (mm), which lands each on a slightly different band max. FIX: part_visible decides ONCE per
  part (PART_DIP_WHOLE 1: the median notch over the part-line roots; Tess 1.8 mm at the run's sampling -> not shown
  -> the arch row takes round 35's code path = f1). np2 after: 0 of 1129 at both samplings.
  STATE: tests (full hair set) + r38a (= defaults + hk.FILL=1 at this commit) for the f1 comparison.
- (1) TESTS: full hair set 162 passed (t38/tests.log, run at 45fc87ab = 2af333de + notes); clumps + lods 26 passed after
  the PART_DIP_WHOLE fix (b5e5f064).
- (3a) r37d (r37c + ARCH_ROOT_TAPER 0.025) crowntop front / 3/4 / side 12.4 / 7.7 / 7.0 px = r37c's to the tenth;
  t37/zz_r37d.png (gSc | r37c | r37d): my look, near identical, the 3/4 front lump on both (r37d's a touch softer at most).
  review-ab: "REVIEW FAILED" (its claude -p before 2026-10-19 13:00 MT) but it wrote the trios + key (t38/ab1:
  front X=old r37c, tq X=new r37d, side X=old) -> a fresh blind subagent reviews the trios.
  STATE: blind A/B running; r38a exporting (t38/q1.sh). NEXT: r38a vs f1 (glbcmp), LOD sheet (t38/lods.sh, + back).
- (3b) BLIND A/B r37c vs r37d (fresh subagent on review-ab's trios t38/ab1, key applied): TIE in every view ("a pixel diff
  found only scattered small changes"). The 3/4 front lump is a MAJOR on BOTH ("a card stands up as a raised shelf behind
  the part"), plus on both: a jagged dark V at the part from the front (card ends splaying at the part line), a layered
  ridge with flicked card ends in profile, no flyaways (the groom's fuzz raises and softens its outline). ARCH_ROOT_TAPER
  stays 0 (no gain). The lump is NOT a root-taper fault.
- (2b) r38a (= defaults at b5e5f064 + hk.FILL=1; exp/exar38a, exp/lodsr38a): "part visible: 0 of 1302 ... (1.8 mm)",
  arch row 17 / 10 / 10 / 5 cards per tier, cap fill 698 / 978 / 407 / 126 = f1's log lines. glbcmp vs f1 LOD0 hair:
  unique verts 53675 of 53675, unique tris 77248 of 77248: F1 REPRODUCED EXACTLY; the GLB's 20546 extra index tris are
  BACK_FACES (the merge's), the same triangles wound the other way. So r37c's 2 % = the per-root notch noise. crowntop
  front / 3/4 / side 12.5 / 7.9 / 7.3 px (f1 12.4 / 7.9 / 7.3).
  STATE: LOD sheet for r38a running (t38/lods.sh r38a: g2 / g4 / g8 x front / 3/4 / back -> t38/lods_r38a.png).
- (6) FRONT DEFICIT, measured first (t38/solidtop.py r38a: crowntop's deficit per third of the crown columns, groom mask
  and ours opened by 0 / 3 / 5 / 7 px = flyaway fuzz removed): front 19.0 / 5.5 / 12.9 px raw, 19.7 / 5.2 / 11.7 opened
  (left / centre / right third); 3/4 12.6 / 6.0 / 2.2; side 8.7 / 6.3 / 2.8. NOT fuzz: the groom's SOLID dome is wider at
  its shoulders (the upper sides from the front), ours is lower there (the reviewer's "crown slightly narrower").
  Levers queued after the LOD sheet (t38/q2.sh): r38b = r38a + ENV_PCT 94 (the top cap; 97 drew frizz arcs, b12),
  r38c = r38a + SIDE_EL (45, 70) (the dome's shoulders under the side rule: outer strands, SIDE_ENV_PCT 99).
- (4) LOD SHEET r38a (t38/lods_r38a.png: rows g2 / g4 / g8 x front, 3/4, back; LOD0-3 per row). LOD1-3 GLBs = f1's
  exactly (glbcmp: 36816 / 23196 / 14382 unique tris all shared). LOOK at each LOD's switch distance (LOD1 @ g2, LOD2 @
  g4, LOD3 @ g8): front holds one rounded crown at every tier; 3/4 LOD1 @ 2 m shows a few dark spiky flicks over the
  tie (small at 4 m, gone at 8 m); LOD3 @ 2 m (not its distance) has loose flicks at the right temple. Back: LOD1-3 read
  as one dome + tail. LOD0 from the BACK at 2 m reads differently from LOD1: the tail a pale striped split bulb and a few
  light blocky patches on the crown (hero tier, < 2 m; geometry = f1's, so f1 had it too, only now seen: f1's sheet had
  no back row). LODs OK: y at the switch distances; OPEN: LOD0 back tail / crown patches (check against the groom's
  back at g1backl before calling the hero tier done).
## Garrett cards c7 (2026-10-18, hair-garrett agent, fresh; order: side volume, front hairline, back carpet, all tiers + A/B)
- (1) SIDE VOLUME, measured ($HG/cards/c7/: miss.py = outline miss maps + a 4x3 band table, crop.py = shaded crops grm | ours,
  capdiag.py / capel.py / din.py / lie.py / objs.py = where roots, lying hair, cap and cards are; c7x.sh = hero trial with
  c7/hx7.py, which adds hq.<CONST> = hair_cap constants). Baseline c6s (= c6M's hero geometry): hair-mask miss vs the groom
  front 24.1 %, 3/4 25.5 %, side 12.1 %, back 6.8 %; the miss is the INNER edge at the temples and in front of the ear (the
  groom's silver temple patch runs down to a sideburn at mid-ear; ours ends at the ear's top), plus a 2-3 px thin outer rim.
  Look: out/c7_miss_c6s.png, c7_crop_base.png.
  NOT the cause (measured): roots outside the hairline (0.0 % of roots / lying points < -4 mm in every azimuth band; din.py,
  lie.py); short strands with no card at the temples (temple L 271 of 12416 roots no card; the 54k no-card strands are behind
  the ears / back, len p50 11-14 mm); the cap buried in the head (field at cap vertices +2..+6 mm, 0 % under, capel.py); the
  cap / cards not reaching low (per 10-deg band their lowest el is at or under the roots' p2, capel.py); a second groom object
  (hair_under = 288k stubble strands 2 mm, lying 0.6 mm: not the patch; objs.py).
  CAP ONLY renders (shots only=[[0,3100]], alpha game and alpha=off: out/c7_cap_only.png, c7_capop.png): even OPAQUE, the
  cap's outline in front of the ear stops at the ear's top with one narrow spur (the line's sideburn notch at az ~70);
  the groom's patch is a broad sheet from the temple down to mid-ear. The groom's temple hair is hair_even 21-85 mm long
  standing 6-11 mm (p50 / p90) off the scalp: the patch is LONG temple strands lying down and back over the region, i.e.
  CARDS' job, not the cap's.
  LEVERS TRIED (all hero, each proven live on the atlas, none moves the read; defaults unchanged, levers kept):
  c7a hair_cap.BASE_IN .3 / BASE_RAMP .6 (NEW levers; the cap's opaque base nearer the line): chart alpha 20.8k px changed,
  render identical by eye. c7b + hair_cap.KEEP_SOFT .4 / THIN_SOFT .4 (NEW: the line's strand thinning): 92k px, the cap's
  edge in front of the ear a touch fuller in profile (out/c7_b.png), nothing at the temple. c7c hair_clumps HL_SOFT .003 /
  HL_ALPHA 1 / BASE_IN .004 (hairline cards opaque from the root): tiles 35.6k px, render identical by eye (out/c7_c.png).
  STATE: committed (levers + cache keys: hair.py chart / atlas keys carry the four hair_cap levers). BEST unchanged = c6M.
## HANDOVER (hair-garrett c7, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: hair-heads2 local commits only. New levers (off at defaults): hair_cap.BASE_IN / BASE_RAMP / KEEP_SOFT / THIN_SOFT.
BEST = exp/c6M (unchanged; no new build beat it, so no A/B was run this session).
FINDING that redirects (1): the missing side mass is NOT short hair, the cap, the hairline or burial: it is the LONG temple
strands (hair_even, carded: 98 % of temple roots have a card) that in the groom lie down and back over the temple to mid-ear.
Their cards don't show there: in c6s only a few thin dark lines in front of the ear.
NEXT, in order: (1) inspect the temple cards themselves (exp/hlp/cut.pkl has cards P / hw / strands / layer): for clumps
rooted az 40-90, compare each card's centre line + width with its strands' points (do cards end early (TAIL / END share),
run narrow (HW_PER_STRAND, EDGE_FADE), sit under the cap (CAP_UNDER / clearance moved 2674 verts), or get dropped by the
hook / sideways rules?). Render only=layer ranges (exp json "layers") to see which layer should carry the patch. Fix that,
prove it on the 3/4 + profile crops (c7/crop.py) and miss.py's 3/4 row 2-3 left bands (73.7 % / 100 % now).
(2) front hairline (dark spiky), (3) back carpet: untouched. (4) review-ab CLI after 2026-10-19 13:00 MT for the A/B.
## Garrett cards c8 (2026-10-18, hair-garrett agent, fresh; order: temple cards vs their strands, fix, then front hairline / back carpet, all tiers + A/B)
- (1) TEMPLE CARDS vs STRANDS ($HG/cards/c8/: tc.py = cut.pkl cards rooted az 40-100 vs their strands; tglb.py = the hero GLB's
  triangles by region x layer: atlas alpha, area, strip GLBs; tcomp.py = per card (connected triangles) alpha root -> tip by
  aux.R; tuv.py = empty cards over the whole head + their UVs). Correction to c7: in the cut the temple strands are 19-24 mm
  (p10-p99 at az 40-100, el -15..35), not 21-85 mm. The cut's temple cards are FINE geometrically (83 cards, per layer median):
  length 18-20 mm vs strands 22, width 12-15 mm vs the strands' p90 spread 10-14, standoff 3-4 mm vs the strands' 5, facing
  |N.radial| .88 (flat on the head), 67-72 % of strand points inside. In the GLB, card AREA exists down to el -35 (12.7 + 19.4
  cm2 at el -35..-15 = the sideburn in front of the ear), but its atlas ALPHA there is 0.00 (el -15..-5: .38; above: .53-.68).
  CAUSE: EMPTY TILES. 263 of the hero's 1501 cards (522 of 5040 cm2, 10 %; 55 in the temple region, all layer 1, root el p50
  -7, az 78) wear a tile with nothing drawn (uv .097-.173 x .913-.968: a black slot in the atlas, out/c8_atlas_alpha.png).
  bake_tiles bakes each cluster's medoid card from its OWN strands, filtered by bake's IN_SHARE (60 % of a strand's points
  inside the card): a medoid whose strands leave it draws nothing (`if not segs: continue`), and the whole cluster is invisible.
  FIX (general): NEW hair_clumps.TILE_REP_DRAWN .5 (default) / TILE_REP_TRY 24 + _drawn_share(): the rep is taken in order of
  closeness to the medoid until one draws >= half its strands (else the best tried); bake_tiles logs medoid -> chosen drawn share.
  STATE: c8a (hero, the fix) running. NEXT: tglb / tuv on c8a (empty cards -> 0?), crops vs G88a at 3/4 + profile.
- (1b) c8a (TILE_REP_DRAWN .5): 3 of the 24 tiles were empty (medoid drawn share 0.00, 0.00, .39 -> chosen .70, .79, .87;
  log line "tile reps' drawn share"); cards with an empty picture 263 -> 192. The other 192 (incl. all 55 at the temple /
  sideburn, el -35..-15) are FLY cards (kind "fly", pooled halo / stray hairs, 2-4 mm wide, the strand-rows atlas's fly tile
  at u .47-.49): sparse by design, not empty. So there are NO baked (clump) cards below el ~-15 in front of the ear: the cut's
  temple cards end at el -15 at the lowest (tip el bins), and the cap's alpha there is .23 / .03. Groom points by object
  (c8/under.py, scalp coords): the patch in front of the ear (az 60-80, el -30..-10) has only 40-217 roots per 10-deg band,
  hair_even 12-17 mm long, the rest of its points are hair from above lying down.
  LOOK (out/c8_crop_a.png, grm | c6s | c8a at front / 3/4 / profile): c8a = c6s by eye. STOP RULE (temples): (1)-(2) did not
  visibly change the temples. The empty-tile fix is kept (correct and general: 71 cards visible again, no cost).
  PROPOSAL (not built): temple / sideburn cards placed as hair artists do: a dedicated row of short cards along the
  sideburn / temple hairline (rooted on the line, lying down-back along the groom's flow there, 12-20 mm, the hairline tile),
  instead of hoping the clump cut makes cards from 12-17 mm strands (MIN_STATIONS 3 made cards for them in c6 and lost the A/B
  at the back: apply it ONLY in the sideburn band, az 60-90 / el < -10, if this is tried).
- (2) COORDINATOR: top LENGTH / SWEEP vs G88a (Garrett v5 beside his photos: a tight dark short crop, a "carpet"). Measured
  (c8/tc.py <az0 az1 el0 el1> on cut.pkl, c8/top.py <tag> = top 45 % crops + hair px / outline top / orientation / lenmeas):
  card GEOMETRY is NOT short: over the top (el 60-90) cards 50 mm vs their strands' L50 52 / L90 55; front top (az +-40, el
  45-90) 32 vs 39 / 44 (-18 %); front band (el 25-45) 20 vs 23. Outline top: groom y 364 vs ours 369 (front), 365 / 368 (3/4)
  = ~4 mm lower. Hair area (id px) ours / groom: front 58 %, 3/4 62 %, profile 79 % (the sides and the front hairline, not the
  top). c8b = hk.HEAD_END .15 (cards run on to where 15 % of the strands still run): hair px +44 / +42 / +59: no change
  (dead for length: the cards already reach the strands' tips). The atlas tiles hold long continuous strands
  (out/c8_tiles_c8a.png). So the "short carpet" is not length: it is the card SURFACE: hundreds of 12-15 mm-wide flat cards
  in three layers, each shaded by its own plane (strands.round .55 = the normal only half bent to the volume), read as
  overlapping scales / a pile. Trial c8c: strands.round 1.0 (every card shades with the hair volume's normal).
- (2b) c8c = strands.round 1.0 (c7/hx7.py NEW st=<json>: spec hair.strands overrides): hair px / outline / orientation equal to
  c6s within 40 px; crops (out/c8_crop_c.png grm | c6s | c8c, front / 3/4 / profile / back): identical by eye. The carpet is
  NOT the per-card normal either (caveat: not checked that the preview's ONE_NORMAL path uses the GLB's normals unchanged; a
  quick flat-colour vs normal-only render would settle it). What the eye sees at 3/4 / profile: the surface is made of many
  short visible card PIECES, each ending in a tip / edge in the middle of the mass (three layers of 20-50 mm cards, the next
  card's end every ~10 mm), where the groom shows long continuous strands flowing from the whorl and swept to his right.
## HANDOVER (hair-garrett c8, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: hair-heads2 local commits only. NEW default hair_clumps.TILE_REP_DRAWN .5 (+ TILE_REP_TRY 24, _drawn_share): no tile is
baked empty any more (c6M had 3 of 24 empty, 71 cards invisible); by eye no change on Garrett. RISK: a shared default; it only
acts where a tile's medoid draws < half its strands (log line "tile reps' drawn share"); Tess not re-checked.
BEST = exp/c6M (unchanged: c8a / c8b / c8c equal it by eye, so no A/B was run).
Scratch $HG/cards/c8/: tc.py <az0 az1 el0 el1> (cut.pkl cards vs their strands per region), tglb.py / tcomp.py / tuv.py (GLB
triangles: atlas alpha by region / layer / card, empty cards + their UVs, strip GLBs in exp/c8s), under.py (groom points by
object per az / el band, groom_pts.npz), top.py <tag> (top crops + hair px / outline top / orientation + lenmeas).
Renders: exp/c8a (fix), c8b (HEAD_END .15), c8c (round 1.0); out/c8_crop_a.png, c8_crop_c.png, c8_top_c6s.png,
c8_tiles_c8a.png, c8_atlas_alpha.png.
FINDINGS: (a) temples: the cut makes no clump cards below el ~-15 in front of the ear (only sparse fly cards there); the
groom's patch there is 12-17 mm hair_even rooted az 60-80 / el -30..-10 plus hair from above lying down. (b) top: card
length = strand length over the top (50 vs 52 mm; front top -18 %); HEAD_END and round are dead for the read. The
deficits are AREA at the front / sides (58 % / 62 % of the groom's hair px) and the SURFACE (pieces, not flow).
NEXT, in order (both are card PLACEMENT, as hair artists do it, not more cut levers):
(1) top flow: a top layer of FEW LONG cards per part side that follow the groom's flow from the whorl / part to the front
and sides (fit to the medoid of LONG strands: the 45-57 mm top strands), with every other card's end tucked under them
(ends staggered under the layer above, not mid-surface). Measure: visible card ends per cm2 in an id pass (card id
change along the flow) vs 0 for the groom; lenmeas at 2x render size (1080 renders give nan streaks: crops too small).
(2) temples / sideburns: a dedicated row of short cards along the temple / sideburn hairline (az 60-90, el -35..0), rooted on
the line, lying down-back along the groom's flow, 12-20 mm, the hairline tile; or MIN_STATIONS 3 ONLY in that band.
(3) front hairline (dark, spiky) and back carpet: untouched. (4) review-ab after 2026-10-19 13:00 MT once a build beats c6M.
## Garrett cards c9 (2026-10-18, hair-garrett agent, fresh; coordinator: card PLACEMENT as artists layer cards, a general tool: (A) flow top layer, (B) hairline / sideburn row)
- (1) CODE (both opt-in, spec `hair.strands.flow_top` / `hair.strands.hairline_row`: true or {options}; defaults None = off;
  hair_cards.STRANDS carries the keys): hair_clumps.FLOW_TOP + flow_row(): head strands rooted over `el` 30 deg, the longer
  half (`len_pct` 50), grouped by their sweep (_sweep: the first PART_REACH's x share >= .35 -> -1 / 0 / +1, so no part is
  needed: Garrett's G88a has none), k-means `cards` 8 per group at 20k triangles (sqrt-scaled per tier, >= 2), each fitted
  on its MEDOID strand (fit medoid 1.0: the line follows the groom's flow), run to where `end` .15 of its strands still
  run, half width <= `hw` 12 mm, laid ONTO the strands' `pct` 94 envelope less ENV_UNDER (the card and its edges, past
  `seat` 15 mm from the root; root seated as ROOT_SEAT), top head layer, own tile group ("flow"). tuck_under(): every other
  head card's stations under a flow card (within its half width across) pulled in to `tuck` 1.5 mm under it (only
  lowered): their ends tucked under the layer above. HAIRLINE_ROW + hairline_row(): head strands rooted in |az| 50-100 /
  el -40..5 (az 0 = front), k-means `cards` 24 per side, fit with min_stations 3 / min_len 6 mm (only there; the cut keeps
  MIN_STATIONS 4), failed clumps split (depth 3), hw <= 8 mm, layer 1's offset, under the envelope. fit() takes
  min_stations / min_len. Tests tests/test_hair_card_rows.py (off by default; flow cards long, on top of the others' stations
  (< 5 % over); the row gives 10 mm temple hairs cards); test_hair_clumps green.
  STATE: committed. NEXT: hero trials c9a (flow_top), c9b (hairline_row) on G88a, crops vs G88a + c6M.
- (2) MEASURE: $HG/cards/c9/ends.py <exp tag> [frames=<render tag>]: VISIBLE CARD ENDS from the hero GLB (no render): samples
  where atlas alpha > .5, z-buffered in shots' frames + a synthetic TOP view; a sample is an END in its card's last 20 %
  (centre line from the strip pairs, root = the end nearer C). Prints hair px, END px share, ends / 10k hair px (cards
  with >= 15 END px visible), cap px share; maps c9/ends_<tag>_<view>.png (red = ends). The groom has none (continuous strands).
  c6M (front / 3/4 / top): END share .094 / .140 / .225, ends per 10k px 2.9 / 15.2 / 55.6, cap share .59 / .46 / .32.
- (3) c9a = flow_top defaults (23 flow cards, 49 mm p50, sweep groups -1 12.4k / 0 8.6k / +1 12.2k strands: the early sweep
  is NOT one-sided on G88a; 2752 stations of other cards tucked; hero 26640 index tris): ends .088 / .133 / .211, per 10k
  3.3 / 18.2 / 53.7 (no real change). LOOK (c9/crop_c9a.png grm | c6s | c9a, front / 3/4 / profile / back): front and 3/4
  = c6s; profile and BACK: a few dark flat patches on the crown (the flow cards read as separate darker flaps). Not better.
  23 cards cover too little of the top to change the surface. Trial c9c: cards 30 per group (~90), hw 15 mm.
- (4) c9b = hairline_row defaults (48 cards; hero 26552): miss.py profile ear row L 67.7 -> 62.9 %, centre 29.6 -> 26.8; ends
  unchanged. LOOK (c9/crop_c9b_z.png): the row cards in front of the ear are sparse thin strips: they wore the HAIRLINE tile
  (at_hairline -> edge: thin, HL_ALPHA-faded). NEW option `edge` (default False = the body tiles). c9d = edge off, hw 12 mm:
  profile ear row L 61.1 %; by eye a small solid patch above / in front of the ear, still well short of the groom's broad
  silver temple sheet down to mid-ear (c9/crop_c9d.png). Next: the band widened up (el -40..25, az 40-100) so the long
  temple strands from above that lie down over the patch get row cards too.
- (5) c9c = flow_top cards 30 / hw 15 mm (90 flow cards, 46 mm p50, 3091 stations tucked; hero 28320 index tris): ends
  .096 / .137 / .219, per 10k 3.7 / 18.8 / 55.8 (the measure does not move: the flow cards cover a share of the top only, the
  rest's ends still show between them). LOOK (c9/crop_c9c.png grm | c6s | c9a | c9c, 3/4 / profile / back): c9a's dark crown
  flaps gone; from the BACK the crown now shows radial streaks converging on the whorl like the groom's (c6s: a uniform
  curly carpet up to the top); profile top a little streakier; 3/4 = c6s. First change to touch the back carpet.
  STATE: c9L = flow_top {cards 30, hw .015} + hairline_row {hw .012, az 40-100, el -40..25}, ALL four tiers (c9/c9L.sh)
  running. NEXT: tiles vs c6s / c6o tiers, blind A/B vs c6M.
- (6) c9L = flow_top {cards 30, hw .015} + hairline_row {hw .012, az 40-100, el -40..25} at ALL four tiers (c9/c9L.sh; flow
  90 / 62 / ... cards, hairline row 50 / 34 ...). Index triangles hero 28892 (c6M 26040), main 11516 (10164), npc 5420
  (4704), far 1716 (1380): FAR OVER the crowd range (300-1500). ends .097 / .141 / .210, per 10k 3.7 / 16.7 / 54.8 (c6M 2.9 /
  15.2 / 55.6: the measure barely moves); miss 3/4 25.5 -> 24.4 %, profile 12.1 -> 11.6 %. LOOK (c9/crop_c9L.png grm | c6s |
  c9L): back crown streaks toward the whorl (closer); profile: a DARK sideburn spur in front of the ear (the groom's is
  silver); 3/4 / front = c6s.
  BLIND A/B (review-ab exit 4 = claude -p not before 2026-10-19 13:00 MT; its trios review/ab_c9L/trio_*.png + key.json went
  to a fresh blind subagent; old = c6o* (c4L = c6M's geometry, same shading script)): front TIE, 3/4 OLD ("crown a bit
  more one mass, front outline less ragged"), side NEW ("temple hair comes further forward"), back NEW ("keeps the lighter
  swept band on top of the crown; old is one uniform texture"), 2 / 4 / 8 m TIE -> NEW 2, OLD 1, TIE 4: a SLIM NEW.
  Shared MAJORs (both): too dark / brown at distance, bald temple-to-ear gap, thin sides, spiky card tips on the outline.
- (7) Rows skip tiers under `min_triangles` 3000 (the cut's triangles; far's ~1100 -> no rows: far = c6M's far; test
  test_rows_skip_tiers_under_their_min_triangles). c9M = c9L's settings with it, all tiers (c9/c9M.sh) building.
- (8) c9M (exp/c9M, c9/c9M.sh): hero / main / npc GLBs byte-identical to c9L's, far 1380 index triangles = c6M's far (no rows
  under min_triangles). BEST line updated to c9M (not approved; code defaults off: the rows live in the spec).
## HANDOVER (hair-garrett c9, 2026-10-18; stopped at the ~70 tool-call budget; nothing in flight)
STATE: hair-heads2 local commits only (not pushed). NEW (opt-in, spec hair.strands): `flow_top` (hair_clumps.FLOW_TOP,
flow_row, tuck_under) and `hairline_row` (HAIRLINE_ROW, hairline_row; `edge`, `min_triangles`), fit(min_stations, min_len),
tile group "flow". Tests tests/test_hair_card_rows.py (4) + test_hair_clumps green. BEST = exp/c9M (slim blind NEW vs c6M).
Scratch $HG/cards/c9/: ends.py (visible card ends: END px share + ends / 10k px, front / 3/4 / synthetic top), c9L.sh (all
tiers with st=<json> + renders), c9M.sh, q1-q3.sh (hero trials via c7x.sh 'st=<json>'), crop_c9{a,b,c,d,L}.png, miss_*.png;
review/ab_c9L (trios + key.json).
LOOK (mine, first): c9M is c6M with two local gains: from the back the crown streaks into the whorl like the groom (c6M: a
uniform carpet to the top), and the profile temple comes a little further forward. It is NOT the groom yet: front and 3/4
look as c6M (flat dark-flecked front, spiky outline tips), the sideburn spur in front of the ear is DARK where the groom's
is silver, the temple-to-ear region is still mostly bald, and at 2-8 m it reads too dark / brown (the reviewer's MAJOR at
every distance).
FINDINGS: (a) the visible-ends measure hardly moves (top 55.6 -> 54.8 per 10k): 90 flow cards over the top cover a share
of it and tuck 3k stations, but the other cards' ends still show between them. To make the top read as long flow, the flow
layer has to COVER the top (cards wide / many enough to close it, e.g. hw 20 mm, cards 60, and the tiles' long strands
lit, not depth-shaded: the flow tiles were baked with the groom's depth shade though they lie on top). (b) G88a's early
sweep is not one-sided (-x 12.4k / back 8.6k / +x 12.2k strands): "swept to his right" is not in the first 3 cm. (c) the
hairline row is placement-limited: 50 cards from roots in the band; the groom's broad silver temple sheet is long hair
from above lying down, which the row only partly takes (band widened to el 25); its cards come out dark (tile tone).
NEXT, in order: (1) flow layer coverage + tone: hw .02 / cards 60, flow tiles baked without the depth shade (the top is
lit); measure ends / 10k on top + back tile. (2) temple sheet: row cards from strands that PASS through the band (not only
rooted there), lighter tone (WISP_LIFT-style lift for the row), the denser cap there (not built this session). (3) tone at
distance (too dark at 2-8 m in both builds). (4) review-ab's CLI after 2026-10-19 13:00 MT.
FOR TESS (how her cards could use (A)): her round-34/35 ARCH row is the same idea for a ponytail crown (cards on strands
over the dome, raised to the envelope, the mass filled under it). flow_top is the general form: no part needed (groups by
sweep), medoid-following lines, the card AND its edges laid on the `pct` envelope, and tuck_under() lowers every other
head card's stations under a flow card by `tuck` (instead of ARCH_FILL raising the cap under the arch). On Tess: try
`hair.strands.flow_top = {"el": 45, "len_pct": 60, "cards": 12, "pct": 94}` with ARCH 0; tuck_under should remove the
daylight under the crown cover without the cap fill; check the part rule (flow groups do not split at the part: add the
part side to the grouping if her groom shows one).
## Garrett cards c10 (2026-10-18, hair-garrett agent, fresh; order: flow layer covering the top, temple sheet from passing strands, tone at distance, export settings in the spec + A/B vs c9M)
- (1) CODE (opt-in): FLOW_TOP / HAIRLINE_ROW `lit` (a card key "lit" in bake: depth shade off, tone x (1 + lit); lit rows
  get their own tile group "hrow"; c9's flow tiles had the groom's depth shade though they lie on top). HAIRLINE_ROW `pass`
  (+ `pass_el` 60, `pass_back` 12 mm): also head strands rooted above the band (el up to pass_el) with a station IN it, their
  card cut from pass_back before they enter (not root-seated): the groom's temple sheet is long hair from above lying down.
  STATE: tests green (4); hero trials c10a (flow cards 60 / hw 20 mm / lit .3, c9's row), c10b (+ row pass / lit .4),
  c10c (flow cards 90 / hw 25 mm / el 20) queued (c10/q1.sh). NEXT: ends.py / top.py / miss.py + crops vs c9M.
- (2) c10a (flow cards 60 per group = 180 / hw 20 mm / lit .3; c9's row): ends per 10k front / 3/4 / top 4.5 / 19.5 / 57.9
  (c9L 3.7 / 16.7 / 54.8: MORE ends: the flow cards' own ends count, 180 of them); top.py orient g1v0 -2.6 / g1v1 17.8 /
  g1left 5.2 (groom 1.8 / 21.8 / -88.8) = c9L's; hero L* front 44.0 (c9L 43.3, groom 46.3), 3/4 41.9 (41.1 / 50.0).
  31100 drawn triangles: OVER.
- (3) TONE AT DISTANCE measured (c10/dtone.py <tags> [views]: hair px L* a* b* p50 vs grm): c9L main / npc / far at g2-g8
  are L* 4-6 under the groom front-on and 11-12 under at 3/4 (g2v1 39.9 vs 50.7), b* 3.7 vs 3.0 (warmer = "brown"); the
  back matches (g1back 37.2 vs 37.5). So the dark is the FRONT / SIDES (the missing silver temple sheet + TONE_FRONT .85,
  a Tess number), not a global gain. CODE: look `tone_front` / `tone_back` override TONE_FRONT / TONE_BACK per model
  (in the tile cache key).
- (4) COORDINATOR DECISION (2026-10-18): the budget counts DRAWN triangles, back faces included (Garrett v6 hero 26148 of
  25000). CODE: cards_job gives fit_budget (budget - cap - 2 x other fixed) / 2 when hair.BACK_FACES (segments lengthen
  to 1.5x first, then cards go by prio); info["drawn_x"]. c10m = c9M's settings under it (hero) queued (c10/q2.sh);
  c10b ran with the old count, c10c with the new.
- (5) DRAWN BUDGET works: c10m (c9M's settings) hero 24224 drawn triangles (c9M 28892), segment 8 -> 10.2 mm, no card
  dropped; c10c 24856 (segment 11.7 mm). LOOK (c10/crop_c10m.png grm | c9L | c10m | c10b | c10c): c10m = c9L by eye at
  3/4, profile, back (the longer segments cost nothing visible at 1 m). ends per 10k front / 3/4 / top: c10m 2.5 / 10.6 /
  55.0, c10c 2.1 / 11.8 / 64.0.
- (6) c10b (c10a + row pass / lit .4): 3/4 L* 41.9 -> 43.3; the temple goes silver like the groom's sheet but as FLAT
  SHINGLES (wide 12 mm lit plates); the bald gap in front of the ear stays (the pass strands join the same 24 clusters a
  side: no new cards lower down). c10c (flow 90 per group / hw 25 mm / el 20 + row pass): front L* 45.6 (groom 46.3), 3/4
  44.8 (c9L 41.1, groom 50.0): the lighter top / temple band of the groom; the top's flow layer reads as a smooth light
  plate with the radial lines (groom-like from the back), top ends per 10k UP (64: the flow cards' own ends). Shingles at
  the temple remain. CODE: hair.export carries tone_front / tone_back / card_sat (card-only, the groom's look untouched).
  STATE: c10d = c10c's flow + row hw 8 mm / lit .25 + tone_front 1.0 (hero) running (c10/q3.sh). NEXT: pick, spec, all tiers, A/B.
- (7) c10d (hero) = c10c's flow + row hw 8 mm / lit .25 + look tone_front 1.0: L* front 46.8 (groom 46.3), 3/4 45.7 (50.0),
  side 43.2 (44.3), back 37.3 (37.5); the temple shingles smaller than c10c's, silver; the gap in front of the ear smaller
  but there. Picked.
- (8) SPEC: hg_G88a (store version 7; before = c10/spec_G88a_before.json): hair.strands.flow_top = {cards 90, hw .025,
  lit .3, el 20}, hair.strands.hairline_row = {hw .008, az [40, 100], el [-40, 25], pass true, lit .25}, hair.export =
  {card_gain 2.1, tone_front 1.0}. c10L = ALL four tiers from the spec with NO overrides (c10/c10L.sh; exp/c10L).
  DRAWN triangles (back faces counted) vs budgets.py (role hero): hero 24856 / 25000, main 12312 / 12500, npc 6368 / 8250,
  far 1380 / 2500 (c9M: 28892 / 11516 / 5420 / 1380: hero was over). Segments 11.7 / 14.3 / 25 / 50 mm, no card dropped.
  Distance tone (dtone.py, 3/4): main g2v1 44.7 (c9M 39.9, groom 50.7), g4v1 45.7 (40.1 / 51.9), g8v1 46.2 (40.7 / 52.7);
  npc ~1 under main; FAR still 37-39 (no rows at far, its own atlas: the far tier is the dark one now).
  BLIND A/B vs c9M (review-ab exit 4 again: trios review/ab_c10L + key.json to a fresh blind subagent): front TIE, 3/4 NEW,
  side NEW, back NEW (barely), 2 m NEW, 4 m NEW (slightly), 8 m TIE -> NEW 5, OLD 0, TIE 2.
  Shared MAJORs: still too dark at 4-8 m ("dark-haired, not grey"), temple-to-front-of-ear coverage missing, flat thin top
  silhouette vs the groom's swept volume, shingle / scale look on the sides + stray dark strand lines by the ears, jagged fringe.
## HANDOVER (hair-garrett c10, 2026-10-18; nothing in flight)
STATE: hair-heads2 local commits only. BEST = exp/c10L (blind NEW 5 / OLD 0 / TIE 2 vs c9M; NOT approved), built from
hg_G88a's SPEC with no overrides: the assembly's export picks it up (hair.strands flow_top / hairline_row, hair.export
card_gain 2.1 / tone_front 1.0). Every tier is under budgets.py in DRAWN triangles (coordinator rule: back faces count).
CODE (c10): hair.cards_job fits cards to (budget - cap - 2 x other fixed) / 2 when BACK_FACES; FLOW_TOP / HAIRLINE_ROW `lit`;
HAIRLINE_ROW `pass` / `pass_el` / `pass_back`; look / export tone_front, tone_back (card_sat via export too). Tests: rows +
back faces green (no unit test of the drawn budget: checked on the c10L export).
Scratch $HG/cards/c10/: q1-q3.sh (hero trials), c10L.sh (all tiers from the spec), dtone.py (hair L*a*b* p50 vs grm per
view), crop_c10{a,b,m,d}.png, spec_G88a_before.json; review/ab_c10L.
LOOK (mine, first): c10L is the first build whose top and temples carry the groom's lighter silver band (3/4 and side);
front matches the groom's tone. Not the groom yet: the temple-to-ear sheet is still short (gap in front of the ear), the
temple reads as shingles, the top is flat/low vs the groom's swept volume, and the FAR tier stays dark.
NEXT: (1) far tier tone (its L* 37-39 vs 50: lift its atlas / tint, it has no rows; or rows at far with a triangle check).
(2) the gap in front of the ear: more row clusters for the low band (pass strands join 24 clusters a side; give the
el < -10 band its own clusters) + the denser cap there (not attempted). (3) shingles: the row cards' tile picture / width
(8 mm lit plates still read as scales). (4) top volume (flow layer env pct / lift).
## Garrett cards c11 (2026-10-18, hair-garrett agent, fresh; order: far-tier tone, the gap in front of the ear, temple shingles, top volume / profile sweep, drawn-budget unit test, all tiers + A/B vs c10L)
- (0) LOOK at c10L before work (c11/crop_far0.png grm | main | far, g2 front / 3/4): beyond the tone, the cards' hair
  AREA is ~58 % of the groom's at 2 m (dtone n: grm 2434 / main 1405 px front, 3179 / 1993 at 3/4): the groom's sides
  stand off the head down to the ear, ours lie flat and stop at the temple; far is one flat dark tone (no silver).
  dtone c10L 3/4: far L* 37.4 / 37.9 / 38.9 at g2 / g4 / g8 (groom 50.7 / 51.9 / 52.7, main 44.7 / 45.7 / 46.2); front far
  41.8 / 42.4 / 44.4 (groom 46.8 / 47.2 / 49.9). b* 3.7-3.9 vs 3.0 (warm) at every tier.
- (1) CODE: hair.export.tier_look {tier: {card_gain, card_sat, tone_front, tone_back, card_grey}} (cards_job: over
  export card_gain / tone_*: the far tier's atlas is its own, so its tone is set without touching the others').
  hair.card_allowance(budget, cap, other): the drawn-budget arithmetic (cap once, the rest x2 with BACK_FACES) as a
  function; test_every_tier_fits_its_drawn_budget_back_faces_counted (tests/test_hair_card_rows.py, every CARD_TIER,
  back faces on / off). HAIRLINE_ROW `low_el` / `low_cards` / `low_hw`: the band's strands entering under low_el (root,
  or a passing strand's first station in the band) clustered on their own (c10: they joined 24 clusters a side and the
  cards followed the upper strands). Tests 5 green.
  Far trials (c11/far.sh, tier_look far): c11f1 card_gain 2.95 / card_sat .8 (target: main's L*, a x1.4 linear gain
  read from the L* gap), c11f2 3.5 / .8. STATE: running (c11/q1.sh). NEXT: dtone vs grm / c10L far.
- (2) FAR TONE c11f1 / f2 (dtone, front g2 / g4 / g8 | 3/4): f1 (gain 2.95) 49.3 / 49.9 / 51.2 | 45.2 / 45.6 / 46.7, f2 (3.5)
  53.2 / 53.9 / 55.2 | 49.3 / 49.7 / 50.6 (groom 46.8 / 47.2 / 49.9 | 50.7 / 51.9 / 52.7). Lightness moves as computed, but
  b* went 3.7 -> 6.2-6.6 (BROWN by eye, c11/crop_far1.png): card_sat .8 RAISED saturation (the look's card_sat is .35 =
  eevee_sat; a tier_look card_sat replaces it). The front / 3/4 split (front over, 3/4 under) is the far tier's missing
  silver sides; one gain sits between. c11f3 = gain 3.2 / sat .4, c11f4 = gain 3.2 / sat .25 (target b* 3.0) queued.
  CODE: HAIRLINE_ROW `rise` (row cards raised toward the side envelope, held under it): hero trials c11a (low band
  clusters), c11b (+ flow pct 98, row lit .12), c11c (+ rise .6) queued (c11/q2.sh, q3.sh).
  Baselines c10L: miss.py front temple rows L / R 29.5 / 32.1 %, ear rows 40.6 / 35.3; 3/4 ear R 47.8; profile ear L
  (front of the ear) 63.8 %; top.py front width 168 px (groom 182), profile orient 0.8 (groom -88.8).
- (3) FAR TONE picked: c11f4 = tier_look far {card_gain 3.2, card_sat .25} (1380 triangles, unchanged): dtone front g2 /
  g4 / g8 51.2 / 51.9 / 53.3, 3/4 47.1 / 47.5 / 48.6, b* 3.5 (groom 46.8 / 47.2 / 49.9 | 50.7 / 51.9 / 52.7, b* 3.0; c10L far
  41.8 / 42.4 / 44.4 | 37.4 / 37.9 / 38.9). Errors +4 front / -4 at 3/4 (c10L -5 / -13): one gain sits between the front
  and the silver sides the far tier has no rows for. c11f3 (sat .4) b* 4.3. Grey-brown by eye fixed (c11/crop_far1.png).
- (4) HERO TRIALS (c11/crop_c11abc.png grm | c10L | c11b | c11c, front / 3/4 / profile): c11a (low band clusters: row 48
  -> 83 cards) profile front-of-ear miss 63.8 -> 56.7 %, front / 3/4 unchanged; c11b (+ flow pct 98, row lit .12) top y
  -1 px, miss total front 22.7 -> 22.2; c11c (+ rise .6) 55.5 %, width 169 px (groom 182, c10L 168). All 24708 drawn tris.
  LOOK: c11a-c c10L by eye: the temple still reads as light flat plates (shingles), the sideburn sheet in front of the
  ear is still a small patch + dark wire hairs, the top no higher. Small measured gains only; rise moved nothing visible
  (the row cards are few and already at the envelope: the side mass is the head cards' layers, not the row).
- (5) CROWN LEDGE (coordinator, assembly s7 evidence: back standoff 3-4 mm to el ~60-66 then 9-10 mm, a 6-7 mm step;
  same in c6M). standoff.py on c10L hero: r98 by elev (6 deg bins) ... 104 / 107 / 114 / 115 ...: +7 mm in one bin at the
  assembly frame's ~50 deg. Suspect: SIDE_EL (60, 80) (sides: top layer on the clump's outer strands, SIDE_OUT_PCT; top:
  0.6 x spread capped at HEAD_SN_MAX, ENV_PCT 90 vs SIDE_ENV_PCT 99). Trials c11d1 SIDE_EL (40, 85), c11d2 (20, 85) on
  c11c's settings queued (c11/q4.sh). NEXT: standoff curve + back crops.
- (6) LEDGE trials: c11d1 SIDE_EL (40, 85) and c11d2 (20, 85) give the SAME standoff curve as c11c to the mm (r98 by 6 deg
  ... 104 / 107 / 114 / 115 ...): SIDE_EL is a DEAD lever for this step (constant not reaching the even groom's clumps cut,
  or the cut cached without it; not traced). c11/standl.py (r98 per export layer range on the back midline) found cards
  (layer0-2) only from the assembly frame's elev ~48 up, the cap alone under it; its per-range numbers do not add up to
  standoff.py's whole-mesh curve (glbload's face order vs the report's layer ranges: unverified), so the step's owner
  (top cards starting over a cap-only back, vs the cap itself) is NOT settled.
- (7) SPEC (before = c11/spec_G88a_before.json): hair.strands.flow_top + pct 98; hairline_row + lit .12, low_el -10 /
  low_cards 24 / low_hw .012, rise .6; hair.export.tier_look {far: {card_gain 3.2, card_sat .25}}. c11L = all four tiers
  from the spec, no overrides (c11/c11L.sh) building.
- (8) c11L (exp/c11L, all four tiers from the spec, no overrides): DRAWN triangles hero 24708 / 25000, main 12412 / 12500,
  npc 6560 / 8250, far 1380 / 2500. dtone 3/4: far g4 / g8 47.5 / 48.6 (c10L 37.9 / 38.9, groom 51.9 / 52.7), front far
  51.9 / 53.3 (groom 47.2 / 49.9); main 3/4 46.4 / 46.3 (c10L 45.7 / 46.2).
  BLIND A/B vs c10L (review-ab exit 4 again on 2026-10-19 before 13:00 MT; trios review/ab_c11L + key.json to a fresh blind
  subagent): front TIE, 3/4 NEW, side NEW, back TIE, 2 m NEW, 4 m NEW, 8 m NEW, far 4 m front NEW -> NEW 6, OLD 0, TIE 2.
  (the reviewer read the temple / front-of-ear patch as the main 1-2 m difference, and the far tone at 4-8 m.)
  Shared MAJORs: volume (tight to the skull, no lift on top / puff at the sides; small silhouette, front views), thin side
  coverage above / in front of the ears, jagged hairline with stray dark crossed strand lines by the ears, shingled
  side texture to 2 m, a separate light top / crown cap with a tonal seam to the darker back / sides, a bluish cast at
  the sideburn / temple.
## HANDOVER (hair-garrett c11, 2026-10-19; nothing in flight)
STATE: hair-heads2 local commits only (not pushed). BEST = exp/c11L (blind NEW 6 / OLD 0 / TIE 2 vs c10L; NOT approved),
built from hg_G88a's SPEC with no overrides (spec before: $HG/cards/c11/spec_G88a_before.json). Every tier is under
budgets.py in DRAWN triangles.
CODE (c11): hair.export.tier_look {tier: {card_gain, card_sat, tone_front, tone_back, card_grey}} (per-tier card look; NB
card_sat REPLACES the look's (.35 on G88a): .8 made far brown); hair.card_allowance + test_every_tier_fits_its_drawn_budget_
back_faces_counted; HAIRLINE_ROW low_el / low_cards / low_hw (low band clustered on its own), rise (toward the side
envelope). Tests tests/test_hair_card_rows.py 5 green.
Scratch $HG/cards/c11/: far.sh (one tier + export overrides via hx7 ex=<json>), q1-q4.sh, c11L.sh, standl.py, crop_far0/1.png,
crop_c11abc.png; review/ab_c11L (trios, key, args).
LOOK (mine, first): c11L's real gain is the FAR tier: it was one dark flat tone at 4-8 m, now a mid grey near the groom's
(neutral, b* 3.6). At 1 m it is c10L plus a little more hair in front of the ear (profile miss 63.8 -> 55.5 %); the temple
still reads as light shingles, the sides lie tight (front width 169 px vs the groom's 182), and the top is no higher.
FINDINGS: (a) far front / 3/4 cannot both match with one gain: front +4, 3/4 -4 L* (the silver sides the far tier has no
rows for). (b) rise / pct 98 / SIDE_EL move almost nothing: the side and top volume is set by the head cards' layers /
cap, not by the rows or the envelope caps. (c) CROWN LEDGE (coordinator, assembly s7): confirmed in c11c's GLB (+7 mm in
one 6 deg bin on the back midline); SIDE_EL (40-85 / 20-85) is a DEAD lever (identical curve); owner not settled
(c11/standl.py: cards only from that elevation up over a cap-only back, but its per-range sums did not reproduce
standoff.py's curve: check glbload's face order first).
NEXT, in order: (1) crown ledge: settle the owner (per-layer standoff with verified face ranges; is the groom's own strand
envelope stepped there?), then grade the back's cap / layer0 up (or the top layers down) across the step. (2) side / top
volume: the head cards' layer offsets on the sides (SIDE_OUT_PCT, HEAD_SN_MAX) vs the groom's 99th pct radius: measure
the cards' radius vs the strands' by region before choosing a lever. (3) shingles: the row / temple cards' tile picture
(fine strands, soft edges) rather than lit plates. (4) review-ab's CLI after 2026-10-19 13:00 MT.
## Garrett cards c12 (2026-10-19, hair-garrett agent, fresh; order: crown ledge cause, side / top volume by region, temple shingles' texture, tonal seam / sideburn cast, A/B vs c11L)
- (1) CROWN LEDGE, CAUSE: the GROOM. c12/ledge.py <exp>: back midline (|x| < 6 mm, behind C = c8/C.json [0, -.0511, 1.6914])
  by elevation over C (6 deg bins), standoff = radius - the strand roots' radius in that bin; groom from exp/hlp/cut.pkl's St.
  groom so50 by elev 18 / 24 / 30 / 36 / 42: 2 / 2 / 1 / 9 / 8 mm (an 8 mm step in ONE bin: the long top hair's ends over
  the short back); groom so98 6 / 8 / 10 / 11 / 11 (graded over ~20 deg by the longest tips). c11L cards (all) so98 3 / 3 / 4 /
  9 / 9: the cards copy the median's step, not the tips' grade (cap 4-6 everywhere; layer0-2 start at elev 36, 2-3 mm
  under it). c11's standl.py "did not add up" because standoff.py centres a hair-only GLB on the hair's mean y (no head
  mesh), not because of face order (layer ranges in the report are [start, COUNT]).
  Lever: the head cards stop where 35 % of their strands still run (HEAD_END .35): the tips that grade the groom are
  cut off. Trials c12e1 HEAD_END .15, c12e2 .05 (c12/q1.sh; hx.sh = hero only + ledge + vol). STATE: running.
- (2) VOLUME BY REGION (c12/vol.py <exp>: standoff over the roots' radius in that direction, groom vs card surface samples;
  coverage = 2-deg direction cells with groom > 2 mm that also hold cards > 2 mm; front half-width p99.5 at z over C):
  c11L | region groom so p50/p90/p98 | cards p50/p90/p98 (mm)
  top 6.7/11.4/15.4 | 4.5/8.6/10.9; crown-back-top 7.8/12.3/16.2 | 5.3/9.7/13.2; temple 3.6/9.7/12.5 | 2.6/5.9/7.4;
  side over the ear 4.0/10.6/13.2 | 3.8/7.0/9.4; side top 8.1/13.2/17.0 | 5.0/9.9/13.3; back 3.5/5.8/13.1 | 2.4/4.7/6.2.
  Coverage 0.99-1.00 everywhere. Half-width at z 0/30/60/90 mm: groom 92.4/87.3/72.0/20.8, cards 89.4/83.6/67.9/12.0.
  => not coverage: the cards' outer surface sits 3-4 mm (p90) / 4-5 mm (p98) under the groom's in EVERY region, worst at
  the temple (p90 61 %). Head layers are spread by min(sn, HEAD_SN_MAX 3 mm) x (-.6, 0, .6) and capped at the ENV_PCT 90
  envelope - ENV_UNDER 1 mm. Trials c12v1 HEAD_SN_MAX .006, c12v2 ENV_PCT 95 + ENV_UNDER 0 (c12/q2.sh). STATE: queued.
- (4, measured first) TONE BY REGION (c12/rtone.py, profile g1left: hair bbox top 22 % / back 35 % lower half; L* b* fine
  blotch): groom top 42.9 / back 38.3; c11L top 50.6 (+7.7: the light top cap) / back 36.1. 3/4 (g1v1) side behind the
  ear: groom 53.7, c11L 44.0 (-9.7: the silver sides). Fine strand texture (std L* - blur 1.5) top groom 5.1 vs 3.8.
  Suspect the flow top layer's lit .3 (tone x 1.3, no depth shade) and the row's lit .12 (temple plates). Trials c12t1
  flow lit 0, c12t2 + row lit 0 (c12/q3.sh, with hero renders + rtone). STATE: queued.
- (5) LEDGE lever: c12e1 HEAD_END .15 = c11L's ledge curve to the mm (cards still start at elev 36; layer counts +40 / +100 /
  +88 elsewhere): DEAD for the step (c12e2 .05 stopped). By eye (c12/ledge_look.png, back / profile, groom | c11L) the
  step is not visible from behind in either; what reads is the light crown cap. VERDICT: the ledge is the frozen groom's
  own (median standoff 1 -> 9 mm at the weight line); the cards copy it faithfully. Grading it would mean cards
  departing from the approved groom (or a groom change): coordinator's call, not done.
- (6) VOLUME levers: c12v1 HEAD_SN_MAX .006 = c11L to the decimal (DEAD: the head clumps' spreads are under the 3 mm cap).
  c12v2 ENV_PCT 95 + ENV_UNDER 0 (alive): cards p90 top 8.6 -> 9.5, crown 9.7 -> 10.6, temple 5.9 -> 6.5, side over ear
  7.0 -> 7.6 (groom 11.4 / 12.3 / 9.7 / 10.6); half-width 89.4/83.6/67.9/12.0 -> 90.2/84.4/69.4/17.7 (groom 92.4/87.3/72.0/20.8).
  CODE: hair_clumps.HEAD_LIFT (m, default 0): every head layer out along its normal (still under the envelope, root
  seated). Trials c12h1 HEAD_LIFT .0025, c12h2 + ENV_UNDER 0 (c12/q4.sh). STATE: queued behind the tone trials.
- (7) TONE trials (rtone, profile top / 3/4 top | profile temple | 3/4 side behind the ear; groom 42.9 / 42.6 | 60.4 | 53.7):
  c11L 50.6 / 49.4 | 61.4 | 44.0; c12t1 (flow_top lit 0) 47.2 / 45.7 | 63.4 | 44.5; c12t2 (+ row lit 0) 47.2 / 46.7 | 50.8 | 41.8.
  LOOK (c12/crop_t.png grm | c11L | t1 | t2): t1 takes the pale crown cap away (the seam to the back softens; still +4
  L* over the groom on top); t2 also darkens the temple plates, but the groom's temple IS silver (60.4): t2 loses it
  (-10 L*), so the row keeps lit .12. Picked: flow_top lit 0. The plates' look is not their tone alone (their facing /
  sameness): shingles NOT fixed. The 3/4 side behind the ear stays ~-9 L* (the groom's silver sides; card_grey per card
  from the locks' grey: next lever, not tried).
- (8) HEAD_LIFT trials: c12h1 HEAD_LIFT .0025: cards p50 +0.1-0.4 mm, p90 / p98 / width unchanged (the envelope pulls
  the lifted cards back: the outer surface IS the ENV cap); c12h2 (+ ENV_UNDER 0) = c12v2. So the side / top volume lever
  is the envelope (ENV_PCT / ENV_UNDER), not the layer offsets: HEAD_LIFT stays in the code at 0 (dead while the cap binds).
  ENV_PCT 97 drew frizz arcs on Tess (b12): 95 / under 0 is the step taken.
- (9) c12L = c11L's spec + overrides st flow_top lit 0, hk.ENV_PCT 95, hk.ENV_UNDER 0, all four tiers (c12/c12L.sh: build,
  renders, vol, rtone, A/B tiles in review/ab_c12L). STATE: building. NB the ENV constants are module-wide (Tess too):
  promote to a spec key (hair.export / strands) before making them defaults.
- (10) c12L built (exp/c12L; DRAWN tris hero 24708 / main 12412 / npc 6560 / far 1380 = c11L's, all under budget). vol: cards
  p90 top 9.5 / crown 10.6 / temple 6.5 / side over the ear 7.6, half-width 90.2/84.4/69.4/17.7. rtone top 47.1 / 45.9.
  review-ab exit 4 again ("REVIEW FAILED", 2026-10-19 ~01:45, before the 13:00 MT fix); trios review/ab_c12L + key.json
  to a fresh blind subagent: front TIE, 3/4 NEW (weak), side OLD, back OLD, 2 m OLD, 4 m npc NEW (weak), 8 m TIE,
  far 4 m TIE -> NEW 2 / OLD 3 / TIE 3: c12L LOSES. The reviewer preferred c11L's LIGHTER top (reads the groom's top as
  pale strands over a dark back in side / back views): my rtone "top" box (upper 22 % of the profile bbox, groom 42.9)
  measured the wrong thing (dark top-front + light crown edge averaged); the flow lit 0 change went against the eye.
  The ENV 95 volume gain (+1 mm p90) is too small to be seen (front TIE). BEST stays c11L.
## HANDOVER (hair-garrett c12, 2026-10-19; nothing in flight)
STATE: hair-heads2 local commits only (not pushed). BEST = exp/c11L (unchanged; c12L lost the blind A/B 2-3-3).
Coordinator: main dc4f3c21 has hair-heads2 through c10; the report's "triangles" = DRAWN there. Next session: MERGE
origin/main first (no rebase).
FINDINGS: (a) CROWN LEDGE = the frozen groom's own: the strands' median standoff steps 1 -> 9 mm at elev 30-36 over C on the
back midline (the long top hair ends over the short back); the cards copy it. Only the longest tips (so98) grade it.
HEAD_END .15 does not move it. Not visible from behind at 1 m in either. Grading = departing from the approved groom:
coordinator's call. (b) VOLUME: coverage is full; the cards' outer surface is 3-4 mm (p90) under the groom's in every
region, worst at the temple. HEAD_SN_MAX (spreads under the cap) and HEAD_LIFT (envelope pulls it back) are dead; the
ENV cap (ENV_PCT / ENV_UNDER) is the live lever but 95 / 0 gives only +1 mm. Next: ENV_PCT per region (sides / temple at
97-99 like SIDE_ENV_PCT already is: check why SIDE_ENV_PCT 99 does not lift the temple: side_weight's C / elev, or the
temple cards are capped by the top env) and a measured silhouette gate (front width at z 60 / 90: 69 / 18 vs 72 / 21 mm).
(c) TONE: the flow top's lit .3 is what makes the top light; the eye (blind) prefers it (lighter crown = the groom's pale
crown strands). The row's lit .12 gives the temple its silver (lit 0: -10 L*). Keep both. A region tone item must be
cut per view by what the reviewer names (crown band in back view, top-front in profile), not a bbox fraction.
(d) Shingles / sideburn bluish strip: untouched (the reviewer still names both); next = the temple cards' picture
(tone_ratio / kid spread / EDGE_FADE on hrow cards) on one tile first.
CODE (c12): hair_clumps.HEAD_LIFT (default 0, no effect). Scratch $HG/cards/c12/: ledge.py, vol.py, rtone.py, hx.sh (hero +
ledge + vol), q1-q4.sh, c12L.sh, crop_t.png, ledge_look.png; review/ab_c12L (trios, key, blind verdict above).
NEW BUDGET RULE (coordinator, 2026-10-19, arrived at the end of c12: NOT implemented, first job next session after the
merge): a role's hair_cards DEFAULT (hero 25k ...) counts CARD FACES (one side); DRAWN triangles (back faces included)
must stay under the role's RANGE maximum (hero 50k, main_npc 20k, secondary_npc 8k, crowd 1.5k), and the vertex count is
reported as well. To do: hair.card_allowance (src/hifipushie/hair.py:2562, used at :2883) takes (faces default, drawn max)
and returns the cards' allowance = min(default - fixed faces, (drawn max - cap - bf x other) / bf); the report adds
"vertices"; tests/test_hair_card_rows.py::test_every_tier_fits_its_drawn_budget_back_faces_counted asserts both limits;
then rebuild every tier of c11L's settings (Garrett gets back ~2x card faces: judge by the A/B whether the extra faces
help the volume / temple, the c12 MAJORs).
## Garrett cards c13 (2026-10-19, hair-garrett agent, fresh; order: the new budget rule, every tier rebuilt from c11L's settings, the crown ledge graded toward the photo, volume, temple texture, seam, sideburn strip, A/B vs c11L)
- (0) MERGED origin/main (f2981bde, no rebase): main's squashed copy of c1-c10 + the Tess hair-cards rounds 26-37 and
  game_ready r53-r60 (CAP_RELAX / CAP_RELAX_FLOOR, cap_fill_arch, CAP_TOP_EL, CARD_ROUGH_MIN, card_faces in the report,
  asset's push-under layers). Resolved as a 3-way against c820679b (main's copy of c10); 167 hair tests green.
  NB c13's builds therefore carry main's cap code (CAP_RELAX 60 ...) that c11L did not: a rebuild of c11L's settings is
  not c11L to the triangle.
- (1) BUDGET RULE (coordinator 2026-10-19): hair.card_allowance(budget, cap, other, back_faces, drawn_max): `budget`
  (tier_triangles: the role's hair_cards default at the tier's LOD) counts CARD FACES, one side (cap + other + cards <=
  budget); DRAWN triangles (cap once, the rest x2 with BACK_FACES) <= drawn_max = hair.tier_drawn_max(tier) = budgets.json
  hair_cards range max of TIER_ROLE {hero: hero 50k, main: main_npc 20k, npc: secondary_npc 8k, far: crowd 1.5k}
  (hair.export.tier_drawn_max {tier: n} overrides). drawn_max None = the old drawn rule (legacy callers). cards_job's
  budget info carries drawn_max; export_hair's tier report adds "vertices" (GPU: distinct position / uv / normal
  corners), "positions", "drawn_max". test_every_tier_fits_its_drawn_budget_back_faces_counted asserts both limits and
  the role maxima. Expected binding limit: hero = faces (25000), main / npc / far = drawn (20000 / 8000 / 1500).
  STATE: done, tests 5 green. NEXT: c13a = every tier from the spec under the new allowance.
- (2) c13a (c13/c13a.sh) = c11L's settings (the spec, no overrides), all four tiers under the new allowance, renders,
  vol, ledge, A/B tiles review/ab_c13a. STATE: building.
- (3) CROWN GRADE (coordinator (b): the cards may depart from the unapproved groom toward the photo, which has no ledge):
  hair_clumps.GRADE_SLOPE (m / deg, default 0 = off) / GRADE_BAND 20 deg / GRADE_AZ 100 / GRADE_SEAT 15 mm: envelope(...,
  grade=) dilates the head strands' ENV_PCT envelope DOWN the back (each bin >= a higher bin within GRADE_BAND less
  slope x the elevation between), and _grade_fill raises head cards (never lowers) onto it where it stands over the
  plain envelope, eased in from the root. Slope 0.3 mm / deg = the groom's own so98 grade (6 / 8 / 10 / 11 mm at elev 18-36).
  test_envelope_grade_spreads_a_back_step (tests/test_hair_clumps.py). Trials (c13/q1.sh, hero + ledge + vol + shots):
  c13g1 GRADE_SLOPE .0003; c13g2 + volume CROWN_FILL .7 (round 31's raise toward the envelope) CROWN_EL -20 (temples
  in), CROWN_SEAT .02, CROWN_END .01. STATE: queued behind c13a.
- (4) c13a BUILT (exp/c13a, c11L's spec under the new allowance): hero drawn 33684 / card faces 18392 / vertices 20691
  (allowance: faces 25000, drawn max 50000), main 14220 / 8158 / 9143 (12500 / 20000), npc 6804 / 4008 / 4740 (8250 / 8000),
  far 1500 / 1084 / 1005 (2500 / 1500); c11L drawn 24708 / 12412 / 6560 / 1380. Only the far tier hits its limit: the
  clumps cut aims at 0.8 x the budget and lands under it (hero 15.3k card faces for a 25k allowance), so the extra
  allowance mostly went UNSPENT. CODE: hair.CARD_CUT_SHARE (default .8, unchanged) to size the cut (trial at 1.1 not run).
  vol c13a = c11L to 0.5 mm (front half-width 89.5/83.5/68.5/11.2 vs groom 92.4/87.3/72.0/20.8).
  BLIND A/B c13a vs c11L (review-ab exit 4 "REVIEW FAILED" again, 2026-10-19; trios to a fresh blind subagent): front /
  3/4 / side / back / 2 m / 4 m / 8 m TIE, far 4 m front NEW -> NEW 1 / OLD 0 / TIE 7. More faces of the same cut change
  nothing visible; the far tier's +120 drawn triangles read as wider temple / side mass at 4 m.
  Shared MAJORs (reviewer): volume (skull-hugging), hairline high with angular temple insets, scale-like clumps with spiky
  ends, grey wrong by region (pale flat temple patch, dark uniform back), stray strands at the ear, a smooth helmet edge
  at 4-8 m.
- (5) PHOTOS (coordinator; read only, never into this repo): /home/joe/dev/s0urc3/docs/img/garrett_ref_full/
  garrett_head_back.png, garrett_head_profile_left_true90.png (+ front / three-quarter). LOOK (mine, c13/c13a_look
  vs photo): the photo's back is ONE mid-light grey from crown to nape, smooth, longer and fuller than the groom; ours is
  a dark bristly back under a pale flat crown cap with a hard seam. The seam reads far more than any ledge.
- (6) GRADE trials: c13g1 (GRADE_SLOPE .0003, GRADE_SEAT 15 mm) = c11L's ledge curve to the mm; c13g2 (+ CROWN_FILL .7,
  CROWN_EL -20, CROWN_SEAT .02, CROWN_END .01): 85 of 1309 head cards raised (max 7.7 mm) but the back midline so98 at elev
  12-30 still 3-4 mm; vol +0.2-0.7 mm p90 (temple 5.9 -> 6.2, side over the ear 7.0 -> 7.7), half-width +0.4 / +1.1 mm.
  Suspect the band's cards are ~1 cm long, so the 15 mm root ease held them down: c13g3 (GRADE_SEAT 3 mm) and c13t1
  (+ hair.export tone_back 1.0: the back as light as the photo's) running (c13/q2.sh).
- (7) c13g3 (GRADE_SEAT 3 mm): 129 of 1309 head cards raised (max 9.2 mm), yet the back midline so98 at elev 12-30 is still
  3-4 mm (ledge.py) and the back view is c11L's by eye: the grade raises cards somewhere, not in the band the ledge item
  measures (not traced: check the grade's C / elevation frame against c8/C.json's, and which classes own the band's
  cards: if the cap or non-"head" cards own it, _grade_fill never sees them). c13t1 (+ hair.export tone_back 1.0):
  back-view L* (c13/: hair id mask, bands from the hair's top) crown 0-15 % / 15-30 % / mid 35-70 % / nape:
  c11L 55.9 / 39.9 / 36.6 / 34.5, c13g3 53.2 / 39.5 / 36.1 / 34.0, c13t1 56.3 / 39.9 / 36.6 / 34.0: tone_back is a DEAD
  lever here (the back is not lighter at all; the tint path for the back's cards not traced). The seam is a ~16-19 L*
  step from the pale crown cap (flow top) to the back in one band; the photo's back is one mid grey.
## HANDOVER (hair-garrett c13, 2026-10-19; nothing in flight: q1 / q2 done, q3 (CARD_CUT_SHARE 1.1) killed unrun)
STATE: hair-heads2 local commits only (not pushed). origin/main merged (f2981bde). BEST stays exp/c11L (the A/B was
c13a NEW 1 / OLD 0 / TIE 7: c13a is the same hair with the new budget's extra far triangles). If the budget rule must be
reflected in the shipped build, c13a = c11L's settings under it with no visible loss.
BUDGETS c13a (drawn / card faces / GPU vertices; limit faces | drawn): hero 33684 / 18392 / 20691 (25000 | 50000), main
14220 / 8158 / 9143 (12500 | 20000), npc 6804 / 4008 / 4740 (8250 | 8000), far 1500 / 1084 / 1005 (2500 | 1500).
CODE (c13): hair.card_allowance(..., drawn_max) + tier_drawn_max + TIER_ROLE (the coordinator's rule; legacy drawn rule
when drawn_max is None), export_hair tier report "vertices" (GPU) / "positions" / "drawn_max"; hair.CARD_CUT_SHARE (.8);
hair_clumps.GRADE_SLOPE / GRADE_BAND / GRADE_AZ / GRADE_SEAT + envelope(grade=) + _grade_fill (off by default); tests
test_every_tier_fits_its_drawn_budget_back_faces_counted, test_envelope_grade_spreads_a_back_step.
Scratch $HG/cards/c13/: c13a.sh, hx.sh (hero + ledge + vol + 4 shots), q1-q3.sh, ledge_* / vol_*; review/ab_c13a (trios,
key, blind verdict above). review-ab still exits 4 ("REVIEW FAILED"); NB its args file needs `eval "set -- $(tail -1 f)"`.
FINDINGS: (a) the new allowance is unspent: the clumps cut makes ~0.6 x the budget's faces (hero 15.3k for 25k); more
faces of the same cut are invisible anyway (A/B 7 ties). Spending them only pays where a measured fault needs cards
(temple / side mass, hairline row), not as density. (b) Grade: the lever runs but does not reach the measured band.
(c) The crown-to-back SEAM (pale flat flow-top cap vs dark bristly back) is the biggest back / profile fault vs the
photo, far more than any ledge, and tone_back does not move the back.
NEXT, in order: (1) trace why tone_back (and the grade) miss the back's cards: dump per-card cls / layer / root elevation
for cards whose surface lies on the back midline at elev 0-30 (which class, which tint path); (2) the seam: grade the
flow top layer's lit toward 0 down its last ~2 cm (a lit ramp along the card, not a global lit) and lift the back's tint
to the photo's mid grey once the tint path is found; (3) volume: CROWN_FILL .7 from el -20 gave +0.3-0.7 mm p90 only;
the cards' p90 is 3-4 mm under the groom at every region; next try the envelope target itself (ENV_PCT per region with
CROWN_FILL), measured by vol.py + front half-width; (4) temple plates' texture and the pale bluish sideburn strip:
untouched this session.
## Garrett cards c14 (2026-10-19, hair-garrett agent, fresh; order: trace why tone_back / the grade miss the back, the seam, else a proposal)
- (0) CULLING (coordinator): main 7bef3431 (single-sided card material) + Blender's glTF import dropping the BACK_FACES
  copies as duplicates (c13t1: 18392 of 33684 drawn triangles imported) = card previews showed front sides only.
  Cherry-picked b4430ada (blender_scene: the card game material never culls). WHICH ROUNDS: 7bef3431 entered hair-heads2
  with c13's merge of origin/main (c11 / c12 commits lack it): c11L / c12 renders were two-sided, c13's (c13a / g / t1)
  were not. Re-rendering c11L / c13t1 / c13g3 hero shots as tag _<t>F (c14/rs.sh).
- (1) PLUMBING CAUSE (the plateau): the cards' VERTEX COLOURS CLIP AT 1.0. A baked card's colour = ramp x tone_k / peak
  with tone_k = bake_k x tint (tint carries tone_front / tone_back, NAPE_LIFT, GREY_TINT, the flow top's lit), then
  hair_cards.mesh clips it to [0, 1]. c14/clip.py (share of card vertices >= .995 per layer range of the hero GLB):
  c11L layer0-2 33 / 36 / 33 %, c13t1 (tone_back 1.0) 82 / 71 / 83 %; cap 0 %. The trace (c14/glbcol.py, c13g3 vs
  c13t1, same geometry): tone_back DID reach 53 % of the vertices (every head card rooted behind C - 2 cm), true ratio
  1.18, but the clipped ratio is p50 1.013: the lift was eaten by the ceiling. Every LIGHTENING card lever (tone_back,
  flow lit, card_gain) has been near-dead since the colour model divided the atlas by bake_k; darkening levers worked
  (c12's flow lit 0 moved the top), which is why it looked like "settings don't reach the back". The atlas meanwhile
  uses ~0.43 of its linear range (c11L bake texels sRGB p99 169, max 175 / 255). Not a cache key, not a class: every
  card is cls head (layer ranges cap / L0 / L1 / L2), and the low back (z < 1.69 behind C) is 16 % cap + 11-18 % L0/L1.
  FIX: hair.export.headroom (look key, default off = 1): hair_cards.atlas moves a factor H (<= headroom, the bake
  block's p99.9 texel <= .98) into the bake block and divides bake_k by it, so the cards' vertex colours drop by H: the
  same picture where nothing clipped (headroom is in the atlas cache key). tests/test_hair_headroom.py: the picture is
  kept and a tone_back lift on a card at the ceiling now moves it by its own ratio (plain path < 1 %). Off by default
  so Tess's builds are untouched; Garrett's trials pass ex={"headroom": 2}.
  STATE: hero builds c14h (headroom 2) and c14t (+ tone_back 1.0) queued (c14/q1.sh, after the re-renders).
- (2) RE-RENDERS under the culling fix (tag _<t>F): c11LF = c11L (mean |d| 0.03 / 255: c11L's GLB predates 7bef3431),
  c13t1F / c13g3F within 1 L* of their culled renders on the back bands. The culling did not cause the plateau.
- (3) THE PHOTO, MEASURED (c14/bands.py; photo: dark low-chroma largest blob, same bands from the hair's top): photo back
  crown 0-15 % / 15-30 % / mid 35-70 % / nape = 34.5 / 31.7 / 36.1 / 32.0 L*, largest 5 %-band step 4.7, fine std 6.4.
  c11LF 52.1 / 39.9 / 36.9 / 33.6, step 9.7 at 10 %, fine std 4.1. => the back's MID is already the photo's grey (36.9 vs
  36.1); the fault is the PALE CROWN BAND (57 L* in the top 10 % vs 38) and the missing fine silver strand contrast.
  tone_back (a back lift) is the wrong direction. NB the A/B tiles (tiles.py) used the GROOM render as the reference,
  whose crown is pale: c12's reviewer preferring the pale crown matched the groom, not the photo. c14/tilesp.py makes
  tiles with the PHOTO as the reference (same crop rule on both).
- (4) HEADROOM WORKS AS PLUMBING: c14h clip share layer0-2 33 / 36 / 33 % -> 0 / 10 / 0 %; c14t (+ tone_back 1.0) vs
  c14h: 64 % of vertices change, ratio p50 1.068 / p95 1.176, and c14/where.py shows the x 1.176 on the back cards at
  EVERY height 1.62-1.76 m. Render: crown band 50.4 -> 54.2 L*, mid 36.8 -> 36.9, nape 33.5 -> 33.6: the back cards'
  colour changes and the back's picture does not.
- (5) THE REAL CAUSE: THE BACK YOU SEE IS THE CAP, NOT THE CARDS. c14/capblack.py writes the hero GLB with the cap's
  vertex colours 0 and the cards' 1: back and profile render (c14/capblack.png, capblack2.png: c14t and c11L alike) are
  BLACK over the whole back and sides; white shows only at the temples / front top and the crown edge. c14/under.py:
  half the head cards' vertices lie UNDER the cap (card - cap radius p50 -1.6 / -1.0 / +0.1 mm for L0 / L1 / L2, p90
  +3-5 mm = tips). Why: an even short groom wears the short cut's BAKED cap (EVEN_SHORT_CAP) lifted to the hair's mid
  height (EVEN_SHORT_LIFT), and cap_under_cards may not push it under EVEN_CAP_KEEP .6 x that height (c3, against c2's
  bare-scalp holes): the short back's cards lie lower than that, so the cap stands over them. Every card lever (tone_back,
  GRADE, HEAD_LIFT, ENV_*) acted on hidden cards: c11 -> c13's plateau. The "dark bristly back" is the cap's baked picture.
- (6) c14s (headroom + flow_top lit 0): crown 44.3 / 39.5 / 36.8 / 33.5, the crown seam gone (bands 46 43 39; largest
  step now 5.6 at the nape edge), closer to the photo's crown (34.5). Trials c14k1 / c14k2 = headroom + tone_back 1.0 +
  hh.EVEN_CAP_KEEP .3 / .15 (cards over the cap at the back; c14/q3.sh). STATE: running.
- (7) BLIND A/B c14s vs c11L, PHOTO as the reference (review-ab exit 4 "REVIEW FAILED" again; its trios review/ab_c14s/out
  + key.json to a fresh blind subagent): back NEW, profile OLD (c11L's lighter temples), 3/4 TIE, front NEW -> NEW 2 /
  OLD 1 / TIE 1. Shared MAJORs: back / crown read as nubbly terrycloth (photo: fine combed strands lying flat), sides
  flat scaly flakes, top low and flat, nape a ragged fringe (photo: a taper), stray cards at the ears.
- (8) c14k1 (EVEN_CAP_KEEP .3): back cards out from under the cap (share under 0.64 -> 0.38), tone_back now moves the
  mid / nape +0.7 L*; by eye (c14/k1_sheet.png: photo | c14s | c14k1) the back is the same nubbly mat and the sides
  turn to flakes: NOT better. c14k2 (.15) killed unrun. Per the brief, tuning STOPS here: proposal below.
## PROPOSAL (c14): short men's hair as a SHELL + strand-texture cap with fins, cards only at the edges
WHY: on Garrett the visible back / sides / crown ARE the cap (c14 (5)); the ~1300 head cards lie under or inside it and
only the temples / front top show cards (as flakes). Every card lever since c11 tuned hidden geometry. The cap's look is
a picture baked from the groom's strands at one depth (hair_cap.py), seen face-on: a nubbly mat, no lay direction, no
strand contrast (fine std 4.2 vs the photo's 6.4), and its edge is a hard seam where the flow-top cards start.
HOW GAMES DO SHORT CUTS (crew / short taper / buzz, e.g. current UE MetaHuman / Frostbite / RE Engine practice): (a) a
scalp-hugging HAIR CAP mesh with a tiling-plus-unique strand texture (combed lay painted in the flow direction, alpha
dithered edge, root-to-tip gradient), often 2-4 thin SHELLS offset 1-3 mm (the outer ones alpha-tested strand layers =
depth / parallax and a soft silhouette); (b) a few FIN rows (cards standing up along the outline: crown, top's edge,
behind the ears) for the silhouette; (c) HAIRLINE cards (small, low, dense) at the front hairline, temples, sideburns
and the nape taper; (d) anisotropic shading driven by the flow map. Cards over the whole head are kept for hair longer
than ~4-5 cm (Tess).
WHAT IT TAKES HERE: (1) hair_cap: bake the cap texture from the groom as a COMBED-LAY strand picture in the cap's UV
(strands drawn as lines along the flow at the atlas texel, not a depth-shaded top view) + its flow / aux maps (most
exists: hair_cap.cap_height, flow, grey per region). (2) shells: 2-3 copies of the cap at offsets from cap_height (the
groom's standoff by region: c12 vol.py has it), alpha-tested strand layers; triangles ~ 3 x cap (3100 -> ~9k hero; far
tier: the cap alone). (3) fins along the silhouette loops (crown edge, top's outline from the front / side) from the
existing row tool (hrow) instead of the whole-head clumps cut. (4) keep the hairline row / sideburn cards (c9) and the
nape taper as a row. (5) gates: back / profile tiles vs the PHOTO (c14/tilesp.py), bands.py (crown / mid / nape L*, the
largest band step, fine std), vol.py (standoff by region), and the cap-black test (c14/capblack.py) to prove which
surface each region shows. Estimate: 2-3 sessions (cap picture + shells 1, fins / rows + tiers 1, A/B + tuning 1).
## HANDOVER (hair-garrett c14, 2026-10-19; nothing in flight: q1 / q2 done, q3's c14k2 killed)
STATE: hair-heads2 local commits only (not pushed). Culling fix b4430ada cherry-picked (2d73367e).
BEST: exp/c14s HERO ONLY (c11L's spec + ex headroom 2 + st flow_top lit 0): won the photo-referenced blind A/B over
c11L 2-1-1 (crown band 44 vs 52 L*, photo 34.5; the crown seam gone). Other tiers not built: c11L stays the shipped set
until c14s's settings are built at all four tiers (c12/c12L.sh with the overrides). NB c12L lost with flow lit 0 against
the GROOM reference; against the photo it wins: the reference choice decided it.
PLUMBING FOUND: (a) the cards' vertex colours clipped at 1 (fix: hair.export.headroom, opt-in, test); (b) the real
plateau: the back / sides you see are the even short CAP standing over the cards (EVEN_CAP_KEEP .6), so card settings
never showed there. (c) A/B tiles used the groom render as the reference (pale crown): use c14/tilesp.py (photo).
CODE (c14): hair_cards.atlas look "headroom" (+ cache key), hair.export.headroom; tests/test_hair_headroom.py.
Scratch $HG/cards/c14/: rs.sh, hx.sh, q1-q3.sh, glbcol.py, ranges.py, clip.py, where.py, under.py, capblack.py, bands.py,
tilesp.py, capblack*.png, k1_sheet.png; review/ab_c14s (trios, key, verdict above). review-ab still exits 4.
NEXT: the coordinator's call on the PROPOSAL above; if declined, build c14s at all tiers and A/B vs c11L on photo tiles.
## Garrett short-hair shells sh1 (2026-10-19, hair-garrett agent, fresh; coordinator: YES to c14's proposal; this session (1) combed cap + (2) shells)
- (0) DESCRIBE (photo back, c14 (3)): crown 0-15 % / mid 35-70 % / nape 70-100 % L* 34.5 / 36.1 / 32.0, largest 5 %-band
  step 4.7, fine std 6.4; by eye: fine combed strands lying flat in one direction (down / back), a taper at the nape, no
  nubbly mat. Items measured on ours: c14/bands.py (same), the cap-black test (which surface shows), photo tiles
  (c14/tilesp.py) front / 3/4 / profile / back.
- (1) CODE (opt-in, spec hair.export.style "shells" + hair.export.shells {heights, base, cover, tiers}; default cards):
  hair_cap.chart now also returns lay (the strands' SIGNED direction smoothed 3 mm), base, length (median strand length by
  root cell), R, e0 (VERSION 12). hair_cap.combed: ~LAY_COVER x area / (width x length) strands traced along the lay from
  random roots (density thinning to the hairline), LAY_LEN 0.75 x the groom's length there (6-35 mm), a slow wobble /
  turn each; z-buffer height = t + 0.5 s (tips over the next roots: shingled lay; s = how far a strand stands); depth =
  roots deep, tips / standing strands lit, strand edges shaded; the cap keeps the chart's opaque base. Shell j at share h
  of the hair's height shows only runs with s x rise(t) >= (h - base) / (1 - base) (sparse outward, alpha-tested).
  hair_cards.atlas(shells=): a block under tiles / bake, one size/2 slot a shell (bake-only slices now [Ht:Hb_]).
  cards_job: cap at SHELL_BASE .4 x the hair's height (hair_cap.shell_height), shells = cap copies at SHELL_HEIGHTS
  (.62, .85), uv into their slots after the final atlas; head cards dropped except the hairline rows (hrow); SHELL_TIERS
  hero 2 / main 2 / npc 1 / far 0. tests/test_hair_shells.py (shells thin outward, follow the lay; atlas block, tiles
  untouched). STATE: hero sh1a building (ex headroom 2 + style shells). NEXT: tiles vs photo, bands, cap-black.
- (2) sh1a (hero, ex headroom 2 + style shells): 13068 triangles (cap + 2 shells 9300, 83 of 1686 cards kept = the
  hairline rows, 3768). 106k combed strands. Sheet $HG/shells/sheet_sh1a.png (photo | c14s | sh1a, tiles by c14/tilesp.py).
  bands (back): crown 38.4 / 39.7 / mid 35.8 / nape 32.5, seam 5.9 at 95 %, fine std 5.1 (photo 34.5 / 31.7 / 36.1 / 32.0,
  4.7, 6.4; c14s 44.3 / 39.5 / 36.8 / 33.5, 5.6, 4.2): the crown's pale band is gone and every band is within 4 L*.
  shells/tex.py on the photo tiles (L*, chroma, fine std x - g1.5, MID std g1.5 - g6 = blotch): back photo 34.3 / 4.0 /
  5.5 / 2.5, c14s 37.2 / 4.8 / 3.3 / 3.0, sh1a 35.4 / 5.2 / 3.9 / 4.3; front photo mid 3.1, sh1a 5.2; 3/4 3.8 vs 4.9.
  LOOK (mine, first): the tone is right but it reads as a dark helmet with pale LEOPARD SPECKS (salt-and-pepper in
  clumps 3-8 mm), no visible lay at 1 m; the top is low (no volume over the crown) and the temples / sides show the
  hairline-row cards as pale flakes against the dark cap. Not yet better than c14s by eye except the back's even tone.
  (fine std is not comparable photo vs render: the render's hair is ~250 px upscaled to the 600 px tile; MID std is.)
  STATE: q2 queued: sh1b = cap only (shells tiers hero 0: is the speckle the shells'?), sh1c = SHELL_WIDTH .5 mm,
  LAY_COVER 8, SHELL_LIT 0 (finer, more strands, outer shells not lit).
- (3) q2 (tex.py back L* / chroma / mid std; photo 34.3 / 4.0 / 2.5): sh1b CAP ONLY (combed cap, no shells) 37.4 / 5.0 /
  3.6, bands 40.7 / 41.6 / 37.4 / 34.2; sh1c (SHELL_WIDTH .5 mm, LAY_COVER 8 = 170k strands, SHELL_LIT 0) 34.9 / 5.1 /
  4.0, bands 37.5 / 38.2 / 35.0 / 31.4, seam 3.8 (photo 4.7): the closest bands yet (every band within 3.5 L*). The shells
  add ~0.4-0.7 of mid std (the speckle) but darken toward the photo. LOOK (shells/cmp_bc.png: photo | c14s | sh1b | sh1c,
  3/4 + back): sh1c is the best of mine: finer speckle, the crown shows strands sweeping in the lay, no nubbly terrycloth,
  no ragged nape fringe. Remaining: salt-and-pepper contrast (grey vs dark strands, the dark base) where the photo is a
  smooth fine silver; the mass is a tight skullcap (photo: volume on top, fuller sides); temple row cards = pale flakes.
  STATE: sh1d = sh1c + LAY_DEP0 / T / S .45 / .3 / .15 (depth range .3-.95 -> .45-.9: less strand contrast) building.
- (4) sh1d (sh1c + LAY_DEP .45 / .3 / .15): DEAD LEVER: atlas cap block mean |d| 0.8 / 255, tex / bands identical to sh1c.
  The combed depth is not what sets the contrast: the salt-and-pepper is GREY strands (look grey x GREY_LIFT) against the
  brown lit / gap colours, at the grey share (cards' tiles .58-.78). Next lever = the grey strands' value / share in the
  combed picture, proven on the atlas block (L* std of the cap block) BEFORE a build.
- (5) BLIND A/B c14s (old) vs sh1c (new), PHOTO as the reference: review-ab exit 4 ("REVIEW FAILED") again; its trios
  ($HG/shells/ab_sh1c/trio_*.png, key.json: X = new everywhere) to a fresh blind subagent: front OLD, 3/4 NEW, profile NEW,
  back TIE -> NEW 2 / OLD 1 / TIE 1, overall "X (new), barely": new reads as ONE consistent hair mass (no flakes / scales,
  no two materials front / back); old's tone is closer. NEW's MAJORs: too dark / brown where the photo is mid-grey silver,
  a stippled "leopard" speckle with no fine strands or back-swept lay, a hard dark line along the front hairline, hard nape
  edge; scruffy edge above the ear / at the sideburn (the hrow cards). NB the measures say the tone matches (back L* 34.9
  vs 34.3) and the eye says too dark: the photo mask (L* < 60-62, low chroma) likely drops the photo's silver highlights:
  re-measure the photo's hair with a real segmentation before tuning tone.
## HANDOVER (hair-garrett sh1, 2026-10-19; nothing in flight)
STATE: hair-heads2 local commits only (not pushed). Shell style built and opt-in: spec hair.export.style "shells"
(+ hair.export.shells {heights, base, cover, tiers}); default cards untouched (tests: test_hair_shells, test_hair_headroom).
BEST: exp/sh1c HERO ONLY = ex {"headroom": 2, "style": "shells"} + hq.SHELL_WIDTH=0.0005 hq.LAY_COVER=8 hq.SHELL_LIT=0
(13068 triangles: cap + 2 shells 9300 + 83 hrow cards 3768). Beat c14s 2-1-1 blind on photo tiles; bands closest yet.
Those three constants should become the defaults (or spec keys) once confirmed; not changed yet.
CODE: hair_cap.chart (+ lay, base, length, R, e0; VERSION 12), hair_cap.combed / shell_height, constants SHELL_HEIGHTS,
SHELL_BASE, LAY_*, SHELL_WIDTH, SHELL_LIT, LAY_DEP*; hair_cards.atlas(shells=) block under tiles / bake (bake slices
[Ht:Hb_]); hair.cards_job wiring (SHELL_TIERS hero 2 / main 2 / npc 1 / far 0; cap at SHELL_BASE x height; cards = hrow only).
SCRATCH $HG/shells/: sx.sh <tag> [hx7 args] (hero build + shots into cards/exp, cards/out), tiles.sh <old> <new> (photo
tiles + sheet + bands), tex.py (L* / chroma / fine / MID std per tile; side photo's mask fails on its black border),
sheet.py, cmp_bc.png, ab_sh1c/.
NEXT (in order): (a) tone / speckle: the grey strands' share and value in the combed picture (lever proven on the atlas
block first), re-measure the photo tone with a segmentation; (b) the front hairline's hard dark line (the cap base runs to
the line: soften base at the front, or a hairline row there); (c) session 2 of the plan: fins along the silhouette (crown
edge, top outline; hair_clumps row tool) for volume / outline (the mass is a tight skullcap), nape taper row, the hrow
cards' pale flakes at the temples (tone them to the cap); (d) all four tiers (SHELL_TIERS) + budget report check, LODs;
(e) A/B vs c14s / c11L on photo tiles (review-ab still exits 4: use a blind subagent on its trios).
## Garrett short-hair shells sh2 (2026-10-19, hair-garrett agent, fresh; order: photo segmentation + tone, grey share / value, front hairline line, fins / nape / temple rows, tiers + A/B)
- (1) PHOTO SEGMENTATION ($HG/shells/seg/: a uv venv with mediapipe; hseg.py <tiles dir> [overlay]): the photo's hair =
  MediaPipe selfie_multiclass class 1 UNION hair_segmenter (the multiclass model alone drops the back photo's nape),
  largest blob, eroded 3 px; renders by colour (the segmenter calls our dark render hair "skin": bg L* 86, skin C > 14).
  Per tile and band (top / mid / low thirds of the mask): L* p10 / p50 / p90, chroma p50, grey share g (L* > 45 & C < 8),
  MID std (g1.5 - g6). CORRECTED PHOTO NUMBERS (all-hair p10 / p50 / p90, C, g, mid):
  front 29.7 / 43.1 / 56.6, C 4.5, g 35 %, mid 3.7 (mid band = temples / sides 40 / 51 / 62, g 68 %)
  q34   27.5 / 42.0 / 57.5, C 2.9, g 35 %, mid 4.1 (mid band 37 / 49 / 61, g 61 %)
  side  24.1 / 37.9 / 56.3, C 2.9, g 26 %, mid 3.6 (mid band 28 / 44 / 61)
  back  24.1 / 34.5 / 46.6, C 3.5, g 12 %, mid 2.8
  sh1c (ours): front 29.6 / 37.2 / 47.3 C 4.2 g 16 % mid 5.8; q34 25.5 / 33.8 / 44.4 C 4.3 g 9 % mid 5.4; side 29.0 / 37.2 /
  48.1 C 4.7 g 18 % mid 4.9; back 25.8 / 34.1 / 45.4 C 5.0 g 11 % mid 4.4. c14s (old): front 45.2 median g 50 %.
  FINDING: the old mask (L* < 60, C < 14) kept 91-100 % of the segmented hair (only 5-6 % of the photo's hair is over
  L* 60): it was NOT dropping the silver. The back matches (34.5 vs 34.1); what is wrong is the FRONT / 3/4 / side: the
  photo's sides and temples are silver (mid band p50 49-51, 61-68 % grey) where ours is 31-37 with 6-8 % grey, plus too
  much chroma (+1-1.5) and blotch (mid std +1.5-2). The c14 / sh1 tone work measured the back only.
  Atlas proxy (sh2/atl.py: cap block + shells block albedo L*, C, grey-ish share by thirds): sh1c cap 32.2 / 34.3 / 59.4,
  C 2.2, grey-ish 29 %: bimodal (dark base / brown strands at ~33, grey strands at ~59) = the leopard.
  STATE: sh2a (look card_grey 1.0 = the cap's grey share x2, grey #8a8784) building. NEXT: atlas proxy, then tiles.
- (2) sh2a = sh1c + look card_grey 1.0 (cap grey share x2) + grey #8a8784: LIVE but OVERSHOT: atlas cap 32.6 / 49.4 / 77.5
  grey-ish 51 % (sh1c 29 %); renders front 40.1 / 52.8 / 65.7 g 78 % (photo 29.7 / 43.1 / 56.6, 35 %), back 52.1 (photo 34.5).
  LOOK: a salt-and-pepper speckle, worse than sh1c: the contrast is grey strands vs the dark brown lit (#3e3631, L* 23).
  The photo is a SMOOTH fine silver: its strands are near one value; the dark is between / under them. sh2b (+ lit
  #4c4540) killed unrun. CODE: hair_cap.GREY_SPREAD (combed regional grey share stretched about its median, default 1;
  photo sides 61-68 % grey vs back 12 %); tests pass. STATE: q2 = sh2c (card_grey .7, grey #7c7976, BASE_EDGE 4 mm),
  sh2d (+ GREY_SPREAD 2); q3 = sh2e (sh2d + lit #5a5551 / gap #2a2624: less strand contrast). NEXT: tones per view.
- (3) trials (sh2/m.sh <tag>: bands, atlas proxy, segmented tone; all-hair p10 / p50 / p90, grey share g, MID std):
  photo front 29.7 / 43.1 / 56.6 g 35 % mid 3.7 | q34 27.5 / 42.0 / 57.5 mid 4.1 | side 24.1 / 37.9 / 56.3 mid 3.6 | back 24.1 / 34.5 / 46.6 mid 2.8
  sh2c (card_grey .7, grey #7c7976, BASE_EDGE 4 mm): front 33.6 / 44.0 / 56.7 g 46 % mid 6.2 | q34 41.0 p50 mid 5.7 | side
  45.2 mid 5.6 | back 41.9 mid 5.5: the front views' value is ON (44 / 41 vs 43 / 42), back / side too light, speckle high.
  sh2d (+ GREY_SPREAD 2; combed share p10 / 50 / 90 0 / .29 / .67): ~ sh2c (back 41.3): the charted grey regions are not
  the photo's (the photo's back is darker than its sides: grey share or the photo's light; unresolved).
  sh2e (sh2d + lit #5a5551 / gap #2a2624): MID std 3.2-4.4 = the photo's (the LEOPARD IS THE LIT / GREY CONTRAST: proven),
  but everything +10-19 L* (front 54.4, back 53.5) and p10 45 vs 24-30 (no dark between strands).
  STATE: sh2f = sh2e's contrast ~10 L* lower (lit #46423e, grey #6c6966, gap #1e1b19) building. NEXT: measure, A/B.
- (4) sh2f (lit #46423e, grey #6c6966, gap #1e1b19, card_grey .7, BASE_EDGE 4 mm, GREY_SPREAD 2): front 36.2 / 44.3 / 54.4
  g 46 % mid 5.2 | q34 33.5 / 41.1 / 51.2 mid 4.9 | side 37.0 / 45.2 / 55.1 mid 4.3 | back 34.1 / 42.1 / 52.4 mid 3.9; bands
  crown 45.0 / 46.6 / mid 42.7 / nape 39.0, fine std 3.8. Front / 3/4 p50 ON the photo; MID std down 0.5-1.6 from sh1c
  (still +1 over the photo); the range is compressed (p10 33-37 vs the photo's 24-30: no dark between strands); back /
  side ~+7 L* too light (the photo's back is darker than its sides; our grey has no such region).
  BLIND A/B sh2f vs sh1c (sh2/ab_sh2f, key.json; front / side X = new, q34 / back X = old): the reviewer answered "Y"
  in every view (= old front / side, new 3/4 / back: 2-2), but its side text calls X "dark brown leopard", which is
  sh1c's look, not X's: its labels are unreliable. MY LOOK (side trio): sh2f is clearly the greyer, closer silver;
  both still read as camouflage speckle with no fine combed lay; the hairline is still a hard cut with a dark rim at
  this scale (BASE_EDGE 4 mm not visible); same tight skullcap volume. Not a clear winner: re-run the A/B with a fresh
  reviewer (or review-ab after 13:00 MT) before promoting anything.
## HANDOVER (hair-garrett sh2, 2026-10-19; nothing in flight)
STATE: hair-heads2 local commits only (not pushed). Steps (1) and (2) done, (3) a lever in place but not proven visible,
(4) fins / nape row / temple toning NOT started, (5) tiers not built, A/B inconclusive.
BEST: unchanged for export: exp/sh1c hero only (sh1's handover settings) until sh2f wins a clean A/B; sh2f = sh1c + hq.BASE_EDGE
=0.004 hq.GREY_SPREAD=2.0 look {"card_grey": 0.7, "grey": "#6c6966", "lit": "#46423e", "gap": "#1e1b19"} is the tone
candidate (front value on the photo, less speckle). BEST GARRETT HAIR FOR EXPORT: still c11L's shipped card set (all tiers).
FINDINGS: (a) the photo mask was NOT dropping the silver (old mask kept 91-100 % of the segmented hair); the real miss was
the front / 3/4 / side value (ours 34-37 vs 42-43) that the back-only tone work never measured. (b) the leopard speckle
is the lit (brown) vs grey strand contrast, proven: sh2e (lit #5a5551) gave the photo's MID std; the grey share raises
value but adds speckle (sh2a). (c) GREY_SPREAD 2 moved nothing regionally: the charted grey regions are not where the
photo is silver (temples / sides 61-68 % grey, back 12 %).
CODE (sh2): hair_cap.BASE_EDGE (default 0; test), hair_cap.GREY_SPREAD (default 1). SCRATCH $HG/shells/: seg/ (mediapipe
venv, hseg.py: photo hair = multiclass class 1 U hair_segmenter; renders by colour), sh2/atl.py (atlas proxy), sh2/m.sh
<tag> (tiles + bands + atlas + segmented tone), sh2/q1-q4.sh, ab_sh2f/.
NEXT (in order): (a) tone: keep sh2f's low contrast but widen the range: a darker opaque base / root shade between strands
(p10 24-30) with the strands' value kept; regional grey from the PHOTO (temples / sides silver, crown / back darker: a
per-region grey share target, not the groom's); (b) hairline: check BASE_EDGE at a close-up (front tile crop), try 8 mm,
and the hrow cards' crosshatch at the front; (c) fins + nape taper row + temple card toning (session 2 of the plan);
(d) promote the winners to the shells style's defaults, all four tiers, clean A/B vs c14s / c11L on photo tiles.
## Garrett short-hair shells sh3 (2026-10-19, hair-garrett agent, fresh; order: tone by region + dark base, hairline, fins / nape / temple rows, tiers + A/B)
- (1) LOOK FIRST (sh2f tiles, back crop at native size): ours = grey BLOBS 1-3 mm long on a brown-grey, no readable lay,
  lumpy edge; the photo = fine long grey strands combed down, a smooth darker layer between them, silver sides, dark
  crown / nape. Segmented bands (top / mid / low thirds, p50): photo front 38.6 / 51.2 / 45.4, q34 38.4 / 49.3 / 29.8,
  side 36.4 / 43.6 / 29.9, back 33.3 / 37.4 / 31.7; sh2f front 46.3 / 40.9 / 40.1, q34 42.3 / 39.1 / 40.6, side 46.3 /
  45.4 / 39.1, back 44.9 / 41.9 / 38.3: OUR REGIONAL PATTERN IS INVERTED (light top, dark sides).
  WHY GREY_SPREAD MOVED NOTHING REGIONALLY (traced): combed's gsh = the chart's grey blurred 6 texels (~2 mm at 2048):
  lock-scale noise, no side-vs-back trend in the groom; the spread stretched that noise (p10/50/90 0 / .29 / .67) =
  clumps of grey strands = more leopard. Dead by construction for regions.
  CODE: hair_cap.GREY_REGION (0..1, default 0): gsh blended to hair_cap.grey_map (GREY_MAP: share by the hair's own
  height h and degrees from the front: top .15; side band front / 60 / 100 / 140 / 180 deg .55 / .7 / .65 / .4 / .3;
  low (sideburn -> nape) .5 / .55 / .4 / .15 / .1; ~1 cm smooth): at 1 the lock noise goes (fine interleave);
  hair_cap.EDGE_SHADE (was the fixed .3 strand-edge shade); hair.py combed cache key now carries GREY_SPREAD / REGION /
  MAP / EDGE_SHADE / BASE_EDGE / BASE_DEPTH (in-process only: tiers in one run would have shared a stale combed picture).
  STATE: sh3/q1 building: sh3a = sh2f tone + GREY_REGION 1 + BASE_EDGE 8 mm (spread off); sh3b = + LAY_COVER 3 +
  BASE_DEPTH .25 (the dark base shows between fewer, longer visible strands); sh3c = LAY_COVER 1.5 + EDGE_SHADE .5.
  NEXT: m.sh per build (bands / p10 / MID std vs the photo), look.
- (2) sh3/q1 (segmented p50 by band top / mid / low; photo front 38.6 / 51.2 / 45.4, side 36.4 / 43.6 / 29.9, back
  33.3 / 37.4 / 31.7; all-hair p10 photo 24-30):
  sh3a (GREY_REGION 1, share p10/50/90 .15 / .27 / .65): front 48.1 / 46.2 / 42.4 (mid +5 from sh2f, toward 51), side
  53.1 / 50.1 / 34.8, back 47.1 / 43.9 / 34.2; p10 33-40; MID std 3.6-4.7 (sh2f 3.9-5.2). The lever is LIVE (mid band,
  nape moved) and the lock clumps are gone, but the TOP stays the lightest band at a .15 grey share: the top is LIT
  (faces the key light, shells' standing strands), not grey. LOOK: finer speckle, still a leopard at the back; the nape
  now a dark hard band.
  sh3b (+ LAY_COVER 3, BASE_DEPTH .25): ~1-2 L* darker everywhere, p10 31-38: fewer strands barely show the base.
  CODE: hair_cap.SHADE_MAP (a GREY_MAP-shaped dict of depth factors by region, None = off): the regional VALUE lever
  for the lit top; hx7 takes hj.<CONST>=<json>. STATE: sh3c (LAY_COVER 1.5, EDGE_SHADE .5) building.
- (3) sh3c (LAY_COVER 1.5 = 32k strands, EDGE_SHADE .5, BASE_DEPTH .25): bands front 47.3 all p50, back top / mid / low
  43.5 / 40.7 / 31.0, p10 26-34 (photo 24-30: the dark base between strands now shows); LOOK (back crops a / b / c):
  the first with a readable downward LAY, strands over a darker base; grey strands still wide pale dashes; a black rim
  at the nape edge.
  sh3d (sh3c + GREY_MAP top .1 / band .6 .75 .5 .3 .2 / low .5 .55 .35 .12 .08, SHADE_MAP top .6, lit #524e4a): all-hair
  p50 front 47.6 / q34 45.9 / side 49.2 / back 43.7 (photo 43.1 / 42.0 / 37.9 / 34.5), p10 36-41 (lit up undid the dark
  base), MID std 4.6 / 4.7 / 3.9 / 3.0 (photo 3.7 / 4.1 / 3.6 / 2.8: closest yet), bands top 48.7 / 46.6 / 51.6 / 46.4 (photo
  38.6 / 38.4 / 36.4 / 33.3): SHADE_MAP top .6 is too weak (shade = .45 + .55 dep^.8 floors it): the top is still the
  lightest band, ~+10 L*. LOOK (small tiles, photo | sh3d, sh2f | sh3c): sh3d reads as fine combed strands with a lay, the
  closest texture so far; too light overall by ~5 L* (back ~9).
  HAIRLINE (front tile crop, 2x): a BLACK DASHED LINE exactly along the front hairline (and around the ear / nape in
  profile), BASE_EDGE 8 mm does not touch it: it is not the texture's base. Hypothesis: the cap is lifted 2 mm +
  sagitta everywhere (hair.py "lift = ... + 0.002") and eases only its HEIGHT to 0 at the line, so its edge floats over
  the skin and the shadowed gap under it shows black. NEXT: ease that lift to 0 over the last ~5 mm in from the
  hairline (or skirt the edge down into the skin) and re-crop; prove with the cap-black test (c14/capblack.py).
  STATE: sh3e (= sh3d + hair.SHELL_FINS .3) and sh3T (sh3e's settings, all four tiers) queued.
- (4) sh3e = sh3d + hair.SHELL_FINS .3 (flow-top / arch cards within .3 of the front / side outline, over 20 deg): 211
  fins, hero 18048 triangles (budget 25000 faces). DOES NOT WIN: the fins' card tone is lighter than the cap (profile crown
  band 58 vs sh3d 43, a pale flake patch on top in profile / back); volume gain small. Off by default (SHELL_FINS 0);
  needs the cards toned to the cap (the temple-row toning, same cause) before it can help.
- (5) BLIND A/B sh3d (new) vs c14s (old), PHOTO as reference (fresh general-purpose subagent on randomised trios
  $HG/shells/sh3/ab/trio_*.png, key.json: front X = new, q34 / side / back Y = new). LABEL CHECK: the reviewer's
  descriptions put the "black rim along the hairline" on the NEW side in every view = consistent with the key.
  Result: front OLD (lighter silver, fuller top; new = darker, black hairline gap), q34 TIE, side NEW (narrowly: value and
  texture closer; old too brown / dark at the back), back NEW (clearly: smooth combed direction, value) -> NEW 2 / OLD 1 /
  TIE 1. Its faults for new: the black rim (hairline, nape, ear), no silver above the ear / darker crown, "scales" at the
  temples (hrow cards). bin/review-ab not tried (before 13:00 MT).
## HANDOVER (hair-garrett sh3, 2026-10-19; nothing in flight: sh3T (all tiers, sh3e settings) killed while queued for memory)
STATE: hair-heads2 local commits only (not pushed). Tone: regional grey + sparse lay over a dark base built and live.
BEST (hero, by numbers + blind A/B 2-1-1 over c14s): exp/sh3d = ex {"headroom": 2, "style": "shells"} + hq.SHELL_WIDTH=
0.0005 hq.SHELL_LIT=0 hq.LAY_COVER=1.5 hq.BASE_EDGE=0.008 hq.GREY_REGION=1 hq.BASE_DEPTH=0.25 hq.EDGE_SHADE=0.5
hj.GREY_MAP={"top": .1, "fa": [0, 60, 100, 140, 180], "band": [.6, .75, .5, .3, .2], "low": [.5, .55, .35, .12, .08],
"band_h": [.15, .35, .6, .8]} hj.SHADE_MAP={"top": .6, ...1} look {"card_grey": .7, "grey": "#6c6966", "lit": "#524e4a",
"gap": "#1e1b19"} (exact args: $HG/shells/sh3/q2.sh). Not promoted to defaults yet (one tier only, black rim unfixed).
BEST GARRETT HAIR FOR EXPORT: still c11L's shipped card set (all tiers): the shells style has no tier set built yet.
NUMBERS (segmented all-hair p50 / MID std; photo front 43.1 / 3.7, q34 42.0 / 4.1, side 37.9 / 3.6, back 34.5 / 2.8):
sh3d 47.6 / 4.6, 45.9 / 4.7, 49.2 / 3.9, 43.7 / 3.0: texture (MID std) closest yet; value +4-11 too light, worst at the
TOP band (+10: photo top 33-39) and the back.
CODE (sh3): hair_cap.GREY_REGION / GREY_MAP / grey_map (regional grey share; GREY_SPREAD was stretching lock noise),
hair_cap.SHADE_MAP (regional depth factor; .6 too weak: shade floors at .45), hair_cap.EDGE_SHADE, hair.SHELL_FINS /
SHELL_FIN_EL / SHELL_FIN_TIERS (fins: off), combed cache key complete; hx7 hj.<CONST>=<json>. tests/test_hair_shells ok.
SCRATCH $HG/shells/sh3/: q1-q3.sh, tiers.sh <tag> [args] (all four tiers + shots), m_sh3*.txt, ab/ (trios, key.json).
NEXT (in order): (a) the BLACK RIM at hairline / nape / ear (every reviewer's top fault): ease hair.py's cap lift
(+2 mm + sagitta) to 0 over the last ~5 mm to the hairline, crop-check the front hairline at 2x, cap-black test;
(b) darker top / back: SHADE_MAP can't go dark enough (shade = .45 + .55 dep^.8): make it a colour factor on the lit
colour by region (or lower top grey + gap), target top band 33-39, back p50 34.5; lit back to #46423e with the dark base;
(c) the hrow / temple cards and fins toned to the cap (both read as pale flakes / scales), then retry fins for the top;
(d) tiers.sh with the winner (npc 8000 / far 1500 drawn: far's cap alone is ~3100: needs a coarser cap or a tier
cap) and promote to the style defaults; A/B again vs c14s / c11L (review-ab after 13:00 MT).
## Garrett short-hair shells sh4 (2026-10-19, hair-garrett agent, fresh; order: black rim cause, darker top / back, temple cards + fins toned, coarser far cap, all tiers + A/B)
Scratch $HG/shells/sh4/ (crop.py <out> <tags...>: front + profile hairline crops at 3x; q1.sh; ns.sh).
- (1) BLACK RIM: NOT A SHADOW. sh3d's hero GLB re-rendered with no hair shadows (shots shadow=0 proxy=0, no game shadow
  map): the rim is unchanged (front hairline, above the ear, nape). Its pixels are pure 0,0,0 and are NOT hair in the id
  pass (black there = skin / background); the atlas's transparent texels are ~110 grey (no alpha-bleed black). So the
  black is something seen THROUGH / UNDER the cap's edge, not the cap's texture. CODE: hair.SHELL_EDGE_LIFT (None = off) /
  SHELL_LIFT_EASE (5 mm): the shells cap's lift (2 mm + sagitta) eased to SHELL_EDGE_LIFT at the hairline; hx7 hh. now
  sets None-valued constants. hair_cap.VALUE_MAP (GREY_MAP-shaped colour factor by region, on the cap + shells' final
  colour via a value channel in hair_cards.atlas; in the combed / atlas cache keys): step (2)'s lever.
  STATE: q1 queued: sh3d cards-only render (is the rim the cap?), sh4a (edge lift 0), sh4b (1 mm), sh4v (sh4a + VALUE_MAP
  top .55 / band .85 .7 .6 .6 .6 / low .85 .75 .65 .6 .6). NEXT: crops + m.sh.
- (2) RIM CAUSE FOUND = the cap's edge lift. sh3d cards-only render (only= the cards' range): the skin at the hairline is
  clean (no hidden faces, no dark paint): the black is the CAP. sh4a (SHELL_EDGE_LIFT 0, ease 5 mm): the rim is GONE at the
  front hairline and over the ear (pure-black px < 30 sum: front 14 -> 0, profile 51 -> 4, back 80 -> 22; crops
  $HG/shells/sh4 crop.py sh3d sh4a). The lifted edge's UNDERSIDE (the cap is single-sided; its back faces are not hair in
  the id pass and shade black) showed through the 2-3 mm gap; shadows had nothing to do with it. A little remains at the
  nape (back 22 px). STATE: sh4b (1 mm) / sh4v (+ VALUE_MAP) building. NEXT: sh4v numbers; SHELL_CARD_VALUE (hair.py, the
  kept cards' colour factor) measured on the render for the temple rows.
- (3) sh4b (edge lift 1 mm): the rim stays (black px front / profile / back 5 / 41 / 56): 0 it is. sh4v (sh4a + VALUE_MAP
  top .55 / band .85 .7 .6 .6 .6 / low .85 .75 .65 .6 .6 on the WHOLE colour): all-hair p50 front 39.4 / q34 36.1 / side 37.0
  / back 31.4 (photo 43.1 / 42.0 / 37.9 / 34.5; sh3d 47.6 / 45.9 / 49.2 / 43.7): the lever is live and overshoots 3-6, BUT
  the silver went with it (p90 46-48 vs photo 47-58, segmented grey share front 69 -> 21 %, mid band front 38 vs 51): the
  photo is dark hair + bright silver (wide range), so the value factor now applies to the dark strands + base only,
  before the grey hairs mix in (hair_cards.atlas). Cards vs cap in profile (ctone.py): sh3d 55.1 / 49.6, sh4v 44.7 / 37.3
  (the cards take VALUE_MAP's "low" row by their angle now): need x .67-.78 on the sides -> SHELL_CARD_VALUE .75.
  STATE: q2 = sh4T, ALL FOUR tiers (sh3/tiers.sh) with sh3d + SHELL_EDGE_LIFT 0 + VALUE_MAP (base only) top .5 / band
  .85 .7 .6 .55 .5 / low .8 .7 .6 .55 .5 + SHELL_CARD_VALUE .75; fins off. NEXT: numbers, far's cap count, A/B.
- (4) sh4T first run FAILED at the far tier: a shells far tier keeps 0 cards (0 of 113: no hairline rows at far), and
  hair_clumps.bake_tiles took percentiles of nothing. FIX: cards_job bakes only when a baked card is kept. Hero / main /
  npc kept 83 / 62 / 51 hairline cards, shells 2 / 2 / 1 / 0. Hero cap + shells p50 32.4 / 33.8 L* (sh3d 43.7 / 44.5).
  STATE: q2 rerun (sh4T, all four tiers) chained to sh4/ab.sh sh4T (tiles + review-ab vs c11L and vs c14s).
- (5) sh4T BUILT, all four tiers (exp/sh4T): hero 13068 faces (cap+2 shells 9300, 83 hairline cards 3768; drawn 16836),
  main 7392 (cap+2 shells 6288; drawn 8496 <= 20000), npc 2832 (cap+1 shell 2424; drawn 3240 <= 8000), far 668 (cap only,
  0 cards; <= 1500): EVERY TIER IN BUDGET; the "far cap 3,100" worry was wrong (far's cap step 14 deg gives 668), no coarser
  cap needed. NUMBERS (hero, segmented all-hair p50 / MID std; photo front 43.1 / 3.7, q34 42.0 / 4.1, side 37.9 / 3.6,
  back 34.5 / 2.8): sh4T 43.5 / 5.0, 41.1 / 5.1, 42.3 / 4.9, 31.9 / 4.6 (sh3d 47.6 / 45.9 / 49.2 / 43.7): VALUE NOW ON THE
  PHOTO (front / q34 within 1, side +4.4, back -2.6); p10 22-34 (photo 24-30); texture std went UP (4.6-5.1 vs photo
  2.8-4.1: darker base, same strands = more contrast). Mid band front 42.7 vs photo 51.2 (the silver sides still short).
  Cards vs cap in profile 48.9 / 43.1 (still +5.8: SHELL_CARD_VALUE .75 not enough; front equal 44.7 / 44.3).
  A/B (bin/review-ab exit 4 before 13:00 MT; fresh blind general-purpose subagent on its trios, keys
  sh4/ab_sh4T_vs_*/key.json; label check: its "black jagged nape" fault sits on the NEW side in every view = consistent):
  vs c11L (shipped): front NEW, q34 NEW, side TIE, back TIE = NEW 2 / OLD 0 / TIE 2. vs c14s: front OLD, q34 NEW, side OLD,
  back OLD = NEW 1 / OLD 3. Its faults for new: BLACK JAGGED NAPE FRINGE (MAJOR, side + back), too dark / brown at the back,
  "wool" texture with no combing direction, light temple plates (q34). For the old ones: shard / plate cards at the temple
  and crown, a light crown cap seam.
  LOOK (mine, side trio, before the reviewer): new = one coherent dark mass, value right in front, but coarse fleck
  texture, no silver sweep over the ear, a black dashed nape edge and a light temple patch (the hairline cards).
## HANDOVER (hair-garrett sh4, 2026-10-19; nothing in flight)
STATE: hair-heads2 local commits only (not pushed). Rim cause found and fixed at the front / ear; value on the photo.
BEST GARRETT HAIR FOR EXPORT: still c11L's shipped card set (all tiers). sh4T beats c11L blind (2-0-2) but loses to c14s
(1-3) and has a MAJOR black nape fringe: not promoted. Candidate set: exp/sh4T (all four tiers, in budget; exact args:
$HG/shells/sh4/q2.sh = sh3d's + hh.SHELL_EDGE_LIFT=0.0 hh.SHELL_CARD_VALUE=0.75 hj.VALUE_MAP={"top": .5, "band": [.85, .7,
.6, .55, .5], "low": [.8, .7, .6, .55, .5]}).
RIM CAUSE: the shells cap is lifted 2 mm + sagitta everywhere; its single-sided edge's UNDERSIDE (not hair in the id
pass, shades black) shows through the gap. Not shadows (no-shadow render unchanged), not texture (transparent texels ~110),
not the skin (cards-only render clean). SHELL_EDGE_LIFT 0 (ease 5 mm) clears the front / ear (black px 14 / 51 -> 0 / 4);
1 mm does not. The NAPE still shows it (back 80 -> 22 px; the reviewer's top fault).
CODE (sh4): hair.SHELL_EDGE_LIFT / SHELL_LIFT_EASE; hair_cap.VALUE_MAP (regional factor on the dark strands + base, before
the grey hairs mix in; in combed + atlas cache keys) -> hair_cards.atlas; hair.SHELL_CARD_VALUE + kept cards take
VALUE_MAP's "low" row by angle (cval); cards_job skips the bake when no baked card is kept (shells far tier crashed);
hx7 hh. sets None-valued constants. tests/test_hair_shells ok.
SCRATCH $HG/shells/sh4/: crop.py (hairline crops 3x), ctone.py (cards vs cap L*), ns.sh, q1.sh, q2.sh, ab.sh <tag>
(tiles + review-ab vs c11L / c14s), m_sh4v.txt, m_sh4T.txt, ab_sh4T_vs_*/ (trios, key.json).
NEXT (in order): (a) the NAPE rim: crop the back at 3x; likely the nape edge needs a longer ease (SHELL_LIFT_EASE 10 mm
there, or ease by the edge's slope: the nape edge hangs, so 5 mm in from the line is still lifted) or the dangling
hairline cards there (reviewer: "black blobs dangling"); count black px in g1back -> 0. (b) silver sides: front mid band
42.7 vs 51.2: raise GREY_MAP band front / 60 deg or VALUE_MAP band toward 1 there; back p50 31.9 -> 34.5 (VALUE_MAP back
.5 -> .58). (c) temple cards still +5.8 L* over the cap in profile: SHELL_CARD_VALUE .75 -> ~.65. (d) texture std too high
now (4.6-5.1 vs 2.8-4.1): EDGE_SHADE .5 -> .35 or BASE_DEPTH up. Then tiers + review-ab (after 13:00 MT) vs c14s / c11L.
## Garrett short-hair shells sh5 (2026-10-19, hair-garrett agent, fresh; order: nape fringe, silver sides + back, temple cards, texture contrast / combing, tiers + A/B)
Scratch $HG/shells/sh5/.
BEST GARRETT HAIR FOR EXPORT (coordinator decision 2026-10-19, NOT Joe-approved): exp/sh4T, style "shells", ALL FOUR tiers in
budget (hero 13068 faces / drawn 16836, main 7392 / 8496, npc 2832 / 3240, far 668). Beat the shipped c11L blind 2-0-2; the only
complete all-tier shells set (c14s is hero-only, not shippable). Exact build ($HG/shells/sh4/q2.sh -> sh3/tiers.sh -> cards/c7/hx7.py
hg_G88a <out> tiers=hero,main,npc,far): ex={"headroom": 2.0, "style": "shells"} hq.SHELL_WIDTH=0.0005 hq.SHELL_LIT=0
hq.GREY_SPREAD=1.0 hq.LAY_COVER=1.5 hq.BASE_EDGE=0.008 hq.GREY_REGION=1.0 hq.BASE_DEPTH=0.25 hq.EDGE_SHADE=0.5
hj.GREY_MAP={"top": 0.1, "fa": [0, 60, 100, 140, 180], "band": [0.6, 0.75, 0.5, 0.3, 0.2], "low": [0.5, 0.55, 0.35, 0.12, 0.08],
"band_h": [0.15, 0.35, 0.6, 0.8]} hj.SHADE_MAP={"top": 0.6, "band": [1, 1, 1, 1, 1], "low": [1, 1, 1, 1, 1]}
hj.VALUE_MAP={"top": 0.5, "band": [0.85, 0.7, 0.6, 0.55, 0.5], "low": [0.8, 0.7, 0.6, 0.55, 0.5]}
look={"card_grey": 0.7, "grey": "#6c6966", "lit": "#524e4a", "gap": "#1e1b19"} hh.SHELL_EDGE_LIFT=0.0 hh.SHELL_CARD_VALUE=0.75.
GLBs $HG/cards/exp/sh4T/hg_G88a_hair_{hero,main,npc,far}.glb. Future builds must beat sh4T AND, at hero, c14s.
