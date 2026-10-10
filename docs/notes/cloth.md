# hifipushie notes: cloth

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- Cloth (2026-10-01, `cloth.py` + `blender_cloth.py`, `pattern.py`, `tailor.py`, `freesewing.py`; the user: garments as
  real construction, drafted made-to-measure, sewn and simulated, never a finished garment warped onto another body).
  `spec["cloth"] = {name: garment}`: `pattern.from` a design in `cloth_designs.json` (FreeSewing parts by name, wraps,
  a seam table, button stitches, interfaced pieces, `fit_alterations`, tailoring `words` -> FreeSewing options) or own
  `pieces` + `seams` (a tablecloth is one piece). FreeSewing (MIT) is drafted in Node from `tailor.measure` (convex-hull
  girths and surface tapes on the body, FreeSewing's names), pack "freesewing" in assets.json, drafts cached
  (`<HOME>/_cache/freesewing`); missing Node/pack raise with the fetch command. `pattern` ops (turn, slash_spread,
  move_point, scale) are general 2D alterations; `large_abdomen` = front - back hps-to-seat past 25 mm, spread at the
  waist. Mesh: one flat mesh of all pieces, seams sampled jointly (chains with gaps = pleats), 1 cm triangles (2 cm made
  blobby padded folds), vertex mass scaled by area (Blender's mass is per vertex), solver quality 6 x (2 cm / h).
  Placement is isometric so rest = start: torso pieces on one generalized cylinder (the densified hull: a hull vertex
  as the start put the bodice 69 mm off centre), sleeves on the bent arm axis (sharp kink), a self-buttoned piece
  (cuff) closed on an exact spiral at its closed girth and moved off the hand's base with the sleeve's excess folded
  under (left open or over the hand it crumpled / dragged the shirt up), neck bands at their own girth on the neck's
  narrow part (`Body.neck_rows`; the neck joint is ~22 mm behind the neck's centre), curved bands on a cone from their
  sewn arc, a turned collar folded round a U with fold-line vertex rows. Sim stages (`blender_cloth.sim`): 0 the bodice
  sewn alone (shoulder seams lift it ~10 cm; with the sleeves on it dragged them up the arms), 1 everything sewn without
  gravity at sewing force 6 over 90 frames (30 whipped the hem up 15 cm) with cuffs held, 2 gravity + self-collision,
  hang (body removed, pins on a hook, rack colliders), self-collision settle. Interfacing (whole pieces or bands
  `{"piece", "near", "within"}`: cut-on plackets) stiffens bending, shear and stretch. Fit report: strain vs the start
  per girth region, negative ease from the flat pattern (`sizing`) = TOO SMALL, and `integrity` (self-crossings per
  piece, crumpled/folded faces, twisted seams) leading the verdict with CORRUPT. Diagnose with per-edge strain by
  piece and direction, start seam gaps per seam, and per-frame traces (`_trace`, `TRACE["stage0"]`): every fix above
  came from those numbers, not from tuning stiffness. Scene: `blender_cloth.show` (collection "cloth", pattern uv,
  Solidify); export: `cloth.export_part` (two-sided, the flat pattern as its atlas). Renders `workspace/cloth_renders/`.
  Cloth 2 (2026-10-02, the user: "learn how to do clothes" like hair, and everything through MCP; renders c20-c22):
  - Tools: `dress` (stores spec.cloth[g] merged, starts the sim in a background thread (`cloth.dress`/`_run_job`,
    progress in `workspace/<m>/cloth_<g>.progress`, `status`), waits `wait` s, returns progress or `cloth.report`),
    `look_cloth` (`cloth.look`: clay views + strain row + report; focus "g:piece", textured EEVEE with detail maps;
    hung garments show the rack, not the body), `sync(cloth_only=True)` (`cloth.sync` -> blender_scene `cloth_sync`),
    pull brings garment colour (`hp_color` node), roughness and SHAPE (Blender sculpt -> per-vertex offsets on that sim,
    `cloth.<g>.sculpt`, dropped and reported when the sim changes). `cloth.validate` at save; a cloth-only edit validates
    only hair+cloth (`store._validate_light`). Guide `guide(topic="cloth")` = `cloth_guide.md` (artists' workflow with
    sources: MD's 20 mm block -> 5-10 mm final, layers, fold lines, clean-up sculpt, Hogarth folds, seams last).
  - Sims never block a sync: `scene_job` takes only cached sims (`build(cached_only=True)`). The sim cache key is the
    sim's own inputs (start, pattern, triangles, seams, stitches, interfacing, both meshes) + blender_cloth.py's hash +
    fabric, not cloth.py: report/clean-up edits never re-simulate (`NOT_SIM` keys: color, roughness, cleanup, detail).
  - quality "final" = the whole sim at `coarse` 2 cm (~45 s), then `transfer` (barycentric in pattern space) onto the
    1 cm mesh whose REST is the coarse placement carried over (placed again at 1 cm its cuff spiral differed and an
    interfaced cuff crumpled), settled 40 frames with self-collision (`blender_cloth.refine`: Basis = rest, shape key
    "start" eased out, Dynamic Mesh). Shirt 3-5 min (was 8-25). "draft" = the coarse sim alone.
  - CORRUPT causes found: (1) no self-collision while sewing (fronts passed through each other): on in every stage;
    (2) the sleeve laid round the kinked elbow overlapped itself inside the crook (58 crossings in every START, grown into
    tangles): the excess round the mitre (r (u . n) tan(theta/2) per angle) is laid as a fin standing out in the mitre
    plane (`wrap.no_fin` off); (3) the hung coat: hang sewing force 200 drew it into a sack (now sew_force) and rack
    colliders kept Blender's 2 cm outer thickness (now 3 mm); the hang stage had no self-collision (now on).
  - Clean-up (`cleanup`): Taubin 4 passes at 1 cm (scaled by (1 cm / h)^2), each move capped at `keep` 4 mm, interfaced
    vertices not smoothed (smoothing crumpled a cuff 2 -> 6%), seams the sim closed welded, pushed off the body (not when
    hung). Strain/fit read the sim's own surface (`V_sim`), integrity the cleaned one (and the sim's, reported).
  - `shape_numbers`: crinkle = median dihedral between neighbouring triangles (1 cm sim 8-10 deg, cleaned 5-6), crinkle_mm
    and folds_mm along the smoothed surface's normal (plain Laplacian over ~15 cm; Taubin keeps low frequencies).
  - Detail maps (`detail_maps`/`write_maps`) on the flat-pattern atlas from the pattern itself: seam grooves + allowance
    ridge on sewn border edges, dashed topstitch at arc length along the outline, turned hems on free edges, buttons
    (discs, holes, button colour) on button* marks, slots on buttonhole*; normal + shade + basecolor; into the scene
    material (normal map on the "pattern" uv) and the export.
  - Neck bands: a piece sewn to an already placed neck piece starts at that piece's edge (the design's fixed "above"
    left the collar 2 cm over a lowered stand); `wrap.tilt` optional (no tilt helped the thin body); the report HINTs a
    band pushed > 8 mm off the neck (taller than the neck: lower the stand).
  - `integrity`'s candidate search: per-edge radius + a few big triangles apart (one global radius made 70M pairs, 11 s).
  - Body: `Body.m` lazy (a collider that isn't a body measures {}); state "draped" collides with the model's built
    mesh (`model_body`), pieces wrapped "flat". `tests/test_cloth.py`.
  - Solver-neutral job + GPU spike (2026-10-02, `cloth_job.py`, `spikes/gpu_cloth/`, renders g01-g02): the sim is a
    folder (job.json + in.npz -> out.npz: flat pattern = rest, start X, F, piece, sew/stitch pairs, interfacing, body,
    pins/hook/rack, `fabric.physical` SI numbers, the stage schedule spelled out by `cloth_job.stages`). Garment key
    `backend`: "blender" (default) | "file" (write the job, wait for out.npz) | "remote" ($HIFIPUSHIE_CLOTH_REMOTE run with
    the folder, e.g. `spikes/gpu_cloth/remote.sh` over ssh); results take the same clean-up/fit/integrity path, and a
    non-Blender backend is in the cache key. `run_newton.py` = NVIDIA Newton 1.6 VBD (warp, Apache-2.0): seams close as
    zero-length springs whose rest length shrinks, then are WELDED into one vertex for the gravity/hang stages (springs
    and self-contact fought: the yoke stretched 22-29%); a CUDA graph per frame; full-surface body contact (SDF) is
    CUDA-only. Results on a rented 4090 (shirt 1 cm 13.5k verts): 50-75 s vs Blender final 425 s / direct 1 cm 2530 s;
    smooth, no tangles, but VBD is convergence-limited (a hung sheet is ~100x softer than its stiffness at 10 substeps;
    stiffer material changes nothing, substeps do): strain p95 17.6% at 10 substeps, 9.9% at 40 (hem rides up, a waist
    crease); 5 mm shirt 56% / 17% with split sleeve seams; the hung coat rubbery at 10 substeps and NaN in the hang
    stage at 30-40 substeps or 5 mm. The user picked the 1 cm / 10-substep Newton shirt as the best LOOK (smooth, no
    tangles) despite its strain: the report now has a "reads" line (sim crinkle, fold depth) ranked before strain.
    Round 2 in run_newton.py: position-based strain limiting after each frame (`strain_limit`; edges past 1+limit
    pulled back, moves capped at 1 mm: 4 cm strain p95 8.9 -> 2.6%), interfaced pieces take their bending rest from the
    placement (`bend_rest`: with the flat pattern's 0 the turned collar unfolded into a hood; Blender's rest is the
    placement), seams stay welded while hung (the hang re-opened them as springs). ZOZO ppf-contact-solver (Apache-2.0;
    strain limiting, stitches; rest = the asset's 3D shape, uv only orients anisotropy; writes vertices REORDERED, map
    back by frame 0) via `run_zozo.py`/`zozo.sh`: its self-contained release (own Python, own HIP runtime) runs on this
    laptop's 890M with the ROCm backend and no SDK: 4 cm shirt 0.45 s/frame, 0 crossings, strain ~0.1%; at 1 cm it
    needs contact-gap 0.3 mm (the 1 cm pattern mesh has 0.5 mm sliver edges along seams: CCD fails at frame 0 with
    1 mm) and runs 9 s/frame (~45 min a shirt): too slow locally; spatial interfacing bend + bend rest from geometry
    together hit a non-PD block once.
    Round 2 on a 4090 (renders g04, g05): Newton shirt 1 cm, 10 substeps, 20 VBD iterations, strain limit 3%: 64 s,
    verdict "fits", 0 crossings, nothing crumpled, the collar turned down properly, smooth (sim crinkle 3.2 deg), strain
    p95 10.4% (round 1: 17.6%, CORRUPT stand, collar a hood). The strain limit alone barely helps at 1 cm (8 Jacobi
    iterations; 60 with a 2 mm cap dropped the coat through the body): iterations do. Hung coat 1 cm, 30 substeps +
    strain limit: 167 s, no NaN (welded hang), reads like a coat on a hanger, strain 8%, crossings only at the back
    vent (Blender has them there too). ZOZO on CUDA, shirt 1 cm: 451 s, strain 0.1% and cotton-like torso wrinkles,
    but the sleeves bunch at the elbows and tear (332 crossings inside the placement overlaps that
    `allow-existing-intersection` exempts) and the collar crumples: its rest = placement inherits the sleeve fins.
    ZOZO's coat: stitches whose ends start together give a NaN force (dropped now); then 2.3 s/frame, unfinished (90
    of 364 frames) at the pod's deadline. Runner defaults now: 10 substeps x 20 iterations + 3% strain limit worn,
    30 substeps hung.
    ZOZO round 3 (2026-10-02, local 890M at 2 cm, renders z0x): the 4090 sleeves rode up and tore because ZOZO sets a
    pin's pass-through (`allow_intersection`) once at build and keeps it after the unpin: every piece pinned while the
    bodice assembled (sleeves, cuffs, collar) passed through the body for the whole sim; and the cuff hold was (hold -
    fixed) = empty. Now garment key `placement: "smooth"` (backend file/remote only): ZOZO's membrane rests on the
    FLAT PATTERN (rest_vert written into the built scene: the frontend only derives a rest from pins), the made pieces
    (`cloth.made_pieces`, wholly interfaced) rest as placed in stretch and bending (`set_bend_rest_vert`; spatial bend
    x40 on them ran without the old non-PD failure); the garment is placed on `Body.straight_arms` (forearms turned
    into line, blended over +-4 cm at the elbow's mitre plane) and a "pose" stage bends them back through 4 poses with
    the sleeves on (sleeves are tubes on one straight fitted axis: a wandering axis stretched the cap 7%, past the
    limit; blousing compressed along the arm, not turned under); the start must be clean: `_piece_crossings` moves
    sleeves down the arm / overlapping torso pieces a layer apart, a cuff's outer layer moves out with the inner one,
    cuffs clear the wrist by CLEAR + h/4. Strain-limited solvers can't START past the limit: check sigma of flat ->
    start per triangle before a run. Runner for smooth jobs: no pins on pieces (a pinned cuff on the wrist is two
    prescribed things in contact: "contact starts overlapping"), allow-existing-intersection on (only the start's
    linked pairs are exempt), the arms split off the static body (a body with a move is solved: 2.95 -> 1.24 s/frame),
    a hung garment's body stops colliding by `collision_windows` (moved away down through the sleeves it dragged them
    against the hanger pins; windows act on solved objects only, so the static body gets a still move; and the session's
    dyn_param.txt (gravity) overwrote the scene's windows file: run_zozo appends them back), output rows by `map_by_name` (frame-0 matching failed on coincident vertices; `zozo_recover.py` rebuilds
    out.npz from a session's vert_N.bin). Mesh: FreeSewing notches were vertices 0.47 mm inside the outline (the 1 cm
    sliver edges); marks within 0.4 h of the outline are its vertex now (min edge 4.1 mm, min quality 0.26).
    Shirt 2 cm: fits, 0 crossings, nothing crumpled, sleeves to the wrists on the bent arms, collar turned down; reads
    crinkly at 2 cm (9.5 deg), strain p95 5.5% (outside of the elbows).
    Rack (`run_zozo`, hung jobs): capsules far from the hook stand still; the hanger's arms start inside the body under
    the hanger loop (`rack_drop` 8 cm lower: from the loop itself they touched the collar, "contact starts overlapping")
    and rise with the pins, colliding from the hang on: the coat is held by its shoulders. 1 cm on a 4090 (z02, z03;
    `pod_zozo.sh check|run`, the release fetched on the pod from GitHub): shirt 164 s (was 451), fits, 0 crossings,
    nothing crumpled, crinkle 7.4 sim / 5.0 cleaned, strain p95 4.9%; hung coat on the rack 664 s, holds its shoulders
    with the sleeves hanging (the best hung coat of the three backends to the eye), but 100 crossings at centre back and
    the stand/collar 18/11% crumpled where the hanger loop is gathered (the 2 cm run: 0 crossings). Open: cuffs start
    as circles round an elliptic wrist (pushed out 18 mm, so the made cuff is too big and ruffles), collar points stand
    up, the back crossings at 1 cm.
  - On a hanger (2026-10-02, "hanger" agent, renders h01-h1x; the user: "none of the coats ended up hanging on their
    hangers": every backend held the coat by pin patches at the neck, the rack decoration). `hanger.py`: a shaped
    hanger fitted to the body (`fit`: arms under the shoulders' upper surface (vertical rays, `clear` 8 mm) along their
    slope, width = shoulder points - 2 cm, wood arms 1.6 cm round at the centre broadening to 4 cm deep rounded ends,
    optional `bar`; the hook's rod up the neck's centre to 5 cm over the garment's start collar, curled over a face-out
    bar running BACK to a post: a through rail put a post in front of the coat), meshed from its own field as one
    closed collider (OUTWARD normals: the first mesh's inward faces held the cloth inside the arms and the coat climbed
    them). State "hung" = `{"hang": {"hanger": {...}, "rail": {...}}}` (the old pinned hang kept). It sits inside the
    body while the garment is dressed; stage "lower" (`Body.arms_down`: arms turned about the shoulder joints until the
    forearms are 7 cm off the torso, 26 deg here; poses `bodyLower`) brings the sleeves to the sides (left in the A-pose
    they hung splayed); then the body goes and gravity settles it onto the hanger with nothing pinned. Blender: seams
    WELDED while hung (as springs they opened under the weight, 36 mm mean, and the arms came out through the shoulder
    seams), hanger skin `HANGER_SKIN` 0.25 h (1 cm held the coat 4 cm up, bouncing), air damping `HANG_AIR`, 240
    frames, the sim's rod thickened to `HOOK_GUARD` 0.4 h (2 cm cloth folded through the 6 mm wire); the fine refine is
    SKIPPED on a hanger (the coarse hang carried onto the 1 cm mesh: the settle flailed 62 mm/frame and crossed at the
    back). ZOZO: hanger + rail static colliders from the start, the body's collision window ends at the hang; the
    lower stage moves the arms object. Newton: static meshes; it can't move its body, so "lower" is skipped there.
    Report `hanger:` line (`hanger.support`, `on_hanger`, `verdict`): the load each support carries = cloth mass by
    nearest support over the cloth graph (contact within 8 mm, by part, pins), still moving (p99 move over the last 6
    frames, `Vprev` from every runner: p90 per vertex <= 1.5 mm/frame and the centre of mass <= 0.5; Blender jitters single
    vertices ~2 mm on a coat whose mass stands still), floor; inside = rays front/back/up from 40-95% along each arm meet cloth, the
    rod crosses no cloth, cloth behind it (4/4 back sectors) and on both sides from 3 cm under the arms to 8 cm up (an open front
    is fine: lapels, V necks). NOT ON ITS HANGER leads the
    verdict; a coat floating in front fails (`tests/test_cloth.py`). ZOZO 2 cm (h04): on the hanger, arms 56/44%, 0
    pins, reads as a coat on a hanger. 1 cm on a 4090 (h12 ZOZO 911 s, h13 Newton 361 s): both ON THE HANGER (arms 100%,
    still), ZOZO's collar sits round the hook; crossings at the back vent (ZOZO 80, Newton 190), sleeves still ~20 deg
    out (arms_down stops 7 cm off the torso), Newton's splayed (no lower stage). Blender final h11 smooth (4.3 deg). Disk: run_zozo prunes vert_N.bin while running, deletes its session after, and
    refuses < 20 GB free / stops < 10 GB; cloth sims refuse < 20 GB.
  - ZOZO as a backend (2026-10-03, "zozo2" agent, renders zz01-zz1x; the user: "defer more Newton and double down
    on ZOZO"; Blender stays the local default). Garment key `backend: "zozo"` (`cloth_job.run_zozo`): the runner is
    `src/hifipushie/cloth_zozo.py`, run by the release's own Python (no hifipushie imports); the release is
    $HIFIPUSHIE_ZOZO / $PPF_ROOT or the optional asset pack "zozo" (assets unpack keeps symlinks: its Python's bin/ is
    symlinks). Local: under resources.heavy, a systemd scope (MemoryMax $HIFIPUSHIE_ZOZO_MEM 6G), device cuda/rocm/cpu
    found or $HIFIPUSHIE_ZOZO_DEVICE. Remote: $HIFIPUSHIE_ZOZO_REMOTE (spikes/gpu_cloth/remote.sh, GPU_RUNNER=zozo,
    GPU_SSH_OPTS; copies the job + the runner; `pod_setup_zozo.sh` unpacks the release on a pod by sha256). Defaults
    for zozo: placement "smooth", ONE sim at `resolution` (no coarse -> fine), clean-up without Taubin (it rounded
    ZOZO's fold crests 20-40%: sleeve crest radius p50 12 -> 17 mm at 1 cm; crinkle 7.0 deg unsmoothed, 0 crossings),
    garment key `zozo` = solver options into job.json (contact_gap, strain_limit, dt, interfacing_bend, snap, set,
    shear_model, uv_frame, ...). The sim cache key hashes the solver's runner (`cloth_job.solver_code`), never
    blender_cloth.py, and not where it ran; `look_cloth(result=)` applies any out.npz. The runner logs per stage where
    the time went (`profile`, from ZOZO's output/data/advance.*: steps/frame, how much of dt each step advanced and
    whether contact or the strain limit stopped it, newton, PCG, contacts) and `progress:` lines; `zozo_rows.npy` maps
    a session's vert_N.bin rows. Report: `sleeves from vertical` for hung garments.
    Material: ZOZO's shell hinge = BEND_SCALE 1.28e-5 x bend x areal density x |e|^2/A, so `zozo_bend` = B / (1.28e-5
    x density) from Kawabata B in PHYSICAL (shirting 0.02 gf cm2/cm -> 1.3, wool coating 0.2 -> 3.5; the runner had
    passed 1.0 for every fabric). Its Baraff-Witkin membrane takes E and nu; a patch test (spikes/gpu_cloth/
    zozo_patch.py) showed nu 0.045 makes it STIFFER in stretch and shear, so the old mapping (E = stretch/density,
    nu 0.3) stays. Placement: cuffs on a spiral round the arm's own (elliptic) sections at their closed girth; bands
    cleared by ZOZO's zone (4 mm, faces checked) not Blender's 8 mm; pieces closed round an arm rest as placed BEFORE
    the push off the body (`_made_rest`; pushed, a cuff rested 17-30% big and ruffled) with a strain limit above their
    start stretch (spatial "strain-limit"); collars/stands rest as placed. Hung: arms down straightened to 3 cm
    (`arms_down(straighten=True)`). Carlton's seam table was wrong: 867 mm of sleeve cap into a 603 mm armhole (the
    hindarm seam runs up to the back pitch / usTip), the stand sewn to the whole 425 mm neckline (now to the lapel's
    roll line), the 341 mm tail gathered into 243 mm (now pleated: FreeSewing points on an outline become outline
    points, `pattern._points_on_outline`). Open: hung sleeves spring out 13-26 deg within ~8 frames of the body
    going (at 8-10 deg at the end of lowering; not bend, not mesh size, not the hanger; compressed underarm cloth
    springing back is the lead), collars stand up, the coat's back side seam is 4 cm shorter than the front's.

- Clothing workflow (2026-10-03/05, "clothflow" agent; the user: "what artists actually do: building tools so LLMs can
  operate like real artists", and "all these learnings need to be codified"; renders `workspace/cloth_renders/wf_*`).
  The rule: construction before solver. A day of solver tuning chased what were pattern faults (cap ease 44%, a
  stretched stand, a missing belt, a pleat sewn shut, no sleeve placket, no lapel roll or facing, nothing pressed, one
  bend for every fabric). Stages, each readable before the next (`cloth_workflow.py`, `guide(topic="cloth")`):
  1. design sheet (`design_garment`, `spec.cloth.<g>.design`; `garment_design.py`): kind, from (draft source), fit,
     fabric, details, method, made. Defaults come from `garment_kb.json`; `cloth.expanded(g)` compiles the sheet into
     the ordinary garment keys (pattern options, drop, folds, generate, fabric, detail), the garment's own keys win.
     A choice the source can't make, or one that needs another (barrel cuff -> sleeve placket), fails.
  2. pattern (`look_pattern`; `pattern_sheet.py`): the flat sheet image (roles, grain, notches, seams numbered both
     sides, folds, interfacing) + evidence that every choice is in the pieces/seams (`garment_design.evidence`, roles
     not piece names), `cloth_check` seam bands (cap band by kind), ease per girth in the fit's band, loose pieces.
  3. construction (`check_garment`): sewing order, layers/lap, fold lines, interfacing, each piece made or draped
     (`made_or_draped`: draped cloth wholly interfaced fails, it is frozen as placed), the sim's stages.
  4. place: the start rendered and checked (crossings: fail for "smooth"/ZOZO, warn for Blender; neck band pushed
     > 8 mm; start stretch past ZOZO's strain limit; layer gaps).
  5. sim: verdict + `garment_kb.json` targets (`sim_measures`: collar cover, layer gaps, collar points, hem level,
     waistband height, sleeves hung, crest radius), each judged at draft or final; appended to `look_cloth`.
  `dress` (the MCP tool) runs `cloth_workflow.gate` (stages 1-3) and refuses to start a sim on hard failures unless
  `force=True`; `cloth.build`/`cloth.dress` in Python aren't gated.
  - `garment_kb.json` is the knowledge base (`garment_reference`): kinds (fit ease bands, default details, cap ease,
    lap, sewing order), details (collar, cuff, sleeve_placket, front_closure, placket, waistband, fly, skirt_closure,
    pockets, hem, yoke, darts, pleats, back_vent, belt, lining, shoulder, topstitch; each choice: made_of, seams,
    folds, needs, dims, evidence, lessons), fabrics with physical numbers -> solver preset + overrides, `designs` (what
    simon / carlton / skirt_block can and can't make, with recipes), targets, lessons. New kinds and details go there.
  - Fold lines: garment/design-table key `folds` [{piece, line, angle, strength, kind press|roll, radius}], angle on
    the pattern-face side (180 flat, 0 over onto the face, 360 under); `garment_design.fold_polyline` resolves the
    line forms; carried in `Bp["folds"]`. The solver side (mesh rows, placement, rest dihedral) is the "clothsim"
    agent's; until then evidence also accepts the old `wrap.fold` U and stage 3 warns.
  - `garment_blocks.py`: own drafts (`pattern.from: "skirt_block"`: front, two backs, darts, CB seam) and `generate`
    (bands sized from the drafted edges they're sewn to: waistband with lap + button, rib neckband as a ring).
    Torso wrap `"level": "waist"` (pattern y = 0 at that body line; the hull's z range stops at the pieces' top);
    `sizing` skips bands closed on themselves and girths the garment doesn't reach (a skirt read "TOO SMALL at chest").
  - `method: "settle"` (construct made pieces finished, settle draped cloth lightly, author fine folds; full sim for
    hung/draped) is the path under test by clothsim: the sheet and plan carry it, the solver doesn't yet.
  - Proved on Simon (`workspace/wf_simon`) and a new kind, the skirt (`workspace/wf_skirt`), at draft quality. Simon:
    the gate stops it (no sleeve placket, cuff seam -1.8%); forced, the collar-cover target reads -19 mm (the funnel).
    The recipe now drafts Simon's collar with no gap and width 1.45 (the seam was -2.4%, the fall covered 3 mm).
    Skirt: stages connect; the draft reads as a skirt but is strained at the dart tips, its hem dips 28 mm and it
    sits 21 mm low; with 11% seat ease one side seam gaped and the waistband crumpled (the pieces start on a cylinder
    far wider than the waist: a waist-fitted start is needed).
  - Open: Simon's sleeve placket (a slit op + cuff start at the slit), Carlton's belt/vent/facing/roll (clothsim),
    leg wraps for trousers, hoods/linings/pockets as pieces, button size and buttonhole direction per design in the
    maps, crease width and fold spacing as tool measures, per-piece fabrics. `tests/test_cloth_workflow.py`.

- Principle-based pattern drafting (2026-10-05, "clothflow" agent; the user: ready-made drafts are references, "we
  also need to distill the _principles_ so we can design jackets that don't exist yet, or any other arbitrary
  clothing"; sheets `workspace/cloth_renders/pd_*`). A new garment = a block + operations + details, as pattern makers
  work (Armstrong's three principles: dart manipulation, added fullness, contouring; Aldrich's blocks; FreeSewing's
  own designs derive from Brian/Bent/Titan the same way).
  - `pattern_blocks.py`: blocks by stated rules from `tailor.measure`: `bodice` (dartless or darted, to waist/hips;
    the front neck depth SOLVED so the neckline = half the neck girth + ease), `knit`, `sleeve` (drafted into an
    armhole: `solve_cap` finds cap height and top shift so front/back cap parts = front/back armhole x (1 + ease) at
    the asked biceps width; wider than the armhole is long -> not ok), `trouser` (forks, slanted back seam, the back
    fork dropped until the back inseam is 5 mm short). HALF pieces, centre at x = 0, every construction point named,
    `sym` = pair | fold | copy.
  - `pattern_draft.py`: the draft D (pieces, seams, `edges`, `notes`, `log`) and `OPS`: style_line (+ take_in),
    dart (pivot; the section holding the centre line never turns; an apex off the dart's centre line is trued onto
    it), dart_to_ease, flare (the centre side stays, the slashed edge is trued to a cubic), lengthen, extend, reshape,
    facing, collar (band / flat / roll from the neckline's own curve), sleeve, two_piece, unfold. What makes them
    compose: NAMED EDGES SURVIVE (`D["edges"]`: armhole_front, neck_back, hem_front, shoulder_front, centre_front...;
    `_remap` rewrites edges and seams through index maps when an outline is cut or a dart moves, breaking a chain
    where two old neighbours aren't neighbours any more; arcs must be resolved on the piece WITH the cut points
    inserted, or the bit up to the cut is lost). `consistency(D)`: every seam's sides equal, or its ease declared in
    `D["notes"]` (cap ease, gathers, the inseam); carried to `Bp["seam_notes"]` and honoured by stage 2 as kind
    "declared". `unfold` mirrors pieces and seams (fold pieces use ".m" names on the right).
  - Wiring: pattern `{"from": "draft", "block", "block_options", "ops"}` through `garment_blocks.draft` and
    `cloth.pieces`; the design sheet takes `block` / `block_options` / `ops` (chest ease defaults to the fit band's
    middle; judged by evidence, no recipe table). Knowledge: `garment_kb.json` `principles` (three principles, blocks
    with their rules, operations with what each keeps, derivations per garment category with why, rules of ease /
    balance / grain / shaping / proportions, sources), `garment_reference(principles=...)`; guide section
    "Designing a garment that doesn't exist". Don't re-dump garment_kb.json with json.dump (it reflows the file).
  - Checked against FreeSewing's Brian on the same body at the same ease (`pd_00_block_vs_brian.png`): chest width,
    armhole depth, shoulder and side seams equal to 0.1 mm, back armhole -2 mm, necklines within 1 mm, back outline
    1.9 mm mean; our front armhole is 9 mm longer (across-front 93%), our sleeve 35 mm narrower with a 26 mm higher
    cap (Brian widens the sleeve by its own rule). A drafted knit tee went through stages 1-4 (`workspace/pd_test`).
  - Style ops (`pattern_styles.py`, registered into `pattern_draft.OPS`; 2026-10-05, sheets pd_10..pd_17): `neckline`
    (widened on front AND back, so the shoulders still match), `shawl` (cut on, on the roll line; neck seam = back
    neck; `pair_seams` = an edge sewn to its own mirror at unfold), `lapel` + `collar` `"stop"`, `cut_away`,
    `darts_to_seam`, `raglan`, `kimono` and `hood` (pattern only: no placement), `pleat`, `buttons`
    (`pair_stitches`), `stitch`. `unfold` may be put in the ops list: ops after it work on one side (asymmetric).
    Bugs these found: a collar's outer edge was drawn on the neck hole's side (flat / roll collars shorter than
    their neck edge, crossing themselves; a band's top longer than its base): the body lies AWAY from the hole;
    a facing as a plain offset of its edge made beaks at corners (now the piece's own band within the width);
    a take-in inside a cropped hem left a hook (its end slides along the hem); point-given fold lines weren't
    mirrored at unfold; `cut_away` dropped the shortened shoulder seam instead of letting consistency fail.
  - `cloth.place` wrap `leg.L` / `leg.R`: one vertical generalized cylinder per leg (hull of that half of the body
    from waist to hem, cut flat 4 mm off the middle plane; outer part of each piece round the outside from the
    front / back corner, the fork's extension on the flat; isometric except the crotch hollow, squeezed under the
    crotch). Slices its own loops: `Body.hull` drops loops wider than the shoulders as arms, i.e. an A-pose's calves
    (the pieces started 37-52 mm inside the legs). Leg pieces count as torso for the assembly stage. `sizing`:
    facings / linings add no girth, pieces carry `wrap.half` (which side of x = 0 they're on: what crosses is
    overlap), side panels measure from their own inner edge (a princess jacket read +74% chest).
  - Three garments from prose through the tools (models `workspace/pd_trousers`, `pd_wrap`, `pd_jacket`; renders
    pd_20..22): wide trousers fit (0 crossings; slide 9 cm down, pool at the feet); the asymmetric wrap tunic reads
    as one (strain 11.8%, hem 9 cm lower on the wrap side); the shawl jacket's pattern and plan pass but its draft
    sim is CORRUPT (the cut-on collar starts up the front of the neck and Blender doesn't bring it round; two-piece
    sleeves bunch at the shoulders). No ZOZO release was on the machine: method "settle" untested on these.
  - Blazer from our blocks vs FreeSewing Jaeger (`pd_30_blazer_vs_jaeger.png`, scratch script): CB length, shoulder,
    back neck, upper armhole within 1-5 mm, armhole 2%, sleeve width 2 mm; Jaeger's shaped CB seam, side panel
    from the armhole, waist +17% (ours +29%), hem +12% over the seat (ours +2%), longer bent sleeve with a hollowed
    under sleeve and a straight gorge are what ours lacks.
  - Open: a start that lays a cut-on collar round the neck, a tailor's under sleeve, shaped CB seam, fish-eye darts
    in hip-length blocks, pockets / linings, head wrap, kimono placement, seat ease not reported for leg pieces
    (sizing reads torso pieces), trousers' length option for bare feet, a waistband that grips.
    `tests/test_pattern_draft.py`, `tests/test_pattern_styles.py`.
  - Round 2 (2026-10-05, "drafting" agent, branch worktree-agent-aaf5034835ab4c449; renders pd_40..pd_4x; scratch
    in the session scratchpad `drafting/`: run.sh <script>, st.py (stages), pl.py (place + crossings by pair + start
    strain by piece), dj.sh (dress + look in its own session), jg2.py (blazer vs Jaeger)).
    - HINGES (`pattern_draft.apply_hinges`, run at unfold): one cloth placed on two parts of the body. `D["hinges"]`
      {piece, at, dir, mid, origin, x, wrap, fold, part}: the piece is cut along the line for PLACEMENT only, the far
      part "<piece>_<part>" moved into its own frame with its own wrap, joined by a seam noted `"virtual": true`
      (seam_notes; `_sewn_arc` skips it; the maps should not draw a groove there: not done). Pieces traced from it
      (`pc["traced"]`: facings) are cut the same way, fold lines that cross are cut with it (`_split_fold`; a
      line point ON the hinge counts as across), and the cut gets a vertex where each fold crosses. `op_shawl` uses
      it: the collar past the neck point goes on the neck wrap (`flip`: pattern face out, `girth`: the whole circle
      a partial band belongs to, `apart`, `out`). The start-gap warning's 279 mm neck seam is now 88 mm.
    - The shawl's back collar needs SPRING: a strip run straight on from the roll line can't turn down (a cylinder's
      top has no isometric fold). It is an annular sector now (`spring` = outer edge - neck seam; default from the
      fall), laid on a cone flaring up, its fall folded at the ONE isometric angle (2 x the cone's half angle) as a
      single crease (a roll's rows round a curved line stretched the flap 70%).
    - `wrap.lies_on` + `cloth._lay_on`: a facing is placed as its front's placed surface, LIES 3 mm off the inside
      face (so on a turned lapel it is the side that shows), with a small untangle against that piece; it takes the
      front's fold lines (same mesh rows). Wrapped and folded by itself it had to pass through its front. The left
      front laps 4 mm + 12 (a fold) + 4 (a facing) out: what lies between the fronts. `style_line` panels start
      2 mm apart (`wrap.shift`): edge on edge they read as crossings. `cloth.mesh`: a roll's rows each end on their
      own outline vertex (sharing one bent every row's end: 150% stretch at the piece's edge).
    - Two-piece sleeve: the under sleeve was built wrong side up (folded-in strips) and so went round the arm the
      other way: both sleeve seams started ~15 cm apart and the sewing knotted the sleeve at the shoulder. Turned
      over now. `elbow` (m the wrist comes forward) bends each piece about its forearm seam's elbow point
      (`pattern.bend` / `unbend`; `wrap.bend`: place lays the straight sleeve): forearm seams equal, the top's
      hindarm 9 mm longer (elbow ease, declared), hem square to the forearm. A jacket sleeve needs `hem_width`
      ~0.28 (the block's default is a shirt cuff's: the forearms read red).
    - `pattern_tailor.py`: `contour` (an edge moved in / out per level: shaped CB seam, hem spring; a style line's
      name shapes BOTH its edges), `join` (two pieces sewn together become one: a side panel with no side seam; the
      seam's shaping is reported lost; b's clashing names become "name@b"), `round_corner` (cut-away hem; the corner's
      name stays on the curve's middle), `fisheye` (run on to the hem as a closed 3 mm cut: no holes in a cloth mesh;
      `darts: true` on a hip-length bodice now makes them), lapel `gorge: "straight"` + `gorge_drop` + `notch`.
      `take_in` on a STRAIGHT cut shaped nothing (two vertices): edges are densified first; a shaped panel seam's
      length difference under 2% is declared (`press_note`: pressed / eased on). `tests/test_pattern_tailor.py`.
      Blazer vs Jaeger again (pd_45): waist +16% (Jaeger +17), hem +12% (+12), CB length +1 mm, CB seam and side
      panel there; left: Jaeger's narrower side panel, its under sleeve's S-shaped top, chest +8% vs +4%.
    - ZOZO start: stage 4 passes for the jacket (0 crossings). Draped triangles that start past the strain limit by
      construction (fold rows on a curving chest, a stand pushed 1-3 mm: 0.7%, up to 16%) get the local strain
      limit in cloth_zozo (`start_over` 3%) and are info in stage 4; more, or > 60%, still fails.
    - Trousers: block `length` words (TROUSER_LENGTHS: floor, shoe, ankle (default: barefoot bodies), cropped, calf,
      knee, shorts); stage 2 `leg_ease`: seat ease in the fit's band from the legs' pieces, per-leg thigh / knee / hem
      against the body's own leg. The waistband slid 9-10 cm because it STARTED wrong: `place`'s torso hull ran up to
      the shoulders for every garment (`max(ytop, -0.03)`: a bug), so a waistband alone lay on the chest's curve,
      its back half 16-25 cm from the trousers. Now the hull stops at the pieces' own top, a band buttoned to itself
      alone on the torso lies at its CLOSED girth a few mm off the waist with its lap a layer out (start gap 161
      -> 46 mm). `waistband` op: the generate entry's chain is made at unfold from the waist edges as they are
      then (it had to be written by hand).
    - Stage 4 `seam_start_gaps`: `turned` = the rotation that lays one side of a seam on the other is > 35 deg
      with a median gap > 8 cm, for seams with a chain side. A waistband mis-ordered by half a turn has gaps of
      only a waist's diameter (247 mm < the 250 mm "far" limit: the distance check did NOT fire); a ring inside a
      ring (hood vs neckline) and a shoulder seam are not turned. `tests/test_cloth_workflow.py`.
    - Placement by hinge again: `kimono` (the sleeve past the underarm-to-shoulder line on the arm: `wrap.cx` =
      the pattern x along the top of the arm, front half `front: -1`, back `+1`, mirrored on the right arm: pair
      pieces on arms in unfold); wrap `head` (hoods: one plan curve round the head from the back, the sides `apart`
      by the centre seam's bow). `pocket` (patch, kangaroo: traced, `lies_on` + `face: "out"`, tacked by
      `sym_stitches` mirrored at unfold; a tacked piece counts as attached in stage 2), `lining` (every body piece
      traced, seams repeated, laid inside, sewn to the shell at hems / sleeve hems / back neck; same outline, no
      pleat, one fabric). Not drafted: welt / flap / in-seam pockets.
    - `skirt` block for the ops (pattern_blocks.skirt; a cut ACROSS a piece names the upper part first and keeps the
      centre seam on both parts; a pleat on a piece cut on the fold is pressed on both halves; pleat `underlays`
      are not girth in `sizing`).
    - Two new garments from prose through the tools (sheets in examples/garment_sheets): `raglan_anorak` (bodice
      cf fold, neckline, sleeve, raglan, hood, kangaroo pocket; model pd_anorak) and `yoke_skirt` (skirt block,
      yokes, a pleat each side, flared back, waistband op; model pd_skirt). What the tools lacked on the way, all
      fixed: a tacked pocket read "sewn to nothing"; the hoodie had no boxy fit band (a straight body on a V-shaped
      torso is +51% at the waist); the turned check fired on a raglan seam (single edges at an angle) and on the
      hood (ring in ring); the kangaroo pocket's default ran past a short hem; the skirt had no block for ops and no
      waistband op; the yoke's centre seam and the second pleat were missing; pleat cloth read as +12% seat ease.
    - Results (renders pd_41 Blender jacket, pd_44 ZOZO jacket (raw V), pd_46 trousers, pd_47 tunic, pd_50 anorak,
      pd_51 skirt): the shawl jacket on ZOZO settle: "fits", 0 crossings, strain p95 1.5% (646 s at 2 cm), lapels
      turned, sleeves smooth; its raw surface had the centre back OPEN from the neck (coincident centre-seam
      stitches are dropped by the solver: centre seams now start 2 mm apart, NOT re-run). Blender draft: reads as
      the jacket, 1 crossing, facing collar 4% crumpled, puffy. The skirt stays at the waist (Blender); the
      trousers on Blender still slide 99 mm (run before the waistband start fix; the ZOZO run never started).
      The anorak's body, pocket and hood read, its RAGLAN SLEEVES crumple at the shoulders (22 crossings): the
      sleeve's shoulder part lies along the arm, 173 mm and ~60 deg from the body's cut. Stage 4 names it
      (turned). Fix = a hinge in `op_raglan`: the shoulder parts placed on the torso in the coordinates they were
      cut in, the sleeve on the arm. The tunic reads as a wrap tunic but is over-cinched (take_in 56 / 62 mm over
      9 cm now really shapes) and strained at the tie.
    - THE ZOZO RELEASE IN THE SCRATCHPAD BROKE during this session (its python/lib/python3.12 lost most of the
      standard library some time after 12:49 on 2026-10-05: "No module named 'encodings'"): every zozo job fails
      until it is unpacked again (asset pack "zozo"). Not caused by these changes.
    - Open, in order: re-run jacket + trousers on ZOZO once the release is back (dj.sh); the raglan hinge; a
      facing's free inner edge (tack it, or settle's treatment of made pieces that lie on draped cloth: asked
      clothsim); virtual seams still draw a groove in the detail maps and the pattern sheet draws hinge parts
      apart from their piece; welt / in-seam pockets; lining trimmed to the facing; the under sleeve's S-shaped
      top; `hem height spread` reads designed curves and yokes as unevenness (skirt 490 mm, tunic 82 mm).
    - Round 3 state at the stop (usage limit): added the raglan hinge (shoulder parts on the torso), pleats laid closed by the wrap (`wrap.pleats`, folds `in_wrap`), welt / flap / in-seam pockets, `y: "waist"` in point specs, the tunic re-cut at the waist. Facings are still wholly interfaced (= made); marking them draped (clothsim's advice) stretched them 100%+ round the roll's rows: reverted, open.
      Sims queued through `drafting/seq.sh` and NOT judged: pd_52_jacket_zozo (running), pd_53_trousers_zozo, pd_54_anorak_blender, pd_55_skirt_zozo, pd_56_tunic_blender (logs in the scratchpad `drafting/<tag>.log`, renders in cloth_renders). Not started: the remaining Jaeger differences (under sleeve `shift_back`, side panel width, chest ease).
    - Stale option trap: `design_garment` merges key by key, so an old `block_options.darts: true` (which did
      nothing at hip length) suddenly made fish-eye darts under a princess line. Give `"darts": false` with panel
      seams, or replace the sheet.
    - Round 4, construction faults (the user on pd_52 / pd_55: "lapels aren't attached right", "stitches super
      visible", "the skirt is unzipped"; renders pd_62..pd_6x). Diagnosed on the raw sims, all three were the same two
      things: MADE PIECES PLACED WHERE THEY CAN'T END, and ZOZO stitches too weak to close a seam.
      - The jacket's board: `front_facing` (wholly interfaced = made = carried rigid by the settle) was a plank 54 mm
        off the body, 16-64 mm off its front, its seams never closed. A facing is now FUSED to its piece
        (`op_facing` sets `wrap.fused`; `cloth.pieces` sets fused pieces and their seams aside in `Bp["fused"]`: one
        cloth for the sim; `"separate": true` keeps a piece). The left front's lap is 4 + 10 mm (was 20).
        `folds.apply`: a flap is only the cloth BESIDE its line: the button stand below a roll line's break point was
        turned 170 deg into the other front (28 crossings, a "70 mm push").
      - The skirt's V at centre back: the waistband (made) was laid on the garment's one cylinder (hip girth), 30 cm
        open at the back, and carried rigid: its button stitch ended 352 mm open and the yokes sewn to its ends were
        held apart. Now a band closed on itself among other torso pieces lies on the body's hull at ITS OWN level
        (the narrowest slice over its height) at its closed girth; shorter than that + the solver's 4 mm clearance
        is `B["band_short"]`, a stage 4 failure (the skirt needed waist ease 3%: its band sits above the waist line).
      - Seams: the runner's own last line had said it all along (seam gaps mean / p95: trousers 3.5 / 14.5 mm, jacket
        15.5 / 57.7, skirt 19.3 / 97.1). ZOZO's `stitch-stiffness` (default 1, its force capped by
        `stitch-length-factor`) at 30 closed every draped seam to ~1 mm (a side seam starting 124 mm apart: 1.4 mm)
        at 7x the time; 8 gives mean 3.1 mm at 3x. The sheets set `zozo.stitch_stiffness: 8`; the default is
        clothsim's call (it stays 1). Clean-up welds seams again after the push off the body (the push reopened
        them) and clay looks draw welded faces (`cloth.welded_faces`: duplicate seam vertices shaded as a pale line).
        Stage 5 measures `seam_gap_p95_mm` (target <= 0.5) and `closure_gap_max_mm` (<= 6) and fails on them.
      - Closures: stage 3 `cloth_workflow.openings`: every pair "<name>.L" / "<name>.R" at the centre must be joined
        by a seam (a zip is sewn as one), stitches (buttons, a tie) or be declared (`design.open: [name]`). The
        skirt sheet said `skirt_closure: "none"`: now `cb_zip`. A zip has no record or geometry yet: clothsim's
        `closures` key (kind, over / under, line, lap, at, state) is agreed; the draft ops (buttons, stitch,
        waistband) should emit its entries once it is on main.
      - Tried and dropped: a waist-SHAPED start (per-level plan curves: the body's hull at each level out to the
        pieces' span there). Seam start gaps 124 -> 15 mm, but 10-30% shear in the start: a pattern puts its taper in
        the side seams and darts, a level-by-level wrap spreads it round the body, and arcs from the centre drift
        between levels. Like CLO, pieces start apart on a simple surface and the SEWING closes them: the stitch
        strength is the lever. Kept from it: in smooth placement the cylinder's girth is the SPAN of each side's
        pieces per level (pleats closed, laid-on pieces out), not the sum of widths.
      - Across cuts (a yoke): the lower part starts 6 mm off and a 3 mm layer out (a flared panel's top corner rises
        past the yoke's at the side seam, on the same surface: crossings once a pocket added vertices there).
      - Results (pd_66 jacket before/after, pd_67 / pd_65 skirt): jacket raw seam gaps 15.5 / 57.7 -> 1.4 / 2.5 mm
        (mean / p95), after clean-up p95 0.5, no board, button 9 mm (target 6: fails), back collar 4% crumpled
        (CORRUPT), body bloused and 6 cm shorter (stiffer stitches haul the fronts up to the carried collar). Skirt
        19.3 / 97.1 -> 1.8 / 4.8 mm, closed at CB, fits; the top of the CB seam 14.8 mm and the band's button 25 mm
        still open (a made band is pushed 4 mm off the body), pleat folds did not hold, pocket bags lump at the sides.
      - `collar` type "tailored" (stand_height + fall on a roll line, back part an annular sector: outer edge 36 mm a
        half longer than the neck edge, ends at the gorge; points cbNeck / cbRoll / cbOuter / endNeck / endRoll /
        endOuter, edges collar_neck / _outer / _end). Pattern + unfold tested only; clothsim places it.
      - STATE at the stop (usage limit, 2026-10-05): main merged in (60ffb1f). pd_64_trousers_zozo was queued behind
        the heavy slot (log `drafting/pd_64_trousers_zozo.log`), not judged. The merge changed the sim cache key:
        pd_62 / pd_63 need a re-sim for new looks. clothsim's taut `hpsToWaistBack` (on main after its merge) moved
        every block: pd_wrap now fails stage 2 (waist ease +11.1%), and numeric y options in the sheets (lapel
        break_y, style line y) need re-reading. Next: judge trousers; the button / band-top gaps (lap, the made
        band's clearance); switch buttons / stitch / waistband ops to clothsim's `closures` key once merged and read
        it in `cloth_workflow.openings`; re-fit the sheets to the new measures; anorak + tunic on ZOZO; run
        tests/test_cloth.py; the ranked "any garment from prose" proposal.
  - Fold lines, method "settle", authored fine folds (2026-10-05, "clothsim" agent, renders fl_*; the user: the cloth
    "appears thick", garments lacked construction; then the north star: artists construct and press collars and
    cuffs, drape the loose cloth, author the fine folds).
    - `folds.py`: garment/design key `folds` ({"piece", "line", "angle" (180 flat, 0 over onto the outside, 360
      under), "kind" press | roll, "radius", "strength", "flap"}; `pattern.fold_line` resolves the line and runs
      its ends out to the outline: a fold must cross its piece). `cloth.mesh` puts a vertex row on the line
      (`folds.rows`/`row_samples`: ladder twins beside the outline, ends snapped onto ring vertices, `force_edges`
      flips; `M["folds"]`). `cloth.place` lays every piece UNFOLDED on its wrap, pushes the base clear, then
      `folds.apply` turns the flap about the row per station as far as asked or as it clears its obstacles (own
      base, earlier pieces on the same body part, the body), eased along the line.
    - A curved crease has ONE isometric fold angle (180 - 2 x the cone's half angle: the fall's cone reflected);
      opened further the flap is stretched (130 deg: 17-75%). The collar blocked at 130 deg until both neck pieces
      shared a radius: each used to clear the neck over its own heights, so the collar stood 4-5 mm inside its stand.
    - Neck bands now go on the neck's own hull a clearance off the skin (`_cuff_spiral(m_min=)`, arc length kept),
      seated where their girth fits but with their top still on the neck (`_neck_frame(band=)`): the old circle
      clear of the neck's widest radius was 20-30% longer than the band, which stood open and far off the sides.
      Seated at the neck's base (1 cm lower) the yoke bunched up behind the collar. A stitched stand (button to
      buttonhole) closes exactly if it is long enough; Simon's isn't on a 4 mm solver standoff (it would need
      ~15% collar ease), so the shirt is open-necked. tailor's "neck" is the narrowest girth (370 here); a collar
      sits lower (385-397).
    - Solver: made pieces rest as placed (the fold is in the placement). Cloth resting flat gets
      `folds.bend_reference` (in.npz `bend_rest`: the flat pattern with flaps turned 170 deg; ZOZO reads hinge rest
      angles from it) and `fold` weights (bend x (1 + 20 x strength) on the rows, one spatial multiplier with the
      interfacing). `zozo.rest_flat: ["collar"]` runs a made piece that way: the collar held 157 deg (rest as
      placed: 129, the shirt lifts the stiff fall), cover 8.5 mm. Blender: `mesh(fold_width=FOLD_WIDTH_FITTED)`
      makes each fold a U 8 mm across (a single crease was blown open to 87 deg by its collision distances and
      crumpled).
    - A simulated crease can't have layers under ~3 mm apart: its first ring of vertices needs a contact gap
      (`wedge` = 1.2 mm / h in `folds.apply`). Layers <= 2 mm come from construction, not from the solver.
    - Method "settle" (`build`: `settle`/`construct`): `_carry` (made pieces pinned in ZOZO, in.npz carryIdx /
      carryPoses = a Kabsch move per pose fitted to the body vertices under each piece; cloth_zozo pins them for
      the whole sim), a 150-frame schedule without the assemble stage, then `_constructed`: transfer onto the fine
      mesh, the made pieces from the fine mesh's own placement (`FOLD_WIDTH_MADE` 1.6 mm U) fitted rigidly to
      where the coarse ones were held, flaps laid again (`_relay`), loose seam vertices drawn onto the made edges,
      `_tuck`. The cache key leaves the fine size out. 184 s sim + ~20 s on the 890M.
    - `cloth_detail.py`: fine folds from the drape's compression (per-triangle smallest principal stretch of
      pattern -> drape; amplitude (L / pi) sqrt(c)), Gabor-like dabs into a height map on the atlas,
      `cloth.fine_folds` -> `detail_maps(extra=)`. Sleeve crease width 6.7 -> 3.4 mm, spacing 19.7 -> 8.7 mm
      against the 1 cm full sim (zz16), measured on renders with the audit's profile method.
    - Folds, second pass (the main session: "combed/hatched"): `cloth_detail.fold_dabs` makes each dab ONE fold (a
      crest or crease, envelope half a wavelength: no ripple trains), bowed, its direction jittered 10 deg, lengths
      and wavelengths log-uniform, fewer where the compression is even; a second, sparse population 2.8x the size goes
      into the GEOMETRY of a mesh <= 1.2 cm (`displace`: outward only, fading 2 cm from outlines; build sets
      `folds_in_geometry`), the fine ones into the normal map.
    - Crossings: 44-90 came down to 18 (collar / front.R 10, sleeves 4 + 4; verdict "fits") once `transfer` ran on
      past the coarse outline instead of clamping (two fine vertices beyond one coarse corner landed on one point:
      a zero-area triangle) and the slit had parallel lips (a wedge's lips were 0.02 mm apart near the tip). The
      tuck and the seam draw still make the rest: moving cloth vertices without contact.
    - The fine settle (default with method "settle"; `fine_settle: false | [press, settle frames]`; `_press_plan`,
      cloth_job mode "fine_settle", cloth_zozo carryIdx / carryPoses / releaseIdx / restIdx; cached `<key>_fine.npz`):
      the constructed fine mesh settled for ~36 frames with the made pieces held and their flaps FREE from frame 0,
      resting folded as made (a fall bends over the shoulder cloth), LOCAL: only cloth within `FINE_REACH` 10 cm of a
      made piece is solved, the rest is held (solving it all, the sleeves crumpled again). What it took, in order:
      `_clear_of_body` (ZOZO's fatal pairs were body VERTICES 1.6-1.9 mm under the middle of sleeve triangles: now
      an exact body-vertex to cloth-face pass, held vertices too); `_relax_stretch` + a strain limit the start can
      meet (triangles at piece outlines started 5-70% stretched: "ccd failed"); flaps never prescribed against cloth
      (two prescribed things squeezing a third: "intersecting pairs"), opened only as far as clears what is under
      them; `_untangle` before and after; the clean-up reverts any vertex it would re-cross. Shirt: 0 crossings,
      "fits", fall covers the neckline seam 7.9 mm at CB, fall over what is under it 2.4 mm median, collar points
      5.4 / 2.2 mm off (with `tacks`: design key, points of a made piece held to the cloth under them, as collar
      stays / buttons do), sleeve crease width 2.7 mm / spacing 6.3 mm (zz16: 6.7 / 19.7). ~260 s settle + 50-100 s
      fine settle on the 890M. Fold flaps are stretch-capped in placement (`max_stretch` 0.30: at 0.04 the shirt
      collar turned 2 deg), and the draped start is relaxed with fold rows and flaps left as laid.
    - The neck-point knot (the main session: "diagnose it with numbers"): `tailor` put the shoulder point at the
      shoulder JOINT's x, inside the arm's root: the shoulder seam was 183 mm for ends 134-139 mm apart. Now the point
      where the shoulder line turns down (slope > the line's + 10 deg, never inside the joint) and shoulderToShoulder
      as a taut tape: 176 vs 148. The 28 mm left: the stand's ~12 mm standoff, the shoulder end 7 mm inside, the
      across-back drafted as a flat width (~10 mm). Three bodies re-checked: shoulderToWrist = the joints' path
      (553 / 583 / 544 mm), hanger width 2 cm inside the shoulder points.
    - Layered garments (`over: "<garment>"`, `cloth_layers.py`, renders ly_*; model `workspace/ly_suit`, Jaeger over
      Simon): the under garment is built first and frozen; `_collider` joins its result to the body (riding the
      body's poses by nearest body vertex), the outer garment is placed on `padded_body` (the body pushed out to
      cover it + `layer_gap` 3 mm). `support` (`SUPPORTS`: shoulder_pad, sleeve_head) are pads on that body, not
      cloth. `cloth_layers.tells` (in `res["tells"]`, the report, targets `layer_*` in garment_kb.json): under collar
      showing above the outer at CB 10-20 mm, cuff past the sleeve 10-15 mm, lapel gap, collar hug, crossings between
      the layers. `hidden` -> `export_part` leaves out the under garment's faces the outer covers (further than
      `hidden_margin` 3 cm from its free edges; `export_hidden: true` keeps them). Jaeger's table (flip_y on stand /
      collar, lapel roll folds on `breakLine`, vent folds, the armhole as one closed seam chain, pads) is in
      cloth_designs.json; its seam check passes except cap ease +1.8% (band 3-6). NO JACKET SIM HAS RUN: the ZOZO
      release was deleted from the scratchpad mid-work. Not built yet: the joint settle where the layers touch,
      lapel facing + gorge, chest canvas, weights copied from the outer layer, `over` in the design sheet.
    - ZOZO drops nothing now: stitches whose ends start together (edge-to-edge panels, a facing on its front) had no
      direction (NaN) and were dropped, so nothing sewed the seam (the "drafting" agent's jacket CB stood open).
      `cloth_zozo.part_stitches`: each such end steps 1 mm back into its own cloth (layers part along the normal),
      held/made ends stay; job `stitch_gap` (0 = drop as before).
    - Jacket rounds (2026-10-06, renders ly_01-ly_03, models `workspace/ly_jkt` (Jaeger alone) / `ly_suit`):
      ly_01 (Jaeger over Simon) was a puffer with a ruff. Causes, each separated on the jacket alone first:
      (1) `padded_body` spread every fold's crest three rings round (pad 29 mm at the median, to 71, over a shirt
      8-16 mm off the body: "biceps" 534 vs 340). Now one ring, and the under garment is `pressed` first (its loose
      cloth to `UNDER_CAP` 8 mm off the body along the body's normals, made pieces as they are, eased 3 cm round
      them; garment key `under_cap`): that pressed surface is the pad, the sim's collider, what the tells read and
      what renders show under the jacket (`res["under_V"]`).
      (2) The neck wrap is a ring round the neck: a tailored collar's stand (291 mm, sewn to a neckline that lies on
      the shoulders and runs down to the gorge) stood under the skull; tilted it went through the shoulders. Wrap
      `"to": "seam"` (`cloth._on_seam`): the piece's sewn edge laid on the edge it is sewn to (the seam's own vertex
      pairs), at the PATTERN's lengths, marched from the middle along the body's surface (the placed neckline is
      not one curve: fronts and backs start apart, 778 mm for 291; past a gap it heads for the edge's end), the piece
      running up the surface from there; `turn` {at, deg, gap} lays a fall over in the wrap (its fold `in_wrap`).
      Pieces are placed in listed order: what it is sewn to must come first.
      (3) `sizing` read -116 mm at the chest: the body's chest line is 10 cm above Jaeger's side panel's top, so the
      panel wasn't measured; the chest is now taken just under a panel that starts under the arm.
      Jaeger alone, 2 cm ZOZO settle: reads as a jacket, 0 sim crossings (4 from the clean-up at the vent), strain
      0.8%, sleeves to the wrists, lapels 164 deg; the collar is a lumpy roll (its fall starts 1.25x stretched: in
      FreeSewing's draft the collar's outer edge is SHORTER than its neck edge, both bow toward the fall; the author's
      own comment says the collar wants a redesign), fronts spread below the buttons (no facing), surface crinkly.
    - BODY MEASUREMENTS MOVED (2026-10-06; every draft changes, results before it are not comparable). Checked
      against FreeSewing's own standard masculine body (packages/models neckstimate: chest 1000, hpsToWaistBack 470,
      waistToArmpit 210, hpsToBust 280, shoulderToShoulder 450, biceps 350, shoulderSlope 13):
      (1) the down-the-body tapes are TAUT now (a hull over the lumbar hollow and the slices' bumps; `tailor.down`).
      hpsToWaistBack standard / heavy / thin body: 545 -> 486, 536 -> 510, 542 -> 481 mm; hpsToBust 331 -> 282.
      FreeSewing's armhole depth is hpsToWaistBack - waistToArmpit: 314 -> 255 (its standard: 260). Simon's and
      Jaeger's armhole base sat 331 mm below hps on a body whose armpit is 207 below it: the "bomber" jacket, the
      rolls across the upper back with the arms out, the body of every shirt 6 cm long. Now 273; Jaeger's CB length
      802 -> 732.
      (2) shoulderSlope is the slope of the shoulder LINE (a fit through the top of the shoulder from 2 cm outside
      hps to the shoulder point), not the chord from hps, which is taken 2 cm up the neck's side: 28 -> 21, 26 -> 26,
      29 -> 22 deg (the hanger's own fit to the surface had read 17; `at["shoulder_slope_chord"]` keeps the old one).
      Still unlike the standard: shoulderToWrist 553 (630: these bodies' arms are short), slope 21 (13).
      The sim cache can't reuse an old sim across this: its key is the sim's own inputs (start, pattern, seams).
      Not yet verified by a sim when written; drafting's blocks use the same measures uncompensated.
    - STATE at the usage-limit stop (2026-10-06, clothsim; branch worktree-agent-a2f0fa7013024989a, NOT mergeable):
      nothing after ly_03 is verified by a sim. Unverified, in order of risk: the taut tape + shoulder slope (every
      draft), the clean-up against the real body + crossings reverted for every garment + group welds, the fine
      settle's body offset fitted to the start (`_start_separation`), closures (band rows, relief, buttons in look /
      export / scene), `pressed` + the one-ring pad. Running when stopped: `cl_01` (zz_shirt with closures, scratch
      log clothsim/cl_01.log; its coarse sim is cached, the fine settle was waiting for the heavy slot; it was
      started BEFORE the shoulder-slope change, so its draft has the taut tape only). Next: judge cl_01 (front / cuff
      close-ups, clay + textured, against fl_17; seam gaps line; closures line), re-run it on the final measures,
      then `go.sh ly_03` again (ly_suit shirt re-simulates first), then pads (`support`), collar hug, vents (a
      lapped vent = one extension flat under, the other folded: both are folded under today), drafting's tailored
      collar (`{"op": "collar", "type": "tailored"}` on its branch, commit 112c5bf) in place of Jaeger's, Simon's
      cuff seam (-3.0%: sleeve hem 198.9 into a 205.1 cuff, probably the slit's lips). Gates old vs new measures:
      only pd_wrap changed (waist +11.1%, band +3..+10).
    - Seams (the user: "stitches super visible"): ZOZO leaves seams a few mm open (Jaeger mean 4.3 / p95 17.8 mm at
      stitch stiffness 1; drafting measured 30 closes them at 6x the time). `cleanup` welds sewn vertices as GROUPS
      (a vertex in two seams kept only its last pair), weighted toward interfaced vertices, and again after the push
      off the body. Gaps over 1.5 h stay: a seam the solver didn't close should fail, not be hidden.
    - Closures (`closures.py`, design-table / garment key `closures`; the user on the shirt: "doesn't have a placket
      or buttons"; schema agreed with drafting): {name, kind buttons | zip | hooks | tie, over, under (same piece for
      a cuff / waistband), holes / buttons mark prefixes or `at` pairs, edge {over, under}, band, size, lift, state
      closed | open | {open_above}}. `expand` -> the stitches (one per closed fastening), a vertex row on each
      band's inner line (a fold entry at 180 deg, `in_wrap`), zips' seams; `M["closures"]` = vertex pairs;
      after the sim `measure` (`res["closures"]`, the report, stage 5: fastenings closed, sides <= 6 mm apart, none
      lost in the mesh), `relief` (bands `lift` 0.8 mm proud) and `buttons_mesh` (`res["buttons"]`: discs with a rim
      on the over layer; in `look`). Stage 3 lists them and fails a chosen front_closure / cuff / fly with no entry.
      Simon's front and cuffs are entries now (its table's bare stitches are gone). Not done: buttons in the export
      and the scene, drafting's zip-in-a-seam / fly / waistband extension, `cloth_workflow.openings` reading state.
    - Open: the yoke ridge behind the collar; the upper sleeve's folds still read busy; Carlton pinned to
      `method: "simulate"` (upper-back pleat bunches, tail knife pleat is a seam gap, cap split +7.5 / -5.0%, stand
      +4%, collar +4.5%).
    - `made` (design table and garment: {piece or role: "made" | "draped"} through garment_design.made_or_draped ->
      `M["made"]` -> `made_pieces`): interfaced-whole pieces can be draped. Carlton's fronts are, with roll-line folds
      `lapel.L/R` (placement only so far: the fronts turn back along the roll line into a V; no facing, no sim).
      Fold flaps of torso pieces lie on their own base only (earlier torso pieces lap them either way).
    - Also: pattern ops `slit` (Simon's sleeve placket: the cuff's seam chain starts and ends at the slit, the cuff
      turned to it: `wrap.turn`, or the mean seam angle when unset) and `trim` (a band cut to the length of the
      edges it is sewn to); torso wrap `align_x`; Carlton's belt (joined at CB), tail vent as a lapped fold
      (seam check: back / belt / tail / side all within +-0.2%); `tests/test_folds.py`.

- Garments (2026-10-06, "garments" agent, branch `garments`: both cloth tracks merged; renders `cloth_renders/ga_*`;
  scratch DURABLE in /mnt/data/hifipushie/garments/: env.sh, run.sh <script> (worktree code on the main workspace),
  tests.sh, gates.py (stages 1-3 on every wf_ / pd_ / zz_ / ly_ / ga_ model), st.py (stages with the garment patched in
  memory), pl.py (place only: crossings by pair, closure start gaps, saves the start), rs.py (clay render of a saved
  start / result), lap.py (how an over band lies on its under piece, by height, for X0 / Vsim / V), band.py (a band's
  closed girth against the body's hull per level), seglen.py, dbg_d.py (a named edge after each draft op), run.py +
  q.sh <queue file> (sims one after another, logs <tag>.log, arrays out/<tag>.npz); prev/ = the two earlier agents'
  scripts. The sandbox refuses heredocs with code and loops: write a script file and run it.)
  - Gates: stages 1-3 no longer simulate a layered garment's under garment (the jacket's gate sat on the heavy slot);
    a garment with no design sheet is judged on its kind's `regular` fit band (was the first: slim); design-table
    `seam_notes` [{"seam": index, "ease", "why"}] (Simon's cuff is 3% longer than the sleeve hem because the placket
    strips aren't sewn on: declared, not hidden); two seam CROSSINGS near each other aren't a notch miss. Jaeger's
    armhole seam chain started at the front pitch and put the sleeve's top notch 27 mm off the shoulder seam (the
    sleeve sewn in rotated): the chain starts top <-> shoulder now. `pattern._points_on_outline` tolerance 0.1 mm
    (Carlton's rollLineEnd fell 2 um off the outline on the new measures and the table crashed). Carlton FAILS stage 2
    honestly (cap split +10.2 / -7.1%, collar on stand +4.5%, chest "+78%": sizing counts the lapel overlap): legacy.
  - `closures.seat` (in `build` after the clean-up, `cleanup.seat: false` turns it off; report line "lap ... laid
    closed"; `res["closures_sim"]` = the sim's own gaps): between the first and last closed fastening the over band is
    laid `LAY` 1.2 mm off the under piece along its normal, easing out over 3 cm; then each fastening's two sides are
    brought together in the surface (half each, sigma 2.5 cm, only up to 12 mm). Why: on the old shirt (lap.py on
    cl_01) the lap was 3-4.6 mm proud all down the chest (the solver's contact gap: construction, not physics, must
    close it) and 22-53 mm apart above the top button and 33 mm at the hem (the fronts part there: as worn, left).
  - Bands closed on themselves: `B["band_short"]` is now measured on EVERY path at the end of `place` (smooth only:
    Blender sews bands shut): the start distance between a piece's own stitched points > 12 mm. A torso band (a
    waistband, alone or among other pieces) lies on the hull of the narrowest level in its height at its closed
    girth, `BAND_CLEAR` 2.5 mm off at least (was 4 mm + the wrap's `out` 4 mm = 50 mm of girth: the trousers' band
    started 77 mm open, the skirt's 25); `B["band_clear"]` makes the ZOZO job run with body_offset 1 mm + contact_gap
    0.5 mm. Stage 4: pd_trousers and pd_skirt start closed. NOT VERIFIED BY A SIM when written (queue q3).
  - Neck bands: seated by their CLOSED girth when buttoned (not their length with the button extensions), and the
    hull is taken over sections that are the neck (8 mm above a 3 cm stand on this body's 3.5 cm neck the sections cut
    the chin, 44-48 mm forward: 6 cm of girth).
  - A buttoned collar is CONSTRUCTED closed (the coordinator's rule: a made band is held, not contact-solved, so it
    needs no solver standoff). `place`: a neck band with its own button stitch lies at its buttoned girth on the hull
    of the neck's sections, each round its own centre (`_cuff_spiral(recentre=)`; this neck leans: the centres drift
    8 mm over 3 cm, 2 cm of girth in one frame; each vertex is shifted by the drift at its height), over the band's
    own height from where it sits (a curved stand's ends are 1-2 cm lower in the pattern: the hull took in the
    trapezius), `HUG_CLEAR` 1.2 mm off the skin; `B["hug"]` (the stand and what shares its spiral) -> job array
    `hugIdx` -> cloth_zozo pins those held vertices with allow_intersection (free of body contact), the job runs with
    body_offset 1 mm + contact_gap 0.5, and a hug band's flap may lie HUG_CLEAR + 2 mm off the skin. Numbers (start):
    collarEase 0.03 -> 30 mm open, 0.07 -> 17, 0.10 -> 6, 0.115 -> 4 (closed, a layer apart): 410 mm round a 397 mm
    neck base = 13 mm of collar ease. The fall then stood up (turned 15 deg, every station at the same 8% = the
    stretch cap): NOT the roll line's curvature (plan radius 72 mm open and buttoned alike) but the 30 mm stand on a
    35 mm neck: pushed 7 mm off the chin, and the flap is turned from the unpushed row. collarStandWidth 0.055
    (20 mm stand; collarWidth 2.0 keeps the fall 44): no push, the fall turns 155 deg. Simon's table has the
    `collar` closure and these options now (ga_03_collar_closed_start.png: reads as a buttoned collar at 2 cm).
    NOT YET SEEN SIMULATED when written (ga_14 / the shirt under ga_11). A general rule is missing: the stand's
    height from the body's neck height (tailor has no neckHeight; `Body.neck_rows` has it: 35 mm here).
  - Seams after the clean-up (stitch stiffness 1 + group welds; shirt ga_01 on the final measures): the sim leaves
    p50 1.7 / p95 5.4 / max 8.8 mm, the clean-up p95 2.05 mm with 66 of 502 sewn pairs still open (target 0.5).
    Cause found: the pass that sends the clean-up's crossings back to the sim's surface also took every crossing the
    SIM itself has (the made collar's ends) and grew the patch two rings a round, undoing the welds round it; it now
    reverts only crossings the clean-up made (not yet re-measured). Stitch stiffness 8 is not a default: the shirt's
    2 cm coarse sim ran 27-30 s/frame (150 frames) against 287 s in all at stiffness 1.
  - Drafting: a SHAPED centre back seam (`contour` on centre_back) was dropped by the next style line
    (`_replace` asked for two points on x = 0): the blazer's back was open from neck to hem and stage 2 passed; a
    piece now keeps its centre if it holds an end of its named centre edge. An edge-form fold line on a piece cut
    on the fold runs on across the fold at unfold (a collar's roll line stopped at centre back). `collar` type
    "tailored" is laid from its seam (wrap "seam" + turn) with its roll fold `in_wrap`; KB front_closure
    `button_stand` (a jacket's 2-3 buttons below the break, no placket).
  - Model `workspace/ga_suit` (mk_blazer.py): ly_suit's shirt + a blazer from OUR blocks (bodice fitted, CB seam
    shaped, side panel with no side seam, lapel with straight gorge, tailored collar, fused facing, 2 buttons, bent
    two-piece sleeve; CB length 751 mm; gate passes; pattern sheet ga_02_blazer_pattern.png). Its START reads as a
    tailored jacket's pieces (lapels turned, seat covered), 11 crossing vertices, but the tailored collar is WRONG
    past the neck point: a band standing round the back of the neck that stops at the neck's sides, its seam to the
    gorge 156 mm away and turned 54 deg. Cause (construction): the op gives the roll line a constant stand height to
    the collar's end, and the collar is placed before the lapels are turned. In a real notched collar the roll line
    runs from 3 cm above the neck edge at CB down to the neck edge where the lapel's roll line meets the neckline;
    past that point the whole collar lies on the turned side, in the lapel's plane, sewn to the gorge. To build:
    the op's fold line from cbRoll to that point; placement of the part past it AFTER the lapel flap is turned, as
    a continuation of the flap (`lies_on` the turned lapel's plane), the part behind it as now.

- Suit (2026-10-07, "suit" agent, branch `worktree-agent-a79355cc3032d8bee`; renders `cloth_renders/su_*`; target =
  Garrett's concept `workspace/garrett_v20/concept_v8_front_apose.png`: charcoal two-button notched jacket worn OPEN,
  pale shirt with the top button open, flat-front trousers with a crease; he is seated in the game. Scratch DURABLE in
  /mnt/data/hifipushie/suit/: env.sh, run.sh <script>, q.sh <queue file> + run.py (one sim: report, OPEN SEAM lines,
  renders; `over=null` runs a layered garment alone; logs <tag>.log, arrays out/<tag>.npz), pl.py (place only),
  cu.py (close-up of a saved start / result: piece or x,y,z, half size, front | back | collar), seamdiag.py (one
  seam's gaps in X0 / V_sim / V along the seam), fs_dbg.py + fs_dbg2.py (where a fine settle's start is stretched,
  from the job's in.npz), pairs.py (a piece's sewn pairs in pattern coordinates), lap_geo.py (lapel / roll line
  numbers of a draft), ro_dbg*.py, gates.py, mk_garrett.py (model `su_garrett` = garrett_v20 COPY + ga_suit's shirt
  and blazer + pd trousers), tests.sh.)
  - VERIFIED BY SIM (first time for all three): trousers pd_trousers 2 cm (su_01: fits, band closed at CB, stays at
    the waist, seams 0.5 / 1.3 / 3.2 mm in the sim at stitch stiffness 8, 0 crossings; but a wide cropped pyjama
    cut, no fly / crease / loops); shirt zz_shirt 2 cm + 1 cm fine settle (su_05: 0 crossings, seams p95 0.24 mm,
    collar closed with the fall turned 155 deg and covering the stand seam 11 mm; "STRAINED at waist" 17.8%, front
    closure sides 12.1 mm apart, collar closure 8.1 mm; reads tall / tight / small points); blazer from our blocks
    alone, 2 cm (su_06: reads as a tailored jacket, 0 crossings, strain 0.4%; neck / gorge seam OPEN 12 of 12 pairs
    to 14.5 mm, shoulder seams 5-6 mm, CB seam 2.7 mm showing as a pale zigzag, back collar a fat roll, fall 108
    deg); Jaeger alone on the new measures (su_07: no longer a bomber in length, but CORRUPT: side seams open 17-34
    mm, armholes 30-36 mm, 165 of 336 pairs open at stitch stiffness 1, side panels crumpled, collar a band: legacy,
    the drafted blazer is the base).
  - Made pieces sewn to each other are ONE construction (`cloth._carry` groups them by seams, root = the piece with
    the most seam to draped cloth; `carry["roots"]`; `_constructed` and `_press_plan` fit the fine placement onto
    the coarse one on the root). Each fitted by itself, the shirt's collar landed 16-25 mm off its stand at all 43
    pairs and the fine settle died ("ccd failed", made pieces 277% stretched at the start): the shirt as merged by
    the garments round could not finish.
  - Notched collar (`op_collar` type tailored after a `lapel`; `_roll_meets_neck`): the roll line is a polyline from
    `stand_height` at CB down to the neck edge where the lapel's roll line crosses the neckline (profile exponent
    from the crossing angle so the two lines meet as one), given as the fold's points and as wrap `turn.line` (run
    on 16 cm as the lapel's roll line). `"roll": "parallel"` = the old constant stand.
  - Wrap "seam" (`cloth._on_seam`): `"worn": true` = the edge it lies on is each torso partner's point at its
    pattern x / height (y = 0 at hps) on the body's front / back (`worn_pt`), at the pattern's lengths from the
    middle: the old march headed for where the fronts START (15 cm ahead on their cylinder) and hugged the neck
    like a shirt band. Frames along the edge come from the body's normals 12 mm above the seam, smoothed (nearest-
    vertex normals in the neck / shoulder crease swung 60 deg), the piece's side of its edge from ONE handedness
    read at the edge's middle (per point by the centroid it flipped along the collar's slanting front: this was in
    the old code too). `turn.line`: points beyond the line are laid as their foot + distance in the turned
    direction; where the line has left the piece (and blended in over its last 5 cm) the point is reflected about
    the line in the pattern, carried into the PARTNER's pattern by the two exact seam pairs (the pairs between are
    off by up to 13 mm along the seam: fold rows on either side: a mesh fault, not fixed) and laid with `worn_pt`.
    Dead end: laying the collar's front as a continuation of the turned lapel where the lapel STARTS (the fronts
    start on a cylinder, the collar is made and held: 3.8x stretch).
  - Seam-wrapped pieces take the bands' clearance (SMOOTH_CLEAR), not the draped 12 mm (the collar's neck edge was
    held 8 mm outside the back neck). Blazer alone re-simulated with it (seamdiag.py, no render): neck / gorge
    seam 6 in the sim 2.1-5.6 mm (was 9-15) with ONE pair at 14.8 mm: the pair beside the roll rows, where the
    mesh pairs the seam's two sides up to 13 mm apart ALONG the seam (pairs.py: collar 0.132 <-> front 0.046; fold
    rows inserted on each side shift the pairing): fix that pairing in `cloth.mesh` next. The clean-up left all 12
    pairs as the sim had them (V = V_sim): the weld did not act on a seam between the made collar and draped
    cloth: not understood (same for the CB seam's 4 pairs at 2.7 mm: the pale zigzag).
  - Layered run (blazer over the shirt, su_08 / su_10): the GPU did NOT crash; ZOZO stops at frame 0, "ccd
    failed", start 1650-1750% stretched. From the job's in.npz (fs_dbg.py): only the COLLAR, 24 triangles to 9.6x
    at pattern |x| 0.09-0.13 (the roll's end / the blend into the front part), and in the layered job the collar
    is not carried (carryIdx empty) and rests on the flat pattern, i.e. it is not treated as made there. pl.py's
    start on `Ctx.body` shows only 1.58x: `build` places on `padded_body` (the pressed shirt, its collar round the
    neck), where the worn chart and the seam frames meet the shirt collar's surface. Next: place with build's own
    body (run.py's res["X0"] is saved in out/<tag>.npz only when the sim finishes: add a place-only path through
    `cloth.build`), find why the collar is not made / carried when `over` is set, and lay the jacket collar over
    the shirt collar (its stand OUTSIDE the shirt's, the "layer_collar" tell 10-20 mm).
  - `worn_pt` returns the point at the body's depth (not a body vertex: two points on one vertex = a rest triangle
    of no size).
  - Garrett: stages 1-3 PASS for shirt, blazer, trousers on `su_garrett`; never placed or simulated on him.
  - Tests: test_pattern_draft, _styles, _tailor, test_folds, test_cloth_workflow, test_cloth, test_cloth_layers,
    test_closures, test_cloth_check pass at 86629f8 (the worn_pt change after it: only the pattern / folds /
    workflow set re-run). No test yet for the notched collar's roll line, wrap worn / turn.line or made groups.
  - NEXT, the coordinator's order: (1) the blazer's neck / gorge seam by construction: re-run `q.sh` with
    "su_09 ga_suit jacket over=null" on the clearance change and read seam 6 / 7 with seamdiag.py (if still open:
    where does the collar's neck edge start against the worn neckline, and does the front's turned gorge reach it:
    the worn chart lifts the collar off_ + 6 mm), then the back fall (108 deg) with the shirt under; (2) CB seam
    zigzag: 2.7 mm should weld (limit 1.5 h): check `cleanup`'s weld on a seam between two draped pieces whose
    vertices were left by `seat` / the crossings revert, or whether the look's `welded_faces` draws it; (3) wear
    state: jacket `closures` state open (the `buttons` op makes stitches, no closures entry: CLOSURES [] in su_06),
    shirt collar open_above; (4) shirt collar proportions as a KB rule from `Body.neck_rows` (stand from neck
    height, fall = stand + 10-15 mm, points 65-75 mm), the 12 mm front gape and the waist strain (stage 2 ease says
    +23% at the waist: so the strain is the lap / buttons, not size: unexplained); (5) trousers: slim straight leg
    to a slight break, crease folds, fly, loops; first place + sim on su_garrett. su_08 (blazer over the shirt,
    the job that crashed the 890M in ccd_collision_edge_edge) fails at its start now: see above.

- Suit 2 (2026-10-07, "suit2" agent, branch `worktree-agent-a42af29b3a3f84fa9`, continues "suit"; renders
  `cloth_renders/su_2*`; scratch DURABLE in /mnt/data/hifipushie/suit2/ (the suit agent's scripts with W = this
  worktree, + run_main.sh <script> (MAIN's src on PYTHONPATH: before / after numbers), plb.py (the START as
  `cloth.build(place_only=True)` makes it, padded body when layered: made / carried, stretch by piece, crossings,
  seam start gaps), pairchk.py (sewn pairs' mismatch along each seam), welddiag.py (what the clean-up's weld does
  and which edges cross which triangles after it), gapgeo.py (a seam's gaps split along / across / normal),
  groove.py (a welded seam's vertices over the chord of their neighbours: pucker), collar_pat.py (the drafted
  collar against what it is sewn to), tests.sh (the nine cloth / pattern test files -> tests.log)).
  - Seam pairing (`cloth.mesh`): a fold line (and a roll's further rows) ending on a sewn edge moved the outline's
    nearest vertex onto itself on ITS side only (up to 0.6 h, 1.3 h for further rows): the seam's two sides were
    paired up to 15.7 mm apart along it (blazer collar / gorge, pairchk.py). Now the fold's ends are found first
    and added as samples of the seam on BOTH sides (and of every other seam the points land on: `sample(extra)`,
    `on_seams`, `at_fraction`); an end within `SEAM_JOIN` 0.15 h of a sample ends on it. 0.0 mm on all 15 seams;
    the blazer's start stretch 125% -> 39%, the sim's worst neck pair 15.0 -> 7.0 mm. EVERY garment with a fold
    ending on a seam re-simulates (Simon: its mesh changed).
  - Why the weld "did not act" on collar / CB / shoulder seams (V == V_sim): it welded, then build's crossing
    check sent it back. A solver leaves layers a contact gap apart (a made collar's fall on the back neck, a lapel
    on its front: 0.5-1.6 mm); a seam vertex welded 1-5 mm went through that layer by a fraction of a mm (134 new
    crossing vertices on the blazer), and the revert, two rings wide at once, reopened every seam within 4 cm.
    `cloth._weld_clear` (before the revert): a vertex whose move made a crossing loses the part of the move along
    the crossed triangle's normal, with the draped vertices welded to it; the revert grows ring by ring
    (`_crossing_hits` = the edge / triangle pairs). Blazer: CB seam 4 open pairs -> 0, shoulders 7 -> 5 of 9, neck
    seams still 1.3-6.6 mm (they end under the tangled collar ends: the collar, not the weld).
  - The CB "pale zigzag" is PUCKER, not a gap: the welded seam's vertices alternately 4 mm sunk / 5-9 mm proud of
    the cloth beside them (groove.py); the two sides share their samples (not an offset along the seam).
    `cloth._seam_relax` (cleanup option `seams`, default on): each closed seam smoothed along its own polyline
    (6 passes, ends kept, <= 2 x keep), the first ring following by half; seams with an interfaced side stay. The
    first version (toward all neighbours, 4 mm cap) took the median 2.0 -> 0.86 mm and still read as a zigzag;
    the along-seam version (su_25_blazer, scratch out/su_25_back.png beside su_21_back / su_23_back): CB, side
    and sleeve seams read as smooth lines, no welts or zigzag in clay at 2 cm. groove.py's number hardly moved
    (median 1.7, p10 / p90 -4.8 / 6.8 mm): it reads the first ring's own scatter and the back's curve, not the
    line: judge seams by render. su_25 also has the front as a closure: 2 of 2 closed, sides 2.8 mm apart.
  - Wear state: op `buttons` writes a closure (`D["pair_closures"]` -> `D["closures"]` at unfold: left over right,
    `state`, `size`; no bare stitches), `pattern_draft.build` returns `closures`, `cloth.pieces` takes them; a
    garment's `closures` entry is laid over the design's of that name key by key ({"name": "collar", "state":
    "open"}; {"name": "front", "state": "open"}); `cloth_workflow.openings` lists a closure worn open as fine.
    Docs: cloth_guide.md (Closures), the dress tool, garment_kb.json. NOT simulated yet (a shirt collar worn open
    falls back to the unbuttoned neck-band placement: unverified since the garments round).
  - THE COLLAR (the open job; the coordinator: before anything layered). ga_suit and su_garrett carry `"made":
    {"collar": "draped"}` since 10-06: the blazer's collar is wholly interfaced but rests on the FLAT pattern, a
    stiff strip bent round the neck = the fat roll in su_06 / su_20-23 (the clearance change did not cure it).
    Made (`made={}` on the command line), its lay (`_on_seam` worn + turn.line) is a ruff of spikes round the neck:
    36 triangles to 3.6x at the front ends (out/pb_alone_made_c.png); `cloth._true_lengths` (wrap key `"true":
    true`, off by default) brings every edge to its pattern length (max 1.06) but the SHAPE stays a crumpled ruff
    (out/pb_alone_made2_c.png): the lay is wrong, not the lengths. The PATTERN is right (collar_pat.py): neck edge
    199.6 mm = back neck 84.2 + front neck 115.4, spring 36 mm (outer 236 for 200), roll line from 30 mm at CB to
    the neck edge 113 mm round (29 mm past the neck point), where the lapel's roll line (break (-20, -400) to
    (58, -16) on front.L) crosses the neckline; the collar's last 87 mm is sewn to the lapel's top (hps side of
    the crossing to cfNeck (-14, -65)); reflected about the lapel's roll line that end lies at x ~105 mm, 89 mm
    under the neck point: on the chest. The lay to build (agreed with the coordinator): (a) from CB to the
    crossing, a back band standing on the worn neckline as an isometric cone, stand + fall folded on the roll line
    at the one isometric angle (as `op_shawl`'s annular sector / `folds.apply`); (b) past it the collar end FLAT in
    the turned lapel's plane, placed AFTER the lapel flap is turned (`lies_on` / `_lay_on` on the turned lapel, or
    the reflected pattern point laid with `worn_pt`: the seam's pairs are exact now, so the two-pair rigid fit in
    `_on_seam` can use all of them), sewn along the gorge. Targets at the START (plb.py): neck seam p50 < 10 mm
    against the WORN neckline (today 128-135 mm: the fronts / backs start on their cylinder, so measure against
    where they will be worn or accept this number for a carried piece), no triangle over 1.3x, 0 crossings; then
    made + carried in the sim, then `over`.
  - Layered run su_24 was stopped unrun (a known-bad collar). The 9.6x layered start was measured BEFORE the
    pairing fix; `plb.py ga_suit jacket <tag>` (no over=null) shows the layered start once the shirt is re-simulated.
  - Tests: test_folds (+ test_fold_ending_on_a_seam_keeps_the_seam_paired), test_cloth (+ test_weld_beside_a_layer_
    stays_welded), test_closures (+ test_drafted_buttons_are_a_closure_with_a_wear_state), test_cloth_layers,
    test_cloth_check, test_cloth_workflow, test_pattern_draft / _styles / _tailor passed after the closures commit;
    re-run tests.sh after the along-seam `_seam_relax`. Still no tests for the notched collar's roll line, wrap
    worn / turn.line, made groups (`_carry` roots).
  - NEXT, in order: (1) (done: su_25 judged, tests.sh green); (2) the collar's made lay (above); (3) the layered start
    (collar made + carried under `over`; `cloth_layers.tells`); (4) Garrett's wear state simulated (jacket front
    "open": do the fronts hang straight or spread? shirt collar "open"); (5) trousers (slim straight leg, crease
    folds, fly, loops / belt); (6) shirt collar proportions as a KB rule from `Body.neck_rows`, the 12 mm front gape
    and the 17.8% waist strain by numbers; (7) all three on su_garrett against the concept. Not touched: 4-7.

- Suit 3 (trousers, shirt) (2026-10-07, "trousers" agent, branch `worktree-agent-a5aa4e100572bcb0c`; scratch DURABLE
  in /mnt/data/hifipushie/trousers/: env.sh, run.sh <script>, tests.sh, q.sh <queue file> + run.py (one sim: report,
  renders incl. trims, `_waist`, `_waist_tex`, `_hem` close-ups for trousers), plr.sh <model> <garment> <tag> (the
  START: plb.py + a clay render out/<tag>.png, log <tag>.log), st.py (stages with patches), psheet.py (pattern sheet
  image), meas.py (tailor measures), parts.py (a model's shell parts), mk.py [garrett] (model `tr_trousers` = the
  test body + suit trousers; su_garrett's cloth.trousers replaced by the same sheet)). PATTERN WORK ONLY: NO SIM RAN
  (root disk under the sims' 20 GB floor: 14 GB free, /tmp/claude-1000 = 41 GB).
  - A kind that drafts itself: `kinds.<k>.draft` {block, block_options, fit_options per fit}, and a detail choice's
    `draft.ops` (its operation, added unless the sheet's own ops hold one of that name; `{"choice", "op": {...}}`
    patches it) and `trims` (`garment_design.compile_sheet`). `{"kind": "suit_trousers", "fit": "tailored"}` alone
    -> trouser block + waistband (opening front) + fly + crease + belt / loops. Evidence types `closure` (kind, on
    role) and `trim`. Sheet -> garment key `trims` (NOT_SIM).
  - Block (`pattern_blocks.trouser`): `leg` = LEG_CUTS skinny / slim / tapered / straight / wide (`leg_cut`: knee =
    knee girth x (1 + ease), never under calf x (1 + ease); hem = a share of the knee, never under heel + 20 mm);
    `tailor.measure` has upperLeg, knee, calf, ankle, heel (`_leg_girths`; heel = a 45 deg plane through the
    ankle). `dart_taper` (a shaping point on each dart leg 35% from the tip: the tip's angle under half), `dart_length`.
    Garrett tailored: knee 428 mm round, hem 377 (heel 342), seat +4.7%, thigh +17%.
  - Ops (pattern_tailor): `crease` (press fold on the piece's `crease` line, angle 205 = a ridge OUT, strength 0.6,
    `in_wrap`, `reach` 5 cm; a fold must cross its piece so the back's runs to the waist too), `fly` (point flyEnd on
    the centre front; `edges.centre_front` becomes the part below it; `pair_closures` kind zip -> at unfold a
    closure {zip, front.L over front.R, seam = the opening}; line `fly_stitch` (a J) kept on the over piece only;
    `cloth.mesh` carries lines named *_stitch as `M["stitch_lines"]`, `detail_maps` draws them as dashes: NOT yet
    seen in a render). `waistband` `opening: "front"`: chain front.L -> back -> front.R, `garment_blocks.generate`
    `extension: "end"` (lapEnd; button on the extension at the high-x end), wrap side "back" + `over: "low"` (the
    lap ramp in `cloth.place` on the low-x end). No band row for the fly's facing: an offset line would end inside
    the piece (folds must cross).
  - `cloth_trims.py` (`validate`, `check`, `meshes(res, g)`): belt (a strap of rectangular section on the band's
    middle line, the over end a thickness out, a buckle box at the buttonhole mark) and belt_loops (strips from the
    band's top over the belt to its bottom) built from the finished band's chart (pattern uv -> position / normal);
    in `cloth.look` and run.py; tested on a synthetic band only (test_trims_ride_a_band), NEVER seen on a sim.
  - Stage 2 (`cloth_workflow.leg_ease`): seat ease from the centre seam's line to the side seam (the forks lie
    between the legs: a 5% draft read +13% on the test body, whose seat line is 6 mm above its crotch); a hem that
    ends on the foot is judged against the heel girth (it read TOO SMALL against the foot's section).
  - Start (`plr.sh su_garrett trousers pl_g2`, out/pl_g2.png): band closed, 0 crossings, but the leg wrap is ONE
    vertical cylinder per leg as deep as the seat: a slim leg's front and back start as slabs, side seams 174 /
    inseams 213 mm apart (p50), the front hem pushed 32 mm off the foot (2 triangles 2.25x), waistband seam p50 223
    mm (the fronts / backs are far from the band, not a mis-ordered chain: check it once the legs start closer).
    Stage 4 fails on it (start past the strain limit on 0.8% of the triangles). The fix to build if the sim can't
    sew it: below the crotch lay each leg's pieces on the leg's own sections (a tube on the hip -> knee -> ankle
    axis, as sleeves on the arm), blended into the torso cylinder over ~10 cm at the crotch. The foot is left out
    of the leg hull (z under ankle + 4 cm).
  - Shoes: his `shoes` part is an 8 mm shell of the foot and the soles lie inside z 0..15 mm: the bare foot stands
    in for the shoe; length "shoe" (hem 30 mm over the floor) is cut for it. Not added to the collider.
  - Darts as "open tucks" in su_01: argued, not measured: pucker of the welded seam (suit2's `_seam_relax` came
    after su_01), the unshaped tip, 10% seat ease. Verify on the first sim's back close-up.
  - Tests: the nine files green at 9b66b6f (tests.log); new in test_pattern_tailor: leg cut, shaped dart, crease /
    fly / front waistband, the kind drafting itself, trims.
  - NEXT, in order: (1) free the disk, then `bash q.sh q1.txt` (tr_01_trousers su_garrett trousers, 2 cm ZOZO
    draft); judge 4 views + _waist / _waist_tex / _hem against the concept (stays at the waist, crease a line,
    one break on the foot, no puff, darts, fly J, belt + loops sitting on the band); (2) if the legs don't sew or
    crumple: the leg-following start above; (3) pattern sheet tr_00_trousers_pattern.png is judged (reads as a
    tailored trouser); in-seam / slant pockets exist as `pocket` type in_seam, not added to the kind; (4) the
    SHIRT, untouched: collar rule from `Body.neck_rows` (stand from the neck's height, fall = stand + 10-15 mm,
    points 65-75 mm, spread for an open collar) through Simon's options, the 12 mm front gape and the "waist
    strain 17.8%" at +23% ease by numbers, then worn with `{"name": "collar", "state": "open"}`; (5) trims in the
    scene / export, a hem's break as a stage 5 target, the back crease ending at the seat.

- Suit 3 (2026-10-07, "collar" agent, branch `worktree-agent-a5c847e94d5c52d32`; renders `cloth_renders/su_30..32_*`;
  scratch DURABLE in /mnt/data/hifipushie/collar/: env.sh, run.sh, q.sh + run.py (renders now draw seams WELDED),
  p.sh <tag> [-o] (blazer alone, collar made, place only; `-o` = the open start; collar numbers, CB column, notched-lay
  info, worst edges), pl.sh (the same layered), pv.sh (p.sh + close-up), plb.py, cu.py (welds closed seams unless
  `raw`), clr.py (collar neck edge vs partners: clearance off the body), fg.py (a seam's pairs: sim / final gap),
  gapgeo.py, zig.py (a seam's line vs itself smoothed), hps.py (where collar / front / back put the neck point),
  unmade.py, tests.sh (the nine + test_collar)).
  - THE NOTCHED COLLAR'S MADE LAY (`cloth._notched_lay`, wrap `lay: "notched"`, set by `op_collar` type tailored
    when the lapel's roll line meets the neck edge): two parts meeting where the roll line comes down to the neck edge.
    The band: the stand runs up the body from the WORN neckline at the seam's clearance (`hug`), the fall turns about
    the roll line station by station as far as clears what is under it (172 deg at CB, ~150 at the neck's side). The
    end: FLAT in one plane through the lapel's roll line (as worn), turned about that line until it rests on the
    chest (a board bridges hollows), isometric (edges 1.00). Stations share position / tangent map / normal / turn,
    smoothed along the line; the sewn edge is a spline (laid per sample, the stand jumped 12-15 mm at every sample);
    the end's plane takes every point past the meeting point ALONG THE NECK EDGE (by foot on the roll line the outer
    end fanned 2-3x), eased over `NOTCH_BLEND` 4 cm; nothing turned stands over `NOTCH_BRIDGE` 12 mm off the body
    (the plane run on past the shoulder's ridge stood up as a wing); a relax pass draws in long edges (`lay_limit`).
    In `_on_seam`: `worn_pt` keeps to the body's own back / front (at the nape the nearest vertex in x, z was the
    throat's: the back neckline charted 9 cm forward) and past the outline sits on the shoulder's top; the worn
    neckline is a CHAIN at the pattern's lengths pulled toward the chart with a fading pull (`lay notched`; smoothing
    the chart and snapping it out walked it 1-2 cm up the slope). Start (blazer alone): collar max 1.15x (p99 1.06),
    0 collar crossings; layered over the pressed shirt 1.10x (9.6x in su_08). LAY_INFO[piece] keeps the lay's numbers.
    The worn neckline rides 1.5-2.5 cm higher than the chart (the chain keeps the pattern's length, the neck narrows
    upward): the jacket's neckline is cut to sit there, and the sim's back sews up to it.
  - SEWN ON OPEN, THEN ROLLED (`_open_start`, method settle): the sim starts with the fall standing open
    (`NOTCH_OPEN_DEG` 40 from the stand, eased in over `NOTCH_OPEN_FADE` 8 cm from the meeting points) and the
    carried poses turn it down (`NOTCH_OPEN_STEPS` 1 / .75 / .5 / .25, last pose closed). Laid down from the start
    (su_30) the fall was a LID over the seam: the draped back came to rest on top of it, 14 mm off the neck, the
    neck seam open at 13 of 13 pairs. build's arrays X = `Xstart`; rest stays the closed lay.
  - su_31 (blazer alone, ZOZO settle 2 cm, 443 s): reads as a tailored jacket, fits, 0 crossings, strain 0.6%; the
    collar hugs the neck and lies on the back (stand off the neck at CB 7 mm, fall 157 deg over the seam, no roll).
    Left: neck seam 10 of 13 pairs open (back neck pairs overlap 5-7 mm, 3 of 5 weld; the NECK POINT: front.L's hps
    sits 16 mm forward of the collar's along the seam and 7 mm further out, shoulder seam open ~10 mm there: front,
    back and collar disagree on hps; gorge 1-11 mm). Not fixed.
  - The "CB zigzag" was never in the garment: the scratch renders drew raw faces (two rows of vertices per closed
    seam, each with its own normal). look_cloth welds (`welded_faces`); the seam line is smooth (zig.py: su_31 final
    max 3.6 mm). `test_cloth::test_cleaned_seam_is_a_smooth_line`.
  - `_collider` drops the under garment's sliver faces (`UNDER_SLIVER`): ZOZO refused the layered job ("degenerate
    shell face" in the pressed shirt).
  - ga_suit / su_garrett: the jacket's `made: {collar: draped}` override is gone (that is why su_10's layered job had
    no carried collar).
  - su_32 (blazer OVER the shirt, first finished layered sim, 2 cm): BAD. The jacket collar stands high round the
    shirt collar (collar_show -19 mm: the jacket covers the shirt collar; collar_hug 27 mm), shirt shows through
    at the armholes / shoulders / back side seams (seams 0-11 open 22-63 mm), cuffs hidden (-29 / -33). The armhole
    and side seams open is NOT the collar: alone (su_31) they close; under `over` the draped jacket is placed on the
    padded body and its seams don't close. Diagnose that first (plb.py layered: start gaps / start stretch by seam vs
    su_31's; padded_body thickness at the armholes), then lay the jacket collar on the shirt collar's OUTSIDE at
    the jacket's own neckline height (the shirt collar 10-20 mm above it at CB): today `worn_pt` reads the padded
    body, whose neck is the shirt collar's cylinder.
  - Tests: the nine cloth / pattern files + test_collar pass (main 17ee597 merged in); merged to main at 2aea2ac.
  - NEXT, in order: (1) su_32's open seams under `over`; (2) the jacket collar against the shirt collar (layer tells);
    (3) the neck point (front / back / collar on one hps: the worn chart of front.L at hps vs where the draped front
    settles; maybe the front's lapel fold start near hps); (4) Garrett's wear state (front open, shirt collar open)
    and su_garrett.

- Suit 4 (layers) (2026-10-07, "layers" agent, branch `worktree-agent-a237f0b282ae815f7`;
  renders `cloth_renders/su_41..45_*`; scratch DURABLE in /mnt/data/hifipushie/layers/: the collar
  agent's scripts retargeted (env.sh, run.sh, q.sh + run.py, plb.py, cu.py ...) + lay1.py <m> <g> <tag> [k=json] (START:
  per-seam start gaps, start stretch per piece, pad thickness by region, jacket vs under garment, saves out/<tag>.npz
  with U/FU), lay2.py <result npz> <start npz> (jacket vertices inside the shirt), lay3.py (open sewn pairs: where,
  what's under), tape.py / om.py (measures bare vs over the shirt; the draft logs), collarcb.py / prof.py (CB column /
  CB profiles of body, shirt, pad, collar), laydbg.py (notched lay at CB), fleck.py <result npz> <start npz> [V]
  (layer crossings + whether the collider dropped those shirt faces), flapchk.py, reststr.py, jobstr.py <job dir>
  [new] (the runner's rest rebuilt from a job's in.npz: start stretch per triangle: find "ccd failed" before the
  GPU), setop.py / setkey.py (edit ga_suit's jacket), show.py, wearchk.py, t1.sh <test>, tests.sh).
  - su_32's open seams were CONSTRUCTION: the jacket was drafted from the bare body. Its armhole sat 12 mm under the
    shirt's own (underarm seams pinched 20-64 mm open over the shirt in the pit) and its neckline was shorter than the
    shirt collar it goes round (the made collar climbed it: collar_show -19). `cloth.over_measures` /
    `draft_measures`: a garment `over` another is drafted from the tape over it: `neck` = the under garment's
    neckline (`under_neckline`: its neck pieces' sewn edge) + 2 pi `UNDER_COLLAR_T` 3 mm (the raw tape round the
    pressed shirt collar read +123 mm: its fall stands off), `waistToArmpit` less the under garment's pad in the pit;
    body girths stay the bare body's (ease bands are against the body). build + the workflow gate (Ctx.meas) use it;
    log "drafted over shirt: {...}". Guide: cloth_guide.md Layers.
  - `padded_body`: each vertex padded along its OWN normal line (`PAD_LATERAL` 8 mm, never further than 1.5x the
    point's own distance), no overhang (`PAD_SLOPE` 1): by nearest vertex the shirt collar's fall made a 3 cm shelf
    at the back neck and the jacket collar was laid on it 24-27 mm off the shirt.
  - `_on_seam`: the piece's side of its sewn edge read from its cloth NEXT TO the edge's middle (by the whole piece's
    centroid, a notched collar drafted round a shirt collar laid its stand DOWNWARD at CB).
  - Clean-up vs the layer under: the sim had 16 jacket/shirt crossings, the clean-up 247 (white flecks of shirt
    through sleeves / armholes; NOT the collider's dropped slivers: fleck.py, 2 of 24k faces, far away). Crossings
    with the under garment now count in build's revert-to-sim (`_layer_crossing_verts`), and a reverted welded seam
    vertex takes its weld group to the mean of its sides' sim positions (sent back alone: pale slits on the sleeves).
  - `made_folds` (garment key; `made_flaps`, `_carry(flaps=)`, rest = the folded flat pattern via the runner's restIdx
    path): the flap past a fold held and carried with the made piece it is sewn to. TRIED on the lapels (su_44b) and
    WORSE (shoulder seams 131-144 mm, neck 248): held regions stay where they START, and the draped fronts start on
    the torso cylinder away from the shoulders. Off on ga_suit. A made lapel needs the forepart STARTED where it is
    worn (next build, below). First attempt failed at frame 0: carried vertices rest as start (world) beside cloth
    resting on uv: 4.3x stretch across the roll line (jobstr.py found it).
  - ga_suit jacket now: collar stand 24 / fall 36 (shirt band 20 mm), sleeve length_bonus -0.04, under_cap 0.004,
    closures front open, interfaced bands (the chest canvas as stiffness) {front.L/R near [break, lapelPoint] within
    0.1}. su_garrett jacket: the same except the bands (not yet).
  - su_45 (2 cm, the shirt open-collared by main's no-tie default): fits, 0 crossings, 0 layer crossings, seams p95
    0.0 (15 of 354 pairs open, all at the collar neck seams: front.L 56 mm, R 16), collar_show 18.3 (ok), cuff_show
    8.4 / 7.2 (target 10-15), lapel_gap 5.6 / 7.1, collar_hug 23 (jacket collar off the shirt collar; partly the
    metric: the shirt collar stands open now), left lapel roll ends at 99 deg (half unrolled, the gorge crumpled).
    Reads as a jacket over a shirt from every side, matte, no flecks, clean back.
  - OPEN, in order: (1) the forepart started where it is WORN (a worn chart for the fronts' tops, like the collar's:
    collar, lapel and front start together on the shoulders; then made_folds can hold the lapel) = the gorge and the
    left lapel; (2) the TENT: from the side the open fronts bow forward from the chest to the hem (suspect front
    balance / length over the shirt (hpsToBust over the shirt +26 mm, not used by over_measures) or the side panel's
    hem flare); (3) the shirt collar reads buttoned though its pieces say open (trousers2's neck start); (4) cuff 2-3 mm
    short of the band; (5) su_garrett (bands, then a sim).

- Seams (2026-10-07, "seams" agent, branch `worktree-agent-ae98ecda411a37796`; the user on the suits: "seams look huge
  and structural"; renders `cloth_renders/sm_01..08` (before = main 2aea2ac / after, the SAME cached sims: su_31
  blazer, su_05 shirt; sm_05 = raking light across the blazer's side panel seam); scratch DURABLE in
  /mnt/data/hifipushie/seams/: run.sh / runb.sh (this branch / main 2aea2ac's src in orig/), prof.py (load a cached
  result: `load(model, garment, patches)`; cross profiles, too few points at 2 cm to trust), m2.py (per stage the
  angle between a seam's two sides' normals vs the cloth's own: THE measure), orient2.py (winding per seam), rs.py
  (clay + textured sheets + close-ups of a cached sim), rk.py (raking-light close-up of one seam), cmp.py).
  Three causes, by measure:
  - WINDING: the pattern mesh winds each piece as its pattern lies; on the blazer back.L/R, top.L, under.L faced IN,
    the rest out (side seams' two normals at 160 deg). Welded, the shared normal cancelled into a pale / dark line;
    Solidify (offset 1) grew one side out and one in; the export's single global flip kept it, its inner shell went
    out on those pieces. `piece_flips` / `oriented_faces` (seam votes, max spanning tree over pieces, then out from
    the body) in every look (`welded_faces` orients; textured looks now weld too, with per-corner uv `uv_corner`),
    the scene's faces and the export (`shared_normals`: a closed seam's vertices one normal). A body-majority rule
    per piece was wrong for folded pieces (the collar's fall outweighs its stand). M["F"] (the sim's) is unchanged.
  - The FREE HINGE: a solver stitch passes no bending, so each side's last rows tilt alone: after the weld the sides'
    normals met at 29 deg median (side seams 20, CB 45, sleeve 30-37) against the cloth's own 10.
    `cleanup.press` (`_seam_press`, PRESS reach 3 cm, 40 Taubin passes, cap 0.4 h; welded groups move as one, ALONG
    THE NORMAL only: a uniform Laplacian slid seam vertices 6 mm in plan, a zigzag; interfaced cloth and "welt" seams
    stay): blazer 29 -> 14 deg (side seams 6-12), shirt 26 -> 14 (yoke 19 -> 7). The shirt's side seams stay 22-31 (a
    deep fin from the sim, not cap-limited). What's left on sleeves is mostly the 2 cm tube's own curvature.
  - The MAPS: a 1.2 mm groove 2.5 mm half width with 0.6 mm ridges 5.5 mm out each side, darkened 45% in the base
    colour, topstitching 6 mm in on EVERY edge. Now seam finishes (garment_kb.json `seam_finishes`, `seam_kinds`,
    detail `seam_finish` / `seam_finishes`; kind default `kinds.<k>.seam_finish`): pressed_open 0.3 mm x 0.7 mm, a
    0.12 mm rise over the allowances, no rows; felled two rows on one side (shirts); welt = the old look, not pressed.
    Hem topstitching from the kind's hem (`hem_topstitch`: blind hems none). Cavity 1 + H / 4 mm, floor 0.7.
  - Before was rendered with main's textured look on RAW faces: every seam was also an open boundary with Solidify
    rims (the stair-stepped pale beads in sm_05).
  - Tests `tests/test_seams.py` (winding, press, finishes in the maps, export normals) + the ten cloth files green.
  - Open: the shirt's side seams (a fin the press can't flatten: look at why the sim folds there), sleeve seams at
    2 cm, a "toward" side per seam for pressed_to_side / felled (today the seam's second piece), seam finishes in the
    pattern sheet, closures / collar seams were not judged one by one (made pieces are interfaced: untouched).
    Careful: `cloth.export_part` / `garments(simulate=True)` STARTS SIMS for uncached garments (an orphaned ZOZO job
    of mine had to be killed): test exports on cached models only.

- Suit 5 (2026-10-08, "suit5" agent, branch `worktree-agent-a7a27cfe57b8650a5`; renders `cloth_renders/su_5*`; scratch
  DURABLE in /mnt/data/hifipushie/suit5/: the layers agent's scripts retargeted + pl0.py <model> <garment> <tag>
  (build place_only ONCE, pickle Bp / mesh / placing body to out/<tag>.pkl) and pl1.py <pkl tag> <out tag> (place()
  again with the CURRENT code in seconds: seam start gaps, start stretch per piece, lapel folds, crossings, worn
  slides; NORELAX=1 skips the start relaxation; saves out/<out>.npz), shd.py (where the shoulder seam's sides start),
  wdbg.py (one worn column's trace), worst.py <tag> <pieces> (worst start triangles), xing.py / xing2.py (crossing
  pairs; a piece's self crossings as flap / row / base), over.py (share of triangles starting past 5%: ZOZO gives a
  local strain limit only under 3%), gapchk.py <job sim dir | npz> (what ZOZO sees at frame 0: cloth within 1 mm of
  unjoined cloth, collider within 2 mm: "ccd failed (toi 0)" at newton step 1 is THIS or a start past the strain
  limit), tent.py <result npz> (open fronts' forward stand by height vs the body, the hem's level by angle), patm.py,
  run_base.sh (main's code from ./base, a detached checkout), shirtchk.py <model> (the shirt alone)).
  - THE FOREPART BUILT WHERE IT IS WORN (`cloth._worn_top`, garment key / kind `worn_top`: garment_kb kinds jacket and
    coat; `cloth.worn_top(g)`). Torso pieces reaching the neck point: each column (fixed pattern x) laid up the body
    from the torso cylinder at the armpit's level in a plane of constant world x (tilted with the cylinder the
    columns ran in to the neck and front and back met different ridges), clearance easing to `WORN_CLEAR` 5 mm (at the
    draped 12 mm the jacket started 19 mm over the shirt and its carried collar held it 27 mm high: collar_show -33,
    cuffs 21-29), arc length = pattern height; ONE slide per piece (median over the columns that cross the shoulder's
    ridge, by the neck the ridge climbs the neck) so its top lands on the ridge, the cylinder part below moves with it,
    side panels with the mean. Columns in front of / behind the neck stop following the body above `WORN_NECK`.
    `_pin_seams`: seams between worn pieces pinned PIN_GAP 2 mm apart toward each side's own cloth (pinned onto one
    point the cloth crossed), faded over the pattern (WORN_PIN); seams to a made piece (the collar) pulled half way.
    The start relaxation (place's final loop) alternates relax + pin + `_repress` for worn pieces, 12 rounds.
    `folds.pressed_flap`: a lapel (fold >= 150 deg on a worn piece, `_pressed`) is PRESSED onto its forepart: each flap
    vertex at its mirror image across the first row in the pattern, on the base by the affine map of the triangle
    holding it, PRESS_LAY 3 mm off, PRESS_WEDGE 0.3 slope by the line (turned rigidly about the roll line over a
    curving forepart it stretched 30% by 50 deg; at 0.06 slope 88 lapel vertices started within ZOZO's 1 mm contact
    gap: "ccd failed" at frame 0). A pressed fold's first row relaxes with its base. `_on_seam(placed=)`: the collar
    lies on the placed partners (`_at_pattern`: a piece's pattern point where the piece lies), not on the body chart.
    `garment_kind` reads a compiled garment's `_design` (it returned "any": seam finishes by kind never applied).
    Start (ga_suit jacket over the shirt): shoulder seams 233-249 -> 2 mm, CB 16 -> 2, collar neck seams p50 131-163
    -> 4 mm, lapels 165 deg + 46 deg (L blocked) -> 176 / 176 pressed, 1.5% of draped triangles past 5%.
  - su_53 (ga_suit5, 2 cm ZOZO, 736 s): fits, 0 layer crossings, seams ALL closed after the clean-up (sim p95 3.3 mm;
    su_45: 15 pairs open, front.L neck 56 mm), lapels roll 150 / 161 deg (su_45: L 99), cuff_show 15.3 / 13.5 (was
    8.4 / 7.2: the jacket now hangs from the shoulders), collar_show 5 (target 10-20: jacket collar still a little
    high), lapel_gap 13.6 (lapels stand off), collar_hug 24, 2 self crossings at the left gorge. Tent (tent.py): front
    hem 20-26 mm above the back's (su_45: 19-70), the open fronts 5 cm forward of the chest line at the hem, now
    symmetric (su_45: L 17 cm off the body at the hip, R 10; su_53 12-13 both).
  - `front_balance` (bodice block option, m; default 0): the front above the chest line spread upward. 20 mm on ga_suit5
    (su_54): hem level (back 837, front 839-859) but the sleeves rode up and bunched (cuffs 24 / 40 mm, sleeve seams
    64 mm open: the raised front armhole), tent unchanged. NOT adopted (ga_suit5 back without it). If tried again,
    keep the armhole: raise only the neck point / gorge and CF, or redraft the sleeve against the new armhole.
  - THE SHIRT: ga_suit's shirt fails main's `fine_start_check` (53 triangles over 1.6x, worst 3.0x at front.R pattern
    [-0.037, -0.103]), checked with main's own code (4fa7cdc): trousers2's. `workspace/ga_suit5` = ga_suit with the
    shirt's `fine_settle: false`; the jacket work ran on it. Drop it once the shirt builds.
  - Tests: the ten cloth / pattern files + test_collar (+ test_worn_forepart; the collar lay tests run with
    worn_top off) + test_seams pass after merging main 4fa7cdc.
  - Round 2 (main 104b1e9 merged; ga_suit5 DELETED, ga_suit's shirt builds again; sims on ga_suit):
    - Canvas A/B (su_55, interfaced []): the tent is NOT the canvas (left front 15 cm off the body at the hem without
      it, 13 with; the canvas keeps the two sides alike). Kept.
    - The tent was the SIDE PANEL'S HEM SPRING: ga_suit's contour on [sideF, sideB] let each of four edges out 16 mm at
      the hem (64 mm of flare per side), and an open front swung it forward. su_56 with it 0: right front hangs 4 cm
      off the body at the hem (was 12), hem level front / back within ~1 cm. ga_suit and su_garrett now have
      `{"op": "contour", "edge": ["sideF", "sideB"], "at": [["waist", 0], ["hem", 0]]}`. su_58 (final ga_suit): fronts
      3-6 cm ahead of the bust plane at the hip, left still ~2 cm further out than the right (the over side).
    - Collar show: a 20 mm stand (su_57) gave collar_show 14.2 but BOTH LAPELS UNROLLED (49 / 113 deg, a funnel round
      the neck): the roll line comes down from a lower stand and the collar's turn pulls the lapels up. Back to 24 mm:
      su_58 collar_show 10.3 (in band, just), lapels 157 / 163 deg. Don't lower the stand without re-checking lapels.
    - Lapel gap: `made_folds: ["lapel roll"]` (su_59) holds the flaps (all over, 160-162 deg) but the gap only goes
      12-15 -> 10-13 mm and the clean-up makes 8 crossings at the left gorge: reverted. The held flap is carried with
      the BODY (Kabsch on body vertices) while its forepart drapes away from where it started: a made flap needs to be
      carried with its own base (the forepart's vertices under it), not the body. Not built.
    - su_garrett: jacket design + canvas bands copied from ga_suit (carry.py). su_60 stopped before the jacket:
      su_garrett's SHIRT fails fine_start_check (8 triangles over 1.6x, worst 2.76x, front.L pattern [0.081, -0.023]):
      trousers2's.
  - Round 3 (main 6c921d9 merged):
    - Lapel op options `roll_radius` (0.006) / `roll_strength` (0.5): ga_suit 0.003 / 1.0 (su_61): lapel_gap 12-15 ->
      9-11 mm, collar_show 15.
    - THE OPEN SLEEVE SEAM (su_54, su_61: hindarm seam 13, 5 pairs at the hem 40-66 mm open; sim max = final, so the
      solver left it): its start. (a) The under sleeve was moved down the arm ALONE, 9-11 cm (place's "pushed off the
      body" rule hit it at the armpit), so it started below its top sleeve; (b) both sleeve pieces lie on ONE cylinder
      the deltoid's clearance sets: the 298 mm hem on a 610 mm circle, both seams 115-155 mm open at the wrist. Now
      (`place`): an aligned piece (the under sleeve) is never moved down alone, pieces sharing an arm go down together,
      and for worn_top garments (jackets, coats; `SLEEVE_TAPER`) each row of a sleeve lies on the radius its own girth
      needs or the arm's clearance there, whichever is more, smoothed along the arm (a cone). Shirts unchanged (their
      cache keys too: with the taper on for every smooth garment ga_suit's and su_garrett's shirts re-simulated and
      failed the fine-start gate). su_64 (ga_suit): ALL seams closed (sim max 14.9 mm, final 0.3), 0 crossings,
      collar_show 15.0, lapel_gap 10-11, cuffs 15.6 / 8.7, fits. Best ga_suit so far: cloth_renders/su_64_sleeves*.
    - `folds.pressed_flap`: past the base (the roll line's top end, off the neckline) the flap AND the roll's further
      rows turn rigidly about the first row (turn_flap left the further rows' own vertices unturned), and every row of
      a pressed roll is pressed with the flap; place re-presses after `_clear_of_body`; worn neck columns ease in over
      WORN_NECK_CLEAR; a column is shortened evenly past its own ridge (WORN_OVER), not piled at it.
    - su_garrett: ga_suit's design + bands carried (carry.py); hip room from the BLOCK (`hips_ease` 0.14), not flare:
      su_62 without it was "TOO SMALL at hips -18 mm", rode up (collar_show -42, cuffs 38-48), side seams burst 110 mm.
      su_60 / su_63 failed CCD at frame 0: Garrett's front.R gorge strip (pattern x -0.06..-0.1, y -0.05..-0.1, between
      the neckline and the roll line's top) starts 2.4-4.5x stretched; front.L is fine. Not solved: the strip lies over
      Garrett's open shirt collar (the padded body there is the collar's stand and fall). su_65 queued after the fixes
      above (start: 4.2% of triangles over 5%, front.R 3.6x max, left sleeve moved 11 cm down by crossings at the cap:
      armhole start 300 mm). Read its log (/mnt/data/hifipushie/suit5/su_65_garrett.log) first.
  - Round 4 (main 667b4a9 merged), Garrett's right gorge, UNSOLVED. su_65 failed CCD like su_60 / su_63. Findings
    (scripts wdbg2.py / wdbg3.py: worn columns' traces and y/z table across neighbouring columns; worst2.py: worst
    start triangles tagged flap F / fold row R / sewn s / base b; rows2.py: a triangle's vertices by fold row):
    - Unrelaxed, both fronts are 3.4-4x at the lapel roll's TOP rows (y -0.03..-0.06, by the neck point): there the
      flap's mirror image falls past the neckline and the pressed / rigid-turn mix disagree. The relaxation fixes
      front.L, not front.R (the flap and its rows are held during the relaxation).
    - Neighbouring worn columns 4 mm apart ended 2-6 cm apart (the columns "running on" past the neck's base beside
      ones "following the body", and following columns tracking every edge of the shirt collar under them). Now:
      the two lays are mixed by POSITION over WORN_NECK_BAND 4 cm (0.08 was worse), and columns are laid on
      `_envelope(body)` (the padded body with hollows / steps filled by 30 rounds of inflate-only smoothing). Garrett
      front.R start max 3.6 -> 2.95 (p99 1.65); ga_suit unchanged (max 1.13).
    - Tried and worse: the flap free during relaxation (5.2x), no pull to the collar (WORN_PULL 0: 5.1x), wider neck
      band (3.8x). Results swing 2.9-5x between runs of small changes: the start relaxation is chaotic there.
    - The render (out/g14_neck.png) shows the jacket's right collar end and gorge interleaved with Garrett's open shirt
      collar (trousers2 widened it): the shirt collar's fall lies where the jacket's gorge and collar end must lie.
      Next idea: lay the jacket collar's front end and the gorge OVER the shirt collar (its fall in the envelope; check
      the padded body there, `padded_body` PAD_SLOPE bridges steps at 45 deg only), or press the lapel only below the
      neckline (no rigid-turn part), then re-run su_garrett. Garrett's left sleeve still goes 11 cm down the arm on
      start crossings at the cap (not looked at).
  - Round 5 (main merged at 0d8517a, trousers2's break included):
    - Pressed lapels map onto the base by the base's own triangles everywhere (PRESS_OFF 1e3: the rigid-turn mix past
      the neckline disagreed with the press, 3-4x at the roll's top rows); Garrett front.R start 2.95 -> 2.2 in the
      re-placement script.
    - Garrett's left sleeve went 11-12 cm down the arm because under.L crosses side.L at the pit (HITS in pl1.py).
      Crossings between pieces SEWN together no longer send a worn_top garment's sleeve down (ZOZO starts with
      existing intersections between linked pieces allowed). Left armhole start seam 300 -> 158 mm max, sleeve seams
      91-96 mm. (Standing the sleeve out instead did not clear the crossing.)
    - su_66 (Garrett) failed CCD again: in the BUILD's own start (lay1.py; pl1.py from a stale pickle had shown 2.2x)
      front.R's gorge (pattern -0.10..-0.12, -0.05..-0.075, base cloth beside the neck point) is 4.2x: "179 triangles
      start up to 324% stretched", over ZOZO's 100% cap. wdbg3.py shows the cause: the worn columns at world x
      -0.100..-0.116 (just outside Garrett's neck point) climb the open shirt collar's STAND and then turn back down
      its far side (their y reverses). Tried and taken back: a 45 deg per-step turn limit (no change), a cap at the
      neck point's height for the columns beside the neck (worse, 4.9x). Garrett's neck point lies where the shirt's
      open stand rises; the jacket's neckline there should lie in FRONT of / against the stand, not over it.
      Ideas, untried: lay the worn columns on the padded body WITHOUT the under garment's neck pieces (the shirt's
      stand / collar) and push out from the real collider only at the end; or end the march (pattern compressed) where a
      column meets a surface rising more steeply than ~60 deg; or draft the jacket's neck over the shirt collar wider
      on Garrett (over_measures' neck: Garrett 407 -> 473 mm drafted, check the gorge against the open stand).
    - Re-pickle (pl0.py) after any spec change before using pl1.py: a stale pickle hid the 4.2x for a round.
    - ga_suit regression check (su_67 -> su_69): the sewn-crossing exemption for sleeves was WRONG: su_67 started
      under.R through side.R and ended with the back / side and armhole seams 37-71 mm open (2476 s sim). Reverted
      (su_68: all seams closed). The `_envelope` raised the worn top over the neck's hollows and the jacket rode up:
      collar_show 15 -> -5.4. ENVELOPE_ROUNDS is 0 (off; the function stays for the Garrett gorge work). su_69 (ga_suit,
      cloth_renders/su_69_suit*): fits, all seams closed, 0 crossings, collar_show 13.4, cuffs 12.6 / 10.3 (in band),
      lapel_gap 9.5-11, under sleeves 2% crumpled. The pressed-lapel change (PRESS_OFF 1e3) is in it. Best ga_suit.
      Garrett's left sleeve still goes down the arm on the side.L / under.L crossing (open).
  - Round 6 (the coordinator's idea: the forepart lies on the shirt's BODY, the open collar between the jacket collar
    and the neck): `worn_body` = the body padded by the under garment WITHOUT its neck pieces' standing part (pieces
    wrapped "neck"; only their vertices within the neck point's radius + WORN_STAND 2 cm of the neck's axis: excluding
    the whole collar put Garrett's front.L inside the open collar's points on his chest, pushed out 11x), set as
    Bp["_worn_body"] in build for worn_top garments over another, used only by `_worn_top`; everything else (push,
    relax, sim collider) keeps the full padded body. Measured on the BUILD's start (lay1.py + worst.py / over.py, not
    pl1.py: pl0's pickle drops `_worn_body`): Garrett front.R 4.24 -> 3.61x max (front.L 2.54), draped triangles over
    5% ~4.7% (ZOZO's local limit wants <= 3%), collar max 1.7 (made: raised limit). ga_suit start: fronts 1.10-1.11, 2.7%
    over 5%, collar 1.81 (was 1.26): NOT yet simulated with this. So: it helps Garrett's right gorge but not enough
    to start; no Garrett sim run with it.
  - HANDOVER (suit5, 2026-10-08). Branch worktree-agent-a7a27cfe57b8650a5, last commit has round 6; main merged.
    Best result: ga_suit su_69 (cloth_renders/su_69_suit*): fits, all seams closed, collar_show 13.4, cuffs in band,
    lapel gap 9.5-11. Garrett: never simulated through (su_60, 63, 65, 66 CCD at frame 0; su_62 finished on older
    code: too small at the hips, since fixed with hips_ease 0.14). Open, in order: (1) Garrett's right gorge: run the
    build start (lay1.py su_garrett jacket <tag>; worst.py <tag> front.R; over.py <tag>) and get front.R under ~1.6x
    and draped over-5% under 3%; the stretched triangles are base cloth at pattern (-0.10..-0.12, -0.05..-0.075)
    between the neck point and the lapel roll's top; wdbg3.py shows the columns there (re-run pl1 only with a fresh
    pickle, and note pl1 lacks `_worn_body`); untried: let the worn columns end where the surface rises > ~60 deg
    (compressing the pattern), or widen the drafted neck over his open stand; (2) his left sleeve: under.L starts through
    side.L in the pit and the sleeve goes 11-12 cm down the arm (exempting sewn pairs opened ga_suit's seams: don't);
    try moving the side panel's top in at the pit instead; (3) lapel gap ~10 mm: a made flap carried with its own
    forepart (Kabsch on the forepart's vertices under it, not the body's); (4) collar_hug 24-26 mm.
    Re-check ga_suit with a sim after (1) / round 6 (su_69 predates worn_body).
  - NEXT, in order: (1) carry made lapel flaps with their forepart (then lapel_gap); (2) su_garrett once its shirt
    builds; (3) collar_hug 17-26 mm. Old list (tent done as above): (1) the tent: fronts 5 cm forward at the hem with the hem 2 cm high at the front (what to check:
    the front's canvas band / interfacing rest, the side panel's hem spring contour +16 mm, the front's waist
    suppression; a sim with interfaced [] isolates the canvas); (2) collar_show 5 -> 10-20 (the jacket collar's stand
    over the shirt's; lower the stand or the worn neck); (3) lapel_gap 13 mm (the pressed lapel's roll rows spring
    back: made_folds on the lapel is now possible since the forepart starts worn); (4) su_garrett: carry ga_suit's
    jacket settings + canvas bands, then the layered sim (needs the shirt to build).

- Suit 6 (2026-10-08, "suit6" agent, branch `worktree-agent-a567f36d476596530`; renders `cloth_renders/su_7*`; scratch
  DURABLE in /mnt/data/hifipushie/suit6/: suit5's scripts retargeted + lay1.py (the BUILD's start; PKL=<tag> also
  pickles it WITH the worn body, so pl1.py <pkl> <out> re-places in ~1 min with the current code; NORELAX=1, ENVR=<rounds>,
  PRESSLAY=<m> overrides), trace.py <pkl> <vertex | piece:point ...> (each place() stage that moves those vertices,
  TRACE_MM threshold), probe.py <pkl> x y z (clearance on the placing / worn / real body), folds_pad.py <pkl> (turned
  faces of the padded bodies), selfx.py <npz> <pkl> (crossing vertices at X / X0 / Vsim / V), xing2.py <npz> <piece>
  <pkl> [key] (a piece's self crossings tagged flap F / fold row R / base b), cbcol.py <pkl> [npz] (centre back: the
  under garment's collar and neckline heights vs the jacket's back and collar), rise.py <result> (z moves start -> end
  by piece), at.py, ut.py, envsweep.sh, fig.py <model> <png> [1 = textured] (the whole outfit front + 3/4 beside the
  concept), tests.sh).
  - GARRETT'S JACKET SIMULATES THROUGH (su_73, su_75; first time). The frame-0 CCD failure was not the gorge columns:
    `padded_body` FOLDED. Offsetting the body along its normals by a pad deeper than a hollow is wide crosses neighbouring
    normals: 116 turned faces round the neck under the open shirt collar, 24 in each pit. Clearance / push-out read a
    folded surface's normals backwards (a gorge vertex 21 mm clear was pushed 56 mm out across the shirt collar), and the
    pit's folds made under.L cross side.L (the left sleeve sent 11 cm down the arm). `_unfold_offset` (in padded_body,
    every padded body): faces turned > ~70 deg from the body's own are smoothed out over up to PAD_UNFOLD rounds, never
    in past the pad. Garrett start fronts 3.6 -> 1.13x, left armhole start p50 189 -> 73 mm, no sleeve crossings.
  - Worn columns running on past the neck's base (free_neck) go the way their last WORN_RUN 4 cm went, frozen when they
    start (the step's own direction at that moment, over the edge of an open collar's point, sent neighbours 4 mm apart
    7 cm apart). front.L 2.5 -> 1.09x.
  - su_71 then hung 15-50 mm HIGH (collar_show -45, cuffs 44, side-back / armhole seams 100 mm open): its back started
    42 mm over the shirt's neckline at CB (ga_suit: 14 under it) and the carried collar held everything up. Two causes:
    (1) back columns behind the neck ran up the nape with the piece's one slide: now they stop at the under garment's
    neckline at that x (`worn_body(...).under_top` = the under garment's body cloth round the neck, WORN_NAPE 0);
    (2) the notched collar's worn neck chain was snapped onto the full padded body (the shirt collar) and its chart
    (where the jacket's neckline lies worn) is 1.30x the collar's neck edge on Garrett (ga_suit 1.15: his back neck curves
    round more than the draft), so the chain cut the corner up the nape. Now `_on_seam(chain_body=)` snaps it on the worn
    body and holds CB (NOTCH_HOLD_CB 4 cm) when the chart is > NOTCH_HOLD_RATIO 1.2 x the edge (ungated, test_collar's
    made lay failed). Garrett collar start CB 1.577 -> 1.554 m.
  - Garrett spec (su_garrett v13-15): jacket colour #3a3836 (charcoal from the concept; was slate #3b4252), collar
    stand 19 / fall 31 (his neck is short: shirt stand 20 / fall 32; ga_suit's 24 / 36 sat over it), sleeve
    length_bonus -0.02 (cuffs were 44 mm), garment keys `press_lay` 0.005 and `worn_envelope` 10 (NEW general keys:
    PRESS_LAY / ENVELOPE_ROUNDS per garment; the open shirt collar's points on his chest under the lapels made the
    pressed left lapel cross its forepart: 13 -> 8 start crossings, and su_73 kept 26 in the sim, su_75 cleaned them).
  - su_75 (Garrett, 2 cm ZOZO settle, 1893 s): fits, 0 crossings after the clean-up (16 in the sim), 2 of 361 sewn pairs
    open (side-back seam L, 42 mm, near the hem), collar_show -4.3 (target 10-20: the jacket collar still covers the
    shirt collar at the back), collar_hug 25, cuffs 27.7 / 26.1 (target 10-15), lapel_gap 7.4 / 6.2 (best so far,
    target 0-6). Outfit beside the concept: cloth_renders/su_75_garrett_outfit.png (clay), _outfit_tex.png. Read: a
    charcoal open two-button jacket over a pale open-collared shirt and dark creased trousers on shoes: the concept's
    outfit. Wrong vs the concept: soft sloping shoulders (no structure), the jacket short and boxy at the hem, sleeves
    a little short and wrinkled, lapels narrow, the shirt collar hidden at the back, the belt not seen (shirt specks at
    the waist in 3/4), trousers a little wide.
  - cloth.look: an under garment shown with the one over it is drawn PRESSED (res["under_V"]: what the outer one was
    simulated over); drawn as its own sim, the shirt's sleeves showed through the jacket in white patches. The body is
    taken from a garment with worn parts (shoes show).
  - ga_suit regression: su_70 (main + worn_body) / su_72 (+ unfold) / su_74 (+ nape cap, chain): fits, all seams
    closed, 0 crossings, collar_show 14.4 / 16.1 / 17.7, cuffs 11.4-14.7 / 9.2-10.5, lapel gap 9-11. su_74 reads
    CORRUPT on under.R 4% crumpled (su_72 under.L 2%, su_69 2%): ragged under-sleeve hems; not traced to a change.
  - Tests: the eleven cloth / pattern files + test_seams green (test_collar after the gate).
  - NEXT: (1) collar_show on Garrett: the jacket collar still reaches the shirt collar's top at CB (try stand 16, or
    the jacket's back neck lower: its CB sits at the shirt neckline); (2) shoulder structure (support: shoulder_pad on
    Garrett's jacket) and length (length_bonus), sleeves +10 mm; (3) the side-back seam's last pairs; (4) the belt
    against the shirt at the waist (trims over a shirt tucked in?); (5) lapel_gap (made flap carried with its forepart),
    collar_hug 25.
  - Round 2 (the coordinator's list: shoulders, length, collar_show, sleeves, belt, lapels, trousers; renders su_76/77):
    - su_garrett v16-20 jacket: `support` [shoulder_pad 12 mm, sleeve_head] + detail shoulder "pad_and_head",
      length_bonus 0.18 (hem z 0.79-0.81: covers the seat; was 0.86), lapel width 0.095, sleeve length_bonus +0.006,
      collar stand 19 / fall 31. Shirt colour #bdb8b4 (#d0cbc7 rendered near white under the clay lights; the concept's
      lit shirt samples ~#a9a5a2).
    - su_76 with collar stand 16 / fall 28 (+ lapel 100): both lapels UNROLLED to 33-41 deg (a funnel round the
      neck), as su_57 on ga_suit: lowering the stand unrolls the lapels. Don't lower the stand to fix collar_show.
    - su_77 (3112 s): fits, lapels roll 142 / 172 deg, lapel_gap 7.9 / 5.7, cuffs 19.8 / 15.7 (was 26-28),
      collar_show -7.9, collar_hug 27, BUT 14 of 376 sewn pairs open (side-back seams 67-108 mm and the underarm
      37-98 mm, all at the pit corner where side panel, back and under sleeve meet: they START 150 / 75 mm apart and the
      pads add tension) and 28 layer crossings. Outfit: cloth_renders/su_77_garrett_outfit_tex.png: longer, greyer
      shirt, lapels rolled, shoulders squarer; still no belt, pit seams not seen in that view.
      Tried and reverted: pinning the side panels to the worn back in place() (sleeves then crossed them and went 7-8
      cm down the arm, pushes 50 mm). Next to try: zozo.stitch_stiffness 3 on the jacket (time), or start the side
      panel's top in at the pit.
    - THE BELT: the shirt was never tucked: a free garment over the trousers' waist. trousers `over: shirt` (the
      shirt pressed under them) is the tuck. `padded_body` now keeps the body's worn parts (shoes): without it the hem
      started inside the shoes (tr_20: "contact starts overlapping"). tr_21 then failed at frame 44: "Intersection
      detected", one cloth face vs a collider edge at the right shoe's top (x -0.22, z 0.10). Not traced. su_garrett's
      trousers are back WITHOUT `over` (the cached tr_19 drape shows).
    - `_unkink` (main's clean-up) capped at KINK_MAX 6 mm per vertex: it walked a sleeve hem's real folds 15-20 mm
      flat (ga_suit su_74 under.R 0.6% crumpled in the sim -> 3.7% after the clean-up, CORRUPT; now 1.2%, fits).
    - Stage 2's hem gate: `cloth_workflow.hem_width` measures each leg piece just over its own hem's corners (a break
      hem dips in the back's middle: read at one level it was 165 mm for 377 and failed "TOO SMALL to pull on").
      Test test_sloped_hem_is_the_whole_leg.
    - NEXT: (1) the pit seams (stitch stiffness / the side panel's start); (2) the trousers over the shirt (the shoe
      intersection: dump the frame-44 state, check the shoe collider slivers UNDER_SLIVER drops); (3) collar_show by
      the jacket's back neck, not the stand; (4) collar_hug; (5) trousers slimmer: a sheet's `block_options` REPLACES the
      kind's draft block options (seat_ease alone made a 165 mm hem): set the leg through fit or extend compile_sheet to
      merge. A new shirt from the "placket" agent will re-simulate everything layered over it.
  - Round 3 (the coordinator's order after su_77; ZOZO now on a rented 4090: env.sh sets HIFIPUSHIE_ZOZO_REMOTE to
    THIS worktree's spikes/gpu_cloth/remote.sh + GPU_SSH_*; LOCAL_ZOZO=1 runs on the laptop; a Garrett jacket is ~6-13
    min there, 50 min here):
    - CORRECTION: a design sheet's `block_options` DO merge over the kind's draft options (compile_sheet's `_merge`);
      the "165 mm hem" was the hem gate's own misread (fixed in round 2), not the merge. Trousers slimmer: the cut is
      `leg` (LEG_CUTS: tailored = "slim"; "skinny" is the next step) or knee ease; not run yet.
    - Stage 2 `front_closure button_stand` counted only stitches: a jacket worn OPEN has its buttons as a closure with no
      stitches and failed "0 stitches". Now a closure's fastening pairs count (garment_design evidence "stitches").
    - THE PIT SEAMS (su_77: side-back 67-110 mm, underarm 37-100 mm open). su_79 = su_77 + zozo.stitch_stiffness 3
      (761 s on the 4090): WORSE, 23 of 380 pairs open (both side-backs 109 mm, both underarms 102 mm), collar_show -11.9.
      Not stiffness. The START: seam 4 (side-back) starts 135-160 mm open over the whole height and sideF 25-35 mm,
      because smooth placement lays every torso piece on ONE cylinder as big as the garment's widest level
      (place(): C = hull offset by (Wmax - P0) / 2 pi; Wmax the max span), and at the jacket's suppressed waist the
      arc left over between front (from CF) and back (from CB) all falls into the side panel's back seam (the panel is
      side "front", measured from CF). Measured: per side leftover ~170 mm at the waist, side panel 53 mm wide there.
      Tried and reverted: moving the side panel back by a share of the leftover (SIDE_CENTRE): at 0.5 it overshot, at
      0.35 both seams started 77 / 127 mm open AND the panel crossed the under sleeves at the pit (the sleeves then
      went 11 cm down the arm, pushes 50 mm). The real fix is a per-level cylinder (each level's hull out to that
      level's own span), which clothflow tried once and dropped for 10-30% shear: try it only for worn_top garments
      below the armpit, arcs measured from CF AND CB at every level, with the start relaxation after.
    - collar_show / collar_hug (the user's annotated read of su_77: the jacket collar must lie LOW and flat round the
      back of the neck outside the shirt collar, the notch lower on the chest, the shirt collar showing above the
      jacket's at the sides): su_garrett v21-22 jacket = op `neckline` {widen 0.012, back 0.035} FIRST in the ops (it
      must come before style lines), lapel `gorge_drop` 0.12 (was 0.085) and `break_y` 0.46 (0.40). Start (g14): the
      notch sits on the chest, the jacket's CB neckline 1.550 (was 1.568; the shirt's neckline at CB 1.556, its collar
      top 1.579). The start lay has the fall OPEN (40 deg), so collar_show can only be read after a sim. NOT SIMULATED:
      layered Garrett runs are on hold until the placket agent's shirt (new sim key) is on main.
    - Trousers over the shirt (the tuck): tr_22 on the 4090 passed the coarse sim (the laptop's tr_21 died at frame 44
      with "Intersection detected" at the shoe top) and then stopped at the fine settle's start check: 103 triangles over
      1.6x, worst 4.4x at back.L/R pattern [0.227, 0.001] (the side of the back's waist seam: the made waistband
      rebuilt at its closed girth on the body's hull, under the pressed shirt tail, so the back's top is cleared over
      the shirt). Next: give the fine settle's band (and `_press_plan`'s clearing) the padded body, or try
      fine_settle false for the trousers over the shirt.

- Suit 7 (2026-10-08, "suit7" agent, branch `worktree-agent-af71a3f0c0a4e3d8a`, continues suit6; renders
  `cloth_renders/su_8*`, `tr_24*`, `om_0*`, checklist sheets `cr_81*`; scratch DURABLE in /mnt/data/hifipushie/suit7/:
  suit6's scripts retargeted + run.sh (EVERY script through /mnt/data/hifipushie/bin/capped, peak RSS printed,
  PYTHONUNBUFFERED), q.sh <queue> / qlocal.sh (LOCAL_ZOZO=1), env.sh (sources /mnt/data/hifipushie/gpubox/env.sh, then
  points HIFIPUSHIE_ZOZO_REMOTE at this worktree's remote.sh), mkq.py (a queue line with design ops patched, compact
  JSON), check.py <tag> <jacket npz> [trousers npz] [shirt npz] [model] (the reference checklist + cr_<tag>_focus /
  _figure), section.py <result npz> (jacket vs body per direction and height + where the two front edges are: THE
  tent measure), tent.py, near1.py, dbg_place.py (place_only with every _piece_crossings call's largest triangle;
  TRACE=1 names the cloth function that moves rows > 5 cm; NOWAIST=1), dbgrun.py <secs> <script> (stack dump when RSS
  passes 4 GB), pp_dbg.py (OVER=shirt UCAP=0.003: the fine settle's start step by step), patdump.py (pieces' boxes and
  x extents by height), meas2.py (tape + hull girths under the waist), gate1.sh / gates3.sh, st_tb.py (a stage with
  its traceback), mk_om.py, cpmodel.py, ed_om1.py, ed_pk.py, patch_*.py (every code edit as a script: the sandbox
  refuses heredocs / loops / pipes it can't verify: write files with the Write tool and run one plain command).
  - THE OOM OF 13:37 WAS THIS THREAD'S (a 17 GB python): every "trousers over shirt" build hit it (suit6's tr_22 too).
    `_leg_tube.level()` read the FRONT leg piece at a row under its own hem (a break hem's back is 12 mm longer; rows
    are rounded to cm levels), got no width, and the front hem's vertices fell back to the seat cylinder at centre
    front between the feet (27 cm triangles in the first placement pass; the relaxation pulled them back, so nobody
    saw); `_piece_crossings` / `_pair_crossing_verts` searched with ONE radius = the largest triangle, so on a 12.7k
    vertex fine mesh every edge paired with every triangle within 14 cm. Fixed: each piece is read no lower than its
    own hem; both searches raise ClothError "the start is broken: a triangle of <piece> is X m across" (main's chunked
    search sits behind that raise); `_clear_of_worn` moves are bounded (WORN_STEP 12 mm a round, WORN_REACH 30 mm).
  - suit6's `_worn_levels` VERIFIED: Garrett su_81: all seams closed (su_79: 23 pairs open to 110 mm), 0 crossings,
    cuffs 13 / 14, collar_show 3.8 (suit6's lower back neck: was -11.9). ga_suit su_82: fits, all closed, collar_show
    12.1, cuffs in band.
  - `cloth._clear_exact` (EXACT_GAP 3 mm): draped start vertices and edge points against the collider's TRIANGLES,
    two-sided for an under garment's cloth (wound as its pattern lies), signed for the closed body. In build after
    place() for a layered smooth start (the start is laid on the PADDED body; the collider is body + the under
    garment's own mesh: ga_suit's top sleeve seam sat 1.8 mm from a pressed shirt-sleeve fold at the elbow, "contact
    starts overlapping" at frame 0 on the 4090), and for the fine settle's start over an under garment (there the
    old code read the collider as a closed Body: the shirt's normals pushed the trousers' back INTO the tucked tail,
    102 triangles 1.6-3.9x: suit6's tr_22 failure). Unlayered garments' starts and keys untouched.
  - THE TUCK WORKS: tr_24 (su_garrett trousers `over: shirt`, `under_cap` 0.003, 461 s on the 4090): fits, 0
    crossings, all seams closed, fly 18 of 18; reads as trousers over a tucked shirt. `cloth.waist_hung` /
    over_measures(waist=layer gap): a garment hung from the waist is taped over what is tucked in, incl. the layer
    gap (793 -> 833 mm; without the gap the band started 13.6 mm short of closing).
  - `collar_hug_mm` (cloth_layers.tells + cloth_reference) is read on the outer collar BEHIND the neck's axis: a
    notched collar's ends lie on the chest. su_81 27.0 -> 18.4 (still a miss; target 0-6).
  - THE TENT, by measure (section.py on su_81): from z 1.40 to 1.00 the fronts lean forward ~10 deg and are plumb below
    the break; the two front edges OVERLAP 15 mm at the centre and the sides hug the hips at 2-8 mm: the jacket hangs
    closed with all its ease in front. Two causes. (1) The stiff front: canvas bands + lapel roll strength 1.0 make
    a board that continues the upper chest's slope down to the break. su_83 (interfaced [], roll_strength 0.2): fronts
    37-47 mm off the body from the chest down (were 57-99), plumb; cost: lapel gap unchanged, 6 crossings at the left
    gorge. (2) The start: an OPEN jacket was started lapped like a buttoned one. `open_gap` (garment key; OPEN_GAP 0.16
    m at the hem, linear from the armpit's level; `cloth.open_gap`, in `_worn_levels`): fronts and side panels start
    that far from CF and every level's curve is that much longer: the loose tube an open jacket is. NOT YET VERIFIED
    BY A SIM (om_02 / om_05 failed at their starts, below).
  - Trouser block option `waist_drop` (m under the natural waist; `pattern_blocks.dropped_waist`): girth there, rise,
    seat line, knee and lengths follow, pieces + band carry wrap "drop" (place(), stage 2 leg ease, the band's
    dimension checks and the waistband height target read it). 0.07 on a scratch copy (su_om_tr): gates pass, band
    860 mm. Not simulated.
  - KB: jacket fit "relaxed" (waist +18..+32%: a straight, unsuppressed body on a V torso). Stage 3 crashed on a
    shirt with no hem topstitch row (None * 1000): fixed. cloth_reference.render_front draws the garments' `collide`
    parts (shoes).
  - `su_om_garrett` (mk_om.py: om_garrett's base + su_garrett's shoes / socks / soles and cloth sheets; head-fit keys
    that need onemesh2's code, base.head.warp as a list and shape hood / hollow / jaw_angle, are LEFT OUT until that
    is on main: take the head at the end, it changes only above the neck). Its tape vs the old body: shoulder slope
    11 deg (22), shoulder to shoulder 468 (481), hps to waist 493 (508), waist to armpit 254 (236), waist 785 (793).
    Sheets (ed_om1.py): jacket length_bonus 0.12, lapel 0.075 + roll_strength 0.3, take_in 0.008 / 0.010, CB waist
    0.012, interfaced [], fit relaxed; trousers over shirt + under_cap 0.003. Scratch copies su_om_pk (+ flap pockets
    [0.125, -0.585] 150 x 55 and breast welts [0.135, -0.275] 100 x 22 on "front": gates pass; flaps / welts are MADE
    pieces carried with the body: expect them to stand off a draped front, as a held lapel did) and su_om_tr
    (waist_drop 0.07).
  - Shirts on the new body: om_01 (main before placket) and om_04 (placket's: one button open, spread collar) both
    read "CORRUPT: collar 4-5% crumpled | fits" with 28-35 sewn pairs open to 4-13 mm: usable as an under garment,
    not finished (placket's thread).
  - FAILED AT THE START on su_om_garrett, not yet diagnosed (the GPU box was deleted at the usage-limit stop):
    om_02 jacket (old shirt): "contact starts overlapping", dynamic vertex 1752 vs the collider, 1.87 mm (so
    _clear_exact's 3 mm did not hold there: check whether that vertex is MADE (collar: not moved), or moved back by
    _carry / _open_start after the clearing: the clearing runs on Xs before `_open_start` makes Xstart); om_05 jacket
    (placket's shirt): Newton stalled at frame 0, "a prescribed pin driven into geometry that cannot yield", held by
    vertex 2097 (a carried made piece, the collar, against the new spread shirt collar?); om_03 trousers: ZOZO's
    builder assertion `left > right` 0.0 / 0.0 while "computing constraints" (a zero-length or zero-area element
    in the job: look at in.npz's rest triangles and stitch pairs; tr_24 on the old body built). Use jobstr.py /
    gapchk.py on workspace/_cache/cloth/job_<key>/sim.
  - Round 2 (same day, after the usage-limit stop; main 3eb0b2b with placket's shirt merged in; commits d3cf2a1 /
    e3edfb6; scratch adds job0.py / job1.py / job2.py / job3.py / job4.py / job5.py <job dir> (a failed job's in.npz
    against its FRAME-0 collider `bodyV0`: least separation, what crosses the under garment and where, degenerate /
    faceless elements, what is near a named vertex; gapchk.py reads the BENT body and calls every straight-arm
    forearm a contact: don't use it for sleeves), slv.py, jts.py, ed_om2.py, patch_exact4 / made / thru / orphan /
    drop / docs.py, resolve1.py; tests/test_suit7.py).
    - The three start failures on su_om_garrett, each a general fault: (1) `_clear_exact` was one-way: now the
      collider's vertices and edge middles are also tested against the CLOTH's triangles (a shirt placket under the
      middle of a 2 cm jacket triangle: 0.013 mm with every cloth vertex and edge point clear). (2) A made collar is
      never cleared: `_lift_made` (made pieces lifted along the body's normal to the padded body's height + 3 mm, at
      most MADE_LIFT 15 mm, evened over the piece), and a layered collar that is sewn on open and turned down by its
      carried poses gets pins that pass through the collider (`Bp["thru"]` -> the runner's hugIdx; no body_offset
      change): prescribed onto the open shirt collar's wings the solver stalled at frame 2-3, "a prescribed pin driven
      into geometry that cannot yield" (om_05 / 07 / 09 / 11; open_gap 0 stalled too: not the open start). (3) ZOZO's
      builder asserts `left > right` 0.0 / 0.0 on a collider vertex with no face area: 10 shoe faces of 5e-11 m2 on the
      new body, then 12 faceless shoe vertices once those faces were dropped: `_collider` leaves out faces under
      0.0005 mm2 AND the vertices they orphan, for the under garment and for worn parts (cleaned before they join the
      poses).
    - Armhole depth is per body: the same sheet on su_om_garrett (hps 33 mm lower, armpit the same) had its armhole
      31 mm shallower from hps: under sleeves crossed back / side panel at the pit, `sleeve_down` 3-6 cm, sleeve seams
      100-125 mm and armholes 110-130 mm open at the start (su_garrett: 1-2 cm, 70-80, 88). bodice `armhole_depth`
      0.14 on its jacket: 1-2 cm, 43-80, 90.
    - om_13 = THE FIRST JACKET THROUGH ON THE NEW BODY, over placket's shirt (524 s): fits, 0 crossings, 0 layer
      crossings, seams closed bar 3 collar pairs (4.5 mm), collar_show 9.6, collar_hug 19.6, cuffs 24.6 / 20.8, lapel gap
      11.5 / 14. section.py: the fronts are 8-10 cm apart at the chest and come together again below the button (2 cm
      at the hips), 53-71 mm off the body in front at the hem (plumb from the chest), sides at the hips +4..6 mm.
      Trousers om_12 (su_om_tr: waist_drop 0.07, over the shirt): 0 crossings, seams closed, STRAINED at hips / seat
      13% (seat ease 5% over a tucked shirt); om_14 (su_om_garrett batch 2: straight leg, drop 0.10, seat ease 7%):
      STRAINED at seat 13.3% still, 0 crossings, fly 9 of 9.
    - Checklist on om_13 + om_12 + om_04 (cr_om13_figure.png with shoes, cr_om13_focus.png): 13 misses (su_81: 18).
      Gone: body length, silhouette, lapel width, tuck, layering, leg opening. Left: collar_hug 20, hem sweep -21%,
      pockets, belt (trims aren't in light results), shoulder +12%, front_hang 55 (84), rise +50 mm (+121), waist
      width 335 vs 414, sleeve width -21%, knee -11%.
    - THE COLLARS ARE NOT RIGHT (the coordinator's and the user's read of om_13_jacket_collar.png): the jacket
      collar's ends stand up as wings 4-6 cm over the shoulder line at both sides of the neck, the back is a thick
      roll, the pressed shirt collar under it draws ragged. The ruff is in the START (out/o2_start.png; collar start
      stretch p99 1.48, max 1.8-1.9 on both bodies) and the collar is made = held as laid. Top item for the next
      round; the coordinator's direction: stand ~2.5 cm up the back of the neck, fall over the neck seam, and from the
      neck's side collar and lapel one flat surface to the notch; consider the collar's ENDS (past where the roll
      line meets the neck edge) as draped interfaced cloth sewn to the gorge, not carried.
    - su_om_garrett's sheets now (ed_om1 + ed_om2): jacket fit relaxed, armhole_depth 0.14, length_bonus 0.12, lapel
      0.075 / roll_strength 0.3, take_in 0.008 / 0.010, CB waist 0.012, panel hem spring 0.006, interfaced [],
      support [sleeve_head] (no pad: shoulder width read +12%), sleeve length_bonus 0.018 / hem_width 0.32; trousers
      over shirt, under_cap 0.003, waist_drop 0.10, leg straight, seat_ease 0.07. om_15 (that jacket) was queued.
    - THE COLLARS, DIAGNOSED (coll_dbg.py <result npz>, cbcol2.py <jacket npz> <shirt npz>; om_13): the jacket collar's
      117 vertices move 0.0-0.5 mm from start to end: the wings are 100% the START LAY of a made, carried piece (not
      the `thru` pins, the open-then-turn schedule or the gorge seam). Sections of the end state (mm). Centre back (y
      behind the neck's axis, z): skin (26-30, 1534-1590) | shirt stand (51-53, 1537-1557) | shirt fall out to (63,
      1534) | jacket back's top (74, 1532) | jacket collar neck edge (74, 1532), stand top (75, 1548), fall edge (85,
      1520): the jacket collar sits correctly outside the shirt's (11 mm out, 11 mm lower); the "thick roll" is the
      SHIRT's open stand standing 23-25 mm off the nape. Neck's side (x, z): neck skin (49-63), shoulder line down to
      (249, 1442) | shirt stand x 80 (20 mm off the neck) | shirt fall = a spread wing out to x 105, z 1508, 15-20 mm
      over the shoulder | jacket front's neck point (94, 1546-1556), its cloth at x 112-128 30 mm over the shoulder |
      jacket collar on top, a shelf out to (149, 1530), 50 mm over the shoulder = the wing. Cause: the jacket's neck
      point (x 94; neck drafted 470 mm over the shirt collar) lies INSIDE the shirt collar's spread wing: the forepart,
      laid on the body without the shirt's neck pieces, is cleared up over the wing and the made collar bridges
      outward. What the jacket needs of the shirt (sent to placket): an open stand within ~5-8 mm of the neck at back
      and sides, a fall within ~12 mm of its stand until past the jacket's neck point. placket is making the stand hug
      (its pk_38: still 16 mm off the nape). If a wing remains over a hugging shirt: the collar's ENDS (past where the
      roll line meets the neck edge) as draped interfaced cloth sewn to the gorge, not the made lay's rigid plane.
    - `pressed()` keeps roll folds' rows and flaps (an open shirt neck's rolled-back fronts) as simulated: pressed flat
      to the cap they drew as a ragged, torn edge under the jacket.
    - Batch 2 on su_om_garrett: jacket om_15 (no pad, sleeves +12 mm / hem 0.32, panel hem spring 6 mm; 619 s): fits,
      0 crossings, collar_show 15.7 (in band), collar_hug 19.2, cuffs 18.7 / 15.1, lapel gap 9.8 / 6.9; the RIGHT collar
      neck seam 6 of 17 pairs open to 16 mm (collar / front.R: watch it). Checklist cr_om15 (11 misses): front_hang
      27.6 mm (su_81 84, om_13 55), rise +20 mm, shoulder still +9.6% without the pad (the block's shoulder: try
      shoulder_ease negative or a narrower across-back), straight legs overshoot (leg opening +25%, length +40 mm: go
      "tapered" or give knee / hem), hem sweep -21%, waist width -16%, pockets, belt.
      su7_collar_om15_vs_concept.png = the concept's collar crop | ours front | 3/4 | back: ours is BAD (wings at both
      sides of the neck, shirt edge ragged: that run predates the pressed() fix).
    - Posed figure for "fronts apart": `su_om_pose` (mk_pose.py 45: every arm joint turned about the shoulder until the
      upper arm is 45 deg from the vertical, the concept's A-pose; ours hang at 25.5). po_01_jacket was running at the
      stop (it builds the shirt on that body first): read section.py on out/po_01_jacket.npz (the last column = where
      the two front edges are) against om_13's 8-10 cm at the chest, 2 cm at the hips.
    - po_01 (su_om_pose jacket over its own shirt, 1027 s): THE POSE DECIDES WHETHER AN OPEN JACKET HANGS OPEN. Arms at
      45 deg: front edges 207 mm apart at the chest, 171 / 156 / 131 / 115 / 121 mm at z 1.25 / 1.15 / 1.05 / 0.95 / 0.88
      (the concept: 12-15 cm at the waist); arms at 25.5 deg (om_13): 106 / 78 / 50 / 33 / 21 / 21. Raised arms lift
      the sleeves and pull the fronts round to the sides. fits, 0 crossings, seams closed bar 3 collar pairs (1.5 mm),
      collar_show 22.1, cuffs 32.6 / 32.8 (the sleeves ride up the raised arms: judge sleeve length at the pose the
      reference is in), lapel gap 9.8 / 10.2. Render po_01_jacket.png. So: compare with a reference IN ITS POSE
      (su_om_pose for this concept), and don't chase "fronts apart" on a body whose arms hang lower.
    - NEXT, in order: (1) the jacket over placket's hugging shirt when it is on main: re-run om jacket, cbcol2.py
      both sections, collar_cmp.py; (2) if wings remain: collar ends draped; (3) po_01's fronts; (4) the right neck
      seam; (5) belt + loops drawn in the figure (cloth_trims.meshes on the trousers' result; check.py's light npz has
      no trims: the checklist reads "belt False"); (6) trousers leg "tapered", length; (7) pockets (su_om_pk: gates
      pass; never simulated); (8) the outfit sheet through cloth.look (fig.py su_om_garrett <png> [1]) once jacket,
      trousers and shirt are all cached for the saved sheets; (9) the head at the end (mk_om.py NOHEADFIT=0 once
      onemesh2's base code is on main).

- Suit 4 (trousers, shirt) (2026-10-07, "trousers2" agent, branch `worktree-agent-a06095d1485fd23a1`; scratch DURABLE in
  /mnt/data/hifipushie/trousers2/: the trousers agent's scripts with W = this worktree, + sdiag.py <tag> [1.05] (start
  stretch: largest principal stretch by piece and height band, p90 per band, the waistband's seam pairs), tdiag.py /
  vdiag.py / col.py (one band's triangles: row / column stretch and shear; one piece's column of vertices), legsec.py
  (the leg's sections), wstrain.py <npz> (a sim result's stretch vs the pattern by piece and direction), marks.py (the
  closures' fastening pairs, flat and at the start), collm.py <model> (neckHeight, collar options, the drafted collar's
  stand / fall / points), neckrows.py, t1.py <test file> <tests...>, run_base.sh (code at ./base, a detached checkout
  of another commit: `git worktree add --detach base <commit>`), patch_*.py (the sandbox refuses heredocs with code)).
  - Trouser legs START ON THE LEG (`cloth._leg_tube`, wrap "follow": false = the old seat cylinder all the way down):
    below the crotch each leg's front + back go on a tube square to a smooth leg axis (quadratic through the
    sections' plan middles), its section the leg's own (radius per direction smoothed `LEG_SMOOTH` up and down)
    pushed out to the cloth's girth (+ `LEG_APART` per seam, >= `LEG_CLEAR` off the leg; `LEG_TAPER` caps how fast
    the girth may fall, 5 = off), front crease line on its front, the back's half the girth round, pattern length
    along the axis, the leg under `LEG_EASE` over the ankle compressed until the hem clears the foot; blended into the
    seat cylinder over `LEG_BLEND` 15 cm under the crotch (the seat cylinder now stops just under that). su_garrett
    start: side seams 174 -> 15, inseams 213 -> 8 mm (p50), 0 crossings, every triangle within 5%: stage 4 passes.
  - THE FIND: a start whose edges are all within 5% can be 9-12% stretched (principal) along the diagonal: a column
    leaning 0.1 against its rows is already ~5% (shear is first order). A tube that narrows down a leg leans its
    outer columns by about a quarter of the narrowing rate; horizontal rows on a leg splayed 11 deg are a shear of that
    slope; a row anchor (the piece's row middle) drifting toward the fork shears the top of the thigh. `_relax_strain`
    (in place()'s start relaxation, after `_relax_stretch`): per triangle the deformation's singular values clamped to
    1.03 (compression left), vertices drawn toward that shape, Jacobi, 300 iterations, 6 rounds with the body clearance.
    It took the trousers from 24-27% of the triangles over 5% to none. Fold rows are held there EXCEPT a trouser leg's
    in-wrap press folds (the crease: held, it pinned a leaning column's shear). It runs for every smooth (ZOZO) start.
  - Front-opening waistband laid the wrong way round (seam p50 223 mm, "half a turn"): its chain starts on the left
    front and runs round the back, laid from the back centre it went to the left first; wrap `"dir": -1` (pattern +x
    round toward -x from the start), set by op_waistband's front opening. Band seam p50 now 54 mm (the seat cylinder
    is wider than the band at the waist).
  - Shirts are WORN as their kind is (the user: "a dress shirt with no tie would have top button unbuttoned and
    open"): garment_kb `kinds.shirt.wear` {no_tie, tie} closure overlays (garment_design.wear, laid in cloth.pieces
    before the garment's own), garment / sheet key `tie` (default false): collar "open", front `{"open_top": 1}` (new
    closure state: the n highest fastenings undone, by their mark's height). Every Simon shirt now starts open.
  - Unbuttoned stand: `_open_closure` (girth from the open closure's fastening pair) and a branch in place()'s neck
    code: seated and laid like a buttoned stand (hull of the neck's own sections over the band's height, recentred),
    no lap, its ends `NECK_OPEN` 35 mm apart at the throat. su_garrett: 114 -> 35 mm open, collar 2.2x -> 1.15x.
    NOT YET SIMULATED: do the fall and points spread into the concept's soft V? The stand is made / carried rigid, so
    the start's gap is the worn gap: judge it on the first sim and tune NECK_OPEN.
  - Collar proportions from the neck: garment_kb `kinds.shirt.collar` + `cloth.collar_options` (design tables with
    `"collar_rule": "simon"`): stand = tailor `neckHeight` (the neck's base up to the jaw landmarks / the girth run) -
    13 mm in 20-35 mm, fall at CB = stand + 12, points 70 (Simon's collarBend solved on its own collar geometry).
    Garrett: neckHeight 29 -> 20 / 32 / 69.6 mm (Simon's table defaults gave 22 / 44 / 57); the test body 40 -> 27 /
    39 / 76. Every Simon shirt's pattern changed. A garment's own pattern options still win.
  - "STRAINED at waist 17.8%" (su_05) was not fit: the pieces' interiors stretch p95 1.5-2%; the worst triangles are
    the fronts' x~0 placket fold rows (0.3x across, 1.5-2.3x along). fit() leaves fold rows out like seam rings. Not
    yet re-read on a sim. The 12 mm front gape: the fastening pairs match in the flat (dy 0) and start 4 mm apart; read
    it on the next sim (the folded placket's layers + contact gaps, or closures.seat reverted).
  - Stage 4: pieces crossing where they are sewn / stitched (or a piece itself) warn instead of fail
    (`cloth_workflow.sewn_crossings`): ZOZO starts with existing intersections allowed and su_05 simulated clean from
    them. The shirt's start on su_garrett has back/sleeve, collar/stand, cuff laps crossing: pre-existing (the base
    17ee597 too), open. Its torso pieces still start as slabs (side seams ~125 mm apart).
  - Since then (sims tr_11..tr_14 on su_garrett; renders `cloth_renders/tr_1N_*`; scripts in the scratch dir:
    q.sh <queue> + run.py (renders draw the `collide` parts), pp_dbg.py <model> <garment> (cloth.build up to
    `_press_plan` from the cached coarse sim: each clearing / relax / untangle step's move, start stretch by piece,
    crossing pairs; stops before the GPU), pp_dbg3/4.py (where the fine start is stretched, edge lengths), sl.py <garment>
    (the mesh's shortest pattern edges), dumpfix.py (a piece + what it is sewn to as a flat-wrap fixture)):
    - Built: hem on the shoes (garment key `collide`: model parts joined to the collider, `cloth.worn_parts`);
      crease as a pressed ridge in the detail maps (`detail.crease_width`); clean-up clears faces off the body EXACTLY
      against its triangles (Body.clearance over-reads by up to 5.5 mm, p50 0.3: the "white specks" were body through
      the seat; a note, not changed); a closed zip's fastenings are its seam's sewn pairs (the fly read "0 of 0");
      clay looks matte (no specular); shirts open as worn without a tie (`kinds.shirt.wear` no_tie: collar `gap` 0.07,
      front open_top 1, plus folds "open neck.L/R": the fronts roll back from the neck to buttonhole2, angle 125);
      Simon's sleeve plackets sewn as zip closures; front.L wrap `out_reach` (the lap's offset eased to the plain curve
      away from the centre: the left-only open seam pairs were the lap pushed out over the whole front); shirt colour
      #d0cbc7 sampled from the concept; ZOZO stray-solver clearing (`cloth_job.clear_strays`,
      PPF_SOLVER_SCAN_DESCENDANTS: "solver is already running" was a host-wide process scan, a dead holder blocked
      every later job).
    - tr_13 trousers (2 cm + 1 cm fine settle): CORRUPT, back.L/back.R crossing at the crotch, CB seam 55 mm open, a hole
      behind the left knee; fly 18/18 closed; crease turn only 8 deg; hem not judgeable (no shoes drawn then). Cause,
      by step (pp_dbg.py): coarse sim clean (fork stretch 1.05), transfer clean (1.13), then `_press_plan`'s
      `_clear_of_body` ran away in the crotch's hollow (pushing along the body's normal there never clears the faces;
      the gap grew every round: 35, 80, 69 mm moves, untangle 62 more): 10.9x start stretch. Fixed: `_clear_of_body(
      grow=)` caps the gap's growth (CLEAR_GROW 4 mm, fine settle only: placement unchanged, coarse caches kept), and
      cloth further than FINE_REACH from the made pieces (carried, never solved) is only cleared FAR_CLEAR 1.2 mm off
      the body. Same coarse result re-planned: fork moves <= 3.3 mm, start 1.30 max, 0 crossings.
    - tr_14 shirt: "ccd failed", max_sigma 11.36: a 0.44 mm sliver edge where the open-neck roll's row passed 0.44 mm
      inside the front's outline at the neck point (and a buttonhole 0.54 mm beside the front band's row). `cloth.mesh`:
      a fold row's inner sample within ROW_KEEP 0.25 h of the outline is left out, one near ANOTHER fold's row is that
      row's vertex, a mark within 0.4 h of a fold row is the row's vertex. Shirt min edge 0.44 -> 2.51 mm. Fixture
      tests/data/simon_front_neck.json (pattern.from_spec takes "names": {name: outline index}).
    - `cloth.fine_start_check` (FINE_START_MAX 0.6): before the fine settle's job, draped triangles the solver moves
      stretched past 1.6x from the flat pattern raise, naming pieces and place: nothing is sent to the GPU.
    - fit(): trouser legs count as body pieces for the girths, a slice that caught only a band is skipped ("waist
      -555 mm"). cloth.look draws the collide parts (shoes) dark grey.
    - NEXT: tr_15 trousers + tr_16 shirt (queue q8.txt) with these fixes: judge crease (turn ~ 8 deg is soft: the
      fine settle only moves cloth within FINE_REACH of the waistband, so the crease at the knee is the 2 cm sim's),
      break on the shoes, the open collar V to the 2nd button, points on the collarbones, left seams closed, plackets.
      Not built: the stand's ends turning back with the open collar. Body.clearance's bias: before / after numbers on
      the shirt and blazer starts are owed before changing it.
    - Round 2 (2026-10-08; sims tr_15..tr_19, renders `cloth_renders/tr_1N_*`; scratch adds pp_dbg.py (+ cached_only),
      sep_dbg.py (stops at the fine-settle job: start separation), seat_dbg.py (what closures.seat's lap crosses),
      layergap.py, fleck.py / kink.py / flipped.py (surface defects by piece), foldmeas.py (band-passed luminance vs
      the worn-shirt photo), hem.py (hem heights front / back / out + along-leg compression), plt.py (trouser start:
      crossings, worn separation, hem), expshirt.py (one garment exported + asset.preview), lk.py (cloth.look saved)):
      - Fine-settle start (`_press_plan`): `_clear_of_body(grow=CLEAR_GROW)` (a gap grown round after round in the
        crotch's hollow sent fork tips 35-106 mm across the body), far cloth only FAR_CLEAR off the body,
        `_clear_of_held` (draped cloth back on the side of a made piece it lies on in the coarse drape, <= HELD_STEP
        a round), a made group laid in another shape than the coarse sim's (> MADE_SHAPE) keeps the coarse shape,
        `_untangle(reshape=True)` and crossings between held pieces ignored; the start cleared of the whole collider
        (shoes) with START_GAP, body offset <= 0.7 x the start's separation. `fine_start_check` (FINE_START_MAX 0.6)
        raises before the GPU: it caught tr_14, tr_16 and ga_suit's shirt.
      - Mesh: fold rows keep their samples except within ROW_END h of their ends (ROW_KEEP); a fold's flap is the
        cloth REACHED from beside its line (`folds._reached`: a collar's points turn with the fall); a mark next to
        a fold row is its vertex. Neck-piece folds are laid first; a front's roll goes under the collar's fall.
      - Shirt worn open (KB `kinds.shirt.wear`): collar gap 10 cm, fronts rolled 85 deg at strength 0.5 to button 2,
        the under front's roll ending 4 cm above the button (both met there and crossed). tr_16d: a soft V to button
        2, points on the collarbones.
      - Shirting fine folds ironed (`cloth_detail.FOLDS` fine_gain 0.45, density 0.6) by measure against
        cloth_refs/shirt_worn_front.png (1-4 / 4-15 mm luminance 0.33-0.44 photo, ours 0.60-0.83 -> 0.38-0.42).
      - Closures: seat lays the lap again after drawing the fastenings together, its crossings reverted ring by ring
        (su_garrett front 9.1 -> 4.8 mm). Clean-up `_unkink` (single-vertex buckles). Folds into the geometry go
        along `oriented_faces` (back.L wound inward had them pushed into the thigh). `folds.press_ridges`: pressed
        trouser creases sharpened in the geometry (PRESS_TURN 35 deg, the cloth beside flattened).
      - Trousers to a break: length "break" (KB default for suit trousers) = 30 mm over the floor, back BREAK_BACK
        12 mm longer; the start (`_hem_on_shoe`) hangs each column to the floor and stops it on what faces up under
        it (HEM_REST_NZ; su_garrett's shoe part stands round the ankle to 10 cm), the length gathered into the
        bottom LEG_BREAK 9 cm, kept WORN_CLEAR off the shoes (`_clear_of_worn`, also in the start relaxation).
        tr_19: fits, 0 crossings, hem 94 mm front (on the vamp) / 58 back, no ankle showing, one soft break, crease
        36 deg. Cut from the shoes' own heights it came out 5 cm short (tr_18): dropped.
      - Look-tool artefact (Overboard tooling card): textured EEVEE looks show pale grainy shards on cloth the
        exported GLB doesn't have; judge surfaces in clay or through asset.preview.
      - Left: back.L/R self-crossings in the trouser start where the hem gathers at the heel (the sim cleared them);
        the shirt's 24 open sewn pairs at the cuffs; suit trousers have no pockets.

- Placket (2026-10-08, "placket" agent, branch `worktree-agent-ab49e1b1d94e336bb`; the user: "We're really not getting
  the shirt placket right"; renders `cloth_renders/pk_*`, sheet `pk_05_placket_before_after.png` (before | after,
  textured + clay, beside cloth_refs/shirt_collar_worn.jpg); refs `cloth_refs/placket_*` (button macro, a placket with
  its button; refs.json); scratch DURABLE in /mnt/data/hifipushie/placket/: run.sh, fr.py <model> <garment> <tag>
  [clay|tex|both] (the CACHED result pickled in out/ after one 100 s load, relief + buttons + maps re-made with the
  code as it is: front band / open top close-ups, seconds), zb.py (one button close-up), mp.py (crops of the detail
  maps round the band), mk.py (closure marks vs edges in the pattern), bt.py (one button alone), sheet.py, fetch.py
  (Commons files + licences into cloth_refs), tests.sh).
  - Diagnosis: the PATTERN was right (front.L's edge 16 mm past CF, holes on CF, the band's inner line a vertex row
    at 30 mm; front.R a French front 10 mm past CF). What was missing was everything that shows: the band was a
    0.8 mm lift over one 1 cm triangle (invisible), the maps drew the front edge as a turned HEM (20 mm plateau, one
    row 6 mm in), buttonholes were thin outlined slots, buttons a dome on a rim (rivets), roughness 0.6.
  - Closure keys (closures.py, KEYS): `finish` {"over": box | french | facing | plain, "under": ...} (default box over,
    french under: a box placket's three layers proud with a crisp fold at the inner edge, the tuck's shadow, a row
    `topstitch` (default 3 mm, measured off the reference) in from each edge; French = a rounded fold only, no rows),
    `hole` auto | along | across (`closures.hole_axis`: along the closure edge where there is one: a placket's
    VERTICAL holes; on a piece closed on itself from the button toward the buttonhole: a cuff's run along it), `button`
    {holes 4|2, color, roughness 0.42, thickness 2.1 mm}. `resolve(pcs=)` stores each closure's edge polylines
    (`edge_xy`) in M["closures"]. These keys are construction LOOK only: in the design table they don't move the sim
    key; in a garment's own `closures` entry they would (g minus NOT_SIM is in the key).
  - Maps (`cloth._closure_bands` + detail_maps): each band from its edge (pattern polyline carried into the atlas,
    EDT), the free edge's hem / hem row suppressed inside bands, band rows a shirt's fine stitch (2 mm, 0.5 mm gaps),
    a `shadow` multiplier into the cavity (stitch dimples, the tuck, the slit: a white shirt's detail reads by shading,
    its thread is near white); buttonholes from the closures (size + 3 mm, a slit between rounded satin beads, bar
    tacks), not from mark names. Map buttons (export fallback) flat with a rim. Shirt atlas: 2880 texels/m.
  - Buttons (`closures.buttons_mesh` -> `_button`): flat sew-through, a low rounded rim, a dished middle, 4 sunk holes
    (2 = across the axis), the thread's two bars along the hole axis, ~510 triangles; on the cloth at the hole (raised
    over cloth standing above its plane within its radius: a roll starting at the 2nd button cut it in half);
    returns color / roughness and `mark` (the button mark: the export samples the button's texel there, not the
    hole's thread). Scene / look / render take the roughness.
  - Simon's table: front closure `finish` box / french explicit, `_doc_front` (the table cuts FreeSewing's seamless
    draft at placketFold1; the classic cut-on box draft's tuck takes back exactly the 2 x fold it adds, so the outline
    after turning is the same: no re-sim).
  - Read (pk_04 / pk_05): textured, the placket now reads as a box band with two rows, flat 4-hole buttons, vertical
    buttonholes showing above / below each button and on the rolled-back top. CLAY STILL SHOWS NO BAND: the crisp step
    is in the normal map only; the geometry is the 0.8 mm `relief` over one 1 cm triangle. Next if clay must show it:
    a post-sim split of the triangles crossing a line ~1.5 mm outside the band's inner row (render / export only;
    appended vertices so closures' vertex ids hold; M must follow: F, uv, piece, border), or a second fold row at
    mesh time (slivers next to 1 cm triangles: ZOZO's ccd failed on 0.44 mm edges once). Also open: the French front's
    soft line 18 mm in (the facing's edge; faint, maybe too visible), cuff buttons not judged by render, the button
    shading has a faint star in the dish (smooth normals across rim and middle), tests at 2048 texels only.
  - Tests: test_closures (+ test_a_box_placket_in_the_maps, test_flat_sew_through_buttons,
    test_a_cuffs_holes_run_along_the_cuff), the eleven cloth / pattern files + test_seams green.
  - Round 2 (same day; the user on su_77: "two buttons open when there should only be one, and there's still no
    placket", collar "not-quite-right"; sims pk_10..pk_29 on su_garrett's shirt, 3-5 min each on the rented 4090;
    renders `cloth_renders/pk_29_shirt*`, outfit framing `pk_30_outfit*.png`; scratch adds pls.py (the START round the
    neck + front start gaps), st.py (worst start triangles of the coarse mesh), sp.py / prof.py (band split + a section
    across the band), mem.py (peak memory by step), fig.py (cloth.look beside the concept), kbfold.py (the wear rule's
    roll angle / strength), resolve.py). su_77 itself was rendered before main had the placket merge (rivet buttons).
    - The band in the MESH (`closures.split_band_edges`, `press_band`, `relief`, in build after the seat;
      `cleanup.band_edges: false` turns it off): a vertex row split in 1.5 mm outside a box band's inner fold (interior
      edges only, new vertices APPENDED, every per-vertex array of M, its fold records and res extended by
      `closures.extend`), the band pressed flat across (the solver's lap sank 3-4 mm between its edges, deeper than any
      step: it read as a groove), lifted `BOX_LIFT` 1.5 x lift = 1.2 mm; what would cross the cloth is kept back
      (`band_kept_back`). Maps: the tuck's shadow and the folded edge's shoulder wider (survive the mip levels). The band
      now shows in clay and at outfit framing.
    - Wear rule (garment_kb kinds.shirt.wear.no_tie): only the COLLAR button open, every front button closed, the
      fronts rolled 95 deg / 0.5 from the neck to 2 cm above button 1 (over) / 6 cm (under): a roll line ending past
      the band's inner row crosses it at a shallow angle = a sliver (3.9x at frame 0: "ccd failed"; 3.1x: the fine
      start gate). Simon `extraTopButton` false (a button 4 cm under the neck that no closure counted).
    - `_spread_open_collar` (in `_place_folds`, after the neck pieces' folds; garment key `collar_spread` [out, down,
      from deg], default 25 / 12 / 75): the open stand and its collar swing out about a hinge up the neck's side and
      tip down, so the collar lies spread instead of standing as a ring (made = carried as placed). 40 / 20 / 70 pulled
      button 1's sides 36 mm apart with 33 crossings; collar gap 6 cm (instead of 10) made the fronts gape between
      buttons 1 and 2; stitch stiffness 8: 8.8 mm but 18 clean-up crossings and 4x the time. Rolls at 60 / 0.3 or 80:
      yoke 1.63x fine start / 16 crossings.
    - Finish by KIND: `kinds.<k>.closure` (shirt box / french, topstitch 3 mm; jacket and coat facing, hole across,
      topstitch 0) laid under lapped closures in cloth.pieces; rows at 0 are not drawn.
    - `closures.covered_buttons` / `button_texels`: the maps draw no button under a CLOSED lap (where the sides ended
      apart it peeked out beside the real one: the "second open button"); the export colours such a button from a
      drawn button's texel.
    - MEMORY: `_piece_crossings` used ONE search radius (the largest triangle's): su_garrett's trousers start made
      12+ GB of candidate pairs in a cached build (killed by the 12 GB guard; possibly the 17 GB process of the
      13:37 OOM). Now per-size: ordinary triangles through the tree in chunks, the few large ones one by one
      (trousers build peak 1.5 GB). The shirt's detail maps at 4096 peak 3.8 GB.
    - pk_29 (final, = pk_21's sim): fits, 0 crossings; front closure 7 of 7 closed but button 1's sides end 19 mm
      apart (!! in the report; buttons 2-7 2-5 mm): the open collar's stand ends (carried) hold the fronts' top
      corners apart and the solver's stitch gives. Seat's pull to 25 mm closed it but its crossings were reverted
      (SEAT_PULL stays 12 mm). OPEN: button 1 (a made top: carry the fronts' corners with the stand, or seat the
      fastening before the fine settle), a slit of skin beside the band under button 1, the V is shallow (the
      concept's opens ~10 cm), collar judged only on the shirt alone (the jacket over it is suit6's re-run).

- Garments from reference art (2026-10-08, "clothlist" agent, branch `worktree-agent-a32bca676fcdb7416`; the user: "a
  similar list for clothing features [as the face's likeness list]"; guide(topic="cloth_reference") =
  `cloth_reference_guide.md`: how tech designers (POM tables, HPS-based), tailors (proportion tells), costume
  designers (layer-by-layer breakdowns, wear state) and garment artists (silhouette -> fit -> construction -> layers ->
  fabric -> folds) read a garment, with sources). Scratch DURABLE in /mnt/data/hifipushie/clothlist/: run.sh <script>
  (this worktree's code, main workspace), cache1.py <model> (which garments have a cached sim with this code),
  dump.py <model> <garments> (cached results -> light npz + closures json in out/), grid.py / rows.py (read pixel
  points off a reference: gridded crops, backdrop row scans), garrett_read.py / garrett_check.py <tag> /
  garrett_brief.py (the Garrett proof).
  - `cloth_checklist.json`: 43 items, each {stage 1 silhouette+lengths .. 5 fabric+folds, kinds, what, view, region,
    type length | width | choice | count | bool | colour | level, anchor / points, measure, tolerance, sets}; choices
    come from garment_kb `details` (one vocabulary). Every hand correction made on Garrett's suit is an item
    (buttons_done, front_state, placket, collar_show / collar_hug / collar_state, belt, knee_width / leg_opening,
    sleeve_end / cuff_show, front_hang): `test_every_hand_correction_is_an_item`.
  - `cloth_reference.py`: `read` (the form, then the design-sheet patch + target table from answers; an orthographic
    front camera fitted to the model's body landmarks by similarity, `fit_camera`; lengths read ANCHORED: the fraction
    between two body landmarks, by HEIGHT ONLY when one is a body level (waist, crotch, floor: `_vertical`), carried
    onto our body; widths in m through the camera's scale; a reading taken on the right side compared on our left),
    `check` (MEASURES on cached sims or light npz results, never simulates; rows with the miss in tolerances, ranked
    by severity x stage weight x confidence; items the picture didn't show judged by the tailoring rule where there is
    one: collar show, cuff show, collar hug, tent), `render_front` (numba z-buffer of body + garments through the
    reference's camera, outer layers nudged forward by `over`), `focus_sheet`, `reference_brief` (shot list +
    per-shot prompts; wear state from the READING, never from the model's possibly wrong state) and
    `check_references` (which items a picture set supports and why not). MCP tools `garment_from_reference`,
    `check_garment_reference`, `garment_reference_brief`. Format of the brief proposed to the likeness agent.
  - Garrett proof (su_garrett, read-only; shirt / trousers cached, jacket = suit6's su_79 npz: its key moved with their
    code): reading `workspace/cloth_renders/cr_garrett_refs.json`, focus sheet `cr_05_focus.png`, whole figure through
    the concept's camera `cr_05_figure.png` (aligns within the camera's 40 mm landmark residual). Ranked: collar hug 27
    mm (rule 0-6), trouser rise 12 cm high (belt sits at the hip in the concept), jacket tent 85 mm, jacket 5 cm long,
    no pockets (concept: flaps + breast welt), belt hidden + shirt untucked (trousers not `over: shirt`), hem sweep
    -19% and waist -20% (concept's skirt flares over the hips), collar show -12 mm, lapel 95 vs ~71 mm, legs now ~10%
    NARROWER than the concept. Measure faults to know: chest width at the pit (+28%) reads the side panels round the
    armhole in A-pose (suspect), rise depends on the projected crotch / waist (hidden under the jacket), colour is lit
    vs albedo, trouser length depends on an ankle guessed in the shoe.
  - Missing measures (said in the check): gorge / notch height and button stance need pattern points / button centres
    a light result lacks; lapel lie needs the full result's fold rows; wear / ageing has no cloth pass; lapel width is
    the drafted op value, not measured on the sim.
  - `tests/test_cloth_reference.py` (12 tests, no sim).

- Suit 8 (2026-10-09, "suit8" agent, branch `worktree-agent-ab5c5e673a635ca9a`, continues suit7; placket's shirt branch
  merged in at 59be3f1; renders `cloth_renders/su8_*`, `om_2*`; scratch DURABLE in /mnt/data/hifipushie/suit8/: suit7's
  scripts retargeted (run.sh sets OPENBLAS_NUM_THREADS=1) + sec.py <start or result npz> [V] [shirt npz] (THE collar
  sections in mm: A centre back, B the neck's side, C the collar by |u| off the body / the under garment, the WING
  number, and R = columns along the shoulder's RIDGE: body | under garment's top | jacket's lowest cloth over what is
  under it), lay.sh <tag> <model> [key=json] (place-only start pickled, sections, a clay close-up of the CLOSED lay;
  lay1.py now saves X = the closed lay, Xopen, the carried idx and the under garment's pieces), dbg8.py <model> (where
  `_worn_top` put each front / back top, the collar's worn chart and chain, the closed start), pad8.py <tag> (the pad
  along the ridge and which shirt piece stands over each vertex), mv8.py <result> (collar moves start -> end by |u|,
  stretched triangles, the edges that folded most), lk9.py (garments drawn `worn_together` beside the concept, from the
  cache or a job's out.npz), sheet8.py (concept crop over rows of cu.py collar sheets), dm8.py (drafting measures bare
  vs over), mk8.py, ed8_tr.py, boxdf.sh (the GPU box's disk), after.sh <log> <queue>, patch_*.py).
  - THE WINGS, by measure. Along the shoulder's ridge beside the neck (pad8.py, su_om_garrett, the old shirt): the
    shirt's stand + fall stood 23-33 mm over the ridge out to x 90 mm, and `padded_body` raised the ridge 30-34 mm
    there and still 12-16 mm at x 100-110 (PAD_SLOPE spreads a pad 1 mm per mm); `_worn_top` slid the fronts' tops onto
    that ridge (neck point at z 1.542 where the shoulder is 1.50-1.52), the made collar went on top. Section B through
    the neck's axis is IN FRONT of the ridge on this square-shouldered body: read the ridge columns (R), not B.
    Three parts: (1) THE SHIRT (placket's: stand 9-13 mm off the neck, fall to |x| 83-88): with it alone the jacket's
    lowest cloth is +8..14 mm over what is under it at x 80-140 (was 30-45); (2) `pressed(fall=)` / `_fall_down`
    (garment key `under_fall`, UNDER_FALL 4 mm over the cap for worn tops, off for anything else: trousers' keys
    untouched): the under garment's collar FALL (the flap of a fold on a piece wrapped round the neck) pressed down
    along the body's normal where the body faces up (FALL_UP nz 0.25..0.6: shoulder tops, not the nape) past FALL_KEEP
    12 mm from its fold; (3) `padded_body(over=)` (garment key `pad_over`, PAD_OVER_WORN 1.1 for worn tops, 1.5
    otherwise): a garment point pads a body vertex only when it lies no more than 1.1 x its own distance to the body up
    that vertex's normal (a collar standing against the neck padded the shoulder under it). With all three: +6..11 mm.
  - om_20 (su_om_garrett jacket over placket's shirt, 2 cm, 107 s on the 4090): fits, collar_show 14.8, seams max
    1.4 mm, cuffs 18.5 / 18, lapel gap 7.3 / 4.7, no wings, clean back (su8_om20_collar_clay.png: drawn with the
    finished shirt, band + buttons, one open). Its collar ENDS (draped: below) crumpled at the hinge.
  - `collar_ends` (garment key; `_draped_ends`, `_open_share`; place keeps `end_w` / `end_u` per collar vertex in
    B["open_lay"]): "draped" (default) = from END_BACK 7 cm of neck edge before the roll line meets it (the neck's
    side) the collar is NOT carried: solved with the lapel, resting as made (the runner's rest for made pieces),
    cleared like draped cloth; "made" = the whole collar held; {"back": m}. Why: the fronts' tops move 14 mm from start
    to end (10 out, 4-8 down: an open jacket's fronts swing out) and a held end stays. Ends only (back 0, om_20): the
    ends follow, 60-95 deg folds at the hinge with the held band. From the neck's side, started OPEN with the band
    (om_22): lapel gap 5.7 / 7.0 (in band, first time), crossings 12 (made: 19), the notch reads from the front, BUT
    the freed fall stood up as flaps at both sides of the neck (nothing turns a free fall down but its own stiffness).
    Now the draped part starts CLOSED and the held band's opening eases out over END_EASE 5 cm before it, at the start
    and in every carried pose. NOT SIMULATED (the GPU box was deleted): first job when a box is up = `q.sh` with
    "om_23 su_om_garrett jacket", then mv8.py + cu.py collar + sheet8.py against om_21 / om_22.
    Sheet: cloth_renders/su8_collars_before_after.png (om_15 | om_21 made | om_22 draped-open, front / 3/4 / side /
    back beside the concept; the shirt there is the pressed stand-in).
  - front_hang 80 mm (om_15: 28), by measure (hang8.py <results> = each front's edge and how far it stands ahead of the
    body by height, KEY=X0 for the start; hang9.py = the same for the pressed shirt): it is the LEFT front alone. Right
    front 40-65 mm ahead of the body from waist to hem in om_15 and om_20-22 alike (plumb from the chest); left front
    85-130 mm in om_20 / 21 / 22 (om_15: 44-65), its edge at x +50..+70, y 5 cm further forward than the right's: swung
    out like a door. NOT the start (om_15's and om_21's starts are the same and symmetric but for the lap) and NOT the
    shirt holding it out (pressed shirt 5-11 mm ahead of the body both sides). What changed: over the hugging shirt the
    fronts end 6-12 cm APART (om_15: nearly closed, edges x -7 / +4, the left lying on the right); freed of the right
    front the over side swings. Untested guesses: the left lapel's roll (the over side's lap adds a layer under it), the
    left collar end; test with a symmetric start (the over front's lap offset 0 when the front closure is worn open).
  - Trousers: `over_measures` tapes the HIPS over the tucked tail too, and the seat by half the hips' share when the
    tail ends above the seat line (hips alone made a dropped waist wider than the seat's quarter allows: band 8 mm
    short of the girth it sits on, stage 2). su_om_garrett's trousers: leg "tapered", no seat_ease override (gates
    pass: band +0.8 mm, seat +4.7% over 970 mm; start clean: stretch 0.038, band closed). NOT SIMULATED.
  - The GPU box's disk: `GPU_MIN_FREE_GB` (gpubox/env.sh) -> remote.sh sets the runner's floor on the BOX's copy
    (cloth_zozo.py itself untouched: its hash is in every ZOZO sim's cache key). On main as 75cdc09.
  - cloth.look did not find the jacket run.py had just cached ("not simulated (idle)"): not traced (lk9.py passes the
    job's out.npz as `result=` instead). Check with om_23: build twice, compare keys (place() bit-for-bit?).
  - Main's shirt (before placket's branch) fails fine_start_check on su_om_garrett (83 triangles over 1.6x at the
    fronts' tops): scratch model `su8_g` = shirt fine_settle false. Not needed once the shirt branch is on main.
  - Tests: tests/test_suit8.py (fall pressed on the shoulder not the nape, draped collar vertices, the open share,
    key defaults).
  - om_23 (the draped part started CLOSED, the band's opening eased out before it) DIED in the solver at frame 0-1:
    "2 block-Jacobi diagonal block(s) are not positive definite" with the strain limit's step at 2e-5 (log
    suit8/om_23.log; job workspace/_cache/cloth/job_7740081fdabcf726). Not diagnosed (suspects: the eased band's start
    is a blend of the open and closed lays = not the made rest's shape beside free cloth that rests as made; check
    jobstr.py on that job's in.npz). `COLLAR_ENDS` is back to "made" (om_21's behaviour, verified); "draped" stays as
    an experimental key value.
  - Queue q210's end (2026-10-09): om_24 (su_om_garrett trousers, tapered, seat taped over the tucked tail, 1627 s):
    0 crossings, seams closed (sim p95 3.3 mm), fly 9 of 9, still "STRAINED at seat" (seat +94 mm 13.7%, hips 6.6%;
    strain p95 3.5%): the seat strain did not go with the tape; not rendered or judged. po_10 / po_11 (su_om_pose)
    never reached the GPU: the pose model's SHIRT fails `fine_start_check` (11 triangles over 1.6x, worst 2.15x,
    front.L pattern [-0.014, -0.156]): shirt2's thread; nothing layered runs on su_om_pose until it builds.
  - HANDOVER (suit8, context near full, 2026-10-09). Branch worktree-agent-ab5c5e673a635ca9a. NOT merged: the
    coordinator's order is shirt2's branch -> main, merge main here, verify, then this branch. A new GPU box is up
    (gpubox/env.sh; solver installed by suit8/boxsetup.sh; deleted after 45 idle minutes). RUNNING when written:
    `q.sh q210.txt` = om_23 (su_om_garrett jacket, the draped collar started closed), om_24 (su_om_garrett trousers:
    tapered, seat taped over the tail), po_10 (su_om_pose jacket: mk_pose.py 45 re-made the model from the current
    su_om_garrett; builds its shirt first), po_11 (su_om_pose trousers); logs suit8/<tag>.log end "DONE rc", arrays
    out/<tag>.npz (with the pressed shirt as U), renders cloth_renders/<tag>*.png. TO JUDGE, in order: om_23:
    `run.sh cu.py out/om_23.npz out/om23_c.png 0,-0.04,1.50 0.17 collar`, sheet8.py with om_21 / om_22 rows (flaps
    behind the neck gone? notch? crossings < 12? lapel gap <= 7?), mv8.py, hang8.py; if flaps or crumple remain set
    COLLAR_ENDS back to "made". Then the symmetric-start test for the left front (NOT written: in place() the over
    front's lap offset = the `lay_` / LAYER ramp + wrap "out" of front.L; make it 0 when the front closure's state is
    open, one sim, hang8.py). om_24: report + check.py (leg opening, length, seat strain). po_10 / po_11: hang8.py
    (fronts apart 12-15 cm at the waist), then the outfit sheet `run.sh lk9.py su_om_pose <png> - 0 front,three all`
    (cached garments; pass jacket=<job out.npz> if the cache misses) beside the concept, clay and `tex`.
  - NEXT, in order: (1) om_23 (above); if the notch still crumples, look at the collar ends' rest (made = the lay's
    plane on the START's chest) vs the flat pattern (`zozo.rest_flat` for the draped part only); (2) the right neck
    seam's open pairs (5-9 of 17, <= 2.3 mm after the clean-up, sim max 4-7 mm); (3) collar_hug 17 (the tell reads
    the jacket collar off the SHIRT collar behind the neck: shirt stand 11-18 mm off the nape + the jacket's own lay
    23-35 mm off the body at CB: lower by seating the jacket's stand against the shirt's, `_lift_made` lifts it to the
    pad + 3 mm); (4) trousers om_24 (su_om_garrett trousers) then check.py; belt + loops in the figure (lk9.py draws
    cloth_trims.meshes); pockets (su_om_pk); (5) su_om_pose: re-run mk_pose.py 45 from the current su_om_garrett, then
    shirt + jacket + trousers there, the outfit sheet (lk9.py su_om_pose <png> - 0 front,three all) beside the concept;
    (6) the head: mk_om.py NOHEADFIT=0 (om_garrett's base is on main), hair locks if cheap. shirt2 (the shirt's new
    owner) will change every settle garment's coarse key (`made_from`): re-run after its merge.

<!-- additions on worktree-agent-ab5c5e673a635ca9a to: - Placket (2026-10-08, "placket" agent, branch `worktree-agent-ab49e1b1d94e336bb`; the user: "We're really not -->
  - Round 3 (2026-10-08/09, same agent; sims pk_31..pk_46; scratch adds plsec.sh <tag> <gap> <spread> (start: centre-
    front gap + stand sections), sec.py <npz> [key] (centre back / neck's side: skin | stand | fall in mm), thr.py
    <tag> [V|Vsim|X0] (throat close-up, pieces coloured), jb2.py <job dir> (exact start distance cloth -> collider),
    shw7.py (run through suit7's run.sh: its cached shirt + a saved jacket surface drawn by my rule)).
    - Button 1 (19 mm open) was GEOMETRY, not the solver: the made stand's centre-front points (button to
      buttonhole) started 167 mm apart (gap 0.10 + spread 25: the swing adds ~4 mm a degree), and a front's neck
      corner lies 31 mm from its roll line, so the corners can part by ~5.3 cm x (1 - cos roll) at most. Fix =
      consistent numbers + `kinds.shirt.worn_top` (the fronts' tops start on the body, neck seam pinned to the
      stand: start gap 95 -> 2 mm; this is fix (a): the fronts' corners start AT the stand; no made flap needed).
      pk_36 (gap 0.05, spread 12/14/75): button 1 3.0 mm, 0 crossings, V open to button 1, no skin slit. Gap 0.02:
      the ends met and tangled with the collar's (pk_35). A worn start on the bare body needs `_clear_exact`.
    - Hug (suit7 / suit8: the jacket collar rode up over the shirt collar's wing): `gap` is laid round the neck, 1.6
      mm of radius a cm. Defaults now gap 0.008 + COLLAR_SPREAD (18, 14, 65): start stand ~10 mm off the skin (the
      buttoned stand's own number by nearest body vertex), centre-front points 80 mm, fall 6 mm wider than the
      stand at the neck's side. `_spread_open_collar` sides by pattern half (lapping ends crossed). SIMS OF THESE
      DEFAULTS: pk_44_om (su_om_garrett), pk_45_shirt (su_garrett), pk_46_gashirt (ga_suit): read their logs.
    - `cloth_layers.tucked` + `cloth.worn_together` (in `garments()`, `look`, `cloth_reference.render_front`):
      the under garment's finished surface, covered cloth laid 4 mm under the outer's inner face. Covered = outer
      cloth along the body's normal from the vertex (TUCK_SIDE 1 cm), or the vertex outside the outer face within
      3 cm. Dead ends: "projects inside a triangle" (fails outside convex sleeves), "not near an open edge" (pulled
      the chest in the V under the lapels). Proof pk_43 / pk_47 (`_front_tex`, `_whole_tex`) vs om_13_jacket_front_tex.
      Left: shards at the jacket's armpits (its own open pit seams show the shirt), layer crossings 3823 -> ~400.
      `cloth.button_color`, kind closure `size` / `button` (jacket 20 mm, tone 0.55). Not done: band edge lines in
      the reference figure; the tucked surface in `cloth_layers.tells` (still the pressed one).

<!-- additions on worktree-agent-aadad0f70eefaeafd to: - Placket (2026-10-08, "placket" agent, branch `worktree-agent-ab49e1b1d94e336bb`; the user: "We're really not -->
      mm of radius a cm. Defaults now gap 0.03 (0.008 built on su_garrett / su_om_garrett, button 1 2.0 mm, stand 9-11 mm off the skin, but ga_suit's fine settle died: collar end 2.98x at the start, lapped ends; 0.03 builds there, pk_49) + COLLAR_SPREAD (18, 14, 65): start stand ~10 mm off the skin (the
    - HANDOVER (placket, 2026-10-09, context full; branch worktree-agent-ab49e1b1d94e336bb, NOT mergeable as asked).
      The shirt's fine-settle START is fragile round the open neck and no collar gap builds on all three models:
      gap 0.008: su_garrett fits (pk_45: button 1 2.0 mm, 0 crossings), su_om_garrett builds (pk_44_om: 2.0 mm, stand
      9-11 mm off the skin, fall to |x| 83 / 88), ga_suit FAILS (pk_46: fine start collar 2.98x at pattern x -0.2,
      ccd failed). gap 0.03 (committed default): su_om_garrett builds (pk_51_om: button 1 2.7 mm, stand 10.6 / 12.6-13
      mm off the skin, fall to |x| 86 / 93, 17-18 mm over the shoulder, collar 5% crumpled = verdict CORRUPT, the
      wearer's-left collar point curls), ga_suit builds as a garment override (pk_49: 2.2 mm, 0 crossings; the KB run
      pk_53 died on the GPU box's disk, not on the shirt), su_garrett REFUSED by fine_start_check (pk_52: front.L
      11.5x at pattern [0.014, -0.12]: the over front's band just under the roll's end). The coarse sims are fine
      in every case: the fault is in `_press_plan` / `_constructed` (the made collar "made_reshaped" 9.8 mm: the
      fine placement's spread differs from the coarse one's and the collar takes the coarse shape by transfer; then
      `_clear_of_held` / `_untangle` round the roll's end). Next: make the spread identical at both mesh sizes
      (compute hinge, centre, radius once from the pattern + neck, not from each mesh's stand vertices), then look at
      the 11.5x triangle with pp_dbg.py (trousers2's scratch). Tools: jb3.py <job dir> (start edges vs flat by piece).

- Shirt 2 (2026-10-09, "shirt2" agent, branch `worktree-agent-aadad0f70eefaeafd`, takes over from placket; renders
  `cloth_renders/s2_*`; scratch DURABLE in /mnt/data/hifipushie/shirt2/: placket's scripts retargeted + env.sh (main's
  remote.sh through gpubox/env.sh; when the box does not answer the remote is nobox.sh, which FAILS: nothing runs
  locally unless LOCAL_ZOZO=1), q.sh <queue> (run.py sims: log <tag>.log, arrays out/<tag>.npz), qs.sh <script.py>
  <queue> (any script over queue lines, logs out/<script>_<tag>.log), pl.py <model> <garment> <tag> [key=json]
  (place only, ~8 min under load: made pieces fine vs their coarse copy, coarse start stretch / crossings, closure and
  neck seam start gaps; saves out/pl_<tag>.npz coarse and plf_<tag>.npz fine), fs.py (the fine settle's START step by
  step from a CACHED coarse sim, no GPU: stretch by piece after each clearing step, gate, made start vs rest; STEPS=1),
  sec.py <npz> [V|X0] (stand / fall sections in mm), bodycmp.py a.npz b.npz (did the body move between two results),
  sh7.sh <tag> [SH_NOFOLD=1 SH_NOMAPS=normal SH_NOBODY=1 SH_THICK=0 SH_NOJACKET=1] (the under garment drawn finished
  under suit7's cached om_15 jacket, front close-up, ~4 min), fleck.py <tucked npz> [zmax] (sharp edges in the visible
  front), tk.py (tucked shirt vs the body), box.sh ['cmd'] (the GPU box: disk, jobs, GPU), t1.py <test file> <tests>,
  tests.sh (the thirteen cloth files: + test_cloth_reference, test_suit7), q4.txt = the seven sims still owed).
  - Merge: placket's branch into main's head; conflicts in cloth_reference.render_front (worn parts AND the finished
    under garment + buttons: both kept) and the KB's jacket kind (button defaults + the relaxed fit band).
  - THE FINE START, the cause: the made pieces were constructed TWICE, once per mesh size (place() on the 2 cm mesh
    for the coarse sim, again on the 1 cm mesh for the result), and the two differed: a fall turns "as far as clears
    what is under it" and what is under it is sampled by the mesh; the fold's wedge and the neck layer are functions
    of the mesh size; the spread hinges on the stand's own vertices. Collar p90 8-10 mm on the Garretts, 38 mm on
    ga_suit. `_press_plan` then either set a collar the drape wasn't solved round, or (over MADE_SHAPE) took the
    coarse sim's faceted collar carried onto the fine mesh as the made shape AND its rest, cleared its layers apart
    vertex by vertex and opened the flap station by station (-70 .. 0 deg): made pieces 160-640% off their rest, fronts
    pushed 3-11x round the roll's end. Which of those a body got flipped with 2 cm of collar gap.
    Now ONE construction (`build`: garment key `made_from`, default "fine"; "each" = the old two): the fine mesh is
    placed FIRST, the coarse placement takes its made pieces as a sampled copy (`transfer(M_f, X0_f, Ms)`; place():
    `B["_made_as"]` {pieces, X, U}; `_place_folds(made=)` lays the copy once the neck pieces' folds and spread are
    made, BEFORE the body pieces' flaps turn, and doesn't turn a given piece's fold again; laid again at the end of
    place() after the pushes; `start_unpushed` takes the fine one's too). Carried back onto the fine mesh the copy is
    the construction within the coarse facets' chords (collar p50 0.4 / p90 3.7 mm at the roll; MADE_SHAPE is 8).
    EVERY settle garment with made pieces has a new coarse sim key (jackets and trousers too).
    Test tests/test_folds.py::test_made_pieces_are_one_construction_at_both_sizes.
  - Default open collar gap 0.008 (garment_kb kinds.shirt.wear.no_tie; the coordinator's choice: Garrett is the goal).
  - Results at 0.008 (4090): su_garrett s2_11: fits, 0 crossings (2 at the cuffs' own laps), nothing crumpled, button
    1 2.0 mm, fine start stretch 32% (placket's same gap: 157%), made pieces 85% off rest (179%), no made_reshaped,
    876 s. su_om_garrett s2_12: fits, nothing crumpled (placket: CORRUPT, collar 4-5%), button 1 2.2 mm, fine start
    54% (gate 60%: thin margin), 1248 s; s2_12_om_collar.png = a clean symmetric open collar, both points down
    (pk_51_om_collar.png: the wearer's-left wing crumpled). ga_suit and the 0.02 / 0.03 margin runs: NOT RUN (two GPU
    boxes died under the queue): `bash q.sh q4.txt`.
  - Collar as worn (sec.py, su_om_garrett s2_12, mm): stand off the skin 15.7 at centre back, 13-15 at the neck's
    sides; a BUTTONED stand on the same body by the same measure (place only, tie=true): 12.9 / 6-7, so the open one
    is +3 / +7. Fall to |x| 87-88 (inside the jacket's neck point at 94), 14-17 mm over the BODY's shoulder under
    it, 6 mm (median) over the shirt cloth under it. su_om_garrett's body MOVED since placket's runs (bodycmp.py: neck
    zone 3.2 mm median, the one-mesh neck change on main): placket's 9-11 mm was the same stand on a fuller nape. A
    buttoned stand on the new body starts 20.8 mm OPEN (place only): band_short there, not looked into.
  - Still in the start, not fixed: the fine PLACEMENT itself has the collar's fall through both fronts' rolled tops
    (69 + 61 crossing pairs), collar / yoke 32, front.L / front.R 122 on su_garrett, the same before this change;
    `_press_plan`'s untangle ends with 41-84 crossing vertices it can't clear (the collar is held). The under front's
    open-neck roll turns 17.7 deg where the over one turns 85 (blocked by the collar's fall): asymmetric by
    construction.
  - Tucked under garment (`cloth_layers.tucked`): covered is taken by the majority of a vertex's neighbours (single
    vertices flipped at an opening's edge), the move falls off over TUCK_FEATHER 5 rings x TUCK_FALL 0.6, a covered
    vertex moves no less than TUCK_EVEN 0.7 x its neighbours' mean. Layer crossings 486 -> 351 on suit7's om_15 pair.
    The PALE FLECKS on the shirt beside the lapel (pk_43) are NOT this: they stay with the normal map off, fine folds
    off, the body out, thickness 0 (s2_b..s2_e) and there is no sharp edge there in the geometry (fleck.py: the only
    sharp edges under the neck are the band's own fold rows). They only show with the jacket over the shirt and lie
    in the lapel's shadow: read as the textured EEVEE look's light leak (the Overboard tooling card), not proven.
  - NOT DONE: ga_suit + margins (q4.txt); the open stand as a hug band (HUG_CLEAR instead of SMOOTH_CLEAR + 0.5 mm:
    3.3 mm of the +3 / +7); band edge lines in cloth_reference.render_front; the jacket drawn with its 20 mm buttons
    (needs a jacket sim on this code: suit8's); export_part / scene sync with the tucked surface checked on a cached
    pair; the lumpy yoke seen from the side in s2_12.

## Made pieces constructed after the drape (2026-10-09, "collarbuild" agent, branch `worktree-agent-a5a0bbd568c7f3c68`; a SPIKE)

The user after ten collar rounds: "Do we need a different tack? Less simulation, more hand-editing?"; the coordinator:
simulate the garment's body, BUILD the collar onto the finished neckline; then the user: "that same principle probably
applies to other parts of clothing". suit8's branch is merged in here. Sheet `workspace/cloth_renders/
cb_01_constructed_vs_sim.png` (concept | simulated om_21 | constructed on the same sim; front, three-quarter, side,
back). Scratch DURABLE in /mnt/data/hifipushie/collarbuild/: run.sh <script> (this worktree's code, capped), run8.sh
(the same with the suit8 worktree's SOURCE first on the path: its cache keys; this worktree's own code found neither
garment cached), dump.py su_om_garrett jacket=<job out.npz> (cached shirt + a job's jacket -> out/su_om_garrett.pkl:
arrays, sew pairs, folds, the shirt as worn; 24 min at load 80, almost all of it cloth.build), jk.py <tag>
[shirt.k=v] [jacket.k=v] [nojacket] [hl] [zoom] [nolapel] [sheet] (both collars + pressed lapels built on the pickle,
tells of both, strips; 17 s), sc.py (shirt collar alone on any saved shirt npz), dbg.py / dbg2.py (a part's rows at
stations; the fall against the shirt's cloth), t.py (the tests), patch*.py / append.py (edits as scripts).
NO SIM WAS RUN.


- cloth10 (2026-10-09, "cloth10" agent, branch `worktree-agent-a7cfe1a69c368b0db`; replaces suit9, shirt2, collarbuild2).
  Scratch DURABLE in /mnt/data/hifipushie/cloth10/: env.sh (sims ONLY remote: box from $BOXENV or gpubox/env.sh, no
  answer -> nobox.sh fails; BROKER=1 -> have.sh hands back results/<job_key>_<mode>/out.npz, else writes the job and
  stops), run.sh <script> (capped, $G on PYTHONPATH, peak RSS), q.sh <queue> + run.py (shirt2's), pl.py (place only),
  check.py <tag> <jacket> [trousers] [shirt] [model] (checklist + figure), runcb.sh jk.py <tag> (collarbuild's
  constructed collars on its pickle, this code), vram.sh [peak] (box nvidia-smi log), tests.sh (15 cloth files),
  broker_test/ (the broker's first real batch: 2 known-good jobs from s2_11 + om / pose shirt coarse jobs, README).
  - Step 0: the three branches merged (main fa9538b). Their uncommitted worktree edits were committed here as WIP
    commits (an isolated agent can't run git in another worktree); their worktrees are still dirty, deletable now.
    test_cloth_layers' tucked-opening assert loosened 1e-9 -> 1e-6 m (failed on shirt2's own branch: the 5-ring feather).
  - Baseline checklist (om_21 jacket + s2_12 shirt + om_24 trousers on su_om_garrett, cr_c10_base_*): collar_hug 17.4
    mm, front_hang 80 mm, hem_sweep -21%, no pockets, shoulders +9%, trousers 23 mm short, rise +20 mm; the shirt
    within tolerance everywhere visible; button 1 2-3 mm (the old 19 mm is gone).
  - Constructed collars on that pair (jk.py, 8 s): notch + pressed lapels crisp (lapel gap 3 mm vs 6.8 simulated),
    but the jacket collar flares as wings beside the neck, shirt cloth pokes through the left lapel, the constructed
    shirt collar reads as thin edges with gaps (out/c10_j1_front.png).
  - su_om_pose shirt place-only: fronts start up to 2.03x stretched (front.R at the hem and the neck's CF), 159 coarse
    start crossings; may fail in the solver.
  - Batching limit: a garment is coarse sim -> fine settle -> (outer garment over its finished result); each job
    exists only after the previous result, so one broker batch per stage, or a live box driving q1.txt.
  - Constructed collar geometry on the cached pair (no sims; c10con.py = the PRODUCTION cloth_made.construct with
    collar on the collarbuild pickle, over a constructed shirt collar; c10jk.py = collarbuild's round-1 harness +
    `diag` (c10diag.py: per-station distances seam/stand/edge to shirt collar, shirt body, neck; shirt points over the
    lapels)). Sheet `cloth_renders/c10_j2_front.png` (simulated | constructed before | after).
    - WINGS / hug: the collar build was not the cause. At centre back the simulated jacket NECKLINE lay 16-19 mm off
      the shirt collar (1.7 mm over the shirt's yoke, below the shirt collar's fall) and 20-40 mm off the neck at its
      sides, so any collar built on it stood off. `hug_neckline` (construct key `hug`, on with collar + an under
      garment): the collar's ease drawing the neckline to `gap` 3 mm off the under COLLAR (nearest point, not along
      a normal: beside the stand's foot no surface lies under the seam along one and centre back moved 0), weight 0
      on the gorge, max pull 20 mm, the cloth within 12 cm following (IDW of the 4 nearest seam moves, smoothstep),
      then kept clear of the whole under garment. Pulling to the nearest layer of the WHOLE shirt did nothing at CB
      (the yoke is right under the seam). Numbers (checklist's measure): collar_hug 15.4 -> 9.1 mm, collar_show 20.2 ->
      10.0 mm, seam pull p50 7.4 / max 16.6 mm, neck-zone stretch p95 1.04 -> 1.08. Pulling the gorge too (gorge=1):
      stretch max 2.37, collar x jacket 17 crossings, rejected; gorge 0.4: no visible gain.
      The rest of hug's 9 mm is the fall's lower rows over the jacket (by design further out); 0-6 needs the
      jacket's back neck higher (pattern/drape), not construction.
      What still reads as a wing: the notch sits at the shoulder top (roll meets the seam 167 mm from CB), so the
      collar end and lapel point lie across the shoulder: pattern (gorge_angle, collarbuild's pattern_styles key),
      needs a sim.
    - SHIRT THROUGH THE LEFT LAPEL: pressed onto its forepart, the lapel's top by the gorge went UNDER the shirt's
      neckline corner (12-33 shirt points over the lapel face, up to 19 mm). Construct key `over_under` (default on
      with an under garment): the pressed flap lifted out over the under garment, both as the flap sees it (shirt
      points over its outer face lift that face's corners: the shirt's neckline EDGE is no surface a settle can see)
      and as a settle sees it, eased over 2 cm. 0 shirt points over either lapel; jacket x shirt crossings 235 -> 264
      (most from the sim, sleeves). Plus the shirt laid under the jacket AS CONSTRUCTED (tucked against the pressed
      jacket, not the simulated one): production already does this (worn_together runs on res["V"] after construct).
    - SHIRT COLLAR: thickness 1.6 -> 2.4 mm (SHIRT default; two plies + interlining) reads as a collar not a sheet.
      The fall's points still hang as twisted ribbons at the open front: drawing them down (fall_hug 7-15 mm) pulled
      them onto the SKIN under the shirt front (now `nohug` layers: kept clear of, never drawn onto); with that, the
      points shrank to crumples by the stand's ends. NOT FIXED: the points need laying on the shirt front as a board
      (like the notched collar's ends), not marched.
    - Tests: test_cloth_made::test_hug_neckline_draws_the_seam_to_what_is_under_it.
  - Round 2 (shirt collar points, flecks, gorge job):
    - The "twisted ribbons" at the shirt's open front were NOT the collar: highlighted (c10jk.py `hl`), they are the
      shirt FRONTS' top corners, the simulated "open neck.L/R" roll flaps standing up; the constructed fall's points
      lay buried under them. construct key `press` (fold-name prefixes, default ["lapel"]): ["open neck"] presses
      them flat like lapels (front.L 77 vertices 9 mm, front.R only 7: the known asymmetric roll). Then
      `lay_points_on_front` lays the fall's rows past the stand on the FRONT's pattern as a board (on_pattern; from
      the neck edge at the column's station, into the front by what is left of the row, turned by the column's
      angle), kept `lay` over the shirt; blended in over u 0.45-0.85. c10_s8 (pressneck + board): ribbons gone,
      points visible lying on the fronts; collar x shirt crossings 9, x its stand 2; fall stretch p95 1.26 max 3.4.
      Points read short (end near the neckline). Laying the tails on the nearest cloth instead (tried first): stretch
      max 5.7, bunched by the stand's ends.
    - The white flecks at the left chest / armholes in c10_j2's after column are in the SIMULATED pair already
      (flecks.py: raw om_21 + worn shirt 43 shirt vertices out through the jacket; constructed 34, the same armhole
      clusters at |x| 0.17-0.21, z 1.21-1.32, plus 6-8 at the left lapel's top). Not from hug / over_under. Cause
      (fleckprobe.py): at the armpit tucked's "out" (away from the nearest body vertex) disagrees with the faces' own
      winding, so they count as tucked 4 mm in; others sit over the jacket's unwelded seams (nearest point on a
      piece's edge: `ins` false). Tried in tucked: pokes exempt from the neighbour vote (34 -> 32), pokes over seams
      (crossings 268 -> 349): both reverted. The +29 jacket x shirt crossings come with over_under's lift.
    - gorge_angle job: q1.txt c10_j3 = the jacket with op:lapel gorge_drop removed, gorge_angle 55 (run.py takes
      op:<op>.<field>=json); every jacket job now has construct={"collar": true} (post-sim, no key change).
      Drafted (draftchk.py, no sim): gorge_angle 55 passes design/pattern/construction; its lapel point is 45 mm below
      the HPS (gorge_drop 0.12 had it 120 mm: the 33 deg gorge ran down the chest with the collar end a strap beside it,
      the "wing"). A steeper gorge is a real notch HIGHER up; c10_j4 = gorge_angle 45 as the in-between.
  - Round 3, the "goofed up" shirt (Joe on c10_s9). c10steps.py, one change per panel (c10_dbg_steps.png, jacket
    hidden): (a) the cached sim alone is clean, its SIMULATED collar reads better than any constructed one; (b) the
    tuck under the jacket makes the facets / shards (chest moved p95 12.5, max 48 mm onto the jacket's lumpy inner
    face: hidden when the jacket is drawn); (c) the open-neck press cut the V (front.R's "flap" 7 vertices moved 44 mm:
    the smaller-side rule on a weak roll); (d) the constructed stand reads tall and tube-like, its end slabs stacked.
    RENDER RULE (also in the guide): a tucked garment is never drawn without the garment over it; show the untucked
    under garment alone, or the tucked one with the outer garment on; gate every sheet in both views (no facets,
    tears, shards). Decisions: the shirt keeps its simulated collar; the open-neck press stays OFF (construct `press`
    default ["lapel"], other prefixes documented EXPERIMENTAL, tested); lay_points_on_front deleted; the constructed
    collar is for the jacket only.
  - Underarm holes (c10_w3 = jacket on, front + three-quarter, NOT clean): the jacket alone has none (c10_w4j); they
    are the SHIRT through the jacket's side / under-sleeve panels in the armpits (underarm.py: ~100 crossing points a
    side at |x| 0.18-0.23, z 1.20-1.33; untucked shirt x jacket 3615 crossings, worn 408, welded tuck 258 points).
    Tried and reverted: pokes always tucked with the oriented normals (underarm 99 -> 131); a crossing-driven
    untangle pushing shirt vertices in along the body normal (crossings 152 -> 88 vertices, but the shirt then stuck
    OUT sideways under the arms: the armpit body normal points sideways). Next: decide coverage there from the
    jacket (shirt inside the jacket's armhole loop = covered) or give the shirt sleeve-head more room in the sim.
    (a) tried (coordinator's pick): a crossing pass after the tuck laying what still crosses `gap` behind the
    jacket along ITS inward normal (welded, piece-wound), 8 rounds: crossings 229 -> 223, underarm points 99/81 ->
    108/100, white shirt still out at both armpits (c10_w4 views front / three / pitL / pitR). The shirt there is
    wedged between the side panel and the under-sleeve with no room: pushed behind one panel it crosses the other.
    Reverted. A geometry pass can't clear it: the shirt needs underarm / sleeve-head room in the SIM (GPU queue).
  - Round 4, the SHIP layering (Joe: s2_12 "at one point you had the shirt like perfect" = the target). c10ship.py:
    shirt = s2_12 drawn exactly as simulated, jacket constructed over it, shirt faces the jacket covers CUT
    (cloth_layers.hidden, margin 3 cm), not tucked. On the CACHED om_21 jacket it fails: that jacket was simulated over
    another shirt (the pickle's, p50 3 / max 95 mm from s2_12), s2_12 is fuller, 1803 crossings of the visible shirt
    with the jacket (c10_w5.png: shirt through the jacket's chest and sleeves). The jacket has to be simulated over
    s2_12 itself. This code no longer meshes the shirt as s2_12 did (13123 vs 13284 vertices, key f7ab... vs a441...):
    run.py `under_pin=<npz>` builds the under garment place-only and puts the pinned shape on it through the pattern
    (pinmap.carry, per piece barycentric in uv; miss 0.0 mm), key pin_<hash>. q1.txt = the jackets (as is, gorge 55,
    gorge 45, open_lap false) and trousers over pinned s2_12; q_optional.txt = a dress-shirt trim (armholeDepthFactor
    0.52, bicepsEase 0.10, sleevecapEase 0, chestEase 0.10) + the pose shirt, only if it beats s2_12.
  - GPU fleet (oxidegen bundle jobs, live 2026-10-09): HIFIPUSHIE_GPU=bundle -> spikes/gpu_cloth/bundle.sh (one job =
    one batch, this checkout's cloth_zozo.py as runner, waits, leaves out.npz; token from OXIDEGEN_TOKEN or
    /mnt/data/hifipushie/gpubox/oxidegen_token). First test batch 4/4, $0.10, peak VRAM 1.3 GB, the pose shirt did not
    fail (78 s). known_good_sim: same in.npz and runner, seam gaps 2.9 / 8.5 mm vs 2.8 / 8.0 originally, vertices p50
    1.4 / p95 4.9 mm from the original result; its fine settle p95 0.1 mm: solver nondeterminism, not code.
  - Round 5 (gate + trace). c10ship.py PIXEL GATE: body drawn magenta, new skin pixels worn vs s2_12 alone from 8
    cameras (5 wide, 3 collar close-up); the cut at the neck opened 210 px (between shirt and jacket collars) -> never
    cut within 5 cm of the shirt collar: 0 px, PASS (c10_w7, j6). Jacket selection: only under_cap 0.035 (j6) / 0.02
    (j5) lie outside s2_12 at the lapels; j6 chest 466 mm vs concept 397, front hang 80 mm (j4 at 0.004: 436 / 50).
    trace.py: the concept traced through its fitted camera vs ours (overlay cloth_renders/c10_trace.png, ours shifted
    to the concept chin). Our Garrett is 40 mm shorter chin -> shoulder line than the concept figure (68 vs 28 mm), so
    chin- and shoulder-anchored heights disagree; robust: notch ~25 mm too wide each side, lapel 75 vs ~64 mm, break
    on the chin anchor matches (398 vs 392-401 mm below), collar_show at CB 6 mm (rule 10-20), chest wide.
  - Round 6 (draft vs the trace, one batch + 1). j8 (collar stand 11 / fall 28, lapel 64 mm, gorge_angle 55, under_cap
    0.02): the steeper gorge moved the notch IN but UP (3 mm below the chin vs concept 56-63): gorge_angle is the wrong
    lever for "lower". The constructed collar's top is set by the NECKLINE (its stand already at the 8 mm floor):
    construct show changes nothing. j9 = neckline back 0.035 -> 0.045, widen 0.012 -> 0.018, collar 11 / 28, lapel
    0.064, gorge_drop kept (0.12), under_cap 0.02: notch 52-55 mm below the chin (concept 56-63) and ~15 mm out,
    collar_show 9.5 mm at CB, shirt collar 6-7 mm above the jacket's at the side neck, lapel 60-62 mm, chest +252
    (j6 +294, j7 at under_cap 0.004 +213). Gates on j9: visible collar / V 0.00 mm, 0 visible crossings, 0 skin px.
    j7 (the j4 fit) fails the crossing gate (71): pressing the HIDDEN shirt under the lapels is still owed.
    Broker: the jacket START is not deterministic run to run (X 1 cm, even the mesh: 3479 vs 3492 vertices), so
    stage.sh's write-then-consume rounds re-key every time for some builds; q.sh straight through (place once,
    wait for the fleet) is the safe path until that is found. Sheet cloth_renders/c10_w9_sheet.png.
  - Round 7. DETERMINISM: the jacket start moved 1 cm run to run (top.L 10 mm down the arm in 1 of 3 runs; seed-free,
    so every rebuild re-keyed the sim). Cause: place()'s sleeve-down retry updated `down` IN PLACE while iterating a
    SET of piece names, so an arm-mate read the new value or not by the set's per-process order (string hashing).
    Fixed (from the old values, sorted); det3.sh: 3 fresh runs identical. Found with det.py (step fingerprints) +
    per-piece X0 hashes. GATE was weak: magenta tested at full brightness only; shaded skin passed. Now any magenta
    hue + a LOW camera set (hem / front edges): j9 had 1597-3186 skin px at the front edges below the break (the cut).
    CUT BY VISIBILITY (cloth_layers.occluded + view_dirs: numpy z-buffer of the jacket from 61 directions, a shirt
    vertex hidden when the jacket is in front from all, eroded 3 rings, collar never cut): 0 skin px on j9 / j10.
    Depth-fleck count (shirt in front of the jacket's outer side by 2-30 mm) reported, not gated: oblique views see
    the V's shirt in front of the far lapel legitimately. LAPELS: cloth_made.board_lapel (construct key board,
    default on): the forepart under each lapel laid as a ruled strip (roll row on its straight chord, across = the
    strip's mean direction) before press_flap. lapelgate.py (front view, max deviation from the chord): concept roll
    edges 2.8 / 8.0 mm; j9 roll 18-34, outer edge 29-44; j10 (boarded) roll 8.5-8.8, outer edge 21. Outer edge still
    curved: not found yet.
  - Round 8. Board fixes tried: chord unclipped past the roll's ends (no change), eased INSIDE the span (pouch smaller,
    roll 8-12 mm, outer edge 21). Board OFF on the same sim (c10_j10n): no pouches, no vertical bulges, lapels curved:
    the board itself made both (moves up to 65-87 mm: a 3D chord between the roll's ends cuts through the chest and
    the settle pushes it back out). board is now default OFF, experimental. j11 / j12 (chest canvas from the break to
    the lapel point, roll_strength 0.8, break_y 0.46 -> 0.49; under_cap 0.02 / 0.004): j11 passes the shirt gates
    (0 crossings, 0 skin px, collar/V 0.00) but the wearer's right lapel crumples into a tab at the lower break
    (roll 43 mm off its chord), break now at the concept's height (383-403 vs 398 mm below the chin); j12 (tight)
    84 visible crossings, collar_show 17.5 mm. Neither is better than w9 to the eye.
  - Round 9: the LAPEL CONSTRUCTED after the drape (cloth_made.made_lapel, construct key lapel="made", now the default;
    "pressed" = the old press_flap). Roll line = the straight chord between the drape's roll-row ends, LIFTED along the
    lapel's normal (a linear lift) until it clears the under garment by 2 x lay (the raw chord ran up to 46 mm deep,
    through the shirt); the base within 2.5 cm of the row gets its bow taken out; the lapel = a ruled sheet over the
    line along ONE cross direction, lifted by ONE plane over (along, across) to clear the under garment (point-by-point
    settling made the outer edge follow every chest bump: 34-50 mm), rising from the fold over a 4 mm soft roll; the
    forepart under it pressed back behind it. Same cached j10 sim (no GPU): roll lines 4.4-4.7 mm off their chord,
    outer edges 0.1-0.2 mm (concept 2.8-8.0; j9 16-41), lapel 65-69 mm, integrity 0 crossings, visible shirt x
    jacket 6, collar / V 0.00 mm, 0 skin px from 12 cameras. lapelgate.py now reads the outer edge on the pattern's
    break -> lapel point segment (the old bins mixed in the roll line and the notch). Sheet cloth_renders/
    c10_w10_sheet.png (concept | w9 | now).
  - Round 10 (hidden-shirt press, tight fit). j12 (under_cap 0.004) rebuilt with the constructed lapels (no GPU):
    the tuck IS the hidden-shirt press (without it 1132 visible crossings: s2_12 through the forepart under the
    lapels); what stays crossing at the armpits is cut (c10ship xcut: crossings with |x| > 0.15, 3 cm inside every
    jacket opening, 6 cm off the V, 2 rings; again after the tuck). Result: 0 skin px (12 cameras), collar 0.00 mm,
    V p95 0.21 / max 8.9 mm (the tuck's feather), visible shirt x jacket 10 (neck), x the made collar 10-16 (CB),
    lapels straight (roll 4.2-4.4, edge 0.2-6.2 mm). The notch did NOT come in with the tight fit (still ~12 mm low,
    out on the shoulder slope): the draft, not the fit. COLLAR RING: at CB the constructed fall runs 16 -> 4 mm above
    the seam then OUTWARD level (rows 11-15 at z +4 mm, 12-14 mm off the shirt collar): a flange, not a fall lying
    down; construct collar_options fall_hug 0.02 changed nothing (no layer within reach). Not fixed. Sheet
    cloth_renders/c10_w11_sheet.png (w10 | tight j12).
  - Round 11. V feather to 0: c10ship lays only COVERED vertices under the jacket (the tuck's feather onto uncovered
    ones dropped): visible collar AND V 0.00 / 0.00 / 0.00 mm vs s2_12, gate PASS (j12). (Production cloth_layers.tucked
    still feathers 5 rings: the pipeline needs the same rule when merge-and-cut lands.) COLLAR FALL as a board
    (notched_collar key fall_board, default on): each back column from the roll's top straight down to where its
    length reaches along the cloth below the seam; the CB fall now runs 13 -> 1 mm above the seam (was flat at 4,
    a flange). From behind (c10_w_j12b_backc.png) it lies down; from the front, small grey tabs remain where the
    collar meets the lapel at the side neck; collar x shirt collar 10-16 crossings at CB unchanged.
  - The covered-only rule is in production: cloth_layers.tucked(keep_shown=True, default): uncovered vertices are
    bit-identical to the finished under garment (rigid groups that moved move whole); keep_shown=False = the old
    5-ring feather. Test test_cloth_layers::test_tuck_leaves_what_shows_bit_identical.
  - HANDOVER (cloth10, 2026-10-09 evening). State: tight-fit jacket j12 (out/c10_j12.pkl: under_cap 0.004, neckline
    back 0.045 / widen 0.018, collar 11 / 28, lapel 0.064, break_y 0.49, chest canvas, roll_strength 0.8) over pinned
    s2_12, lapels CONSTRUCTED (made_lapel), collar fall boarded, shirt layered by c10ship (visibility cut + crossing
    cut + covered-only tuck): visible collar / V 0.00 mm, 0 skin px from 12 cameras. Sheets c10_w10_sheet, c10_w12.
    OPEN, in order: (1) side-neck TABS: grey lumps on top of the shoulders behind the shirt collar points, where the
    constructed collar meets the lapel (stations where the stand runs out / the ends blend, wE); present with and
    without fall_board, so the ends' blend, not the board; (2) the notch ~12 mm low and out on the shoulder slope:
    a draft fix (gorge_drop / lapel point x; gorge_angle moved it UP); (3) shoulders: lumps, the wearer's right
    sleeve-head dent, a spike at the wearer's left shoulder seam; (4) shirt collar x jacket collar 10-16 crossings
    at CB; (5) c10ship's cut rules (vis + xcut) into the pipeline (merge-and-cut export, step 4 of the brief).
    Tools: judge.sh <tag> (gates + lapel straightness + trace + preview), stage.sh <queue> (one broker batch per
    stage, deterministic now), q.sh with BROKER=1 to rebuild from pulled results (construct-only changes need no GPU).
- cloth11 (2026-10-09/10, "cloth11" agent; continues cloth10 on Garrett's jacket over pinned s2_12). Scratch DURABLE in
  /mnt/data/hifipushie/cloth11/: cloth10's tools retargeted (env.sh, run.sh, q.sh, stage.sh, judge.sh, c10ship.py ...)
  + run.py `dumpcon=<pkl>` (saves construct()'s inputs during a build), con.py <tag> [key.path=json] [under=carried|s2]
  (construct() alone on a dump, ~3 s, writes a run.py-like pkl), sweep.py (construct variants in-process + collar fold
  counts), kinks.py / cprobe.py (the made collar's grid: folded quads by station / row positions), xprobe.py (made
  collar x shirt crossings by station/row), xj.py (which jacket pieces cross the visible shirt), spikes.py,
  views.sh <tag> (neck + upper-figure renders, no gates), cmpfig.py; c10ship.py gained neck=1|2, hl=1 (made collar
  orange), sh=1|2, fig=1, cover=pipe (the PIPELINE's rule: tucked + cloth_layers.cut, as the export does).
  - (1) Side-neck TABS: the made collar's end lay (on the lapel's pattern, columns running back over the shoulder) and
    the fall (columns running out and down) are ~90 deg apart; blended point by point per station (wE) their outer rows
    crossed: 39 quads folded > 120 deg at stations 11-19 / 44-50 (the corner of the neck seam where the roll line meets
    it). blend_smooth / blend_reach more: no change. Fix: `cloth_made.patch_transition` (collar_options blend_patch,
    default 3): the meeting zone laid as a patch between its boundary columns (whole curves blended by arc, carried to
    each station's seam point). Folds 39 -> 9, none at the side neck; the knotted flags in the three-quarter views gone.
  - Back fall edge: the fall board's columns took their way down from the normal of whatever lay under each station;
    the outer edge zigzagged 10-25 mm in x across the back (st 22-30), folded quads at CB, a kink visible from behind.
    Board directions and ends now smoothed along the seam (collar_options board_smooth, default 6): folds 12 -> 2,
    a clean edge (out/bsm_cmp.png).
  - (4) Shirt collar x jacket collar 10-16 at CB: NOT in the construction's own view (vs the under garment it was
    given: 0). The jacket was constructed over s2_12 CARRIED onto this code's mesh (pinmap: same positions, another
    triangulation) while c10ship draws s2_12's own mesh; at the collar's sharp roll the two surfaces differ by mm and the
    stand, 3 mm off, went through the drawn one. Stand clearance `off` 0.003 -> 0.005 (mid-surface to mid-surface is
    already 2.7 mm for a 2.4 mm shirt collar + 3 mm jacket collar): 0 crossings. (Constructing over s2_12's own mesh
    also gave 0 at the collar but moved hug/over_under: 44 crossings at the back neck; rejected.)
  - (5) Merge-and-cut in the pipeline: `cloth_layers.cut(under, outer, keep)`: visibility (hidden from all 61 view
    directions by the outer garment's welded surface, its made parts as slabs, the pieces they replace left out, AND
    the body; grown 3 rings; keep never cut) + crossings (cut 2 rings round where the under cloth crosses the outer one,
    3 cm inside every opening and 6 cm from the openings the under garment shows through: no hard-coded |x| / z as in
    c10ship). `export_part` uses it by default (outer garment key hidden_rule "margin" = the old `hidden`).
    `tucked` now lays the under garment under the outer's MADE parts, not the hidden simulated pieces they replace
    (shirt by the neck crossed the made collar: 6 -> 0). On the real pair (c10ship cover=pipe, bsm_1): 0 skin px from
    12 cameras, collar and uncovered shirt bit-identical, visible shirt x jacket 10, x made collar 0. Tests:
    test_cloth_layers::test_cut_by_visibility_and_crossings, ::test_tuck_lays_under_the_made_parts_not_the_pieces...,
    test_cloth_made::test_patch_transition_never_folds_where_two_lays_meet.
    NOT DONE: the export ships the SIMULATED collar (export_part never draws res["made"]["parts"]): on j12 that piece
    has an 85 mm spike at the wearer's left side neck (spikes.py). The made parts need exporting as geometry.
  - Disk guard: cloth sims refused at < 20 GB free even when the solver runs on the GPU fleet (the disks were at
    16 / 22 GB free); remote (bundle / HIFIPUSHIE_ZOZO_REMOTE) zozo jobs now need 1 GB.
  - (2) Notch, three draft sims over j12 (one broker batch + 1 rerun): n1 gorge_drop 0.105 + lapel roll_stand 0.03,
    n2 gorge_angle 40 + roll_stand 0.03, n3 roll_stand 0.035. Lapels straighter in all (roll 2.8-3.4, edge < 1.1 mm),
    but: n1 notch 16 mm higher by the chin (35/37 below it vs concept 63/56), shirt shards at the wearer's right V
    edge (gate passes); n2 the wearer's left lapel flares out as a wing, 142 skin px; n3 notch at the chin anchor
    (-10/-3) but the lapel tops stand off the shirt (dark gap), 271 skin px. None better than j12 by eye: j12 kept.
    MEASUREMENT CAVEAT: trace.py's "notch" for ours is the made collar's END TIP (G[0,-1]), 30 mm outside the gorge
    end; the gorge end itself (wpts.py: draft points found on the mesh) lies at x +-135 z 1470 = the concept's notch
    by the chin anchor. By the shoulder line ours is 30-40 mm low, by the chin 12 mm high (Garrett's neck is short:
    chin -> shoulder 28 vs 68 mm). In the front view the notch is at ~0.51 of the half shoulder width (concept 0.64:
    not too far out) but above the shirt collar points (concept: level with them). The "12-15 mm out and low" brief
    does not survive this; the lever that reads as the "wing" is the collar END lying back over the shoulder.
  - (3) Shoulders: sleeve cap_ease 0.045 -> 0.03 (s1) / 0.02 (s2): no visible gain at the sleeve heads, the lapels
    flared and waved (run-to-run sim spread), gates FAIL (602 / 26 skin px, 76 / 191 visible crossings). Rejected.
    spikes.py on j12: the sharpest interior shoulder points are the shoulder seam / sleeve-cap corners (back.L
    +0.217, 9 mm; back.R -0.221, 11 mm umbrella offset), the lumps are the sim's sleeve heads; not fixed.
  - Spend: notch batch $0.055 + $0.033, sleeve batch $0.103 (one instance failed and was retried) + $0.094 = $0.28.
  - Current best: out/c11_k4.pkl = the j12 sim with this code's construction (con.py c11_k4 under=carried): 0 skin px
    (12 cameras), visible collar / V 0.00 mm vs s2_12, lapels roll 4.2-4.4 / edge 0.2-6.2 mm, collar x shirt collar 0,
    visible shirt x jacket 10 (front.L by the gorge), collar_show 18.9 mm. Renders out/c11_k4_neck.png, _fig.png;
    before / after: out/j12_k4_neck.png, j12_k4_fig.png, ba_tabs.png, bsm_cmp.png. At whole-figure scale the change is
    small (the knotted tabs show only in the three-quarter views): no sheet sent.
  - Round 2 (coordinator, after the merge of 2699cd3). EXPORT: export_part now ships each constructed part (made
    collar) as a closed slab of its thickness, its pattern uv placed where its source piece lies in the atlas, and drops
    the simulated pieces it replaces (`replaces`); test_seams::test_export_ships_made_parts_not_the_pieces_they_replace
    writes a GLB and reads it back (made part present, no triangle of its source).
  - RE-DRESS on the current Garrett (gc_dress: style head_size 1.0, was 1.138): model workspace/su_gc = gc_dress's spec
    (frozen copy, 2026-10-10 00:24) + su_om_garrett's shirt (as s2_12: no patches) and jacket; the jacket with j12's ops
    (q_g.txt, no under_pin: over the NEW shirt sim). The shirt's fine settle was refused (13 slivers at the open neck by
    the front edges up to 2.3x after the coarse -> fine carry and body clearing; the coarse sim itself was clean, max
    1.22x): `cloth.relax_start` (edge-length relaxation of the over-stretched triangles + 2 rings, never made or carried
    vertices; only when fine_start_check fails, so passing starts and their cache keys are untouched): 2.3 -> 1.6x,
    41 vertices moved <= 1.5 mm. test_cloth::test_relax_start_gives_back_a_slivers_stretch.
    run.py now also pickles the under garment (<tag>_under.pkl, its body + joints); c10ship pair=<tag>, trace.py third
    arg, judge.sh / views.sh PAIR=<tag> judge a pair on its own body (pairload.py).
    Spend: shirt coarse $0.046 + fine $0.018 + jacket $0.042 = $0.107 (three stages: each needs the previous result).
    RESULT c11_gj: chin 1541 (was 1529), shoulder line 1512: the notch by the chin 68 / 60 mm below it vs concept 63 / 56
    (was 51 / 44: -12 -> +5 / +4, it came to the concept on its own); by the shoulder line still -39 / -31 (concept
    +5 / +11). Jacket collar top at the side neck 6-9 mm below the chin (concept 20-21); shirt collar 11-13 mm above
    the jacket's there; collar_show at CB 24.7 mm (rule 10-20). BUT: the wearer's left lapel flares out as a wing
    (lapel 97 mm from the roll, right 65), shirt flecks at its edge, 99 visible crossings, GATE FAIL 546 skin px (low
    front cameras: at the wearer's left front edge by the shirt's hem). The new shirt's collar does NOT read like
    s2_12's: the band's ends stand out as small slabs beside the collar points (a button showing at one), the points
    spread wider and shorter (out/shirt_alone_cmp.png: s2_12 | new). Not yet known whether that is the body or code
    since s2_12 (meshing changed: 13123 vs 13284 vertices).
