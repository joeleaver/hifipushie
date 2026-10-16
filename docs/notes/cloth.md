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
  - Round 3. OLD-BODY CONTROL: s2_12's spec re-simmed on su_om_garrett with current code ($0.035) matches s2_12 (same
    13284 vertices; collar p50 0.7 / p95 5.9 mm, stand 0.0, fronts 1-2 mm; same look, out/os_cmp.png). The 13123 vs
    13284 was never meshing: s2_12's npz is AFTER the post-sim band-edge split (front.L 2461 vs 2300 place-only). So
    the new-body difference was the BODY: Garrett's narrower neck (stand 435 vs 459 mm) put the band's CF ends 10 mm
    higher and 10 mm nearer CF (x +-40 z 1500 vs +-50 z 1490), out from under the collar points: two tabs beside the V,
    a button on one. Construction tried and rejected: turning the band ends in about the neck seam (bigger tabs),
    the open-neck press (front corners folded out into a flap).
    DRAFT RULE `cloth.band_ends` (applied in cloth.pieces for designs with a collar_rule; pattern key band_ends: false
    turns it off): each band end runs past CF no further than its button needs (button side half a button + 2 mm,
    buttonhole side half of button + 3 mm + 2 mm) or the collar point's reach past its sewn end, whichever is more,
    and the end is a quarter ellipse from the top's CF to the bottom edge. Only shortens. Garrett: 9.2 / 14.8 ->
    7.5 / 9.0 mm (the points reach 6 mm). Recorded in the draft as draft.band_ends. NOTE: it changes every Simon
    shirt's draft (su_om_garrett's too): their cached sims re-key. test_cloth::test_band_ends_run_past_cf_only_as_far...
    RE-SIM c11_gb (su_gc, shirt + jacket j12-style over it; $0.043 + $0.012 + $0.043 = $0.098): band ends under the
    collar points (out/gb_neck.png); jacket GATE PASS: 0 skin px from 12 cameras incl. the low ones, 0 visible shirt x
    jacket crossings, 0 x the made collar, visible collar / V 0.00 mm vs the shirt as simulated, lapels straight (roll
    4.7-5.2, edge 0.1 mm) and symmetric (63 / 64 mm, the 97 mm wing gone). Trace: notch 67 / 69 mm below the chin vs
    concept 63 / 56; break 415-423 vs 398; collar_show at CB 25.5 mm (rule 10-20: over). Sheet
    cloth_renders/c11_gb_sheet.png (concept | c11_k4 | c11_gb). Still: the collar ends stand up a little at the
    shoulders; the chest reads fuller than the concept's.
  - Round 4 (chest, collar show; over c11_gb's shirt). Checklist on c11_gb (check.py now takes models without
    trousers; topk.py makes its light npz from a run.py pkl): chest 441 vs 397 mm (+11%), shoulders 528 vs 482
    (+10%), front_hang 85 mm (rule -40..10), hem_sweep -21%, collar_hug 16.6 mm, sleeve -14%. One batch:
    gc1 = neckline.back 0.045 -> 0.035 + block chest_ease 0.10 -> 0.06; gc2 = the same with chest_ease 0.03.
    gc2's sim STALLED on the fleet (progress frozen at "sewing" for 40+ min, a normal job takes 60-90 s): cancelled,
    but the batch cost $0.70 (the stalled instance billed). [CORRECTED 2026-10-10, coordinator: do NOT cancel quiet
    jobs by hand (a cancel is billed for the time held; the runner prints only at setup and end): the broker's stall
    guard kills a job with no output AND no GPU use for 10 min, free. Submit with timeout_minutes ~30, stall_minutes
    default. bl.sh status <batch> to look.]
    [UPDATED 2026-10-10, broker prod v132: a job is free only if it fails BEFORE reaching a box (no machine, box never
    up, bad input); once on a box its time is billed however it ends (success, failure, stall, cancel, box death), so
    failed sims now cost their run time: check inputs / starts before sending. get_bundle_batch entries carry
    box_activity (active / quiet, idle_secs, last GPU / CPU / disk / net use); a box idle 15 min fails its jobs as
    "stalled" and is replaced (per-job stall_minutes, default 10, applies first). A working long sim is no longer cut
    by the 1-hour box cap (ZOZO reads ~26% GPU, 1 core: shows as active).]
    gc1 (out/c11_gc1.pkl, its shirt c11_gc1_under.pkl = c11_gb's): collar_show at CB 25.5 -> 12.4 mm (rule 10-20: OK);
    gates PASS (0 skin px, collar / V 0.00), lapels straight (roll 4.7-5.3, edge 0.1-0.3) 64 / 67 mm, notch 67 / 66 mm
    below the chin (concept 63 / 56); visible shirt x jacket 32 (was 0). Chest only 441 -> 436 mm: four points of
    ease is 5 mm of front-view width; the width there is the shoulders / sleeve heads (528 vs 482) and the fronts
    hanging open (front_hang 85 -> 112 mm), not the body ease.
  - HANDOVER (cloth11, 2026-10-10). Best: out/c11_gc1.pkl over c11_gc1_under.pkl (model su_gc: gc_dress frozen
    2026-10-10 00:24 + the suit; jacket = j12's ops with neckline.back 0.035, chest_ease 0.06; q_gc.txt line 1).
    Judge any build with PAIR=<tag> judge.sh <tag> and PAIR=<tag> views.sh <short>; check.py <tag> <jacket lt npz> -
    <shirt lt npz> su_gc (topk.py makes them). OPEN, in order: (3) the jacket collar ends lifting at the shoulders;
    (4) the top button 16-22 mm low (break 414-420 vs 398 below the chin: lapel break_y 0.49 -> ~0.47);
    (5) shoulders 528 vs 482 mm (+10%): the block's shoulder width / sleeve-head support, which is also most of the
    chest width; (6) front_hang 112 mm (the fronts swing open: hem spring / front balance), hem_sweep -21%;
    the 32 visible crossings gc1 brought back. Spend this agent: $0.28 + $0.24 + gc batch $0.70 = ~$1.22.
- 2026-10-10 (coordinator): job_f5a18a2711f675af_sim (cloth11's gc2, su_gc jacket with chest ease 0.03) HANGS at setup ("3447 verts ... mode sim") on the fleet twice (batches 7b86783e and fb37002d); both cancelled. Reproducible: inspect that scene's inputs before resubmitting. Broker now has a stall watchdog (no output and no GPU use for stall_minutes, default 10: the job is killed and marked failed; since prod v132 its box time is billed). Submit with timeout_minutes ~30, and don't cancel quiet jobs by hand: a cancel is billed for the time held.

## cloth12 (2026-10-13, "cloth12" agent; continues cloth11 on Garrett's jacket, model su_gc)
SUMMARY (one page; details per gate below). Garrett's jacket (su_gc) from "a strap with a tab" to reading as the
concept at figure scale; 9 broker sims + 1 duplicate, $0.47; construction worked on cached sims (con.py, seconds).
- Side-neck tabs: the made collar's outer edge was squeezed to 0.35-0.5 of its cut length where the end turns into
  the back: fall boarded at its pattern length + the transition as one smooth outer edge (Hermite), straight columns.
- Collar end a strap: laid on the forepart's eased cloth (21-33 of 39 mm): end columns at their cut width.
- Notch: measured the wrong point before (the collar tip); the apex was 13-17 mm low -> lapel gorge_drop 0.12 -> 0.10.
  Rim: the collar end lies on the lapel by its thickness. Shape: collar point 15 mm.
- Lapel: canvassed roll graded 2 -> 7 mm from break to gorge (made_lapel roll_top).
- "Jagged cut edges": Workbench stencil shadows, not the cut (render shadows switch; judge with shadows off).
- Production cut: the tuck moved the shirt up to 38 mm into the body (skin showing): never closer than 1 mm now.
- Right front swinging open: ruled out pattern, body, shirt, closure lap, start, mesh (opt-in mirror_mesh) one test
  each; cause was the made collar's carried START: one end's lay took points of the other end round the back
  (cloth._end_points). Then the button stance 20 -> 12 mm put both fronts at the concept's opening at the button.
- Best: out/c12_n10c.pkl (gorge_drop 0.10, collar point 0.015, lapel stand 0.012); gates pass (0 skin px, 0 visible
  crossings), notch 57 / 55 mm below the chin (concept 63 / 56), fronts symmetric, 132-138 mm apart at the button.
- Rules distilled into cloth_guide.md ("What goes wrong", "Judging what you see", "Made pieces constructed after the
  drape"); background split to cloth_background.md (guide topic cloth_background).
- Open: notch V crispness, chest V ~2 cm narrow, a ridge at the left side neck, shoulders, CB collar crossings, the
  shirt re-sim on the final measures.

Scratch DURABLE in /mnt/data/hifipushie/cloth12/: cloth11's tools retargeted to this worktree (env.sh: BLAS/OMP 4
threads; stage.sh: --timeout-minutes 30; bl.sh: oxidegen's maintained scripts/bundle/bundle_client.py), + run_c11.sh /
q_c11.sh (the same on cloth11's code, src_c11 = `git archive 2770134 src`: reproduces c11_gc1's sim keys for a construct
dump), c10ship.py side=1 (each side neck close, made collar orange with hl=1: out/<tag>_snR.png / _snL.png).
- Re-check on current main: c11_gc1 does NOT rebuild from the pulled results: the SHIRT's coarse job re-keyed
  (job_d038170a001a4e2d; tess2's coarse-start clearance, dae08b3 / 7708de2). Baseline re-sim c12_b0 queued (3 stages).
- Broker: uploads failed (JSONDecodeError on the PUT): signed upload links now go straight to the object store, which
  answers with an empty body. spikes/gpu_cloth/bundle_client.py put() no longer parses it; cloth12's bl.sh uses
  oxidegen's client. Nothing was submitted (no cost).
- cloth.render passes Blender `-t` (HIFIPUSHIE_BLENDER_THREADS, default 6): the machine is shared.
- (1) TABS, looked at on c11_gc1 (out/c12_v_gc1_snR/L.png, made collar orange): the made collar's END is a ~20 mm strap
  along the gorge from the side neck to the notch; where it meets the back collar (the transition, stations 8-17 /
  47-51) the wearer's right is a KNOT, the left a sharp elbow; kinks.py: quads folded > 100 deg across stations 8, 9,
  12, 13, 15, 17 and 48-49. In the front view the outer corner of that elbow pokes up above the shoulder line: the "tab".
  Measured (stp.py: per station, 3D / pattern length): in the transition the made collar's OUTER EDGE ran at 0.35-0.47
  of its pattern length and the columns at 26-37 of 45-58 mm: the fall was squeezed, not laid, so it stood as a wall
  beside the neck and its outer corner bunched into the knot. (Also: gc1 is reproducible bit-for-bit for construct
  work: run_c11.sh rebuilds its sim keys; the jacket's in.npz differed from cloth11's only by 1e-16 float noise in the
  body arrays, so results/job_145426d722484014_sim was reused under the new key d5661d1b33a79621.)
  FIX (cloth_made.notched_collar, construction only): (a) the fall board takes each column's PATTERN length from the
  roll down (collar_options board_length "pattern", default; "laid" = before); (b) the TRANSITION (stations with end
  weight 0 < wE < transition_end 0.98, widened transition_widen 2 into the back) is no longer a point blend / patch:
  its outer edge is ONE Hermite curve from the last pure end column's outer corner to the first boarded back column's
  end, carrying both edges' directions on; each column = the back's own stand + fold (stands under transition_flat
  6 mm laid flat), then straight from the roll's top to its point on that edge; inner rows evened (transition_smooth 4).
  collar_options transition "patch" = cloth11's patch_transition (kept). plotc.py <pkl> <png> [side] plots the grid
  (front / top / side views): out/plot_k0.png (before: the outer edge's S-bend at the corner) vs plot_k7.png.
  Result c12_k9 (con on c11_gc1's sim): folds > 100 deg 8 -> 6, the outer edge one curve; gates as gc1 (0 skin px,
  collar / V 0.00 mm, 32 visible shirt x jacket crossings, lapels roll 4.7-5.3 / edge 0.1-0.3 mm).
  GATE 1 sheet workspace/cloth_renders/c12_g1_tabs_sheet.png (concept | c12_k9 | c11_gc1). My read: the upright
  horns at the shoulder tops in the front neck view are gone, the collar now lies out over the shoulders and turns
  the corner at the wearer's left cleanly. STILL WRONG: the wearer's right inner corner (by the seam where the end
  meets the back) still crumples (3-5 mm, rows next to the seam: the end lay's own first rows lie forward of the seam
  and the seam carry there is 8 mm); the collar end reads as a ~20 mm strap lying ON the lapel (its columns 28-33 of
  39 mm: on_pattern compresses it) and the notch's V is not visible; at figure scale the gap to the concept is the
  fronts hanging open (lapels vertical, a wide shirt V), not the collar. transition_end 0.9999 tried: worse.
- Gate 2 (coordinator after gate 1: (a) the lapel reads as a strap with no notch V and no roll, (b) the fronts hang wide
  open, (c) jagged white cut edges at the neck; diagnose in pattern / construction terms, fix in that order).
  New baseline on CURRENT main: c12_b0 = c11_gc1's queue line + layer_gap 0.005 (the new coarse-start standoff check,
  dae08b3, refused gc1's jacket start: side.R 1.65 mm from the shirt). Every build: con.py on its dump with this code
  (c12_<t>c), j2.sh <t> (gates, lapels, trace, trace_g.py = the GORGE END itself, not the collar's end tip, + across).
  - (a) CAUSES: (1) the collar END was laid on the forepart's board, which carries the forepart's ease near the neck
    (hug_neckline draws the neckline in, 12 cm of cloth follows): the end came out at 21-33 of its 39 mm cut width, a
    strap; (2) the gorge end (the notch's apex) sat 13-17 mm LOW below the chin (b0: 80 / 69 mm vs concept 63 / 56; by
    trace_g, the old "notch" number was the collar end's tip, 30 mm away). Lapel width itself is the concept's: 63-67
    mm from the roll (concept ~64 front view; at the notch ~65 mm across in the concept crop, out/concept_chest.png).
    FIXES: construction: each end column at its CUT length from the seam (collar_options end_length "pattern",
    default): end widths 38-41 mm = the pattern; the transition starts transition_widen_end 2 stations inside the end
    (its outer corner hooked back by the seam's corner: the knot came back on the new sim). Draft: lapel gorge_drop
    0.12 -> 0.10 (sim c12_n1): gorge end 63 / 52 mm below the chin (concept 63 / 56), across 0.63 / 0.57 of the half
    shoulder (concept ~0.56); 0.09 (n2) overshoots 11-13 mm high, 137 visible crossings. NOT fixed: the notch's V
    does not read in clay (the lapel's top edge past the collar end lies flush on the forepart, same grey, no rim),
    and the lapel has no soft roll (made_lapel lays it as a ruled board).
  - (b) MEASURED (gap.py, front edge to front edge by height): n1 169 at the chest, 138-181 from the break down;
    concept ~182 at the chest, ~131 at the top button (1.14 mm/px): ours is the concept's at the chest and 1-5 cm
    too open at and below the break: the roll lines run vertical instead of closing to the button. Tried: button
    stance (lapel stand) 0.02 -> 0.03 (c12_n3, $0.04): WORSE (gap 161-183, 122 visible crossings): the wider extension
    rolls out with the lapel. CAUSE (not yet fixed): the fronts' balance below the break (they swing out from the
    chest), not the stance; next lever: front balance / the hem's spring (cloth11's front_hang 112 mm), chest canvas.
  - (c) The "jagged white cut edges" were Workbench STENCIL SHADOWS of the 2 cm draft jacket on the shirt, not the cut:
    rendered with shadows off the edges are clean (the cut, a 4 cm opening margin and a feathered tuck changed
    nothing). cloth.render(shadows=) / job "shadows" / HIFIPUSHIE_CLOTH_SHADOWS=0 (default stays on; cloth12's env.sh
    sets 0). The production cut (c10ship cover=pipe) on this pair shows SKIN at the wearer's right chest: tucked moves
    covered shirt up to 38 mm, into the body there (pipeline item 5, not done).
  - GATE 2 sheet workspace/cloth_renders/c12_g2_sheet.png (concept | c12_n1c | c11_gc1, all without shadows).
    Spend this agent: $0.092 baseline (incl. a $0.021 duplicate shirt sim: two stage.sh runs overlapped) + $0.054
    notch pair + $0.040 stance = $0.186.
  - RESTART: scratch /mnt/data/hifipushie/cloth12 (env.sh: shirt sims cached in results/). Best = out/c12_n1c.pkl over
    c12_n1_under.pkl (q_n.txt line 1: gorge_drop 0.10). Rebuild after construct code changes: SRC=con_n1 BASE=c12_n1
    bash cv.sh c12_n1c; judge: bash j2.sh n1; views: HL=0 bash vw.sh c12_n1c c12_n1 fig=1; sheet: uv run python
    sheet.py c12_n1c c12_gc1s <png> <title>. Sims: bash stage.sh <queue> 3 (ONE at a time: check `ps aux | grep
    stage.sh` first).
    NEXT: (b) front balance (fronts 1-5 cm too open below the break), the notch V reading (lapel edge rim / roll), the
    wearer's right inner corner, then items 3-5 (shoulders, CB collar crossings, cut rules in the pipeline: the
    tucked skin hole).
- Gate 3 (coordinator: (1) the lapel's ROLL, (2) a notch V with a rim, (3) front balance below the break, then item 5).
  - (1) ROLL: made_lapel laid the lapel as a pressed board (3 mm over its forepart). Now a canvassed roll (made_lapel
    roll_break / roll_top / roll_width, construct key lapel_options; default roll_top 7 mm): the roll line stands
    off the chest by R, from 2 mm at the break to roll_top at the gorge (eased), the lapel falling from it to lie flat
    by roll_width x R + 8 mm across; the fall is built BEFORE the clearance lift (after it, the lapel's outer part
    sank through the shirt: a shirt button showed through the lapel). roll_top 10-12 mm put a knot back at the
    wearer's right side neck (the collar end lies on the lifted gorge): 7 mm is clean. In clay the roll is subtle.
    Test test_construct_presses_lapels... asserts the graded roll (flat case kept with roll_top 0).
  - (2) NOTCH V: (a) the collar's END now lies on the lapel by its own thickness (collar_options end_over 1.0: it had
    sunk flush into the lapel, no rim); (b) draft: collar point 15 mm (op collar point: the end's outer corner run
    on toward the lapel point: the end edge leans like the concept's and the V narrows) = sim c12_n4 ($0.048). Notch
    closes (c10ship notch=1: out/c12_v_<tag>_noA/noB.png): the wearer's right reads as a collar point over a lapel
    with a step; the wearer's left still reads square from three-quarter. n4 gate: 13 new skin px in one close
    three-quarter camera (FAIL; n1 with the same construction passes); notch 62 / 47 mm below the chin (concept
    63 / 56), the left one 9 mm high and 20 mm further in than n1.
  - (3) FRONT BALANCE: NOT FIXED. Per side (gap.py idea at 20 mm steps, out/ n4/r12 numbers): the wearer's LEFT front
    edge runs 60 -> 24 mm off x 0 from the break down (close to the concept's ~65 at the button); the wearer's RIGHT
    hangs at 85-100 mm the whole way: the open look is the right front swinging out (an asymmetric sim; the button
    stance is not the lever, gate 2). Next: find why the right front swings (its start / the closure's "open" state
    / the lapel roll's fold strength on that side) before any draft change.
  - (5) PRODUCTION CUT, skin at the right chest: cloth_layers.tucked laid covered shirt `gap` under the jacket's
    inner face even where that face lies on the skin: moved up to 38 mm INTO the body, so the skin drew over it.
    Now no tucked vertex goes under TUCK_BODY (1 mm) outside the body (each move cut back by bisection; a start already
    inside keeps its place): c10ship cover=pipe on r12: the skin patch is gone (out/pipe_cmp.png), V moved p95 9.2 /
    max 28.8 mm (was 11.2 / 38.0). test_cloth_layers passes (12 ok); no new test yet for this guard.
  - GATE 3 sheet workspace/cloth_renders/c12_g3_sheet.png (concept | c12_n4c | c11_gc1, + notch closes; shadows off).
    Spend: $0.186 + n4 $0.048 = $0.234.
  - RESTART: best passing = out/c12_n1c.pkl (gorge_drop 0.10, roll 7 mm, end over the lapel; gates PASS, 0 visible
    crossings); best notch shape = out/c12_n4c.pkl (+ collar point 0.015; 13 skin px). Commands as in gate 2's
    RESTART; notch closes: HL=0 bash vw.sh <tag> <pair> notch=1; sheet: NOTCH=1 uv run python sheet.py ...
    NEXT: the right front's swing, n4's 13 skin px, the left notch end, a test for the tuck's body guard.
- Gate 4 (coordinator: (1) why the wearer's right front swings, (2) the collar point with 0 skin px, (3) the left
  notch squarish, (4) a test for the production-cut fix; then merge-ready).
  - (1) RIGHT FRONT SWING, split by elimination (edges.py <npz>: each front's innermost edge, start X0 and end, by
    height). Pattern: front.L / front.R mirror images (uv match). Shirt and body under them: symmetric within 3 mm
    (body mirror distance p50 2.8 / p99 5.4 mm; shirt depth at x +-40 / +-80 equal to 1-4 mm). Sim inputs mirrored
    (stiff, fold, rest, start): equal up to the meshes' difference. Closure layering: c12_n5 (closure over front.R
    instead of .L, $0.039): BOTH fronts swing further out, the right still more (-101..-162 vs 64..84 mm): not the
    lap. Start: c12_n6 (open_lap false: both fronts start alike, $0.049): the right ends EXACTLY as before (-81..-94
    mm off centre, 45 mm further forward than the left at the hem), the left 15-73. So neither start nor closure.
    Remaining asymmetric input: the MESH: each piece is meshed on its own (cloth.mesh), front.R 540 vertices vs
    front.L 538, a different triangulation (mirror match up to 14 mm), and every sim so far (gc1, b0, n1-n6) has
    the right front out: a triangulation bias in bending is the suspect. NEXT TEST (not done: re-keys every cached
    sim of every garment): mesh each .R piece as the mirror of its .L piece, one sim.
  - (2) COLLAR POINT 15 mm (c12_n4c) and the 13 skin px: in the close three-quarter camera at the wearer's left shirt
    collar point. Cut alone (tuck=0): 0 px; so it is the TUCK: shirt front cloth beside its collar point taken under
    the longer collar point (by the collar's end) opens a slit at the band. Tried in the harness: the shirt collar
    never split by the tuck (collar_whole, kept: no change), the shirt within 2 cm of its collar never cut (no
    change), held from the tuck within 1.5 cm (37 px), 2.5 cm (0 px but 32 visible crossings there), 4 cm (0 px,
    82 crossings). NOT clean yet: the shirt by its collar point and the jacket's collar point compete for the same
    place; c12_n1c (no point) stays the passing best. cloth_layers.tucked gained `hold` (per vertex: never moved).
  - (3) LEFT NOTCH squarish: the collar end's corner (end edge vs seam) is 125 deg on the right, 105 deg on the left
    (pattern 111): the end is laid on each forepart's own drape and the fronts hang differently: tied to (1).
  - (4) test_cloth_layers::test_tuck_never_lays_the_under_garment_into_the_body (outer cloth on the skin; without the
    guard the tuck leaves the under garment 4 mm inside the body) + `hold`.
  - Merge-ready: the cloth test set one file per process (tests.sh, HIFIPUSHIE_ASSETS set): 15 files, all rc 0, 0
    skipped (folds 13, cloth 26, cloth_layers 13, closures 12, cloth_check 1, cloth_workflow 12, pattern_draft 9,
    pattern_styles 8, pattern_tailor 17, collar 4, seams 5, cloth_reference 12, suit7 5, suit8 6, cloth_made 13).
    Spend this agent: $0.322 (n5 $0.039, n6 $0.049 this gate).
  - STATE: best passing c12_n1c (gorge_drop 0.10; construction: pattern-length fall, Hermite transition from inside
    the end, end at its cut width and over the lapel, 7 mm roll); best notch c12_n4c (+ collar point 15 mm; 13 skin px).
    NEXT: (a) mirrored .R meshes, one sim, to settle the right front's swing; (b) the shirt-by-its-collar-point vs
    jacket collar point clash (point 10 mm, or hold + a local press of the shirt's front under the lapel);
    (c) shoulders (item 3), CB collar crossings (item 4); (d) the shirt on the final measures.
  - RESTART: scratch /mnt/data/hifipushie/cloth12 (env.sh: BLAS 4 threads, shadows off; bl.sh = oxidegen's client).
    Rebuild construct on a sim: SRC=con_<t> BASE=c12_<t> bash cv.sh c12_<t>c [construct key=json ...]; judge: bash
    j2.sh <t>; renders: HL=0 bash vw.sh c12_<t>c c12_<t> fig=1 notch=1; sheet: NOTCH=1 uv run python sheet.py <now>
    <before> <png> <title>; fronts: uv run python edges.py out/c12_<t>.npz; sims: bash stage.sh <queue> 3 (one at a
    time; q_n*.txt are the lines used; check `ps aux | grep stage.sh` first).
- Gate 5 (coordinator: the mirrored mesh as an OPT-IN flag, one test sim, the fronts' numbers).
  - Garment key `mirror_mesh` (default false: no cached sim re-keys): cloth.mesh anchors each piece's interior hex
    lattice on the pattern's x = 0, so a .R piece drafted as the mirror of its .L piece meshes as the exact mirror
    (mmchk.py on su_gc's jacket: back / front / side pairs 0.0 mm apart, equal counts; off: 492/493, 547/555, 137/139
    vertices, up to 17 mm apart). test_cloth::test_mirror_mesh_meshes_a_mirrored_piece_as_the_mirror.
  - Sim c12_n7 = n1 + mirror_mesh ($0.030): the wearer's right front still hangs 75-92 mm off centre (n1: 78-92), the
    left moved further IN (9-66; n1 21-93). The mesh is NOT the cause.
  - NEW SUSPECT (found while checking every sim input for symmetry; body, poses, padded collider, stiffness and fold
    arrays are all symmetric within 6 mm): the made COLLAR's start. The collar is carried (held through the poses,
    carryPoses) and its two ends start up to 133 mm from mirror images: the wearer's right end (uv x -208..-175) starts
    on the CHEST near centre front (x -26..+3, y -157..-174, z 1457-1480), the left end at the side neck (x 73-75,
    z 1563). Sewn to the gorges, the right end then drags the right front through the sew. n6 (fronts start alike)
    still 46 mm asymmetric. The drafted turn line is symmetric ([1] / [-2] at x -151 / +151 mm); the asymmetry comes
    from cloth._on_seam's worn / notched chain (the chart of each partner's worn point: `placed` fronts use their own
    start positions) or its chain relaxation. Next: print LAY_INFO[collar] chain vs chart per side on a place-only
    build (no sim), fix the placement, then one sim.
  - Spend: $0.352 total (this gate $0.030).
  - STATE: mirror_mesh in (opt-in, tested); the right front's swing NOT fixed; the collar's asymmetric carried start is
    the lead. NEXT: the collar placement (cloth._on_seam notched chain), then one sim with it fixed.
- Gate 6 (coordinator: place-only check of the collar's start, fix, a test, ONE sim).
  - CAUSE (collchain.py: su_gc's jacket built place-only, BROKER=1, no sim; prints the notched chain per side and each
    end's lay): the band chain was symmetric within 7 mm, but each END is laid in its front's lapel plane from the
    collar points past where its roll line meets the neck edge, and that selection was only a half-plane (along the
    run-on): with the collar's deep arc it ALSO took the other end round the back. Carried into front.R's pattern
    they landed 0.2 m off the piece (qf x +229 mm on a piece spanning -234..+20), their extrapolated worn points
    turned the right end's plane (fit clearance -43 / +61 mm) and the end started on the chest by centre front. Fix:
    cloth._end_points = past the meeting point AND on that end's side of the collar (neck edge's middle -> meeting
    point). Place-only after: collar start mirror error max 133 -> 15.6 mm, both ends' fits sane (-2.5..6.4 /
    4.5..10 mm). Tests: test_collar::test_end_points_take_only_their_own_end (a deep arc where the half-plane takes the
    other end; fails on the old rule), test_worn_forepart now also asserts the ends start as mirror images (< 25 mm;
    the ga_suit fixture's collar never hit the bug, so this alone doesn't catch it). This fix changes the start
    of any notched collar whose half-plane reached the other end: those sims re-key.
  - ONE SIM c12_n8 = n1's line with the fix ($0.044): the fronts' edges from centre, R / L by height 1400..1150:
    75/60, 71/56, 66/52, 62/49, 58/45, 53/45 mm (n1: 92/76, 89/73, 84/69, 78/65, 89/61, 88/93): the right front no
    longer swings, the two hang within 13-15 mm of each other (below 1100 the left closes further: 31-63 vs 50-71).
    Gap at the chest 135 mm, at the button 98 mm (concept ~182 / ~131): now a little MORE closed than the concept.
    Gates PASS (0 skin px, 0 visible crossings), lapels 63 / 63 mm, notch 61 / 47 mm below the chin (concept 63 / 56;
    the left 9 mm high), across -127 / +110 mm. Notch corners (end edge vs gorge seam) 86 / 93 deg: symmetric now
    (n4: 125 / 105). Sheet workspace/cloth_renders/c12_g6_collar_start_sheet.png (concept | n8 | n1, + notch closes):
    the right side neck's knot is gone, both collar ends read alike; the notch V is still weak in clay (n8 has no
    collar point: the point 15 mm on top of this is the next sim).
  - Merge-ready: tests.sh, 15 cloth files one per process, HIFIPUSHIE_ASSETS set: all rc 0, 0 skipped (cloth 27,
    collar 5, cloth_layers 13, cloth_made 13 ...). mirror_mesh stays opt-in (default off).
    Spend this agent: $0.396 (this gate $0.044).
  - STATE: best = out/c12_n8c.pkl (gorge_drop 0.10, collar start fixed; gates PASS). NEXT: collar point 15 mm on n8
    (one sim) and its tuck slit at the shirt collar point; the left notch 9 mm high / 17 mm in; the fronts now a
    little closed below the break; shoulders; CB crossings; the shirt on the final measures.
  - RESTART: as gate 4's, plus: place-only collar check: BROKER=1 bash run.sh collchain.py [key=json]; the fronts:
    uv run python edges.py out/c12_<t>.npz.
- Gate 7 (branch cloth12b off main 17974ff; coordinator: the collar point on n8 + the shirt-collar slit, the left
  notch 9 mm high, the fronts slightly closed below the button). One broker batch, two sims ($0.076):
  n9 = n8 + collar point 15 mm; n10 = n9 + button stance (lapel stand) 0.02 -> 0.012.
  - Left notch high, diagnosed first on n8: the SIM put the left gorge end 14 mm higher and 17 mm further in than
    the right (constructed = simulated there), while the fronts' upper parts agree within 2 mm: a residual front
    asymmetry, not construction.
  - n9: gates PASS with the point (0 skin px: the 13 px slit of n4 came with the old asymmetric collar start), notch
    62 / 53 mm below the chin, fronts as n8 (R 54-76 / L 48-61 mm from centre).
  - n10 (CHOSEN): gates PASS (0 skin px, 0 visible crossings), notch 57 / 55 mm below the chin (concept 63 / 56) and
    across -127 / +131 mm: both sides now alike; fronts R 64-77 / L 65-81 mm from centre at 1150-1400 (symmetric),
    gap 158 mm at the chest, 132-138 at the button (concept ~182 / ~131); collar-end corners 108 / 112 deg (drafted
    111); lapels 63 / 63 mm; collar folds > 100 deg: 0. The narrower stance let the fronts sit back to the concept's
    opening at the button (and evened the two sides, with them the notches).
  - Sheet workspace/cloth_renders/c12_g7_sheet.png (concept | n10 | n8, + notch closes). My read: the fronts and the
    shirt V now match the concept's proportions at the button; both collar ends are pointed alike over their lapels;
    still weak: the notch V reads only as an edge in clay, the chest V is narrower than the concept's (158 vs ~182 mm:
    the lapels' roll lines sit in), a small lump at the wearer's left side neck in the front neck view.
  - Spend this agent: $0.472 (this gate $0.076).
  - STATE: best = out/c12_n10c.pkl (q_n9.txt line 2: gorge_drop 0.10, collar point 0.015, lapel stand 0.012).
    NEXT: shoulders (item 3), CB collar crossings, the shirt re-sim on the final measures; the chest V width.
- Gate 8 (coordinator: (1) the notch V, (2) the chest V ~2 cm narrow, (3) the left side-neck lump; + DISTIL). One
  batch, two sims ($0.069): n11 = n10 + break_y 0.49 -> 0.455 + lapel notch 0.035 -> 0.020; n12 = the same with notch
  0.027. notchv.py <pkl>: the V per side (apex = collar gorge end, collar point, lapel point; angle 3D / front view,
  mouth, both edges).
  - (1) NOTCH V. n10: V 74-77 deg (3D), mouth 47-50 mm, collar end edge 40 mm, lapel top edge 38 mm (= the draft's
    notch 35 mm). n11 (notch 20 mm): 67-73 deg, mouth 37-39, lapel top 20 mm, but the apex 10-15 mm LOW (a shorter
    notch runs the collar further down the gorge). n12 (27 mm): 81-86 deg, mouth 50-53, apex 5-9 mm low. A 10-15 mm
    mouth with a 40 mm collar end edge is not geometry: the concept's notch has short arms (~20 mm each); ours has
    the collar's full end width as one arm. In clay the lapel's top edge past the collar end is a faint line (the
    lapel lies 3 mm over its forepart, same normal, a 0.8 mm rendered sheet): the step that reads is the collar end's.
    Not yet crisp. Levers left: a narrower collar END (the draft's end width / point), a lapel edge rendered at the
    cloth's real thickness (3-4 mm: wool + canvas + facing).
  - (2) CHEST V: the break raised to the concept's (396-404 vs 398 mm below the chin; was 430-436) but the chest
    opening stayed ~160 mm (concept ~182): the roll lines' top sits in. Not fixed; lever: the roll line's top
    (lapel roll_stand) or the neckline width.
  - (3) LEFT SIDE NECK: in the front neck view the collar's stand turning the side neck reads as a ridge with a gap
    under it (closes: clean). Per-station check: no fold > 100 deg; one 93 deg crease at the station where the
    transition starts (st 57 / 8), outer edge 0.4-0.5 of its cut length there. Transition columns now at their cut
    length (transition_length, default on): no visible change. Left as is.
  - Sheet workspace/cloth_renders/c12_g8_sheet.png (concept | n12 | n10). At figure scale n12 ~ n10.
  - DISTIL (Joe's question, via the coordinator): cloth_guide.md gained the cloth12 rules (fault table: lopsided
    result -> mirror check of every sim input place-only; measure what you name; made pieces at their cut length /
    width; transition one smooth edge; lapel roll; notch rim; button stance; tuck never into the body; stencil
    shadows; one stage run at a time), "Judging what you see" (shadows off, both sides, one run) and a new section
    "Made pieces constructed after the drape (construct)" (the construct key was undocumented). Background (how
    artists work, sources, the skirt and suit-trouser walk-throughs, where each lesson lives) moved to
    cloth_background.md (guide topic cloth_background): guide 112 -> 102 KB. PROPOSED further cut (not mechanical):
    the fault table's rows whose fix is "Fixed: ..." (closed bugs, ~40% of its 25 KB) to the background as history,
    and "Tool reference" (9.6 KB) folded into each tool's guide(topic=<tool>).
  - Spend this agent: $0.541 (this gate $0.069).
  - STATE: best c12_n12c (gorge_drop 0.10, collar point 15 mm, stance 12 mm, break_y 0.455, notch 27 mm) or n10
    (break 35 mm low, notch at height); gates pass on both. NEXT: the notch's arms (collar end width), the chest V
    (roll line top), shoulders, CB crossings, the shirt re-sim.
- Gate 9 (branch cloth12c off main c755cbc; Joe's standing rule: a sheet + blunt read each gate, carry on).
  - GUIDE CUT: 6 closed-bug fault rows (the code prevents them: white flecks from the clean-up, crossing-search
    memory, "0 stitches" for open fronts, mesher slivers, ZOZO zero-area collider faces, the broken-start memory blow)
    moved to cloth_background "## Closed faults (history)"; rows with live advice kept (made_reshaped check, band ease,
    frame-0 collider check, trousers' under_cap). Tool reference -> cloth_tools.md (topic cloth_tools; every
    guide(topic=<tool>) still resolves: guidechk.py). cloth_guide 102 -> 91 KB.
  - Render: cloth.render objects take "offset" (Solidify; 0 = the sheet is the cloth's middle). The jacket at 3.5 mm
    centred (c10ship jk_th / jk_off): the lapel edges gain a faint rim, the collar end's own step reads LESS (the
    shell's thickness meets it). Not adopted; the notch's read is the draft's.
  - Sims (one batch, $0.064): n13 = n12 + collar height_front 0.028 (the END 28 mm wide, the back stays 39) + notch
    0.025 + gorge_drop 0.095; n14 = n13 + lapel roll_stand 0.028.
    n13: notch 61 / 59 mm below the chin (concept 63 / 56), break 396 / 404 (398), collar end edge 29 mm, V 79-84 deg
    front view, mouth 47-49 mm; gates pass. The collar END reads as a collar's end, not a strap; the V still not a crisp
    dark gap (the lapel's top edge beyond the collar end lies flush on its forepart).
    n14 (roll_stand 0.028): the chest opening did NOT widen; the right front closed (43-68 mm from centre vs left
    59-82): rejected. The chest V (~155 vs ~182 mm) is open.
  - Sheet workspace/cloth_renders/c12_g9_sheet.png (concept | n13 | n12). Spend this agent: $0.605.
  - STATE: best c12_n13c (q_n13.txt line 1). NEXT: shoulders, CB collar crossings, the shirt re-sim; chest V (the
    neckline's front width / roll line top), the notch gap's depth.
- Gate 10 (shoulders). Checklist (ck.sh <t> -> out/check_<t>.txt) on n13: shoulder_width 514 mm front view (concept
  482, +6.7%), chest 435 (397), front_hang 53 mm (rule -40..10), hem_sweep -14%, cuff_show 12 mm (18), pockets none
  (the concept has flap pockets). Three single-change sims ($0.128):
  - n15 block shoulder_ease -0.04: the shoulder POINTS came in 13 mm a side but the front-view width went UP (519):
    the width is the sleeve heads, not the shoulder seam; front_hang 75. Rejected.
  - n16 sleeve cap_ease 0.045 -> 0.03 (CHOSEN): shoulder width 509 (within tolerance), hem_sweep -9%, gates pass, notch
    61 / 59, break 396 / 402; cuff_show 6 mm (the sleeve hangs lower: next, sleeve length_bonus).
  - n17 flap pockets (run.py addop=<json op>, a pocket op type flap on the front): the fronts got heavier and wavier,
    front_hang 90, notch asymmetric: rejected for now (the checklist still says "pockets none": it reads
    design.details, not the ops).
  - The "spike at a shoulder seam" was the MADE COLLAR's top at the side neck, seen edge-on from behind: the final
    settle pushed each transition point off the shirt's stand on its own, a ragged silhouette. Fix: the transition
    smoothed and settled again after the final settle (collar_options settle_smooth, default 2): a rounded top
    (out/spike*.png). No-op where there is no transition.
  - Sheet workspace/cloth_renders/c12_g10_sheet.png (concept | n16 | n13), shoulders c12_g10_shoulders.png.
    Spend this agent: $0.733.
  - CB collar crossings (item 4): 0 visible shirt x made collar on every build since cloth11's stand clearance; closed.
  - STATE: best c12_n16c (q_n16.txt line 1). NEXT: cuff show (sleeve length_bonus), front_hang (side panel hem spring:
    run.py can only patch every contour op at once: add an index), the shirt re-sim, pockets (with a front check).
- Gate 11 (front hang, cuff show, run-to-run variance). run.py gained op:<name>@<k>.<field> (only the k-th op of
  that name: the jacket has two contour ops, centre back and the side panels). Four sims ($0.183 with n21):
  - VARIANCE: n21 = n16 re-keyed by a no-op (layer_gap 0.005 -> 0.0051): every checklist number within 2 mm of n16
    (front_hang 54.2 / 53.7, cuff 5.5 / 6.2, hem 435 / 437, chest 440 / 439, shoulders 509 / 509, notch +-2 mm). So a
    one-sim difference over ~5 mm is the change, not the solver.
  - n18 side-panel hem spring 6 -> 0 mm (the guide's tent fix): front_hang 54 -> 66, hem sweep 437 -> 425: worse here.
  - n20 hem spring 6 -> 12 mm: front_hang 55 (same), hem sweep 389 (-48 mm): the side panels' spring is not this
    jacket's front-hang lever. Rejected.
  - n19 sleeve length_bonus 0.018 -> 0.008: cuff show 6 -> 4 mm (WORSE: the cuff_show measure does not move with the
    sleeve's length the way its hint says), front_hang 46, hem sweep 454 (in tolerance), but 8 visible shirt x jacket
    crossings (n16: 0). Not adopted.
  - The shirt: simulated on current main this session (c12_b0's shirt, job d038...); alone it reads clean (collar,
    band ends under the points, top button open): out c11_w_<t>.png top rows. No re-sim needed.
  - Sheet workspace/cloth_renders/c12_g11_sheet.png (concept | n19 | n16): visually the same at every scale.
  - Spend this agent: $0.916.
  - STATE: best still c12_n16c. NEXT: front_hang (53 mm; levers left: canvas / chest ease / the fronts' balance at the
    shoulder), chest width +10% (chest_ease 0.06 -> 0.03), the cuff_show measure, pockets.
  - CORRECTION (gate 11): I read n18 and n19 SWAPPED off a combined grep. Per file (ck.sh, one at a time):
    n18 side-panel hem spring 6 -> 0 mm: front_hang 54 -> 46, hem sweep 437 -> 454 (within tolerance), cuff 4.3,
    0 visible crossings: the guide's tent rule holds here too. n19 sleeve length_bonus 0.018 -> 0.008: cuff show 6 -> 10
    mm (the measure DOES track the sleeve: nothing to fix in it), front_hang 66, 8 visible crossings. n20 spring 12 mm:
    front_hang 55, hem sweep 389. So: best = n18 (q_n18.txt line 1). Lesson: one file per reading (the grep -h of
    several checklists interleaved their lines; read each build's numbers from its own file).
- WRAP (2026-10-14; Joe: the jacket is done for now). Best = out/c12_n18c.pkl (q_n18.txt line 1: gorge_drop 0.095,
  break_y 0.455, lapel notch 0.025 / stand 0.012, collar point 0.015 / height_front 0.028, sleeve cap_ease 0.03, side
  panels' hem spring 0); gates pass (0 skin px, 0 visible crossings), notch 61 / 59 mm below the chin (concept 63 / 56),
  break 398 / 403 (398), fronts symmetric, front_hang 46 mm, shoulders 504 mm (482), hem sweep 454 (482).
  - Chest-width batch n22 (chest_ease 0.06 -> 0.03) COST $0.664: the job did not stall, it crawled (frame 116/150 at
    21 min, ~10x normal) and failed at 22 min ($0.397); stage.sh's next round resubmitted it ($0.267 until cancelled).
    stage.sh now never resubmits a job it sent before (sent.txt) and times jobs out at 8 min. Same ease that hung
    cloth11's gc2: on this jacket a tighter chest makes ZOZO crawl.
  - Buttons: built on the finished drape (closures.buttons_mesh, after the sim), drawn by look_cloth and export; the
    jacket had both all along at the stance on the wearer's right front (closure front.L over front.R); only the
    scratch harness didn't draw them (c10ship now does, jbtn=1). No sim. Note: their MARKS are mesh vertices, so adding /
    moving buttons re-keys the sim; anchoring open closures' buttons by pattern position instead would change every
    buttoned garment's mesh once (a default for Joe).
  - Guide: "Rules first" list at the top of cloth_guide.md (9 rules, each pointing at its fault row / stage), fault
    rows for a detail queued for a sim and for a crawling ZOZO job; front hang / noise / front-view width lessons.
  - FINAL sheet workspace/cloth_renders/c12_final_sheet.png (concept | n18 | c11_gc1, shadows off).
  - STILL OFF vs the concept: the notch V is an edge, not an open dark gap; the chest opening ~2.5 cm narrow (~155 vs
    ~182 mm at the chest); the chest +10% wide (440 vs 397; a tighter ease makes the sim crawl); the fronts still 46 mm
    forward of the body (rule <= 10); cuff show 4-6 mm (18); no flap pockets or breast welt (one try made the fronts
    heavy); buttonholes only in the textured maps; a small ridge where the collar stand turns at the side neck.
  - Spend this agent: $1.58 (of it $0.66 the n22 chest batch).
  - STATE: done, merge-ready. NEXT (when the jacket comes back): the notch gap's depth, the chest opening (neckline
    front width), pockets with a front-hang check, button marks without re-keying (decision).

## dress-tess (2026-10-14, "dress-tess" agent, branch `worktree-agent-ac06d0eb5553e576b`; Tess's outfit, model dt_tess)
SUMMARY (one page; kept current). The test: do the cloth guide's rules carry from Garrett's suit to a new person and
new garment kinds (jeans, a knit sweater, an open lab coat)? Model `dt_tess` = tess_a1's spec (MakeHuman body, the
shoes.py grey trainers, socks; hair th_W18 left alone). References (never copied): s0urc3/docs/img/tess_ref_full/
tess_apose_v4_70110ef2.png (A-pose; 1.24 mm/px, HPS at y ~280) and tess_concept_v1_db4c5da5.png.
Scratch DURABLE in /mnt/data/hifipushie/dress_tess/: cloth12's env.sh / run.sh / q.sh / stage.sh (cloth12's FIXED copy:
never resubmits a sent job, 8 min job timeout; sent.txt) / bl.sh / have.sh / run.py retargeted; dg.py <model> <garment>
<json> [stages] (design sheet + checks, images out/<model>_<garment>_<tag>_*), sheet.py (REFERENCE | ours), pz.py /
side.py (piece extents, pocket outside its piece), meas.py (the body's tapes), tests.sh. Designs: j*.json (jeans),
s*.json (sweater), c*.json (coat).

### 0. The outfit in words (from both pictures)
- JEANS: dark indigo, near black-navy (#171b26), five-pocket, mid rise (the top hidden under the sweater's band),
  straight leg, relaxed at the thigh, no crease; long: the hem stacks on the trainers' tongue in 2-3 soft folds, no
  sock showing; soft knee folds; heavy denim (holds broad folds, no fine crinkle).
- SWEATER: mustard / ochre (#b07a26) crew-neck knit, medium gauge, relaxed (falls straight from the chest, blouses a
  little over the band); ribbed neckband ~20 mm sitting close at the base of the neck; ribbed hem band ~50 mm whose
  bottom edge is ~45 mm under the natural waist (485 mm under the HPS), over the jeans' waistband; sleeves hidden
  under the coat; knit drape: soft, rounded, no crisp creases.
- LAB COAT: white (#e9e8e3) poly-cotton twill, light, unlined, no pads; knee length (hem ~885 mm under the HPS),
  straight, single-breasted with 4 buttons ~130 mm apart from the break (~235 mm under the HPS) down to mid-thigh,
  worn OPEN: the fronts hang ~15-20 cm apart at the chest, closer below (the A-pose arms pull them to the sides);
  notched lapels, notch ~60 mm under the HPS, lapel ~70 mm wide, soft roll; collar low round the neck; chest patch
  pocket on her LEFT (~110 x 130, top ~185 mm under the HPS), two hip patch pockets (~170 x 190, top ~445 mm under
  the HPS); set-in sleeves, straight and loose, to the base of the hand; many long vertical folds from shoulder to hem.
- LANYARD: dark blue strap round the neck over the sweater, clip, ID badge in a blue holder at mid chest.
- SHOES: grey trainers, white soles (the existing shoes.py stand-in on tess_a1).

### Rules used / rules missing (running list)
USED (carried over): length + collide shoes (trousers); start seam gaps read before simming (stage 4); a rib band
shorter than its edge (KB); waist_drop for mid rise ("Trousers read high-waisted"); fix in the pattern / construction.
From tess2's notes, NOT the guide: worn_top for a knit whose neckband is laid from the seam; a hem band on torso +
align; sleeve length_bonus +0.06 on a worn_top knit.
MISSING / WRONG (fixed in code, or written into the guide):
1. jeans and suit_trousers are kinds, but stage 1's kind list doesn't name them (found via garment_reference).
2. Stage 4 says trouser legs start on tubes (side 15 / inseam 8 mm); jeans started as SLABS (median 160 / p95 232
   mm): `_leg_tube` took exactly one front + one back piece per leg, and jeans have pocket_side / yoke too. FIXED
   (cloth._leg_tube: the leg's own pieces are the ones reaching the hem): median 23 / p95 162 mm.
3. A drafted knit (block knit, details rib_neckband / rib / rib_band) failed "a neckband piece (none in the pattern)"
   with nothing saying how to make one (`generate` is only in cloth_background, for own pieces). FIXED: the KB's band
   details carry `draft.generate` (tess2's proven bands), compile_sheet adds them; a garment's own band of a name
   replaces the design's.
4. `block_options.hips_ease` does nothing unless `fitted: true` (the knit hangs straight from the chest).
5. A body cut to the waist (`length` <= hpsToWaistBack + 3 cm) names its hem points cbWaist / waist, not cbHem / hem:
   hem-band chains must follow (KeyError otherwise).
6. A hem band laid from the seam (wrap seam, like the neckband) started 135% stretched: keep torso + align.
7. The guide's own `closures: [{"name": "front", "state": "open"}]` was refused at save ("needs name and over"):
   FIXED (closures.validate: an entry without over is an overlay by name).
8. A patch pocket on one side after `unfold` (a chest pocket on front.L) was "sewn to nothing": FIXED (op_pocket:
   after unfold its tacks are stitches).
9. Jeans back pockets sank through the backs in the sim (31 crossings, CORRUPT): FIXED as construction (a patch
   pocket is topstitched flat): `cloth.seat_patch_pockets` lays each `lies_on` / face-out piece on its piece as it
   finally lies, 1.5 mm out (+1 mm steps where chords cross), kept only if nothing new crosses: 31 -> 0.
10. tests/test_cloth_workflow.py ran only the tests above its `__main__` block (6 never ran as a script): moved.

### Jeans
- j1 ({kind: jeans, fit straight, denim, collide shoes}): every pre-sim check passed first time. Sim dj1 ($0.044
  coarse + fine): reads as straight trousers, clean hang; CORRUPT from the pockets (fixed above; re-judged on the
  cached sim: "fits", 0 crossings). Wrong against the reference: no stack (sock shows at the front: cut to "break"),
  the band about at the natural waist (high), almost no folds, colour too blue.
- j2: waist_drop 0.07, length "floor", colour #171b26.
- STATE (step 1): jeans j1 judged, fixes 2/7/8/9 in code with tests (cloth test set 15 files rc 0, 0 skipped); j2 sim
  queued; sweater s6 and coat c2 pass their pre-sim stages. Spend $0.044.
  NEXT: judge j2 -> jeans sheet; sweater over the jeans; coat over the sweater.
  RESTART: scratch /mnt/data/hifipushie/dress_tess (source env.sh via run.sh). Checks: bash run.sh dg.py dt_tess
  <garment> /mnt/data/hifipushie/dress_tess/<design>.json [stages]. Sims: echo "<tag> dt_tess <garment>" > q_x.txt;
  bash stage.sh /mnt/data/hifipushie/dress_tess/q_x.txt 3 (ONE at a time; cached results: BROKER=1 bash q.sh q_x.txt);
  renders workspace/cloth_renders/<tag>*.png; spend from stage_*.out "batch done" lines.
- j2 sim (NICO-TOP, $0): band now 0.965-1.004 m (natural waist 1.035), still a sliver of sock at the front: the
  stand-in shoe is a SLIPPER (no tongue): the hem rests on its vamp, ~66 mm up, below which the throat shows sock. A
  raised shoe collar (box region top 96 -> 118 mm) gave an upward cap: the hem start stopped on it and the leg folded
  through ITSELF; stage 4 only warned (any piece crossing itself was excused) and the sim crawled at 4.7 s a frame to
  its time limit. FIXED: (11) a piece through itself is excused only where it is sewn / stitched to itself (cuff lap,
  sleeve underarm), else stage 4 FAILS; (12) `_hem_on_shoe` gathers over max(LEG_BREAK, deficit / LEG_GATHER 0.6), so
  rows never turn over. The shoe got a TONGUE instead (blob shoe_tongue.L, layer 1, part shoes).
- j3 (length 1.05 m from the waist, for a stack): CORRUPT at the hem (54 crossings, 2-3% crumpled), the hem wraps
  under the shoe: too much length for a 2 cm sim to stack. Rented $0.077 (231 s on a 4090: the same job ran 4.5 s a
  frame on NICO-TOP). Dead end at this resolution.
- j2t (floor + tongue): fits, 0 crossings, seams closed; rented $0.032. SHEET workspace/cloth_renders/
  dt_01_jeans_sheet.png. My read: straight jeans at the right rise and colour; WRONG vs the reference: her jeans are
  fuller from the knee down (hem ~370 mm round vs our 344, knee ~400 vs 370) and stack on the trainers' tongue with
  2-3 folds; ours taper slightly, hang clean (almost no folds) and show a sliver of sock at the front.
- j4: knee 0.20 / hem 0.19 (half girths: 397 / 380 mm round) for her fuller leg; NICO-TOP.
- Spend: $0.044 (j1) + $0.077 (j3 rented) + $0.032 (j2t rented) = $0.153.
- j4 (NICO-TOP $0): fits, 0 crossings; fuller below the knee, hem covers the tongue. Coordinator: "smooth dark SLACKS,
  not jeans": (1) fabric behaviour, (2) fuller below the knee, (3) denim details (contrast topstitching, yoke, pocket
  design, loops, rivets, coin pocket) and indigo wear (paint); say in the guide which is construction vs paint.
- (13) FOUND: ZOZO reads only cloth_job.PHYSICAL (5 presets), never the KB fabric's gsm / bending length: cotton_twill
  runs as 400 g/m2 denim, french_terry / rib_knit as 180 g/m2 jersey (B 1e-6), and denim's own preset is soft (B 3e-5 =
  19.7 mm bending length, KB 22-30). Per garment: fabric {"preset", "physical": {"density", "bend"}} with B = w g c^3.
  NOT changed as a default (it would re-key every cached sim): coordinator's call.
- j5 = j4 + denim B 6.9e-5 (26 mm) + golden thread (#b8843a): fits, 0 crossings, folds rms 3.3 mm (unchanged): in a
  straight A-pose stance stiffer denim still hangs clean; her knee / ankle folds are worn-in memory and a stack the 2 cm
  sim can't hold (j3). Guide: "What makes jeans read as JEANS" table (fabric+sim / pattern / construction / detail
  maps / paint; arcuate stitching, rivets, coin pocket and cloth wear paint NOT built). Jeans: 6 rounds (j1, j2, j3
  dead end, j2t, j4, j5).
- Sweater s7: s6 + over jeans + fabric {jersey, physical 0.30 / 8e-6}; pre-sim stages pass (hem band closing seam
  starts 30 cm open: WARN, as tess2's). Sim on NICO-TOP.
- (14) Joe: "use the real cloth values": ZOZO now gets the KB fabric's numbers by default (commit 5cccb4f, alone for
  merging): density = gsm / 1000, B = w g c^3 (garment_design.kb_physical via cloth.fabric); presets only as a
  fallback with a stage-3 WARN; test test_cloth::test_a_kb_fabrics_real_numbers_reach_the_job.
- BODY SWITCH: Joe picked tess_n1 (GNM-native head). dt_tess now has tess_n1's `base` (v22, to_n1.py). The body is
  NOT the same below the neck: neck 297 -> 330 mm round, neckHeight 40 -> 45, shoulders 350 -> 336, chest 847 -> 838,
  HPS 24 mm lower and 27 mm further forward (1.426 -> 1.402 m). Every garment re-drafts from it.
- j6 (= j5, fabric "denim" from the KB: 395 g/m2, B 6.81e-5) on n1: fits, 0 crossings, folds 3.3 mm.
- MOVEMENT SETTLE (Joe: one try): garment key `move` {"knees": 40, "steps": 3} (cloth.knee_bend / _move_poses: after
  the pose stage's arms the collider curls each lower leg back 40 deg and returns, then gravity). dj6m: fits, 0
  crossings, folds 3.3 -> 3.4 mm, NO memory folds to see (out/move_cmp.png). Why: the cloth rests on its flat pattern
  and is elastic (no plasticity in our ZOZO jobs): it springs back once the knee straightens; and in method "settle"
  the pose stage was 30 frames (fixed: 72 with a move). Worn-in folds need plastic set (ZOZO has a plastic_state) or
  authored folds (detail.folds / a Blender hand pass). Test test_cloth::test_a_knee_move_curls_the_shins_and_comes_back.
- BODY: Tess's head frozen at tp_h3 (tess_n1 + jaw / chin): dt_tess v26 carries tp_h3's base (neck 331.7 mm round,
  +1.7 over n1; HPS +2 mm). Jeans and sweater re-simmed on it (dj7, ds9).
- Sweater s8 (on n1; fabric french_terry from the KB: 315 g/m2, B 8.5e-6; length 0.487 m from the HPS so the band's
  lower edge lies ~2 cm under the jeans' front top; over jeans; worn_top): coarse sim fine (NICO-TOP $0); the FINE
  start was refused locally (31 triangles over 1.6x, neckband 2.0x, hem band 1.9x): tess2's open item (folded bands'
  fold rows cross themselves when the coarse sim is carried onto the fine mesh) is still open. s9 = s8 +
  fine_settle false (tess2's interim: the coarse drape carried to 1 cm).
- stage.sh: a layered garment's build writes its under garment's job too; the same job came up in two logs and the
  broker refused the batch ("appears twice"): de-duplicated.
- Rounds so far: jeans 7 (j1, j2, j3 dead end, j2t, j4, j5, j6/j7 re-sims on new bodies), sweater 9 design passes (s1-s9;
  s1-s5 pre-sim only), 1 sim before the body switch.
- s9 (tp_h3, over jeans, fine_settle false; NICO-TOP $0): CORRUPT (neckband 29% / cuffs 9% / hem band 11% crumpled,
  armhole seams 24 mm and cuff seams 36 mm open). Close-ups: the neckband was INVISIBLE: (15) a generated band's
  `height` is its CUT height; folded in half it shows half: tess2's 22 mm neckband was an 11 mm rim, and stage 2's
  neckband_width reported 22 and passed. FIXED (bad56b4): stage 2 reports folded bands' finished heights
  (neckband_width, cuff_height, band_height), KB cuts 44 / 100 / 100 mm (22 / 50 / 50 finished).
- s10 = KB band sizes + armhole_depth 0.06 + sleeve length_bonus 0: neckband and hem band now READ (sheet); still
  CORRUPT (neckband 15% crumpled, cuffs 5%), armhole seams 30 mm open, cuff ring seams 48 mm open. Start gaps
  (sg.py: per seam, place_only): sleeve caps 76 / 143 mm, underarms 79, neckband ring 76, cuff rings 92-103, hem band
  ring 310 (!): the rings are laid at their CUT length round a bigger girth, the sim can't close them.
- (16) `wrap` "seam" + `stretch_on: true` (lay a band stretched ON the edge it is sewn to) and `dir: "down"` (a hem
  band runs down): ring closing seams 76 -> 4 mm (neckband), 310 -> 2 mm (hem band), but the start is 97-146%
  stretched and lies inside the contact standoff (neckband stands up the neck like a turtleneck, hem band flares):
  NOT usable yet (s11, not simmed). Kept as opt-in keys.
- SWEATER SHEET workspace/cloth_renders/dt_02_sweater_sheet.png (s10). My read: reads as a mustard crew-neck
  sweater from the front, relaxed, blousing over the band like hers, the band at the right height; WRONG: the hem
  band reads as a folded roll, not ribbed (no rib texture: detail maps have no rib), the neckband ruffles at the back,
  armhole holes and ruffled cuffs (both hidden under the coat). Sweater: 4 sims (s7 cancelled, s8 fine start refused,
  s9, s10), 11 design passes.
- Coordinator after the sweater sheet: don't leave the sweater's faults (the figure is seen without the coat too):
  (1) armhole / underarm seams 30-48 mm open, (2) band starts (cut ~10-20% short and stretched on, distributed),
  (3) the back neckband ruffle; rib texture is paint (missing).
- (17) FOUND: ZOZO held EVERY fabric to its 5% strain limit (cloth_zozo default), knits too (only declared bands
  got more): a knit couldn't stretch onto the arm or take its bands. AND the start: a knit sleeve 12% narrower than
  the deltoid (knits have negative ease) was laid as a bigger cylinder 12 mm off the arm (`gap`), so its underarm
  seam started 79-116 mm open; then the start relaxation took every triangle back to 3% / 2%. FIXED (7355361):
  `cloth.strain_limit_of(g)` (the fabric's own limit, French terry 20%; wovens keep 5%; the garment's zozo wins; in
  the job, the key (knits only), the stage-4 check, the fine settle), knit sleeves clear the arm by 4 mm and wrap
  each row's own girth (stretched on up to 0.8 x the limit), the start relaxed to 0.6 / 0.5 x the knit's limit.
  Underarm start 79 -> 12-20 mm.
- (18) knitted_rib (KB: collar, cuff, hem): a KNITTED sweater's rib is single-layer, knitted on, not a folded strip;
  laid stretched ON the edge (wrap seam stretch_on; hem dir down). The folded strip's flap turned on a cone was what
  started 97-146% stretched. Rings at the start: neckband 76 -> 27 mm, hem band 310 -> 38. The cuff ring still starts
  96 mm open (the arm's radius at the wrist reads the hand: 51 mm).
- s15 (knitted_rib everywhere, length_bonus 0, NICO-TOP $0): 0 crossings, bands not crumpled, underarm / cuff / hem
  seams closed (<= 2 mm), the neckband smooth at the back (no ruffle); still open: the sleeve CAP at the underarm
  (9 of 54 pairs, max 20 mm: small holes at the front armpit; the cap starts 62 / 113 mm off the armhole), cuffs 5%
  "crumpled" (the report's metric on a single-layer band at a bent wrist). The neckband now reads flush (no rib, no
  thickness): it wants rib texture (paint) to read as a band.
- (19) The coat's stage-4 FAIL "front.L through itself": a lapel pressed onto its own forepart is construction:
  sewn_crossings now also excuses a piece crossing itself where it has a fold line (my rule 11 was too strict).
- Coat: c3 refused locally twice ("start inside the standoff from the garment under it", back at the waist): the
  coat at 18% chest ease had no room over a sweater that is itself +17.5% (the guide: body girths stay the bare
  body's, give the ease for what's under it): chest 0.26 (seat +30%, the regular band's top; hips_ease does
  nothing on an unfitted block: same rule as the knit). layer_gap 0.006.
- MACHINE RULES (coordinator / Joe, 2026-10-14): every Blender runs under /mnt/data/hifipushie/bin/capped, which loads
  a GPU lock around each render call (the desktop froze sharing the GPU); "gpulock: waited N s" is queueing, not a
  hang; never start Blender outside capped, never take the lock around whole scripts. Size check renders to what is
  judged: ~512 px close-ups for an armpit / cuff / band / collar, ~768 px for a whole garment; the smallest thing judged
  spans 3-4 px or more; don't read sheets over ~1600 px when a crop answers; full multi-view sheets only for the gate
  sheets sent to the coordinator.
- Coat (lab coat over the sweater, c9 -> c10): chest ease 26% (an unfitted block's seat follows the chest: 30%);
  armhole_depth 0.16; layer_gap 0.006, under_cap 0.004. The coarse start was refused locally 3x (1.2-2.3 mm inside the
  standoff from the sweater at the back armpit): (20) the exact clear's 8 rounds weren't enough; 24 clear it (5ab54fa,
  also in the fine start). The coat's coarse sim ran (NICO-TOP); its FINE settle died at frame 0 on NICO-TOP
  ("contact starts overlapping", a coat vertex vs the sweater collider; the fine start's separation from the collider
  was 0.00 mm with its made pieces held): c10 = fine_settle false (re-keys the coarse: rented, to save time).
- (21) A chain of layered garments re-sims from the bottom whenever anything upstream re-keys (a code change to the
  jeans' key re-simmed jeans, sweater and coat in turn): batch upstream changes before simming the outer layer.
- PROCESS (2026-10-14, docs/notes/gates.md on main): every piece DESCRIBED first as a checklist
  (workspace/checklists/tess_sweater.json, git-ignored), every item MEASURED every round (table on every sheet),
  LOOKED at by the blind reviewer (/mnt/data/hifipushie/bin/review, pairs per region) until it PASSES, APPROVED only
  by Joe / the coordinator (workspace/approved.json). No sim until the pattern passes its checklist items. Sims go to
  the RENTED fleet by default (Joe: cloth budget $5/day), NICO-TOP (LOCAL=1 in stage.sh) as the fallback; never
  resubmit a failed job; timeouts set.
- Joe on the sweater (ds17): "These arm holes make no sense": the armscye ran deep, its seams read as side lines to
  the hem. Measured (armpit.py on the results): the sleeve's lowest seam point was 66-79 mm under the body's armpit
  in every round (ds9 66, ds10 79, ds15 72, ds17 74). CAUSE (22): the bodice / knit block places the underarm
  `waistToArmpit` up from the waist along the BACK's tape (chest_y -227 mm under the HPS), but on Tess the back's tape
  is 18% longer than the vertical (447 HPS to waist against 380): the draft's underarm lands ~41 mm under the armpit in
  the world, and the knit sags ~30 mm more in the sim. Not the hoodie kind and not the armpit-hole fix. GATES added:
  stage 2 `draft_underarm` (where the draft's armhole bottom lands on this body, WARN outside 0-35 mm) and the report's
  `underarm` line on the result (`underarm_drop`, 10-45 mm). s19: armhole_depth -0.15 -> the draft lands 10 mm under
  the armpit.
- The first table (ds17 against tess_sweater.json): neckline_drop_cf 12 mm (ref 35-60) FAIL (a mock neck); neckband
  17 mm (18-30) FAIL; hem band bottom 456 (465-505) FAIL; hem band height 47 PASS; blousing 1.10 (1.00-1.06) FAIL;
  side lines seen from the front FAIL; underarm 74 (15-45) FAIL; chest ease +17.5% PASS; knit surface / neck rib /
  hem rib FAIL (none); colour #b07a26 vs #946a2a FAIL; clean: 0 crossings but cuff ring seams 43 mm open FAIL.
- (23) Knit surface: detail "surface": "knit" (cloth.knit_surface: stockinette V columns, wale 4.5 / course 3.6 mm,
  k2p2 rib on the band roles, yarn fuzz in the shade); fabric sweater_knit (KB: 375 g/m2, bending length 13 mm, 30%
  stretch). The hoodie kind's seams are topstitched: a knit's are pressed_to_side.
- (24) The coordinator made the back-tape underarm the DEFAULT for every block (block option underarm_rule
  "waist_tape_legacy" = the old rule) and sleeves set into the armhole by default (set_sleeves "free" = old); Garrett's
  approved su_gc garments pinned to both. Garrett's jacket c12_n18 measured: the under sleeve's armhole bottom 73-77 mm
  under his armpit at the start, 79-80 in the result (for Joe).
- s19 -> s22: placed 17-19 mm, the RESULT still 62-67 mm under the armpit: the underarm point slides 45 mm out and
  down the A-posed arm in the sim (x 0.167 -> 0.212). Not the stitches alone (set_sleeves hold: no change), not
  biceps ease (0.18: no change). CAUSE (25): the knit sleeve's cap was 201 mm tall, 108% of the armhole depth (the
  draft LOGGED "!! the cap stands higher than the armhole is deep" and no gate printed it): its underarm seam was
  292 mm for an arm that needs ~350, and with the cuff held at the wrist the short underarm hauled the armhole down
  the arm. FIX: stage 2 now prints every "!!" line of the draft log as a WARNING and the cap height as info; s24 =
  biceps ease 35%, cap eased 6% onto the armhole (knit), chest ease 12% -> cap 143 mm (77%), underarm seam 353 mm.
- s22's fine settle failed on the rented box (exit 1, "the step is held by dynamic edge 13512, time of impact
  1.5e-4": a collision stall); not resubmitted.
- Spend $0.70 (s19 0.077, s21 0.19, s22 0.12, c11 chain 0.11 before it was stopped: the sweater changed under it).

## Handover 2026-10-14 17:30 (dress-tess, Tess's outfit; model dt_tess)
Branch `worktree-agent-ac06d0eb5553e576b`, worktree /home/joe/dev/hifipushie/.claude/worktrees/agent-ac06d0eb5553e576b,
last commit = the one adding this handover (after b7b8e7f). Commits not merged: 5cccb4f (KB fabric numbers, standalone,
mergeable alone), the rest of the branch since 118bf2f. Cloth test set last run rc 0 at f964c2e; the LAST change (knit
sleeve cap left at its armhole, cloth.place) is committed WITHOUT a full test run: run tests.sh first.

### Scratch /mnt/data/hifipushie/dress_tess (DURABLE)
- env.sh / run.sh <script> [args] (worktree code, capped, peak RSS) / q.sh <queue> (each line "<tag> dt_tess <garment>
  [key=json ...]" -> run.py: build, report, renders cloth_renders/<tag>*.png, out/<tag>.npz + .pkl).
- stage.sh <queue> [rounds]: broker batches per round; RENTED fleet by default (8 min), LOCAL=1 = NICO-TOP (30 min);
  TMIN overrides; NEVER resubmits a job in sent.txt (remove a line only for a job that never ran); de-dups jobs.
- bl.sh (oxidegen bundle client: list / status <batch> / cancel), have.sh (hands pulled results back), spend.py
  (sum of this agent's batches: python3 spend.py).
- dg.py <model> <garment> <json> [stages]: design sheet + checks, images out/<model>_<garment>_<tag>_*.
- Measures: msw.py <npz> (sweater checklist numbers), armpit.py <pkl> (underarm, side seams), ua_job.py <job key>
  (underarm in a coarse job's start vs result: cheapest check, no fine needed), slide.py <job key> (piece motion),
  sg.py <garment> (per-seam START gaps, place_only), cpt.py (a start point vs the collider), ua_other.py (another
  model), capvar.py '<design patch>' (sleeve cap height per variant), meta.py, front.py, pieces2d.py.
- Review: rv_renders.py <garments> <tag> region=x,y,z,zoom,views... (textured look_cloth close-ups out/rv_<tag>_*),
  rvpairs.py <tag> <dir> region=x0,y0,x1,y1@tile (ref | ours crops), then /mnt/data/hifipushie/bin/review <dir> pairs
  --context "..." --stage "the sweater: construction, fit, drape, fabric surface, colour" --not "the body and head;
  hair; other garments". sheet.py (gate sheets), lanyard.py (stand-in lanyard + badge parts), shoe.py (trainer tongue),
  to_n1.py (body base swap), pin_legacy.py (legacy pins).
- Designs: j1..j6 (jeans), s1..s24 (sweater; s24 = current), c1..c11 (coat; c11 = current).

### Model dt_tess
tp_h3's base (approved head, its body: neck 332 mm, NOT tess_a1's body), stand-in trainers with a tongue, lanyard +
clip + badge as model parts (lanyard / clip / badge / badge_card), garments jeans / sweater / coat (sweater "over" jeans,
coat "over" sweater: a change upstream re-sims the chain).

### Sweater (checklist workspace/checklists/tess_sweater.json; NOT approved)
- Current design s24 (kind `sweater`: knit block + set-in sleeve, knitted_rib bands, sweater_knit fabric; underarm
  -0.018, chest_ease 0.12, side seams contoured 15 mm back, sleeve biceps 0.35 / cap_ease -0.06 (cap 143 mm, 77%),
  low crew (neckline front 0.035), hem welt 0.88, set_sleeves into_armhole, stitch_stiffness 8, detail surface knit,
  #9a6a1f). Pattern checks pass; placed underarm 1.8 cm.
- In flight: NONE. Last: tag ds24b, coarse job_ba36176220f63d04 SUCCEEDED (underarm 38-39 mm in the result: PASS);
  its fine settle job_ba36176220f63d04_fine_settle FAILED (exit 1) and is in sent.txt: do NOT resubmit. s22 / s24 fine
  settles failed the same way ("step held by dynamic edge", collision stall). To get a usable result: add garment key
  `fine_settle: false` (re-keys the coarse: one new rented sim, ~$0.10) OR find the stall (results/<job>_fine_settle/
  failure/output.log; s21's fine settle worked, s22+ didn't: suspect the knit sleeve start or cap ease).
- Item table (best result per item): neckline top 36 mm under HPS (35-60 pass, s19); neckband 20 (18-30 pass);
  hem band bottom 499 (465-505 pass); hem band 48 (pass); blousing 1.03 (pass); underarm 39 mm (15-45 PASS, s24b coarse
  only); chest ease +15.6 (pass); knit surface present (review: too fine / printed-stripe ribs, v2 since); colour
  #9a6a1f vs #946a2a (not re-measured); clean: cuffs 18-41% "crumpled" (s21), cuff rings start ~100 mm open (the arm
  radius at the wrist reads the hand). Side lines from the front: not re-judged since s19.
- Last review: rv/s19/review.md FAIL. Open MAJORs: boxy / hem wider than chest (s24: chest 12%, welt 0.88 since);
  horizontal ripples across the chest; ribs read as printed stripes, body knit as a fine grid (knit v2 since: k1p1 by
  relief, wale 5.5 / course 4.5 mm, jitter); neckband stands up + faceted + a line round it (lean -20, hem 0 since);
  hem band flares, ledge at the join. NONE of these re-reviewed after s19: next round renders + reviews s24.

### Lab coat (NOT approved; no checklist written yet: write workspace/checklists/tess_labcoat.json first)
- Current design c11 (kind coat, bodice block, cotton_twill (KB), chest_ease 0.26, armhole_depth 0.16, length 0.89,
  lapel break 0.25, tailored collar, 4 buttons worn open, hip pockets + chest pocket on front.L, sleeve +0.06,
  layer_gap 0.006, under_cap 0.004, fine_settle false, open_lap false, construct collar). NOTE: with the new defaults
  its underarm rule changed (armhole_depth 0.16 -> 2.5 cm + 0.14 x waistToArmpit ~ 5.7 cm): re-check stage 4.
- Best result c10 (rented): reads as a white knee lab coat; CORRUPT (made collar x fronts 145 crossings), over front
  swings across (fixed by open_lap false in c11, unsimmed), collar stands up at the back, lapels 16 mm off, sweater cuffs
  show 4-5 cm. c11's own sim never ran (its chain re-simmed the sweater first; stopped).

### Jeans (NOT approved; checklist not written: tess_jeans.json)
- j6 = kind jeans straight, KB denim, waist_drop 0.07, length floor, knee 0.20 / hem 0.19 (half girths), collide shoes
  + soles, thread #b8843a. Result: fits, 0 crossings, seams closed. Coordinator's "slacks" faults: no folds (elastic
  cloth: no memory; a stack length went CORRUPT), no denim surface / wear paint, hardware missing (arcuate stitching,
  rivets, coin pocket), thread too faint, a sock sliver at the front hem.

### Findings for the guide (all in the notes above and cloth_guide.md)
- Underarm: blocks put it waistToArmpit up from the waist along the BACK's tape (18% longer than vertical on Tess):
  ~4 cm low. Now default for every block: hpsToArmpitBack (new tailor tape) + `underarm` (2.5 cm); legacy pins
  `block_options.underarm_rule: "waist_tape_legacy"` and `set_sleeves: "free"` written into su_gc's jacket + shirt
  (Garrett's approved c12_n18 measured 73-80 mm under his armpit: Joe's call; his redraft waits on Joe).
- The result's underarm drop (6 cm in every sweater round) was the SLEEVE START: sent 1 cm at a time down the arm to
  clear the bodice, the cap started 6-11 cm off and the stitches hauled the armhole down. Knits now keep the cap at the
  armhole (sewn crossings allowed): 6.4 -> 3.9 cm. Wovens unchanged (same fault likely: Garrett's 8 cm).
- Gates added: stage 2 underarm ESTIMATE + every "!!" draft-log line (the tall cap was logged, never shown), stage 4
  underarm AS PLACED with WARNING, report underarm on the result; KB kind `sweater`; knit strain limit from the fabric;
  KB fabric physics to ZOZO by default; folded bands report finished heights; knitted_rib choices; knit surface.
- Tried and failed (one line each): folded rib bands on a cone laid stretched (97-146% start); wrap seam hem band
  (135%); jeans stack length 1.05 m (CORRUPT at 2 cm); raised shoe collar box (upward cap, hem folded through itself);
  move {"knees"} settle (no memory folds: elastic cloth; parked, opt-in); biceps ease alone for the underarm; a
  lower cap alone for the underarm; layer_gap up for the coat's standoff (worse); NICO-TOP before oxidegen v143
  (leftover solver killed jobs).

### Decisions / rules
Rented GPU by default via oxidegen, NICO-TOP fallback; $5/day cloth budget; a pattern passes its checklist items
before any sim; never resubmit a failed job; Garrett's jacket redraft waits on Joe; Oxidegen still wants ONE batch of
4 real sims (run_s per job vs solo, spend) when 4 are ready; only Joe / the coordinator approve (bin/approve).
Spend so far: $0.93 (python3 /mnt/data/hifipushie/dress_tess/spend.py).

### NEXT, in order
1. tests.sh (cloth test set) on the last commit; fix if red.
2. Sweater: get a result for s24 (fine_settle false or fix the fine stall), measure (msw.py, armpit.py), render
   review crops (rv_renders.py front / neck / hem; add a side / underarm crop), review, fix the worst MAJOR, loop.
3. Write tess_labcoat.json and tess_jeans.json checklists; coat c11 pattern checks with the new defaults, then sim
   (with 3 other ready sims as Oxidegen's 4-at-once batch if possible).
4. Rib texture reads as paint/maps only; denim surface + wear paint for cloth are not built.

## Guide rewrite (2026-10-14, "guides" agent): history moved out of the cloth guides

cloth_guide.md went from 918 lines to a ~170-line core (describe the garment first, construction before solver,
stages with gates, self-review loop, common mistakes, known gaps) plus sub-topics cloth_design, cloth_construction,
cloth_sim, cloth_faults, cloth_blocks. What left the product (kept here as the record):
- The founding lesson (2026-10-03): a day of solver tuning (stiffness, shear, plasticity, mesh size) chased symptoms
  whose causes were construction: a sleeve cap with 44% ease, a collar stand stretched over a long neckline, a
  missing belt, a lapped pleat sewn shut, no sleeve placket, a coat with no lapel roll or facing, a collar never
  pressed, every fabric with the same bend.
- ZOZO real fabric numbers (2026-10-14, Joe: "use the real cloth values"): until then ZOZO ran every fabric on 5
  presets (cotton twill as 400 g/m2 denim, french terry as 180 g/m2 jersey, 8x too limp).
- Studio-only sim logistics (not product content): "sims cost money"; Garrett's jacket at chest_ease 0.03 crawled at
  10x and cost $0.66 in two tries; oxidegen bundle jobs `where: "local"` (bundle_client `run --local --gpu
  --via-storage`) on NICO-TOP (laptop 3070 Ti, $0, ~5x slower than a rented 4090, ~4.5 s a frame on 2800-vertex
  jeans: 20 min timeout); the rented fleet ~$0.03-0.08 a 2 cm garment; a Garrett-sized jacket over a shirt at 2 cm
  ~6-13 min on a 4090; a job "provisioning" is queued behind another client's batch; one stage.sh run at a time (a
  sim billed twice when two overlapped); take a never-started job out of sent.txt and resubmit once.
- Body measurements moved on 2026-10-06 (down-the-body tapes taut, shoulder slope from the shoulder line): every
  draft changed (armhole 6 cm higher, a jacket 7 cm shorter at CB); results before then aren't comparable. Before
  2026-10-06 the advice was to leave a short neck's collar open (the solver's standoff, gone since).
- The shirt wear rule until 2026-10-08 also undid the top front button (two open: the user called it wrong).
- Model-specific numbers dropped from the tables: Garrett jacket length_bonus 0.18, hips_ease 0.14, worn_envelope 10
  (30 rode the jacket up, collar showing -5 mm), lapel stand 0.02 -> 0.012 (~131 mm at the button), the tent
  numbers (6 mm spring: fronts 54 mm off the body; 0: 46; 12 mm narrowed the hem 48 mm), short-neck stand 16 mm
  (lapels 33-41 deg), su_om_garrett armhole_depth 0.14; Tess's sweater band 485 mm under the HPS, jeans knee / hem
  0.20 / 0.19; the jeans "smooth dark slacks" verdict; cloth12's asymmetry (the right collar END started on the chest
  133 mm from the left's mirror image; scratch collchain.py, edges.py) fixed in `cloth._end_points`; the test
  shirt's settle numbers (205 s vs 290-450 s, crease 3.4 vs 6.7 mm, fold spacing 8.7 vs 19.7, collar fall 5 mm below
  vs 12 above the seam, 18 crossings); c10ship notch=1 camera; section.py / edges.py-style front-edge numbers.

### Moved from cloth_guide.md "block + operations" (prose designs and draft comparisons)

Checked against a known draft: our bodice block on the test body against FreeSewing's Brian at the same ease has
the same chest width, armhole depth, shoulder seam and side seam to 0.1 mm, back armhole within 2 mm, necklines
within 1 mm, and the back outline within 2 mm on average (`workspace/cloth_renders/pd_00_block_vs_brian.png`). Ours
hollows the front armhole 9 mm more (Aldrich's narrower across-front), and for the same biceps ease our sleeve is
35 mm narrower with a 26 mm higher cap: Brian widens its sleeve by its own rule, ours solves the cap for the width
asked.

**Three garments designed from prose through these tools** (sheets and draft renders `workspace/cloth_renders/
pd_20..22_*`), judged honestly:
- *Wide-leg trousers* (trouser block, relaxed, waistband generated): all stages pass; the 2 cm draft reads as
  trousers, verdict "fits", 0 crossings, strain p95 5.9%. Wrong: they slide 9 cm down (a waistband 17 mm over the
  waist holds nothing), pool on the feet (the block's length runs to 3 cm off the floor), and balloon at the hem.
- *Asymmetric wrap tunic* (bodice, neckline widened, princess lines, `unfold`, the left front extended 22 cm and
  both fronts cut to V lines, tied by a stitch): reads as a wrap tunic; 2 crossings, strain 11.8%, the hem hangs
  9 cm lower on the wrap side, the under front bunches at the neck. The gate was right three times on the way
  (waist ease outside the fit, a take-in that ran into the hips): shaping lives at the DRAFT's waist line, the
  check measures at the body's.
- *Cropped shawl-collar princess jacket* (bodice, princess lines, `shawl`, facing, one button, two-piece sleeve):
  the pattern and construction stages pass and the sheet reads as that jacket. The draft sim is CORRUPT: the
  cut-on collar starts standing up the front of the neck and Blender's sewing doesn't bring it round (twisted
  collar seams), and the two-piece sleeves bunch at the shoulders. This design needs a start that lays the collar
  round the neck (a fold-aware placement) and method "settle"; neither was available here.

**A blazer from our blocks against FreeSewing's Jaeger** on the same body (`pd_30_blazer_vs_jaeger.png`): centre
back length, shoulder seam, upper armhole and back neck agree within 1-5 mm, the armhole within 12 mm (2%), top +
under sleeve width within 2 mm. Where a tailor's draft differs from ours, and what to build next: Jaeger shapes the
centre back seam and cuts a side panel that drops from the armhole (ours: a straight CB and a diagonal style line);
its waist is 17% over the body where ours is 29% (the fitted block leaves 36 mm a quarter for seams we only half
used); its hem has 12% over the seat (ours 2%: hips ease is taken at the high hip); its sleeve is 30 mm longer,
bent far more at the elbow, with a hollowed under sleeve and a hem 39 mm wider; its gorge is a straight line and the
front hem is cut away in a curve.

Since then: `contour` (the shaped centre back, the hem's spring), `join` (the side panel with no side seam), the
straight gorge, `round_corner` (the cut-away hem), `fisheye`, the bent two-piece sleeve, and `take_in` on a straight
cut (it had shaped nothing: the cut had no vertices) bring the same blazer to waist +16% (Jaeger +17%) and hem +12%
(+12%).

### Moved from cloth_background.md (lesson index, still-open list, closed faults)

#### Where each lesson lives

| Lesson (cloth_audit.md, 2026-10-03) | Where it is enforced |
|---|---|
| Sleeve cap ease 44% on the coat | Stage 2 seam check, cap band by kind |
| Stand stretched over a long neckline; collar shorter than its stand | Stage 2 band seams; simon's collar is drafted with no gap |
| Missing belt (side seams -20%) | Stage 2 plain seams; `belt` detail |
| Lapped pleat sewn shut | `back_vent: lapped_vent` evidence: a fold on the tail |
| No sleeve placket | `cuff: barrel` needs `sleeve_placket`; cuff seam band |
| No lapel roll, no facing, fronts frozen | `collar: notched_lapel` evidence; stage 3 made or draped |
| Collar never pressed; the 10 mm U | Fold lines with angle; stage 3 warns on a placed-only fold |
| The fall didn't cover the stand | `fall_cover` in stage 2; collar cover target in stage 5 |
| Every fabric the same bend | Fabrics with physical numbers; interfacing multiplier check |
| Layers held 5-17 mm apart | Layer gaps at the start (stage 4) and settled (stage 5) |
| Cloth reads thick (no crest under 7 mm at 1 cm) | Crest radius target; finals at 5 mm or less |
| 20 mm hems everywhere, 11 mm buttons on a coat | Hem depth per hem choice; the plan warns about coat buttons |
| Sleeves splayed on the hanger | Sleeve angle target |
| Pieces crossed or overstretched at the start | Stage 4 |

The suit rounds (2026-10-06..08: a shirt, a blazer from our blocks over it, suit trousers, on a test body and on
Garrett):

| Lesson | Where it is enforced |
|---|---|
| A garment worn over another is drafted over it | Automatic with `over` (draft log "drafted over"); layer tells in stage 5 (collar / cuff show, lapel gap, collar hug, crossings) |
| Jackets and coats are built on the form | Kind default `worn_top`; no check of its own (stage 4 start gaps show a failure) |
| Bands closed on themselves start closed | Stage 4 fails "<band> starts with its fastening N mm open" |
| Seams close: p95 gap <= 0.5 mm after the clean-up, closures <= 6 mm | Stage 5 targets `seam_gap_p95_mm`, `closure_gap_max_mm`; OPEN SEAM lines in the report |
| A strain-limited start: shear counts, 3% target, fine start under 1.6x | Stage 4 start strain (`start_strain_over_limit`); the fine settle's start check refuses before the GPU |
| Openings at the centre are joined or declared | Stage 3 openings: a seam, stitches, a closure, a closure worn open, or `design.open` |
| A chosen closure has a closure entry | Stage 3 fails a `front_closure` / `cuff` / `fly` with none |
| A trouser hem can be pulled on | Stage 2 hem per leg piece against heel + instep |
| Seat ease from the centre seam to the side seam | Stage 2 `leg_ease` |
| A jacket's hip room from `hips_ease`, not flare; the tent is the side panel's spring | NONE: read hem level and the open fronts on the sim (target `hem_level_mm` covers the hem only) |
| Don't lower a jacket stand to show the shirt collar | NONE: `layer_collar_show_mm` measures the result; the lapels' roll angles are in the report's fold lines |
| A shirt without a tie: only the collar open, collar spread | Kind default (`kinds.shirt.wear`, `collar_spread`); no check |
| Collar size from the neck | Applied by `collar_rule` on Simon; stage 4 HINT when a neck band is pushed > 8 mm off the neck |
| A placket / faced edge shows by its finish | Closure defaults by kind (`kinds.<k>.closure`: shirt box / french, jacket and coat facing, holes across); no check |
| Pit seams start too far apart on a fitted jacket | NONE yet: stage 4 lists seam start gaps; read them |
| The padded body folds in hollows | Fixed in the code; no check |
| Judge in clay / GLB, not the textured look; renders before a change show old code | NONE: discipline |

Still open (the checks say so where they can):
- Carlton's facing and lapel roll; pleats as folds (they are seam gaps: a fold that dies out inside a piece is a
  cone, and a pleat's layers are finer than a 1-2 cm mesh); double-layer (bagged) cuffs and collars;
- welt / flap / in-seam pockets; a lining's own pleat and fabric;
- button size and buttonhole direction are per closure now (`size`, `hole`) but not defaulted per kind (a jacket's
  closure needs `finish` / `hole` set by hand);
- a fitted jacket's pit seams (start); the jacket collar hugging the shirt collar (`collar_hug` 23-27 mm, target 6);
  front, back and collar disagreeing on the neck point (shoulder seam open ~10 mm there); the shirt's side seams
  standing as a fin the press can't flatten; hem height spread reads designed curves (a shirttail, a yoke) as
  unevenness;
- crease width and fold spacing measured by the tools; grain anisotropy.

#### Closed faults (history)

Faults the code now prevents; kept as the record of what was seen and why.

| What you see | Why | Fix |
|---|---|---|
| White flecks of shirt through a jacket's sleeves / armholes | The clean-up moved jacket cloth through the shirt under it | Fixed: crossings with the under garment send those vertices back to the sim's surface |
| A cached build or a look killed for memory (exit 137) with one huge start triangle | `_piece_crossings` searched every edge against every triangle at the largest triangle's radius | Fixed (per-size search, chunked); a start with a huge triangle is still worth reading (st.py-style: worst start triangles) |
| A jacket front reads open "0 stitches" in stage 2 | A front worn open has its buttons as a closure with no stitches | Fixed (closures' fastenings count); state "open" is fine |
| ZOZO "ccd failed", max_sigma ~11 at frame 0 | A sliver edge (under 1 mm) in the mesh: a fold row or a mark next to the outline | Fixed in the mesher; the fine start check names the place if one comes back |
| ZOZO builder: assertion `left > right` 0.0 / 0.0 while "computing constraints" | A collider vertex whose faces have no area (an under garment's welded seam slivers), or none at all | Fixed in the collider (faces under 0.0005 mm2 and the vertices they orphan are left out) |
| A build eats 12+ GB before any sim | A broken start (one triangle 10-30 cm across) searched for crossings with one radius | Fixed: such a start raises "the start is broken: a triangle of <piece> is X m across" |

## dress-garrett (2026-10-14, "dress-garrett" agent, branch `worktree-agent-a772e41978c43cfa6`; Garrett's suit on gp_h6c)
Goal (Joe): the suit on Garrett's FINAL body (approved head gp_h6c): the jacket redrafted with the corrected armhole
(back-tape underarm, set_sleeves into_armhole; c12_n18c's underarm was 73-80 mm under the armpit), the shirt, new
flat-front creased trousers; checked standing AND seated. Model `dg_garrett` = gp_h6c + su_om_garrett's shoes stand-in
(socks / shoes / soles: the feet are identical) + cloth shirt (su_gc's simon) / jacket (su_gc + q_n18's patches baked
in, legacy pins dropped) / trousers (suit_trousers). Checklists workspace/checklists/garrett_{jacket,shirt,trousers}.json
(items from clothlist's garrett_refs.json readings of the concept + the approved sheets). Scratch DURABLE in
/mnt/data/hifipushie/dress_garrett/: cloth12's + dress_tess's tools retargeted (env.sh, run.sh, q.sh, stage.sh with
sent.txt, run.py, check.py (the concept checklist), armpit.py, ua_job.py, spend.py: batches stage_q_dg*), mk.py (makes
the model), upd.py (sets garment keys in the saved spec), chk.py (check_garment with patches), bodies.py (tapes).
- The underarm default and set_sleeves into_armhole were only on dress-tess's branch: merged here (8a3bbe7f); its guide
  hunks folded into the split guides by hand.
- Body: gp_h6c vs su_gc (old): neck 406 (370), shoulders 482 (468), hpsToWaistBack 515 (496), hpsToArmpitBack 258
  (228), chest / waist / legs within 1 cm. The first check_garment on a new model took 24 min (the body build).
- Jacket j0 (c12_n18c as is, pins dropped): stage 2 FAILS chest ease +5.2% (fit relaxed 8-18%: the approved jacket's
  0.06 was never stage-2 checked) and the underarm estimate 4.6 cm (kind 0-3.5): the default 2.5 cm + armhole_depth's
  extra (0.14 - 0.02) x waistToArmpit = 5.5 cm down the back tape. j1: block_options.underarm 0.035 (~3 cm vertical),
  chest_ease 0.08 (the band's floor; tighter made ZOZO crawl in cloth12).
- Trousers t0: suit_trousers tailored, leg tapered (concept knee 146 / opening 114 mm front-view = knee 459 / hem 367
  round: tapered on his 353 knee), waist_drop 0.07, over shirt, collide shoes + soles, #2f2e2e.
- STATE: model + checklists made; j1 / s0 / t0 checks running. NEXT: shirt sim (rented), then jacket + trousers over it.
- Shirt dg_s1 (su_gc's simon, set_sleeves default): stage 4 FAILS the same way the APPROVED shirt does on su_gc
  (sg0: collar/stand crossings, "stand 44-46 mm inside the neck/jaw", fronts 62-83% stretched on 1.6% of triangles):
  pre-existing, it simulated clean before. Sim rented ($0.048, coarse + fine): fits, strain p95 0.6%, 2 cuff
  crossings (0 before the clean-up), collar open with the points spread 137 mm, band ends under the points; renders
  workspace/cloth_renders/dg_s1*.png. NOT reviewed yet. Its result is what the jacket / trousers lay on.
- Jacket: j2 = underarm 0.035 + chest_ease 0.09: stage 2 PASSES (underarm estimate 2.8 cm, ease 8%+). Stage 4 (j3):
  ok, but the under sleeve AS PLACED 6.6 cm under the armpit (top sleeve 1-1.8 cm above). pl.py: the two-piece sleeve
  crossed the back / side panel it is sewn to and went down the arm 2 rounds (2 cm). FIX (commit "cloth: a woven
  sleeve set into its armhole ..."): with set_sleeves into_armhole (the default; `B["sleeves_set"]`) a woven keeps its
  sewn sleeve/bodice crossings at the start as knits do; test test_collar::test_a_woven_sleeve_set_into_its_armhole_
  is_not_sent_down_the_arm (ga_suit: 1 round vs 3 free; PASS). pl.py after the fix: no rounds down, but the under
  sleeve's lowest sewn point still reads 68 / 87 mm (the measure reads the SLEEVE as laid on its arm cylinder; with the
  bodice held the sewing should pull it up: only a result tells).
- Trousers t1 (suit_trousers tailored, leg tapered, waist_drop 0.07, over shirt): stages 2-4 pass.

## Handover 2026-10-15 (dress-garrett; context full)
- Branch `worktree-agent-a772e41978c43cfa6` (main 76b62922 + dress-tess merged at 10ca1cd7 + 3 commits: notes, the
  woven set-in sleeve start fix, its test). Not pushed; main merges. Scratch /mnt/data/hifipushie/dress_garrett/ (see
  the section head; spend.py counts batches stage_q_dg*).
- Model dg_garrett (v4+): gp_h6c + shoes stand-in + cloth shirt / jacket (n18 baked, underarm 0.035, chest_ease 0.09,
  pins dropped) / trousers. Checklists workspace/checklists/garrett_{jacket,shirt,trousers}.json (also in scratch
  checklists/). Concept readings: /mnt/data/hifipushie/clothlist/garrett_refs.json; check.py <tag> <jacket npz>
  [trousers npz] [shirt npz] dg_garrett = the concept checklist; vw.sh <pkl tag> <pair tag> fig=1 + sheet.py <now>
  c12_n18c <out> = the approved sheet's layout (concept | now | approved; the approved tiles copied to out/).
- BATCH stage_q_dg_b1 (4 jobs, ONE rented batch, 8 min limit) ALL FAILED, $0.162 (not resubmitted):
  dg_j4 (jacket, underarm 0.035): exit 1 at 4 s, ZOZO "failed to advance" (a pair in contact at the start, no
  allowance; allow-existing-intersection is on, the bodice is pinned while sewing: suspect the kept sewn crossings
  meeting the held bodice / the shirt collider); dg_j5 (underarm 0.025): CRAWLED, 14 s a frame (frame 23/150 at 7 min,
  ~40 min to go: like cloth12's n22 chest-ease crawl); dg_t1 / dg_t2 (trousers, drop 0.07 / 0.045): 4.5-4.9 s a frame,
  frames 79-89 of 150 at the limit (a 150-frame trousers sim needs ~12 min there: give trousers 15 min).
  OXIDEGEN MEASUREMENT: in the batch, trousers 4.5-4.9 s/frame; no solo run of the same sims exists to compare (the
  shirt ran alone, 2 stages, $0.048). Owed: run t1 alone with the same limit and report run_s beside the batch's.
- Spend this agent: $0.210 (shirt $0.048 + batch $0.162). dress-tess's own: $0.76 at its spend.py (2026-10-14).
- Decisions: chest ease raised to the KB band's floor (8%: the approved 6% fails stage 2; concept chest reads narrower,
  441 vs 397 front view on the approved); underarm via block option `underarm` (not armhole_depth); trousers leg
  tapered from the concept's knee / opening; no authored folds besides the crease.
- NEXT: (1) jacket: find dg_j4's start contact before any resubmit (run its job on NICO-TOP, where local, free, to get
  the full log, or check the start for sleeve x shirt-collider / pinned-bodice contact); if the kept crossings cause it,
  keep them only for pairs not on held pieces, or don't pin the bodice where a sleeve crosses it. Then the jacket's
  crawl (j5): compare its job with c12_n18's (chest ease, underarm). (2) trousers t1 with timeout 15 min (stage.sh TMIN=15),
  then judge rise / length / crease against the checklist. (3) review per garment (bin/review, --stage/--not as the
  brief), seated check: export_asset's rig layers_seated (rig_audit.seated) + a seated render. (4) shirt review.

## dress-garrett, 2026-10-15 (continued)
- Merged main (7f472faf). Shirt review r1 on dg_s1 (simon defaults): FAIL. MAJORs: the collar a ring standing off the
  neck, points like wings; baggy (flat-pattern ease chest +15%, waist +22%); cuffs deep, standing off; surface smooth.
- Start faults found (all cost money before): ZOZO's batch error keeps only the TAIL of its log, and the pair line was
  cut off. cloth_zozo._solver_said now puts the lines that name the pair last. dg_j4 = jacket side.L top edge 1.71 mm
  from the body's LEFT armpit crease, EDGE TO EDGE (contact offset 2 mm; every vertex / edge sample > 3 mm: the old
  clearance samples points). dg_j5 = the same edge at 0.26 mm: crawled 14 s / frame. Fix: `_clear_exact` ends with
  an exact cloth-edge x collider-edge pass, outward only (`_seg_seg`, `_clear_edges`; test_suit7). Cloth tests: all 15
  files pass.
- Batch vs solo (Oxidegen's question): trousers t1 ALONE on a rented 4090 ran 4.4-4.6 s / frame (frame 94/150 at
  7:53), the same as in the 4-job batch. A trousers sim needs ~12 min: TMIN=15.
- Shirt s2 (ease chest 0.105 / waist 0.08 = flat +10% / +15%; collarEase 0.03): the coarse sim was fine, and the FINE SETTLE
  crawled (60-90 s / frame, $0.19): the smaller collar seats higher on the tapering neck and rested on the jaw
  (collar edges 0.12 mm off). Scratch stage.sh now runs preflight.py on every batch: refuse if FREE cloth (not carried
  made pieces, plus released flaps) has an edge within 2 mm of a collider edge. It separates every past pass / fail.
- Garment key `wrap` {piece: {wrap keys}} (cloth.py; cloth_design.md): a drafted piece's wrap set per garment (neck
  band tilt).
- Collar attempts (review "collar stands up / off the neck" MAJOR): s3 collarEase 0.07 + neck bands tilt 15 about
  the nape (the V opens, fit slimmer; collar still upright); s4 + collar_spread [30,22,55] without tilt (worse: tall,
  crumpled, points folded in); s5 s3 + collarStandWidth 0.045 + collarWidth 1.8 (as s3); s6 s5 + collar_spread
  [26,20,60] (wider, lower, points out: best so far; review r3 still MAJOR "stands up like a funnel, gap round the
  neck"). Saved into dg_garrett as the shirt. The guide's own rule: a tucked under garment is judged with what's over
  it. So NEXT: jacket j6 + trousers t3 over s6 (batch stage_q_dg_b2), then the shirt reviewed as worn.
- Textured renders show dark smudges at the shoulders beside the collar (clay is clean; the maps are clean): a render
  issue, still open.
- Spend (this agent, 2026-10-15): ~$0.70 (failures $0.35: the s2 fine settle $0.19, the t1 solo control $0.15).
- Coordinator's decision on the collar (STUCK sent): judge the shirt AS WORN under the jacket. If it still reads as a
  funnel / off the neck there, it gets a dedicated general fix to how open collars are laid. If it reads right
  worn, it's a known gap. Cuff, shoulder smudges and untucked flare are judged worn too. Fix the jacket's real faults
  first.
- NICO-TOP first (coordinator, pending Joe): `LOCAL=1` in stage.sh when bl.sh machines shows NICO-TOP gpu_free;
  rented when it's busy. It was busy (1 job) all day.
- Jacket j6 (underarm 0.035, over shirt s6; batch stage_q_dg_b2): SIMULATES now (447 s, 3 s / frame: the start fix
  works). But the check says CORRUPT: 80 crossings in front.L / front.R, all made by the clean-up (0 in the sim). The lapel roll
  ended at 44-46 deg (n18c on su_gc: 146-150), so the lapels unrolled in the sim, and "lapel pressed" then moved
  them 50-51 mm (n18c: 9-17 mm) through the fronts. The collar-to-neck seam (seams 6 / 7) is open 104 mm after the
  clean-up (n18c 41 mm). The jacket collar floats over the shoulders in dg_j6_collar.png. Under sleeve still 61-62 mm
  under the armpit (top sleeve -10 / -13). Suspect: the s6 shirt's spread collar points (wider, out onto the
  collarbones) push the lapels / gorge open. Test it: the jacket over the s1-style shirt (collar_spread default), one
  change.
- Trousers t3 (tapered leg, waist_drop 0.07, over s6): sim 496 s ($0.08 share), fine settle ran in 2 s on rented
  ($0.046) although preflight refused it (1.2 mm over the shirt / shoes). Preflight now uses 1 mm for fine settles
  and 2 mm for first sims. 0 crossings, fits, crease pressed (15-18 / 35 deg). Review r1 (out/rv_t3/r1): FAIL. MAJORs:
  no break, hem short; the crease fades below the thigh; legs taper (the concept reads straight); smooth fabric; belt
  sits on top of the waist as a tube, no buckle, no waistband visible. t4 = leg "straight" + length "floor"
  (stage_q_dg_t4) running.
- Review crops: rvshirt.sh <tag> <round> (shirt); out/rv_t3 (trousers: concept boxes whole 400,780,860,1720 / hem
  400,1450,860,1720 / waist 440,760,820,960 vs tile 0 of <tag>.png, _hem, _waist_tex).
- Spend (this agent, 2026-10-15): ~$1.15.
- NEXT: (1) t4 result -> review; then the belt / waistband (belt is a trim: cloth_trims), the crease below the knee.
  (2) Jacket: the lapel unrolling and the collar seam opening (the shirt-collar test above), then the 62 mm under
  sleeve. (3) The shirt reviewed WORN (jacket + trousers on). (4) Seated checks for all three.

## Handover 2026-10-15 b (dress-garrett; context full)
- Spec dg_garrett's shirt is now s5's config (= s6 WITHOUT collar_spread: default spread). Results for s3-s6 are cached
  in /mnt/data/hifipushie/dress_garrett/results. To go back to s6: upd.py dg_garrett shirt 'collar_spread=[26,20,60]'.
- Jacket j7 = j6 over that shirt: still CORRUPT, but only 22 crossings, all front.L. Lapel roll end: R 155 deg (rolled,
  like n18c), L 67.5 deg (unrolled). Collar-to-neck seam L open 128 mm. ONE SIDE WRONG = an asymmetric input (the
  guide). The left side is also where the side.L top edge started on the armpit crease (j4 / j5). NEXT: compare L / R
  start inputs (check_garment stages=["place"]; the body's left vs right armpit / shoulder on gp_h6c; the pieces' starts
  mirrored) before touching the draft. Then the 61-62 mm under sleeve (top sleeve -6 / -13: the under sleeve hangs
  low after the sim too; the set-in start fix didn't pull it up).
- Trousers t4 (leg straight, length floor): sim 374 s + fine settle, both ok ($0.10). Renders were being written at
  handover (stage_q_dg_t4 round 3 build): dg_t4*.png. NEXT: review it with out/rv_t3's crops (swap res_* for dg_t4
  tiles), then the belt / waistband MAJORs (the belt is a trim) and the crease below the knee.
- Spend this agent 2026-10-15: ~$1.30 (spend.py sums stage_q_dg* batches; the diag / solo / t3f batches are named
  dg_j4diag2, stage_q_dg_t1solo, stage_q_dg_t3f).

## dress-garrett, 2026-10-15 c (fresh session)
- Trousers t4 (leg straight, length floor; renders finished): review out/rv_t4/r1 FAIL. MAJORs: the leg flares below the
  knee (hem reads 15-20% wider than the knee; the concept's is ~10% narrower), no crease below the thigh, cloth reads
  knit / fleece, belt sticks out past the trousers at the hips, hem stands off the instep (no break), belt a round tube
  with ring loops, buckle a featureless block, no visible waistband / fly. Floor length made the hem pile out and flare.
- Trims (cloth_trims.py, general): a strap's four sides and a box's six faces have their own vertices (square edges in a
  smooth-shaded render: shared corners shaded the belt as a tube and the buckle as a blob); the buckle is a FRAME (four
  bars, the bar the prong turns on, a prong) and a leather keeper beside it; trims carry `roughness` (belt 0.45,
  buckle 0.3) into cloth.look.
- t5 (running, rented, TMIN 15): leg straight + hem 0.205 flat (410 round, 88% of the 466 knee), length back to the
  kind's "break", crease op angle 240 / strength 0.8 (design.ops overrides the detail's 205 / 0.6: the pressed ridge is
  sharpened to 60 deg, was 35), belt {"type": "leather", "trim": {color #2b1e16, width 0.03, roughness 0.4}}.
- JACKET one-sided lapel: the INPUT difference found. asym.py <model> <garment> [k=json] (place only: L vs mirrored R per
  piece, collider / under / body mirror distances). The pattern is mirror-exact (lrpat.py), body and padded collider
  symmetric below 1.3 m (p95 < 1 mm). The start is not: front.L (the closure's OVER side) starts 10 mm further out
  (y -10 mm mean at every height 0.85-1.25 m; p50 15 mm from the mirrored front.R): the lap offset (OPEN_LAP default
  True) for a front worn OPEN, with nothing between the fronts. open_lap false: the offset is gone (mean y within
  2-3 mm; p50 8-9 mm = the meshes' lattice noise: front.L 548 vs front.R 553 vertices, side 143 / 144; mirror_mesh true
  does NOT equalise them: the outline / fold-row sampling differs too). j8 = j7 + open_lap false (running, rented).
- Jacket UNDERARM 61 mm (j7, under sleeve; already 57 mm at the START, so not sim sag). Root: the draft puts the
  underarm at hpsToArmpitBack + underarm down the back pattern, and gp_h6c's back tape reads 258 mm (su_gc 228, bodies
  otherwise within 1 cm): GNM's neck section is 14 cm deep (su_gc 12), its widest-x point (= HPS, tailor.py) sits at
  y -0.037 (su_gc -0.017), and the taut tape first crosses 5 cm of neck top before it goes down (hps.py, neckloop.py).
  In the world the start's armhole bottom is 244 mm under the HPS for 293 mm of pattern; the armpit 187 mm under it.
  Not changed in tailor.py (every draft on every body would re-key; a coordinator call): recorded as a known bias of the
  back tape on thick-necked GNM bodies. Place-only (pl.py, open_lap false): underarm 0.0 -> under sleeve 42 / 43 mm
  placed, 0.01 -> 32 / 35 (placement noise ~10 mm: the under sleeve's push varies 52-82 mm); target 10-45.
- Spend 2026-10-15 (this session): t5 sim $0.098, j8 sim $0.057.
- j8 = j7 + open_lap false (rented $0.057, 167 s): crossings 22 -> 2 (collar / front.L), lapel roll ends 112 / 143 deg
  (j7: 67.5 / 155), lapel_gap 15.5 mm, collar_show 22, underarm still 62 / 63. Render dg_j8.png: the wearer's left
  lapel still stands off the chest as a board in the side view. Better, still one-sided.
- The other asymmetric input: the MESH. mirror_mesh never reached the sim mesh: cloth.build meshed (Ms) BEFORE
  place_keys copied the garment keys onto the pieces (so front.L / front.R 548 / 553 with it on). With the key set,
  cloth.mesh gives mirror-exact pieces (lrmesh.py: front 98 + 449 border + interior, every vertex with a mirror match,
  side and back too). FIX: place_keys before the first mesh (commit "cloth.build: garment keys set before ...").
  j9 = j8 + mirror_mesh true + underarm 0.01 (running, rented).
- t5's fine settle refused by preflight (back.L 0.72 mm < 1 mm): re-run on NICO-TOP (LOCAL=1, free; stage.sh now
  honours NOPREFLIGHT=1, used only for free local runs).
- j9 (j8 + mirror_mesh + underarm 0.01): CRAWLED (18-28 s / frame, frame 19 at 480 s; $0.162). The raised armhole
  crawls ZOZO as j5 (underarm 0.025) did: a tight underarm in contact under the arm. Keep 0.035 until the start's
  underarm contact is understood (preflight passes it: > 2 mm edge to edge, so it's not the edge rule).
- j10 (j8 + mirror_mesh only): ran 2.3-3.4 s / frame but hit the 8 min limit at frame 101 / 150 ($0.160; j8 needed
  167 s, j6 447 s: the mirror mesh's run is slower). Removed from sent.txt: RESUBMIT with TMIN=12 (not a crawl).

## Handover 2026-10-15 c (dress-garrett; coordinator's tool-call clock: 100 calls)
- Branch worktree-agent-a772e41978c43cfa6, not pushed. This session's commits: cloth_trims (square-edged strap / boxes,
  frame buckle + prong + keeper, trim roughness into cloth.look); cloth.build place_keys before the first mesh
  (mirror_mesh reaches the sim mesh: before it never did); notes.
- Spend this session: $0.48 (t5 sim 0.098, j8 0.057, j9 crawl 0.162, j10 limit 0.160). Day total ~ $1.78.
- TROUSERS: t4 review r1 FAIL (out/rv_t4; MAJORs above). t5 (straight, hem 0.205, length "break", crease 240 / 0.8,
  brown leather belt 30 mm) sim done; its fine settle was refused by preflight (back.L 0.72 mm) and is QUEUED on
  NICO-TOP (stage_t5b.out, LOCAL=1 NOPREFLIGHT=1, free). When it returns, stage.sh's next round renders dg_t5*.png
  (check dg_t5.log ends DONE 0). NEXT: crops as out/rv_t4 (tile 0 of dg_t5.png 0,0,396,640; _hem and _waist_tex
  0,0,640,640; concept crops copied there), bin/review with the same --stage / --not; the hem / break, crease below
  the knee, belt / buckle / keeper, waistband and fly visibility. Fabric surface (knit vs worsted) is the fine-fold /
  detail maps: not touched yet.
- JACKET: L / R input asymmetry = (1) the open front's lap offset (front.L 10 mm out: open_lap false fixes it), (2)
  the mesh (mirror_mesh, now actually applied). j8 (open_lap only) is better (lapel roll 112 / 143, 2 crossings) but the
  left lapel still stands off as a board. NEXT: resubmit q_dg_j10.txt with TMIN=12 (open_lap false + mirror_mesh true),
  then compare the lapel roll ends (FOLD lapel roll lines in the log) and the collar seam gap; if symmetric, save both
  keys into dg_garrett (upd.py dg_garrett jacket open_lap=false mirror_mesh=true) and consider making open_lap False
  the default for fronts worn open (a coordinator call: re-keys open garments).
- UNDERARM: root found (GNM's deep neck puts HPS 2 cm forward; the back tape reads 258 vs su_gc 228). Lowering the
  draft's underarm (0.01) brings the placed under sleeve to 32-35 mm but the sim crawls. Open: why a raised armhole
  crawls (look at the start's underarm contact with the shirt collider, ua_job.py / startprox.py).
- Scripts added in scratch: asym.py (L / R start), lrpat.py (pattern L / R), lrmesh.py (mesh L / R), hps.py,
  neckloop.py, ua2.py / ua3.py (armhole seam z start / result).
- STATE: jacket asymmetry partly fixed (open_lap), mesh fix committed but unsimmed; trousers t5 waiting on NICO-TOP.
  NEXT: j10 with TMIN=12, t5 review, then shirt worn review.

## dress-garrett, 2026-10-15 d (coordinator calls: open_lap default, side-neck point)
- `cloth.OPEN_LAP = False` (coordinator): a front worn OPEN starts its over side level with the under side; open_lap
  true keeps the old lapped start. Re-keys open garments' cached sims (accepted). test_suit8 asserts the default.
- HPS fix (`tailor._side_neck`, coordinator): the hps is where the shoulder's CREST (trapezius ridge, read in a
  section along y 1 cm outside the loop's widest point, below the loop) meets the neck loop, not the loop's widest-x
  point; `at["neck_side.L"]` keeps the widest point (the neck's half width: cloth's worn-collar filter reads it).
  The tapes from the hps (`tailor.measure.down`) now start below the crest (`at["neck_base_z"]`): with the hps moved
  back, the FRONT tape ran round GNM's deep neck front instead (hpsToBust 249 -> 326 on gp_h6c, and the shirt's draft
  failed: buttonholes outside front.L, the front 7 cm wider). Test: test_pattern_tailor
  test_side_neck_point_on_the_shoulder_crest (synthetic loop + crest, fallback).
- Draft numbers before -> after (mm; default bodice, underarm 0.035; hpsfix.py / mmdiff.py in scratch):
  | body | hps y | hpsToArmpitBack | armhole depth | vertical hps-armpit | hpsToWaistBack | hpsToBust |
  | dg_garrett (gp_h6c) | -0.037 -> +0.004 | 258.0 -> 222.6 | 264 -> 231 | 187 -> 194 | 515 -> 483 | 249 -> 281 |
  | su_gc (old body)    | -0.017 -> -0.009 | 228.0 -> 218.5 | 233 -> 223 | 180 -> 181 | 496 -> 490 | 277 -> 275 |
  | dt_tess             | -0.039 -> -0.004 | 222.4 -> 198.3 | 239 -> 209 | 154 -> 164 | 447 -> 431 | 238 -> 271 |
  Back tape / vertical drop: 1.38 / 1.27 / 1.44 -> 1.15 / 1.21 / 1.21 (one ratio now, the three bodies alike); the
  front tape on gp_h6c now matches su_gc's (281 vs 275: bodies within 1 cm, as measured before). Tess's shoulderSlope
  11.0 -> 14.1 (her hps rose 1 cm), gp_h6c 10.9 -> 9.9. The approved c12_n18c (su_gc) is NOT re-simulated: its draft
  would move 10 mm on the back tape to the armpit, 6 mm on hps->waist back, armhole depth -10 mm.
- Cloth test set on the final code (tests.sh, one file per process): all 15 files rc 0 (folds 13, cloth 30, layers 13,
  closures 13, check 1, workflow 20, pattern_draft 9, styles 8, tailor 21, collar 6, seams 5, reference 12, suit7 6,
  suit8 6, made 13).
- The raised-armhole question resolved THROUGH THE DRAFT: place-only (pl.py, default underarm 0.035) under sleeve
  57 / 59 -> 35 / 36 mm; j10's sim 33 / 40 (target 10-45; j8 62 / 63). No hand-set underarm.
- j10 (open_lap default false + mirror_mesh + hps fix; rented $0.100, 294 s, no crawl): NEW fault: the collar /
  neckline seams open (OPEN SEAM 6 / 7: 9 of 17 pairs, final max 59 / 84 mm, sim max 20 / 21), crossings 22 -> 67
  (front.L 28, front.R 26: now both sides alike), lapel roll ends 51 / 142 deg (j8 112 / 143), lapel_gap 9.5 / 9.7,
  collar_show 20.8. Likely cause: the hps moved 1.6 cm in and 4 cm back on gp_h6c; the jacket's neckline / collar
  placement reads `at["hps.L"]` (cloth.py support kinds ~5908, worn placement `hps`, collar draping from the neck's
  side) while the front's draft gained 3 cm of hps->bust. Look at the START (place-only: collar seam gap per pair,
  front neck point vs body hps) before any resubmit. Renders dg_j10*.png were made by stage.sh locally (before the
  new render rule reached me): NOT reviewed.
- An old j10 stage.sh round (previous session, 8-min limit) was resubmitting to rented at 16:14: cancelled (SIGINT ->
  the client cancels its batch). t5's round 2 re-ran its SIM on NICO-TOP (the code change re-keyed it; free, queued).

## Handover 2026-10-15 d (dress-garrett; 70-call limit)
- Branch worktree-agent-a772e41978c43cfa6, not pushed. Commits this session: tailor side-neck hps + tapes below the
  crest, OPEN_LAP False, tests, notes.
- Spend this session: j10 $0.100 (+ the cancelled stale j10 batch, cents). Day ~ $1.88 of $5.
- RULE (Joe, via coordinator, 2026-10-15): ALL renders go to NICO-TOP via spikes/offload/remote.sh (<= 12 GB, own
  folder per submit, detached, many frames per submit); laptop only for small check crops (< ~5 s) and flat / ID
  passes; CPU cap 10 cores for all agents. stage.sh / q.sh still render dg_*.png locally after a sim: route those
  through remote.sh before the next round.
- STATE: both coordinator calls done and tested; underarm fixed by the draft; j10 has a NEW collar-seam fault from
  the hps move; t5 re-simming on NICO-TOP (stage_t5b.out); shirt not reviewed (its draft also moved: re-sim needed).
- NEXT: (1) j10 collar seam: place-only start, the neckline / collar pairs' gap and where front / back hps land vs
  `at["hps.L"]`; fix in placement or draft, not the solver; (2) t5 review when NICO-TOP returns it (crops as out/rv_t4);
  (3) shirt re-sim on the new draft, then review AS WORN; renders on NICO-TOP.

## dress-garrett, 2026-10-15 e
- j10's "collar seams open" (OPEN SEAM 6 / 7, 59 / 84 mm; j8 had it too: 80 / 137) is NOT a fault of the start or the
  hps move: those pairs belong to the SIMULATED collar, which the made (constructed) notched collar replaces and which
  never ships (cloth.py export: `cloth_made.drawn`). The made collar is built on `seam_chain(V)` after the lapels are
  pressed, so it sits on the neckline: madegap.py dg_j10 / dg_j8: neckline vertices to the made collar 0.0 / 0.0 mm
  both sides. FIX (reporting): `cloth.seam_gaps(..., made=)` leaves out pairs of pieces a made part `replaces` and
  reports `made_seam` (shipped part to the seam's other side, p50 / max) + `replaced_pairs`; check prints it. On j10:
  open 18 -> 0, made_seam 0.0 / 0.0 over 34 pairs. Scratch run.py's OPEN SEAM skips replaced pieces too (sgchk.py
  <tag> re-reads a saved result). Test: test_cloth_made test_seam_gaps_leave_out_pieces_a_made_part_replaces.
- Still real on j10: crossings 67 (front.L 28 / front.R 26 after the clean-up; the sim left 8) and the lapel roll
  one-sided at the end (51 / 142 deg) from a symmetric start (165.1 / 165.0, gap 5.0 / 5.0). The press then moves the
  unrolled left flap 53 mm (right 39) through its forepart: the crossings follow from the unroll.
STATE: collar-seam report fixed. NEXT: asym.py on the current code (open_lap false default, mirror_mesh) for what is
still L / R different at the start (the shirt under it: its closure laps left over right).

## dress-garrett, 2026-10-15 f (fresh session; method change: sim for the big read, finish by hand)
- Merged main (de23ee7b: guide rule 3 / stage 7 Finish).
- `cloth_made.construct` key `mirror` ("mean" | "L"): open fronts finished as ONE shape, the way a tailor presses both
  lapels from one template. `mirror_pairs(M)` (L/R vertex correspondence by pattern point: the R piece's uv is the
  left's with u negated on body pieces, identical on sleeves), `symmetrize` (each pair to the mean of left and mirrored
  right, weight 0-1), applied to the drape within `mirror_reach` (0.10 m) of the left lapel BEFORE the lapels are made
  (both built on the same base) and again after; the made collar (`mirror_part`, station i <-> n-1-i on its grid).
  Mirror plane x0 = the body's x centre. Test: test_cloth_made test_mirror_pairs_and_symmetrize_make_left_and_right_one_shape.
- On j10's drape (con.py replay of the dumped construct inputs, out/con_j10.pkl; symchk.py): lapel flaps L vs mirrored
  R 0.0 / 0.2 mm (was p50 47 / max 146 mm in the drape), made collar 0.0 mm (was 3.8 mm), both flaps over the shirt
  (0 of 61 below it each side; without mirror the right flap had 11 below, down to -17.6 mm).
- BIG READ FAILS ON j10 (looked at dg_j10.png beside dg_j8.png; hang.py): the fronts SWING OPEN in the sim: front edge
  |x| at the hem 254 / 261 mm (j8 59 / 74), moved back 8-12 cm in y, while both starts are alike (edge |x| 50, no
  front-to-front contact: lapx.py min 70 mm). So j10 is not a base to finish on (mirroring can't fix a hang). Drape L/R
  mismatch outside the lapels is 43 mm p50 at the chest (uvdbg2.py), so this is the hang, not a local fault.
  Suspect: the start change (open_lap false, the coordinator's default) or the hps move. j11 = j10 + open_lap=true +
  construct.mirror="mean" submitted to NICO-TOP (stage.sh LOCAL=1, free): one sim answers which.
- Scratch (/mnt/data/hifipushie/dress_garrett): symchk.py <pkl tag> under=<tag> (mirror mismatch, flaps vs the shirt),
  hang.py <npz tags> (front hang at start / sim / finish), lapx.py (fronts' start gap), con.py replays (m1 = no mirror,
  m2 = mirror on j10). run.py dumpcon=<name> writes into the WORKTREE dir (run.sh cd's to $W): move it to out/<name>.pkl.
STATE: mirror construct in and tested; jacket hang regressed in j10; j11 on NICO-TOP.
NEXT: j11 hang.py + front crop (rr.sh on NICO-TOP); if it hangs like j8 with j10's underarm, it is the base: then
finish (sync cloth_only, sculpt, pull) and set construct.mirror in the spec; else the hps / neckline is the suspect.

## Handover 2026-10-15 f (dress-garrett; 70-call limit)
- Branch worktree-agent-a772e41978c43cfa6 (main merged at de23ee7b), not pushed. Commit 719357f5: construct `mirror`.
- Sims IN FLIGHT (detached, nothing to babysit): `stage.sh q_dg_r1.txt` (stage_r1.out) = t5 (trousers, unchanged
  line) + j11 (jacket = j10 + open_lap=true + construct.mirror="mean") as ONE RENTED batch. NICO-TOP was blocked by other
  agents' jobs (t5 had sat "queued" there 15:20-17:15), so both moved to rented per the rule (t5's old job name
  removed from sent.txt). stage.sh runs the fine settle round, then rr.sh sends the sheets to NICO-TOP
  (rr_q_dg_r1.out) -> workspace/cloth_renders/dg_t5*.png, dg_j11*.png.
- Spend: this session's rented batch is still running (expect ~$0.10-0.30: 2 sims + settles); day was ~$1.90 before it.
- Jacket sim count is far past the 3 + 2 budget (j1-j11). j11 is a regression check (j10's fronts swing open), not a
  tuning round: if j11 hangs like j8 it is THE base; stop simulating the jacket and finish.
NEXT, in order:
1. j11: `bash run.sh hang.py dg_j11` (hem edge |x| should be ~60-75 mm like j8, not 250), underarm from dg_j11.log
   (10-45), then symchk.py dg_j11 (flaps 0 mm mirror, 0 below the shirt). Look at dg_j11.png front beside dg_j8.
   If it hangs: set `construct.mirror: "mean"` + `open_lap: true` in workspace/dg_garrett/spec.json (jacket), and
   flag open_lap to the coordinator (their default false broke this open jacket's hang).
   If it still swings: the hps move is the suspect (place-only start of j10 vs j8: front neck vs hps), a pattern
   question, not another sim.
2. Finish the jacket on that drape: sync(cloth_only=True), scripted bpy sculpt (smooth / grab on vertex groups by
   region), pull -> cloth.jacket.sculpt; record each edit here.
3. t5: hang.py-style review of the big read only (straight leg, break, crease line); belt and crease are finish detail.
4. Shirt: one re-sim on the new draft (hps fix), then the collar finished by hand and judged AS WORN (V and points).

## dress-garrett, 2026-10-15 g (fresh session)
- Coordinator audit: the old t5 settle job on NICO-TOP (job_1d6508bd8bee8848_sim, batch dbd1d0c2 =
  stage_q_dg_t5_151803.r2, its client killed by SIGINT while queued so never cancelled) was still QUEUED: cancelled
  (`bundle_client.py cancel <batch>`, token ~/.config/oxidegen/hifipushie-cloth-token). Lesson: after interrupting a
  stage.sh round, check `bundle_client.py status <batch>`; the client cancels only when it is running.
- Rented batch r1 (t5 + j11): $0.143 sims + $0.015 j11 fine settle = $0.158. Day ~ $2.06 of $5.
- j11 (j10 + open_lap=true + construct.mirror) STILL SWINGS OPEN (hang.py; front edge |x| at the hem, mm):
  | run | start X0 L / R | sim L / R | finish L / R |
  | j8  | 48 / 49 | 59 / 74 | 59 / 74 |
  | j10 | 49 / 50 | 261 / 254 | 261 / 254 |
  | j11 | 49 / 50 | 142 / 254 | 157 / 255 |
  The starts are alike in all three: open_lap is NOT the cause, so the coordinator's open_lap:false default stands
  (no revert). Underarm j11 32 / 39 (target 10-45); fronts CORRUPT flag 104 / 102 crossings (open_lap start).
- THE CAUSE IS THE DRAFT'S FRONT BALANCE (drcmp.py: the jacket draft and the body tapes, side-neck hps vs the old
  widest-x hps, mm):
  | | old hps (j8) | side-neck hps (j10, j11) |
  | body hpsToSeatFront / hpsToSeatBack | 678 / 711 | 713 / 673 |
  | body front - back | -33 | +40 |
  | jacket front.L / back.L piece height | 783 / 783 | 751 / 751 |
  The jacket block drafts the front as long as the back (`pattern_blocks` option `front_balance`, default 0, never
  set from the body). With the hps on the shoulder crest the body's front tape grew 35 mm and the back's shrank 38,
  but both pieces shrank 32: the front is ~7 cm short against the body relative to j8. A short front balance is the
  textbook cause of fronts swinging apart at the hem (the erect-figure fault: the front is pulled up over the chest).
  FIX PROPOSED (pattern, not solver): front_balance from the body, (hpsToSeatFront - hpsToSeatBack) or the same at the
  chest, ~40 mm here; it raises the front's neck point and shoulder over the back's (pattern_blocks.py ~215). Needs a
  sim to confirm: over the jacket's sim budget, so the coordinator's call.
- Renders dg_j11 / dg_t5 submitted to NICO-TOP by stage.sh (rr_q_dg_r1.out, batch dgrr-180515), queued 40+ min
  behind other agents' jobs: t5's review waits on them.
- Scratch: drcmp.py <model> <garment> (body tapes and piece extents, old vs new hps; ~10 min, runs the draft twice).
STATE: j11 not a base (front balance short since the hps fix); old t5 job cancelled; t5 renders queued on NICO-TOP.
NEXT: coordinator decision on front_balance from the body (+ one jacket sim); then t5 review (bin/review) when the
renders land; shirt re-sim.
- Coordinator approved the fix (its own HPS fix, `tailor._side_neck`, moved the front / back tapes: that is where this
  regression came from). `pattern_blocks.front_balance(m, opt)`: bodice option `front_balance` now defaults to
  "auto" = clip(hpsToSeatFront - hpsToSeatBack, 0, 80 mm); an explicit number wins. Test:
  test_pattern_draft test_front_balance_auto_from_the_body_tapes (10 passed). gp_h6c: 40 mm.
- Other readers of the same tapes: `cloth.ALTERATIONS["large_abdomen"]` (front minus back past 25 mm, spread at the
  waist). Since the hps fix every man's body reads ~+40, so an opted-in large_abdomen now fires on a flat belly AND
  double-counts with auto front_balance. Not used by dg_garrett. TODO: re-baseline its 25 mm threshold on side-neck
  tapes (or subtract front_balance). Trousers (`trouser`, `leg_cut`) and skirt do not read hps tapes; the shirt and
  Tess's coat are bodice blocks, so they get "auto" too (their drafts move: re-key their sims).

## Handover 2026-10-15 g (dress-garrett; 70-call limit)
- Commits: f5cb7d2e (notes), front_balance auto + test. Not pushed.
- IN FLIGHT (detached): `stage.sh q_dg_j12.txt 3` (stage_j12.out), ONE rented jacket sim j12 = current code (auto front
  balance 40 mm, open_lap default false) + mirror_mesh + construct.mirror="mean". The coordinator approved ONE sim. If
  the hang matches j8 (hang.py dg_j12: hem edge |x| ~60-75 mm), it is THE BASE: no more jacket sims, finish on the drape.
  If not, report STUCK with the numbers; do not re-sim.
- Renders dg_j11 / dg_t5: NICO-TOP batch dgrr-180515 (rr_q_dg_r1.out), queued for 1 h+. Wait with
  `/mnt/data/hifipushie/bin/offload wait <batch>` (coordinator), not a poll loop. j12's sheets go the same way once its rounds finish.
- RULE (coordinator audit): run /mnt/data/hifipushie/bin/review on every result judged, every round (reference | result crops).
  The last session ran none. t5 and j12 each need one.
- Spend: rented r1 $0.158 + j12 (~$0.10, pending). Day ~$2.16 of $5.
NEXT: (1) j12 hang.py + symchk.py + bin/review of the front; (2) PASS -> finish (sync cloth_only, sculpt, pull ->
cloth.jacket.sculpt; set construct.mirror in the spec); (3) t5 bin/review when the renders land; (4) shirt: one re-sim
(its draft moved twice: hps + auto front balance), collar finished by hand, judged as worn; (5) large_abdomen threshold.

## dress-garrett, 2026-10-15 h (fresh session)
- Cherry-picked main bef0229c (remote.sh per-commit archive link) as f142d82d: a j12 render submit from the same
  folder would otherwise have swapped dgrr-180515's queued archive.
- large_abdomen re-based (6c1f7f79): `cloth.FRONT_BACK_NORM_MM` = 40, the alteration takes only the excess. Side-neck
  tapes (fbnorm.py, mm, F-B): dg_garrett +40, ga_garrett +40, dt_tess +40, ga_tess +32, dg_mh (waist / chest 0.88)
  +76 -> 37 mm. FOUND: the shirt is FreeSewing `simon`, which lists large_abdomen, so since the hps fix the OLD rule
  fired 15 mm on Garrett's flat belly; it is 0 now. (So the shirt's draft moved by THIS, not by front_balance: bodice
  blocks get front_balance, FreeSewing tables get fit_alterations, never both.) test_pattern_draft: __main__ moved last,
  script runs now include the two new tests.
- Review scripts: rvjacket.sh / rvtrousers.sh <tag> <round> (concept crops | sheet front panels; ERROR file when
  renders are missing). chain_t5.sh (detached): offload wait dgrr-180515, then rr.sh's unpack, then rvtrousers dg_t5.
- Shirt s7 (= spec shirt, current code) launched on rented: stage_s7.out.
- j12 (auto front_balance 40 mm, open_lap false, mirror_mesh, construct.mirror "mean"; rented $0.082): FAIL, STUCK.
  The fronts swing open MORE than j11 (hang.py, front edge |x| mm, chest / waist / hem):
  | run | X0 L / R hem | finish L chest / waist / hem | finish R chest / waist / hem |
  | j8  | 48 / 49 | 74 / 51 / 59 | 78 / 60 / 74 |
  | j11 | 49 / 50 | - / - / 157 | - / - / 255 |
  | j12 | 52 / 51 | 119 / 171 / 247 | 120 / 173 / 245 |
  Hem front edge y: L -67, R -210 (j8 -172 / -177): the left front swings back round the side. Starts alike (X0)
  again, so the swing comes in the sim. Symmetry (symchk): lapel flaps p95 0.2 mm, made collar 0.0, front above z 1.15
  p95 28 / max 60 mm (the drape itself is asymmetric; construct.mirror moved the lapels 10 mm). Seams: 3 of 342 sewn
  pairs OPEN (top.L / under.L); underarm under.L / R 48 / 47 mm (target 10-45: FAIL), top 21 / 24; integrity 101
  crossings (fronts 43 / 43) after the clean-up; start pushed off the body up to 70 mm (under.R).
  CONCLUSION: raising the front's neck by the body's front-minus-back did NOT bring back j8's hang, so front balance
  is not the (whole) cause of the j10+ swing. No re-sim (rule). For the coordinator: what else changed j8 -> j10
  besides the hps (the draft diff of every piece, drcmp.py extended to the j8 vs j12 jacket pieces: neck point, shoulder
  slope, side seam lengths, armhole), or take j8 as the base and finish it by hand.
- MY ERROR (cost $0.003): committing the large_abdomen re-base while j12's stage.sh was between rounds changed the
  shirt draft, so round 2 (the jacket is drafted over the shirt) wrote a NEW shirt job, which failed at frame 0
  (job_59811cc701ce1e71: "ccd failed (toi 0)" at newton step 1). j12 was finished with the old rule restored
  temporarily (uncommitted, restored after). Lesson: never change code under an in-flight multi-round stage.sh.
- s7 (the shirt on the re-based draft) = that same failed job: stage.sh refused to resend it, rightly. Its start is clear
  of the start body (3.0 mm, preflight passes); startprox on the END pose body shows 25 vertices per sleeve and 7 per
  cuff inside it (the body moves up to 78 mm; the j12 jacket's start shows the same kind of thing and ran, so this is
  NOT proven to be the cause; an "inside" check in preflight false-fired on the jacket: reverted). Shirt NOT simulated.
- Spend today ~ $2.15 of $5 (j12 $0.082 + s7 $0.003).
- Renders: dg_j12 -> NICO-TOP dgrr-192421; chain_j12rv.sh runs rvjacket dg_j12 r1 when it lands (rv_j12.out,
  out/rv_dg_j12/r1). dg_t5 / dg_j11: dgrr-180515 still queued (80 min); chain_t5.sh runs rvtrousers dg_t5 r1
  (rv_t5.out). Test set: tests.sh launched (tests.log).
STATE: j12 FAIL (STUCK, numbers above); shirt s7 failed at frame 0 (draft re-based); reviews chained on NICO-TOP renders.
NEXT: coordinator: j8-as-base vs a draft diff j8 -> j12; read rv_t5 / rv_j12 when they land; shirt start (why the
re-based draft fails at newton step 1) before any shirt sim.
- Cloth test set (tests.sh, one file per process, capped): all 15 files rc 0 (pattern_draft 11 ok incl. the new tests).

## Handover 2026-10-15 h (dress-garrett)
- Commits (not pushed): f142d82d (cherry-pick bef0229c), 6c1f7f79 (large_abdomen re-base + test), 447b04d7 (test main
  block last), notes 6ca9b695 / 9ed7a88a / this.
- j12 = FAIL, STUCK (table above): front_balance auto did not restore j8's hang. Jacket gets no more sims without the
  coordinator. Not finished by hand; construct.mirror not set in the spec (only for a passing base).
- Shirt s7 failed at frame 0 on rented (job_59811cc701ce1e71, never resend). Its draft moved because the large_abdomen
  re-base stopped a 15 mm spread that had been firing on Garrett's flat belly.
- IN FLIGHT (detached, NICO-TOP queue backed up 80+ min): dgrr-180515 (dg_t5, dg_j11) -> chain_t5.sh -> rvtrousers.sh
  dg_t5 r1 (rv_t5.out, out/rv_dg_t5/r1); dgrr-192421 (dg_j12) -> chain_j12rv.sh -> rvjacket.sh dg_j12 r1 (rv_j12.out).
  A review with missing renders writes out/rv_<tag>/ERROR.
- Spend: ~$2.15 of $5 today.
NEXT: (1) read both reviews; answer every MAJOR in these notes; (2) coordinator: j8 as the jacket base (finish by hand)
or a j8 -> j12 draft diff first; (3) shirt: find why the re-based start fails at newton step 1 (compare its in.npz with
the last shirt job that ran) before one re-sim.
- j8 -> j12 DRAFT DIFF (coordinator's call, no sims; pdiff.py <A> <B>: per piece the flat uv size / area / perimeter,
  X0 start and sim-end centroids, mm). Same body (bbox identical).
  | piece | uv height j8 / j12 | area cm2 | start centroid z | SIM-END centroid (x, y, z) j8 -> j12 |
  | back.L | 783 / 751 (-32) | 1679 / 1606 | 1199 / 1214 | (110, 82, 1215) -> (111, 72, 1248): +33 up |
  | front.L | 783 / 791 (+8) | 1710 / 1721 | 1211 / 1211 | (133, -103, 1194) -> (220, -120, 1248): +54 up, +87 out |
  | front.R | 783 / 791 | | 1205 / 1216 | (-140, -105, 1193) -> (-212, -117, 1245) |
  | side.L | 544 / 540 | 416 / 417 | 1051 / 1067 | (199, 23, 1064) -> (220, -5, 1125): +61 up, 28 forward |
  | under.L | 498 / 530 (+32) | 604 / 632 | 1115 / 1074 | start x 166..360 -> 101..296 (65 mm further in) |
  Widths, collar, top sleeves unchanged (<= 1 mm). RANKED by how much each can swing the fronts open:
  1. THE BACK IS 32 mm SHORTER (the side-neck hps's back tape, 711 -> 673, cut straight into the back length) and the
     front only +8 (front_balance 40 minus the same tape loss). The whole jacket hangs 33-61 mm HIGHER at the end of the
     sim, the side panels most (+61) and they move forward 28 mm: the short back hangs the jacket from the shoulders,
     lifts the side seams, and they pull the fronts' side edges up and round. That fits the coordinator's reading
     (both fronts ~245, the left hem round the side, y -67). The length is drafted as hps tape + "hips" + bonus, so
     moving the hps shortened the GARMENT, not just the balance.
  2. Under sleeve 32 mm taller (deeper armhole; underarm 48 / 47 vs 10-45) and started 65 mm further in: start pushed
     off the body 60-70 mm (rest stretch at the side / underarm, pulling the side seam).
  3. Front balance itself: +40 drafted, but net front length only +8 vs j8.
  NAMED CAUSE: the jacket's back length (back balance) fell 32 mm with the hps move; the hem level is referenced to
  the hps tape. Single pattern change proposed: draft the length to the same hem LEVEL as j8 (back length = the old
  back tape's length, i.e. reference the hem to the waist / seat z, not to the hps tape), keeping front_balance auto
  on top. Not tested (no sim without approval). Lapel break / roll line and darts: not separable from uv stats
  (darts false in the spec; collar unchanged); a per-seam diff of the armhole curve is still owed.
STATE: cause named (back length -32 mm, jacket rides up 33-61 mm). NEXT: coordinator approval for the one sim.

## dress-garrett, 2026-10-15 i (fresh session; coordinator approved ONE jacket sim for the length rule)
- LENGTH RULE (commit 63ad77ce, coordinator's call): a garment's length comes from a fixed body level, never from the
  hps tape. `tailor`: `napeToWaistBack` = the taut tape from the neck loop's centre back (`at["cb_neck"]`) down the
  centre back to the waist; it doesn't depend on where the hps is (nape.py dg_garrett: 489.2 mm under both the side-neck
  and the old widest-x hps, while hpsToWaistBack reads 482.7 / 515.0). `pattern_blocks.bodice`: length = 0.05 neck (the
  back neck's own depth on the pattern) + napeToWaistBack (+ waistToHips for "hips"); the waist line (darts, pockets)
  and the armhole stay on the hps tapes; a numeric length is still metres below the hps. Every bodice block takes it
  (the jacket, and Tess's coat if it is a bodice block: its draft moves, re-key its sims). FreeSewing drafts
  (`cloth.length_level`, the shirt is `simon`): hpsToWaistBack set to the same nape level and waistToArmpit shifted by
  the same amount, so FS's armhole (hpsToWaistBack - waistToArmpit) stays: on the test body (+26 mm) simon's armhole
  moved 3 mm, waist 26, hem 32 (FS scales its hem). Test: test_pattern_draft test_hem_height_does_not_move_with_the_hps.
- j13 = j12 + the length rule ONLY (pdiff.py job_f16cb855 (j12) vs job_1888662c (j13)): every body piece +29 mm at the
  hem, nothing else moved; back 780 (j8 783), front 820 (+40 front balance on top). The UNDER SLEEVE (+32 mm taller,
  start 65 mm further in) does NOT follow from the length: it is the deeper/raised armhole of the hps fix (hpsToArmpitBack
  258 -> 223): separate, left as is. The shirt under it is j12's EXACTLY (collider bodyV max diff 0.0): run with
  XPATH=$G/j13src (a copy of the source with the shirt drafted as for j12: FRONT_BACK_NORM 25, length_level off for
  FreeSewing), because the shirt on the current code needs its own sim (s7 frame-0 cause unknown). run.sh now puts
  $XPATH before $G on PYTHONPATH.
- MY ERROR ($0.006): nape.py called cloth.model_body(..., simulate=True) for the jacket, which re-drafted the shirt and
  resubmitted the failed shirt job (job_59811cc701ce1e71) to rented (failed again, ccd toi 0). Measurement scripts must
  pass simulate=False (and HIFIPUSHIE_GPU=none).
- SHIRT s7 FRAME-0 ("ccd failed (toi 0)", job_59811cc701ce1e71) vs the last shirt jobs that ran (job_6fbc9b50,
  job_ee5cb7d8): selfprox.py / selfx.py <jobs> (start self-proximity, edge x triangle crossings, slivers).
  Cross-piece crossings and near-contacts are about the same in all three (fronts lapped 37 / 65, collar / stand 65 / 61,
  collar / yoke 33 / 35, cuffs folded 3 / 3), so the collar / placket stack is NOT what changed. NEW in s7, and only on
  the wearer's left: a SLIVER in the BACK's mesh at the left armhole (outline vertex v27 at uv (244, -231) and an interior
  vertex v775 2.21 mm apart; a 2.39 mm edge next to it; 2 faces under 10 mm2; the good jobs' shortest edge is 4.05 mm,
  no face under 18 mm2). At the START it has folded: v775 is 0.22 mm from a non-incident triangle of its own piece
  (rest: fine), which is inside the 2 mm contact offset at time 0: the likeliest cause of toi 0. preflight.py checks only
  cloth vs body, so it passed. Not proven by a run (no shirt sim without the cause fixed + approval).
  FIX DIRECTION (code, not yet done): the mesher must not put an interior point closer than ~half an edge to the outline
  (the back's armhole moved with the hps fix / re-drafts, so an interior lattice point landed 2 mm off it); and preflight
  should add same-piece non-incident pairs < contact offset at the start (selfprox's check), cheap.

## Handover 2026-10-15 i (dress-garrett; 70-call clock)
- Commits (not pushed): 63ad77ce (length rule + test), notes. Worktree clean except scratch-only files.
- IN FLIGHT (detached): `XPATH=$G/j13src stage.sh q_dg_j13.txt 3` (stage_j13.out, stage_q_dg_j13_194915.r*.out,
  dg_j13.log): the ONE approved rented jacket sim. Round 1 was still drafting at handover; it writes job_1888662c5e641270
  and submits it. DON'T commit code that changes the shirt / jacket drafts while it is between rounds (it reads $G/j13src
  for the package, but scripts are in $G). Renders then go to NICO-TOP via rr.sh (rr_q_dg_j13.out).
- Reviews: dgrr-180515 (t5 / j11, queued 106 min) -> chain_t5.sh -> rv_t5.out / out/rv_dg_t5/r1; dgrr-192421 (j12) ->
  chain_j12rv.sh -> rv_j12.out / out/rv_dg_j12/r1. Not landed yet: no verdicts to record.
- Spend: ~$2.16 + j13 (~$0.10, pending) + my $0.006 shirt resubmit (error above).
NEXT: (1) `bash run.sh hang.py dg_j13` beside j8 (hem edge |x| 59 / 74, y -172 / -177; j12 247 / 245): PASS -> the
base, finish on the drape; FAIL -> report STUCK with the table, no re-sim. (2) bin/review for j13 (rvjacket.sh dg_j13 r1)
when its renders land; read rv_t5 / rv_j12 and answer every MAJOR. (3) shirt: mesher sliver fix + preflight self check,
then ask for one shirt sim (the shirt now also takes length_level: its hem drops ~33 mm on gp_h6c). (4) Tess's coat: if
it is a bodice block its length changes with 63ad77ce: tell dress-tess.

## Handover 2026-10-15 j (dress-garrett; 70-call clock)
- j13 (napeToWaistBack length, job_1888662c5e641270, rented $0.0825): FAIL, STUCK, reported to main, no re-sim.
  hang.py front-edge |x| (finished V, L / R mm): hem j8 59 / 74 vs j13 244 / 239 (j12 247 / 245); waist 51 / 60 vs
  188 / 192; chest 74 / 78 vs 130 / 130; hem off body 128 / 111 (j8 26 / 34). Starts match j8 (X0 hem |x| 52 / 51), so the
  swing happens in the sim. 50 crossings after clean-up (6 in sim); lapel roll ends 38 deg (from 167). So the length
  rule was NOT the cause.
- (3) DONE a0a615df: rented submits need cloth_job.submitting() or HP_SUBMIT_SIMS=1 (cloth.dress's worker and
  garments(simulate=True) opt in; cloth_workflow's measuring body now simulate=False). Free remotes (have.sh,
  nobox.sh, $HP_FREE_REMOTES) are not gated. Otherwise run_zozo raises SimNotSubmitted. Test:
  test_tooling.test_rented_sims_need_an_explicit_opt_in. stage.sh needs no change (BROKER=1 + bl.sh).
- (2) Mesher: NOT changed, and the diagnosis was wrong. s7's v775 is 15.6 mm (0.78 h) off the outline in the pattern,
  and the lattice already keeps 0.6 h. The sliver is a PLACEMENT crush: that back edge starts at 0.14 x its pattern
  length (good shirts 0.48 x at the same armhole spot). cloth_job.start_self_check (a0a615df, test reproduces s7 on a
  synthetic grid + the real jobs when cached) fails a same-piece vertex inside the contact gap of its own sheet facing
  the same way (a crush). Fold rows +1 ring and fold-overs (opposite facing: lapel creases at 0.04 mm ran in j8) are
  exempt. Squeezed edges are reported only: j8's undercollar started at 0.13 x and ran. $G/preflight.py now runs it
  (skips on snapshots without it, e.g. j13src). Calibrated: s7 FAIL; s6-era shirts, j8, j12, j13 ok.
- s8 (shirt on current code incl. length_level, job_af3ca3e0866feb40): body preflight 3.00 mm, self check ok, no edge
  under 0.25 x. Submitted (the ONE approved). FAILED at frame 0 on rented in 2 s: ppf-cts-solver backend.rs:1347
  "failed to advance", $0.0020. Never resend. So the self check is necessary but not sufficient: s8's frame-0 cause
  is still unknown. Next: compare s8 vs the last good shirt job (job_6fbc9b50) with selfx.py (edge x triangle
  crossings by piece pair: s7's cross-piece counts matched the good ones) and stitches (297 vs ?), before asking for
  any sim.
- (4) armhole, measured from j13's log (no draft change): underarm below the body's armpit top.L / R 19 / 19 mm,
  under.L / R 47 / 45 (the check's range 10-45; guide: jacket ~3 cm). The top sleeve is a little shallow and the under
  sleeve a little deep, 27 mm apart, so the fault is the two-piece sleeve's under-seam placement, not the armhole
  depth. Left for after the HPS A/B: the HPS change moves this too.
- (5) t5 review (out/rv_dg_t5/r1/review.md): VERDICT FAIL. Trousers MAJORs: legs barely taper (thigh -> hem ~140 ->
  115-120 px vs ref 165 -> 100); front crease lost below the knee; no hem break (soft collar on the shoe); white flecks
  at the front hems (something shows through); no fly placket / crotch drag folds; belt missing. OTHER STAGES: shoes
  crude with holes at the toes; shirt pale blue, ragged placket. No answers yet. j12 review (dgrr-192421) still queued.
- Spend today ~$2.27 + j13 $0.0825 + s8 $0.002 = ~$2.36 of $5.
STATE: j13 FAIL/STUCK; s8 FAIL at frame 0; guard + self check committed (a0a615df).
NEXT (coordinator APPROVED, one rented sim): j14 = j13's exact code + settings with ONLY the HPS definition back to
the old widest-x point. Add a flag, don't revert: tailor.py:245 `at["hps.L"], zc_ = _side_neck(V, T, L)`. The old
value is `at["neck_side.L"]` (L[argmax x]). Make it e.g. pattern measurements / env hps="crest"|"widest", defaulting
to crest so no cached key moves. Run with `stage.sh q_dg_j14.txt 3` (same line as q_dg_j13 + the flag). If j14 hangs
like j8: NO sim, diff the drafted lines that read the hps (shoulder seam, neck point, back neck width, lapel break /
roll line, front shoulder slope), j13 vs j14 per line, and report which lines move the fronts. If j14 still swings:
pdiff the job inputs j8 vs j14 (placement, settings, mirror_mesh / construct.mirror: j12 / j13 added mirror_mesh=true
+ construct.mirror="mean", j10 / j11 had neither) and report before any further sim.

## Handover 2026-10-15 k (dress-garrett; 70-call clock)
- (1) j14 A/B (df7a9208: `HP_HPS=widest` env in tailor.measure = the old hps, the neck loop's widest point, no
  neck_base_z; default "crest", no cached key moves). Run `HP_HPS=widest stage.sh q_dg_j14.txt 3`. The env reaches the
  SHIRT under the jacket too, so the build first wrote a new shirt: sim job_354254cf1a529fe6 SUCCEEDED (44 s, $0.0203)
  and its fine settle succeeded ($0.0112). The JACKET start (job_5c4f11ea993b2572) was REFUSED by preflight: self check
  FAIL, 2 same-piece crushed pairs, under.R 0.15 mm / under.L 0.27 mm (most squeezed edges under.L 0.12 x, under.R
  0.14 x their pattern length). Not submitted. So no jacket verdict: the A/B is BLOCKED at the start, the widest hps
  crushes the under sleeves in placement (j13's crest start passed the check).
- Preflight fix (scratch $G/preflight.py): the self check skips fine settles. They start from a sim's rest, cloth
  folded on itself at the contact gap: the fine settles that ran (6fbc9b50, 7813e7ca, 0c06de36) all read 39-55
  crushed pairs at 0.3-0.8 mm, so the check is for first sims' starts only (it first refused j14's shirt fine settle).
- (2) Shirt frame 0. backend.rs:1347 panics when `advance` fails; the solver log says `### ccd failed (toi 0)` at time
  0, Newton step 1 (driver/step.rs:2389: the line-search toi = min(contact CCD, strain-limit CCD) <= f32 eps). No
  OverlappingStart record was printed. ccd.rs's notes say ACCD returns 0 without a record when the first advance
  underflows, i.e. a pair essentially touching that the step drives together. The failed job's full log isn't kept
  (the batch status holds only the tail). Static measures on the runner's start (part_stitches applied:
  $G/startgap.py, eegap.py, slim.py (the strain-limit set-up replayed), stdiff.py, sewthru.py) do NOT separate s7 / s8
  from the shirts that ran: v-t 0.01 mm and e-e 0.002-0.01 mm cross-piece pairs (fronts, stand / collar) in all of
  them, body 3.0-3.6 mm, ~2.5% of triangles over the strain limit in all of them, no stitch through the body.
  ONE difference: the sleeve underarm seam starts open 103-105 mm in s7 / s8 and 91-92 mm in every shirt that ran,
  including j14's shirt, which is s8's code with ONLY the hps switched. So the crest hps is what makes the shirt fail
  at frame 0 (s7 / s8 are the only shirts drafted with it). The mechanism is still unknown, and NO preflight was
  written: I couldn't reproduce the cause, only correlate it.
- (3) Sleeve underarm: the check's "top 19 / under 47" is NOT a placement fault. underarm_drop_at reads the TORSO
  vertices sewn to each sleeve piece. The under sleeve is sewn to the armhole's bottom, so its number is the armhole
  depth; the top sleeve's is only where its seams end on the armhole (the pitch points), always higher. $G/ua_jk.py on
  j13: under -68 vs top -94 (same 26 mm in the start, -67 / -137). The fault is the armhole bottom at 45-47 mm under
  the armpit (guide ~30, j8 62). Fix = the jacket block's armhole_depth about -15 mm, on the next approved jacket sim,
  measured by the same check. Not changed.
- (4) t5 trousers plan (no sim; needs approval): pattern = leg cut "tapered" (knee +30%, hem 0.80 x knee) -> "slim" or an
  explicit hem ~36-37 cm (ref taper 165 -> 100 px vs ours 140 -> 117); crease = a pressed fold line along the
  draft's crease (folds.py) to the hem; length = length "break" (sloped hem, BREAK_BACK) so one break sits on the vamp;
  flecks = render / material (probe with $G/fleckprobe.py before any sim); fly placket + belt in the waistband = made
  pieces after the drape.
- Spend: j14 shirt $0.0203 + fine settle $0.0112; day ~$2.39 of $5.
STATE: j14 BLOCKED (jacket start crushes the under sleeves, not submitted); shirt frame 0 correlates with the crest
hps, cause unknown; preflight skips fine settles.
NEXT (coordinator's call): (a) j14's under-sleeve crush is a placement fault. Fix it, or exempt it, before any A/B
sim. (b) For the shirt: with NO sim, diff the shirt draft crest vs widest (sleeve seam, armhole, cap) to find the
line that opens the sleeve underseam 12 mm more. Or keep the failing log: a free NICO-TOP frame-0 probe (frames 1,
full solver log) of s8 would name the pair.

## Handover 2026-10-15 l (dress-garrett; 70-call clock reached, STOPPED)
Coordinator decisions after k: (1) drop the j14 A/B. With NO sim, diff crest vs widest (jacket AND shirt) for every
drafted quantity downstream of the hps, find which tape feeds the armhole, and re-derive it from an hps-independent
landmark (armpit level, as 63ad77ce did for the length rule with the nape), with a test. Target: armhole bottom about
30 mm below the armpit by the underarm check. Then ONE jacket sim j15 = crest + the armhole fix (APPROVED); if it
still swings, report it with the diff numbers. (2) APPROVED: a free NICO-TOP 1-frame probe of s8 that keeps the full
solver log. If the pair it names sits at the underarm seam, the preflight check can test for that. (4) APPROVED: probe
the trouser flecks first (no sim), then ONE rented trousers sim with taper + crease line + hem-break length.
Also: port the scratch preflight's fine-settle skip into the repo's preflight, with a test.
- Body tapes, crest vs widest ($G/mmab.py dg_garrett, tailor.measure under HP_HPS): the hps moves from
  [61, -36, 1549] to [45, 4, 1556] mm, 40 mm BACK and 16 mm in. Every tape from the hps moves by about 35 mm, back
  and front in opposite directions:
  - hpsToArmpitBack 258.0 -> 222.6 (-35.4)
  - hpsToWaistBack 515.0 -> 482.7 (-32.3)
  - hpsToSeatBack 710.7 -> 673.3 (-37.4)
  - hpsToBust 249.0 -> 280.9 (+31.9)
  - hpsToSeatFront 678.4 -> 713.2 (+34.8)
  - shoulderSlope 10.9 -> 9.9
  Nothing else moves. So the crest moves front / back BALANCE by about 67 mm (front about 33 longer, back about 35
  shorter), and the armhole's back depth tape (hpsToArmpitBack) by 35 mm. That is the likeliest common cause of the
  jacket swing, the deeper armhole and the shirt's wider underseam opening. Not yet checked: which block lines read
  these tapes (pattern_blocks: armhole depth from hpsToArmpitBack? front length from hpsToBust / hpsToSeatFront?).
NEXT: grep pattern_blocks / tailor for these five tapes. Make the armhole depth (and, if the fronts read hpsToBust /
hpsToSeatFront, the front balance) come from the armpit / waist levels, not the hps. Add a test that the draft's
armhole depth and front / back balance do not move when the hps moves 40 mm. Measure with the underarm check
(target about 30 mm), then j15 (approved). The s8 probe and the trouser fleck probe need no money.

## Pre-placement cache (2026-10-16, render1b agent)
cloth.build caches its finished result under a key of its inputs BEFORE placement (`cloth.pre_key`: garment, body
mesh + joints + key, the garment under it (sim key, pressed verts, its own pre_key), worn colliders, frames, the
source of the whole package + json): `_cache/cloth/pre_<key>.pkl`, used only while the sim npz it names exists; a
cached_only build that found no sim leaves `pre_<key>.miss` (that sim key), so an unsimulated garment isn't placed
again. garments() / cached() memoise builds and body meshes for the call (the jeans were built 3x, body_mesh 6x).
dt_tess COPY (jeans simulated, sweater + coat not): cloth-only garments() 464-657 s cold -> 13 s warm; jeans V,
V_sim, X0, rest, mesh F/uv/piece and sim key identical to the old path. Any edit under src/hifipushie re-keys every
pre entry once (the sim npz keys are unchanged); renders, `result=` and place_only always run; a pre hit doesn't
replay build()'s log lines; HIFIPUSHIE_CLOTH_PRE=0 turns it off. tests/test_cloth_precache.py. Agents: merge main.

## Handover 2026-10-15 m (dress-garrett; 70-call clock)
- Merged main (one Blender per job 01917898, pre-placement cache b9551475; d4cac458). Cloth tests one file per
  process: all pass (before and after the change below).
- HPS by the standards. ANSUR II measurer's handbook (TR11-017, downloaded to /mnt/data/hifipushie/standards/
  ansur2_tr15007/; DTIC was down, openlab.psu.edu mirrors it): 5.2.43 trapezius point = where the trapezius' anterior
  border crosses the LATERAL NECK landmark, which (5.2.29) is the bottom of a tape laid round the BASE of the neck over
  the anterior neck point. ISO 8559-1's side neck point is the same idea (text paywalled, not read). Both old hps sat
  on the loop 2 cm UP the neck: neither is on the base line.
- New default (4e6be7bb): tailor._neck_base = the lowest section of a plane tilted 32 deg (front down; ANSUR
  cervicale - suprasternale 79 mm men / 66 women) that is still the neck's loop (girth within 1.06 of the narrowest
  such loop); hps = its outermost point (no muscles to palpate). HP_HPS=crest / widest keep the old ones.
- Population check: shoulder length (hps -> shoulder point, chord) against ANSUR II p5-p95 men, / stature 0.076-0.095,
  / biacromial 0.330-0.391 ($G/m/hpsab.py):
  - dg_garrett: widest 170 mm (0.096 OUT / 0.391), crest 187 (0.106 OUT / 0.432 OUT), base 159 (0.090 / 0.366 ok).
  - dg_mh: widest 159 ok, crest 185 OUT / OUT, base 148 ok. gp_A01: widest 168 ok, crest 170 OUT, base 152 ok.
  - Tess (dt_tess, ga_tess; women p5-p95 0.074-0.093 / 0.339-0.405): base 99-103 mm OUT, widest 111 OUT, crest
    125 ok. But her shoulder breadth itself (2 x shoulder point x = 313 mm) is under the women's p5: the shoulder
    point, not the hps, is the outlier there (crest passes only by moving 15 mm in). FAIL on Tess, reported.
  - Fore-aft: no standard number exists for it (ANSUR has none); base sits at y -30 on Garrett, near widest (-36),
    crest +4. Front minus back to the seat: widest -32, crest +40, base -31.
- FRONT_BACK_NORM_MM re-read on the base hps: -14 (largest of the flat bodies: garrett -31, dt_tess -26, ga_tess -18,
  gp_A01 -14). dg_mh read +76 (crest) and -50 (base): the base tapes don't show his belly; open question.
  front_balance "auto" kept: 0 on Garrett with the base hps (as j8).
- Jacket redraft, no sim ($G/m/drab.py dg_garrett jacket), widest (j8's hps) | crest (j10-j14) | base:
  - front balance 0 | 40 | 0; armhole front + back 282 + 273 | 289 + 241 | 264 + 255 mm (front - back 9 | 48 | 9);
    sleeve top shifted -7 | -35 | -7 mm; cap height 206 | 188 | 181.
  - armhole depth (from hps on the pattern) 293 | 258 | 276 = the back tape to the armpit 258 | 223 | 241 + 35.
    So the base draft's BALANCE is j8's; the crest's 40 mm front balance and 48 mm armhole asymmetry were the swing.
  - Armhole depth in the world is NOT fixed by the hps: every draft puts the underarm 35 mm down the tape below the
    armpit, and the hang lost 27 (j8: 62 below) / 11 (j13 crest: 46). The ~30 mm target needs the block's underarm
    allowance (UNDERARM_DEFAULT + armhole_depth share) cut, measured on a placement. Not changed.
- Shirt: its FreeSewing log isn't in P["log"] (drab printed only tapes). hpsToWaistBack is forced from the nape in
  all three; hpsToArmpitBack 258 | 223 | 241. The underseam opening (91 good vs 104 crest) needs a placement: NOT measured.
STATE: hps landmark fixed (base-of-neck), tests pass, jacket balance back to j8's in the draft. No sim run, $0 spent.
NEXT: (1) place_only the jacket and shirt on the base hps: underarm check ($G/ua_jk.py) and the sleeve underseam
opening; (2) if the shirt opens ~91 mm, j15 = base hps jacket (approved) with the underarm allowance cut ~25 mm if the
placement still reads ~60 below; (3) s8 probe only if the shirt still opens >100; (4) trousers flecks + t5;
(5) port the preflight fine-settle skip ($G/preflight.py) with a test. Tess's shoulder point to the dress-tess thread.

## Handover 2026-10-15 n (dress-garrett; 70-call clock)
- (1) Underarm allowance, measured on PLACEMENTS (BROKER=1 run.py: the start is written, nothing submitted; jacket over
  the shirt pinned to out/dg_s6.npz). Garrett's armpit z = 1.362 (tailor; ua_jk.py's default 1.252 is not this body:
  pass 1.362). The jacket's allowance is the SPEC's block_options.underarm 0.035 (the code default 0.025 doesn't reach
  it). Start numbers ($G/uastart.py, ua_jk.py, stdiff.py, preflight.py), armhole bottom below the armpit | cap height |
  longest stitch gap at the start | preflight:
  - j8 (ran): 60 | - | 92 mm | ok.  underarm 0.035 (base hps): 58 | 178 (73% of depth) | 126 (top-under) | self FAIL 2
    crushed pairs side.R 0.8 mm.  0.020: 48 | - | 184 (under-back) | ok.  0.010: 41 | 143 (65%) | 257 | ok.
    0.010 + biceps_ease 0.08: 41 | - | 198 | ok.
  - The cut WORKS on the torso (draft: armhole depth 276 -> 251, the world armhole 17 mm up; target ~30 below, 41
    reached at 0.010). But the cap drops faster than the armhole rises (fixed biceps, shorter armhole: 178 -> 143),
    so the sleeve crosses the bodice and place() pushes both sleeve pieces down the arm (the _down loop, up to 10 cm):
    the under sleeve starts 18-26 cm off its armhole seam. Every cut tried (0.020, 0.010, 0.010 with a narrower
    sleeve) does this. NO j15 sim: its start is a placement fault, not worth $ (the sew stage would haul 20+ cm).
  - Fix needed (placement, not pattern): the cap-height / armhole-depth match the push-down loop assumes, or align
    the sleeve's underarm to the armhole bottom instead of its cap top to the shoulder point for a set-in jacket
    sleeve. Not changed (the coordinator's call: placement code shared by every garment).
- (3) Shirt start on the base hps (job_8d54e01c87f818d4): underseam opens 101 mm (s8 103, failed; good shirts 91-92):
  NOT the good shirts. Draft diff widest -> base ($G/shdiff.py): only waistToArmpit (240 -> 260, derived so the forced
  nape length holds) and hpsToArmpitBack (258 -> 241) move: sleeve 408 -> 399 mm wide, yoke 122 -> 117 high. The
  narrower sleeve on the same arm cylinder opens ~10 mm more: the likeliest link to frame 0. Preflight passes it.
  Free NICO-TOP probe submitted (batch dg_probe_s8_base, $G/probe/: s8 + this shirt, a copy of the runner that keeps
  solver_stdout.log, 6 frames): QUEUED behind ~9 batches when this session stopped. Pull with
  `offload wait dg_probe_s8_base`; logs land in $G/probe/results/.
- (4) large_abdomen now reads the body directly: tailor mm chestDepth / waistDepth (section y extents),
  ALTERATIONS large_abdomen = excess of waistDepth - chestDepth over ABDOMEN_NORM_MM -17 (ANSUR II men's median;
  p5 -47, p75 -4, p95 +18; women's median -35, bust in the chest). Bodies: dg_garrett -32, gp_A01 -31, MakeHuman
  default male (workspace dg_mh0) -45, dg_mh -14 -> 3 mm. So dg_mh's belly is a median man's by the population
  (wd/cd 0.95 vs ANSUR p50 0.93): the alteration barely fires on him. The deepest band below the waist is the seat,
  not the belly (useless as a measure). Test updated (tests/test_pattern_draft.py).
- (5) Trouser flecks, no sim ($G/fleck2.py on workspace/dg_garrett/build/closeup.npz): BODY SKIN through the
  footwear, not the trousers: 73 skin vertices at the shoe's throat (z 0.10-0.105, 2.4-4.5 mm outside the shoes,
  nearest cover = shoes, not socks) and 115 at the toes (up to 9 mm out, shoes / soles). OTHER STAGE (footwear: the
  shoes and socks must cover the foot); no trousers sim fixes it. Trousers sim NOT run (taper/crease/break untested).
- (6) cloth_job.preflight(arrays, cfg): body clearance (2 mm first sims, 1 mm fine settles) + start_self_check for
  first sims only (fine settles skipped); tests/test_tooling.py test_preflight_skips_the_self_check_on_fine_settles.
- For the coordinator (Tess): her shoulder breadth (2 x shoulder point x) 313 mm is under ANSUR II women's p5, so on
  the base hps her shoulder length reads 99-103 mm (women p5-p95 / stature 0.074-0.093 OUT; crest 125 passed only by
  moving the hps 15 mm in). The outlier is her shoulder point, not the hps.
- Spend: $0 this session (day ~$2.39 of $5).
STATE: allowance cut verified on the torso (58 -> 41 mm under the armpit) but every cut start has the sleeves pushed
10 cm down the arm (stitch gaps 184-257 mm): j15 NOT run, STUCK at placement. Shirt start = the failing class (101 mm).
NEXT: (a) placement: keep a set-in sleeve's underarm on the armhole bottom when the cap is lower than the armhole
(or raise the cap: cap ease / a higher cap for tailored jackets, 80%+ of depth), then re-place 0.010 and expect the
gap <= j8's 92 mm; (b) read the probe logs when dg_probe_s8_base ends; (c) footwear coverage to its stage owner.

## Handover 2026-10-15 o (dress-garrett; 70-call clock reached, STOPPED)
- (b) Cap height by garment kind (pattern_blocks.CAP_HEIGHT_BY_KIND jacket / coat / blazer 0.75; cap_for_height;
  pattern_draft.op_sleeve measures the armhole depth as a tailor does: vertical, shoulder point to underarm, front/back
  mean; the design's kind reaches the draft through garment_design's pattern dict -> D["meta"]["kind"]). Source: "about
  2/3 to 3/4 of the armhole depth measured vertically from the shoulder point to the underarm" for a fitted sleeve
  (Pattern Principles Oct/Nov 2005, quoted on the Threads Magazine pattern-drafting forum; secondhand, original not
  read); tailored = the high end, shirts lower (minervapatterns.com, sleeve block and armhole); a basic cap ~2 cm short
  of the armhole depth (US4894918A). Order: cap ease up to CAP_EASE_MAX 0.05 (coat band 3-6%), then the biceps ease down
  to CAP_BICEPS_EASE_MIN 0.08; never below the plain solve. Shirts / knits unchanged (kind not listed).
  Jacket drafts ($G/capdraft.py): underarm 0.035: depth 245, cap 184 (75%), cap ease 4.5%, biceps 15%.
  underarm 0.010: depth 220, cap 162 (74%), cap ease 5.0%, biceps ease 8% (at the floor: a slim jacket sleeve, 342 mm).
  Test: tests/test_pattern_draft.py test_jacket_cap_height_from_the_armhole_depth (all draft tests pass).
- (a) Placement by notches (cloth._sleeve_notches + place(_set=)): with sleeves_set, after the torso is laid, each arm's
  anchor sleeve moves DOWN so its underarm point(s) (underarm / underarmF / underarmB) are level along the arm with the
  torso point they are sewn to (only down; a high cap keeps its crown at the shoulder point). The _down loop stays as
  a last resort and now warns (B["place_warnings"] + warnings.warn). Bug fixed in it: an "align"ed piece (two-piece
  under sleeve) took its own _down ON TOP of its anchor's, so it went down twice as far (the 18-26 cm). Test:
  tests/test_tooling.py test_set_in_sleeve_is_set_by_its_underarm_notch.
- j15 start with both (underarm 0.010, over pinned dg_s6; job_86b74bac2c965b50, BROKER, nothing submitted):
  armhole bottom 1321 = 41 mm under the armpit (1.362; target ~30: NOT reached, the allowance cut is unchanged by this),
  under sleeve top 1310; longest sew gap 184.6 mm under.L-back.L (180 R), top.L-under.L 173 (was 257; j8 92: NOT
  reached); preflight body ok (7.8 mm) + self ok. No place warning in the log (the _down loop did not fire?). FAIL.
  Not diagnosed (out of calls): the top/under gap of 173 mm says the two sleeve pieces are not set together; check
  B["sleeve_set"] (is under aligned in this jacket, or its own anchor?) and whether the crown, now set down the arm by
  (shoulder point -> armhole bottom) - cap, leaves the back armhole's upper stitches (vertex 57) far off.
- j15 sim NOT run ($0; day ~$2.39 of $5). Shirt probe dg_probe_s8_base still QUEUED (45 min). Footwear flecks not touched.
- Regression running detached ($G/regr.sh: $G/regr.py on dg_garrett:shirt, dt_tess:jeans/sweater/coat, old code
  = 7f41b098 archive in $G/oldsrc via XPATH, then new): read $G/regr_old.out vs regr_new.out (RES lines: gap max,
  crossings, set/down, warnings). wf_/pd_/ga_ gates not run (gates.py needs the garments env; not tried).
STATE: cap-height-by-kind + notch setting + align double-down fix in, tests pass, j15 start FAILS (41 mm, gap 185 vs 92).
Regression unread. NOT MERGEABLE until regr_new is no worse than regr_old.
NEXT: (1) read regr outputs; (2) print B["sleeve_set"] / wraps for the jacket (add to run.py) and fix the top-under
separation; (3) then j15 placement again, sim only if gap <= ~100 and underarm ~30; (4) probe logs; (5) footwear.

## Handover 2026-10-15 p (dress-garrett; 70-call clock)
- (1) j15 start = base hps + notch placement + cap rule + underarm 0.035 (the j8 allowance), placement only (BROKER
  run.py, jacket over pinned dg_s6; $G/runp.py = run.py printing B["sleeve_set"]; HP_DEBUG_ARM=1 for the cylinders):
  - sleeve_set {top: 0.0}: at 0.035 the cap (75%) is high enough, so notch placement does nothing here (as asked).
  - As handed over (job_1a286cd4581c6256): longest gap 126 mm top.L-under.L, self check FAIL (side.R 0.78 / 0.88 mm):
    notch placement did NOT cure the self check. Armhole bottom 1300 = 62 mm under the armpit (j8's 62).
  - (2) the sleeve pairing, diagnosed ($G/tu.py: seam pairs by angle round the arm): the UNDER sleeve was pushed out
    round the arm on its own by the push-out rounds (its corner at the armpit; the body isn't radial to the arm there):
    R 59 -> 78 -> 97 -> 121 mm while the top stayed at Rp 88, both sleeve seams ~75 deg apart (j8: ~55 deg, 82 mm).
    FIX (cloth._sleeve_push_out): a piece aligned to another on its arm is never pushed out alone; its local push is
    left to the clearance pass. Test tests/test_tooling.py test_aligned_under_sleeve_is_not_pushed_out_alone.
    After: sleeve seams 83-86 mm (j8 90-92). Longest gap now back.L-side.L 111 mm (j8 100): a torso seam, from the
    base-hps draft (present before the fix too). Per pair: $G/pairgap.py <job keys>.
  - Self check: the crushed pairs are the side panel's armhole bottom (z 1.30, edges at 0.11 x) and, after the fix,
    the under sleeve's front corner at the armpit (0.66 mm, a Z-press). Added cloth._self_crushed / _uncrush /
    _unstack after the clearance pass (open crushed edges to 0.5 x, lift same-facing pairs to 1.5 mm, only round the
    self check's pairs). On the jacket: self check ok. But on Tess's jeans (whose start RAN) it raised the start
    stretch 0.04 -> 0.35 even when local: their sub-1 mm pairs (my mask is ~made_v, the preflight also skips
    carryIdx / fold rings: that difference is the next thing to read) are harmless. So it is OFF by default:
    HP_UNCRUSH=1 turns it on. Underarm 0.040 (not asked): sleeves 84, back-side 93, one pair at 0.96 mm.
- (4) Regression (place_only, $G/regr.py; old = 7f41b098 in $G/oldsrc): defaults on the new code = old on
  dg_garrett:shirt (101 mm, p95 92, stretch 1.067) and dt_tess:jeans (185 / 157 / 0.04); jeans' start arrays
  byte-identical (only the key, which hashes the code, moved: I copied job_0b4e1e25's out.npz into job_8be5228f so
  the layers over them can place). Sweater / coat need the jeans' / sweater's sims under the new key: the sweater's
  new start NOT compared (old: 119 mm cuff-cuff, p95 74). wf_/pd_/ga_ gates not run. ga_tess has no cloth key.
- (5) probe dg_probe_s8_base: still QUEUED on NICO-TOP (~1 h) when this session stopped. Not read.
- No sim run, $0 (day ~$2.39 of $5).
STATE: j15 start (HP_UNCRUSH=1, underarm 0.035): longest gap 111 mm (<= 120), preflight body 7.1 mm ok + self ok,
armhole 62 mm under the armpit (= j8). Ready for the ONE approved rented sim; not submitted (calls).
NEXT: (a) submit j15 with HP_UNCRUSH=1 (same command as dg_j15j35 in $G, without BROKER, under the submit opt-in),
measure the hang against j8 (hem |x| 59/74, waist 51/60, chest 74/78): PASS -> j15 base, finish by hand; FAIL ->
STUCK; (b) the sweater regression (needs the jeans sim under the new key, or pin); (c) why the jeans' pairs are
harmless (mask vs preflight skips), then UNCRUSH on by default; (d) probe logs; (e) armhole depth later.
- Late check: with the defaults (HP_UNCRUSH off) jeans read 220 / 165 / 0.045, but dt_tess/spec.json was edited at
  22:53 by dress-tess mid-run (history 0086): not comparable. The align-fix-only run on the unedited spec matched old
  exactly. Re-run regr.py on a frozen copy of dt_tess next time. HP_UNCRUSH=1 jacket start = job_8d2453a84a44a9d7.

## dress-garrett 2026-10-15 q (in progress)
- j15 rented sim (HP_UNCRUSH=1, job_8d2453a84a44a9d7) FAILED at frame 0, $0.0014: "ccd failed (toi 0)". Cause = ZOZO's
  strain limiter (strain_toi.kernel: a face starting at / past its limit returns SL_toi 0), not a contact pair.
  cloth_zozo gives over-limit draped triangles a local limit only while they are <= start_over 3% of the cloth: j15
  3.47% over 5% (217 faces; worst side.R armhole bottom 1.42x, front shoulders z 1.47-1.50 1.26-1.39x) -> no local
  limit -> fail. Every base-hps j15 variant 3.23-3.47% (uncrush adds ~14 faces). j8 (ran) 2.27%, 0 past.
- Shirt probe dg_probe_s8_base, the frame-0 "pair": the same limiter. Base-hps shirt 3.04% (OFF), worst front.R at the
  neckline z 1.52, 4.25x = the solver's max_sigma 4.252; s8 2.50% (on) with 31 faces past the 100% cap (s5 / s6 ran with
  26-28: s8 is marginal there). Tool: $G/slstart.py <job dirs>.
- cloth_job.start_strain_check (replays cloth_zozo's limits without editing it) in preflight; run_zozo now refuses a
  PAID submit whose start fails preflight (HP_SKIP_PREFLIGHT=1 overrides). Test test_preflight_fails_a_start_past_the_
  strain_limiter. On real jobs: j15 FAIL, base shirt FAIL, j8 / s6 ok.
- Coordinator: NOT start_over (solver tuning); the base-hps draft no longer fits at the shoulders / neckline / armhole
  bottom: diagnose pattern edge vs body path, fix in the draft from the base-of-neck ring, relax only a residual.

## Handover 2026-10-15 q (dress-garrett; 70-call clock)
- (1) j15 rented sim submitted as approved (HP_UNCRUSH=1, $G/q_dg_j15s.sh, job_8d2453a84a44a9d7): FAILED at frame 0,
  $0.0014 (day ~$2.39 of $5); not resubmitted. No hang to measure: verdict FAIL / STUCK sent to the coordinator.
  Cause (no contact pair): ZOZO's strain limiter (see q above): 3.47% of the start's triangles > 5% stretched, over
  cloth_zozo's start_over 3%, so no local limit. Every base-hps j15 variant 3.23-3.47%; j8 2.27%.
- (5) Probe dg_probe_s8_base read ($G/probe/results/*/solver_stdout.log: both fail at newton step 1, SL_toi 0): the
  frame-0 "pair" is the strain limiter at the FRONT NECKLINE (front.R tri 2349, z 1.525, x -0.07: 4.25x = the solver's
  max_sigma). Preflight check written (cloth_job.start_strain_check, in preflight; run_zozo refuses a paid submit that
  fails it; test test_preflight_fails_a_start_past_the_strain_limiter). Commit 22d53eda.
- Coordinator's decision: NO start_over raise (solver tuning). Fix the draft where it no longer fits the base hps;
  relax_strain only for a small residual afterwards; then ONE approved j15 if preflight passes; shirt gets the same fix.
- Diagnosis so far (no sim; $G/overmap.py <job dirs>, $G/necks.py <model> <garment>):
  - Over-limit faces are stretched LENGTHWISE (pattern v) at z 1.45-1.55 (shoulders / neck), fronts and backs.
    j15 vs j8: fronts ~70 vs ~35 faces (front.L/R 1.5 v 23/24 vs 4/11), backs about the same (~100 both). The FRONT
    is what the base hps broke; the backs were over in j8 too.
  - dg_garrett body, base hps: hps.L [62.6, -30.2, 1519.4] mm = the base-of-neck ring's lateral point; the ring is
    tilted 99 mm: cb (nape) 1569.8 = 50 mm ABOVE the hps, cf 1470.9 = 48.5 below. Ring girth 430.8 (the loop up the
    neck 406.5); quarter arcs front 105, back 108.
  - Draft (pattern_blocks.bodice, all from mm["neck"] = the UPPER loop): neck width nw 89 mm (ring half width 62.6:
    the pattern is 26 mm WIDER), front neck depth 62 below the hps line (body 48.5), back neck bn = 0.05 x neck = 20
    BELOW the hps (body: 50 ABOVE: 70 mm short at CB). Neckline length 427 (406.5 x 1.05) vs ring 431: NOT short.
  - So the neckline girth is fine; its SHAPE does not match the ring the base hps sits on: wider and with the hps at
    the ring's mid height, the back neck rises 50 mm above it on the body. Not yet checked: the front's path hps ->
    chest over the shoulder vs the pattern (hpsToBust is not read by the draft's front length, only by a bust dart),
    and the shoulder seam (pattern nw -> sx, 152 mm, vs the body hps -> shoulder point).
  - Suspicion to test first: nw / fn / bn should come from the ring (half width, cf / cb drop from the hps), i.e.
    `neckBase` + the ring's points from tailor (loops["neck_base"]), not mm["neck"]; and/or the base hps itself is too
    low (50 under the nape; real side neck points sit near the cervicale's height): check ANSUR (cervicale height -
    trapezius-point height) before changing either.
- (4) Regression on a FROZEN copy: workspace/dt_tess_frz (spec.json + cloth_*.npz + history copied 2026-10-15 ~23:00,
  from dt_tess history 0086). $G/regr2.sh -> regr2_old.out (7f41b098) / regr2_new.out / regr2_unc.out (HP_UNCRUSH=1)
  on dt_tess_frz:jeans/sweater/coat + dg_garrett:shirt, unders pinned to their own START when no finished result
  matches the mesh (regr2.py prints "pin ... <- its start (sha ..)": the shas must match old vs new). RUNNING when
  this session stopped; first line (old): jeans 220 / 164 / stretch 0.042. Read all three; notch placement mergeable
  only if new == old on jeans / sweater / coat / shirt. wf_/pd_/ga_ gates not run.
- (3) HP_UNCRUSH safe-default work NOT started (it is not the j15 blocker: uncrush adds ~14 of 217 over faces). Plan:
  the mask = the preflight's (skip carryIdx + fold rings via folds.weights), and a stretch cap (revert the uncrush
  where the local max strain rises past max(before, 1.10)); test on the jacket and dt_tess_frz:jeans (0.04 must hold).
- Not merged origin/main yet (b32d303f game camera): merge before any render.
STATE: preflight strain check in (22d53eda); j15 FAIL at frame 0 (start 3.47% over the limit), STUCK on the draft
under the base hps: the neckline is drafted from the upper neck loop, not the base ring (width +26 mm, CB 70 mm low).
NEXT: (a) finish the diagnosis (front hps -> chest path vs pattern; shoulder seam; ANSUR check of the base hps height);
(b) fix the draft from the ring, with a test; re-place; preflight strain < 3% (aim j8's 2.27%, 0 past); (c) ONE
approved j15; (d) shirt same fix + check; (e) read regr2_*; (f) UNCRUSH default; (g) merge main before renders.

## Handover 2026-10-15 r (dress-garrett; 70-call clock reached, STOPPED)
- Merged origin/main (b32d303f camera fix) -> 1fb97d66. Cloth tests one file per process ($G/tests.sh): all green
  except test_collar::test_made_lay (collar far-edge ratio median 0.896, wants |1 - m| < 0.03): it failed BEFORE any
  edit of this session (log 23:10, edits from 23:13), i.e. at 9d47997d + main. Not investigated.
- (1) Base ring vs ANSUR II (men within 40 mm of 1770, n 1742; $G/ansurchk/ansur_neck.py, python3 -I, latin-1):
  cervicale p5/50/95 1512/1530/1548, suprasternale 1432/1450/1470, acromial 1426/1453/1480; cerv - supra 61/79/98,
  cerv - acrom 56/77/100, supra - acrom -25/-2/21; neck base girth 397/434/478; shoulder length 135/150/166.
  - Absolute heights: Garrett's ring cb 1569.8 (> p95 by 22), cf 1470.9 (p95), but his shoulder point 1484 is over p95
    too: head + neck above the shoulders are ~20-40 mm short of the population (GNM head). Judge RELATIVE to the
    shoulder point: Garrett at the fixed 32 deg tilt cb - sp 85 (ok), cf - sp -13.5 (ok), cb - cf 99 (p95 98: edge);
    dg_mh cb - sp 110 (OUT, p95 100), cb - cf 122 (OUT). Verdict: the 32 deg ring is too steep (the neck leans ~10 deg
    forward on top of it: dg_garrett nd y -0.175, dg_mh -0.213); back too high on dg_mh.
  - tailor._neck_base_level: tilt solved (drop read at 12/20/28/36 deg, interpolated) so cb - cf = NECK_BASE_DROP x
    stature. 0.0445 (men p50): Garrett cb - cf 79, ring girth 416 (was 431), hps z 1518 (was 1519.4); dg_mh 81, all
    three ANSUR items in band. BUT dg_mh's hps -> shoulder point then reads 0.0754 of stature (test_side_neck_point_
    meets_the_population_shoulder_length wants >= 0.076; at 0.0425: biacromial ratio 0.3287 < 0.330): the two
    population checks pull dg_mh's ring opposite ways by < 1%. So NECK_BASE_DROP = None (OFF) by default: opt-in.
- (2) Neckline draft from the ring: pattern_blocks.bodice block option neckline "ring" (default "upper_loop" = old
  rule; OPT-IN until a placed start passes the strain preflight). front depth = the ring's cf drop under the hps
  (mm neckBaseFrontDrop), back drop = raw hps tape - the ring's cb tape (napeBaseToWaistBack; cloth.length_level keeps
  hpsToWaistBackRaw), width solved so the neckline = max(1.01 ring, 1.05 neck); CB length from the ring's cb tape.
  New tailor tapes: napeBaseToWaistBack, cfBaseToWaistFront, hpsToWaistFront (at cb_neck_base / cf_neck_base).
  Test test_pattern_tailor::test_neckline_is_drafted_on_the_base_ring (Garrett, dt_tess_frz, dg_mh; drop 0.0445).
  Numbers at drop 0.0445 (per half front / back vs the ring's quarter arcs): Garrett 115 / 99 vs 109 / 101 (old draft
  121 / 92 vs 105 / 108), width 98, front 41, back -8; Tess 99 / 87 vs 94 / 92; dg_mh 124 / 117 vs 126 / 118.
  - FINDINGS that block it: (a) the back drop from tapes is UNSTABLE: Garrett's ring-cb tape read 523 / 453 / ~490
    for rings 4-22 mm apart (bn +34 .. -22): the taut tape from a start on the neck (down() at x = 0 from cb - 1 cm)
    must be checked before bn can come from it; (b) hpsToWaistFront - cfBaseToWaistFront is NOT the front depth (85
    on Garrett vs a 48.5 drop: the chest's prominence), so the front uses the z drop; (c) the worn placement maps
    pattern y to world z below the hps (cloth.py ~3236), so a pattern cb at -bn lands bn under the hps while the
    body's ring cb is 35-50 ABOVE it: the brief's "back neck rise" would be -35..-50 mm, which no flat block has.
    Decide (coordinator): bn from the placement's geometry (rise) or from a fixed tape, before re-placing.
  - The handover-q claim "neck width 26 mm too wide" was wrong: the flat width is the arc round the body (the ring's
    horizontal quarter arcs ~93-95 on Garrett), not the ring's 3D half width 62.6; the real fault in the old draft was
    the split: front neckline 121 vs the ring's 105, back 92 vs 108.
- (3) NOT done: j15 / shirt not re-placed, no preflight, (4) no sim (spend unchanged, ~$2.39 of $5).
- Coordinator's extra: start_self_check exempts a sewn vertex on faces one ring from its own sew partner (a tube's
  seam placed closed). s30 / s31 sweater starts that ran: 186 / 194 -> 0 pairs; s7 still 2 (fails), j8 / j12 pass.
  Commit 9b6a7a24, tests in test_tooling (synthetic tube + the real starts).
- (5) Regression on dt_tess_frz (regr2_old by the old code, regr2_new / _unc by a SNAPSHOT of 9d47997d + main in
  $G/newsrc via $G/regr3.sh, so this session's edits don't leak in): jeans new == old (220 / 164 / 0 crossings /
  0.042), sweater new == old (120 / 67 / 5 / 0.508; new also reports set sleeve 0.0); coat ERRORED in the OLD code
  (TypeError float(list)) so no baseline; shirt and the UNCRUSH run were still running at the stop. Mergeable on
  jeans + sweater; coat and shirt not yet shown.
STATE: self check fix in (9b6a7a24); ring neckline + ring tilt solve in as OPT-IN, tested, not default; j15 still STUCK.
NEXT: (a) make the ring-cb tape stable (or define bn from the placement) - coordinator's call on (c); (b) with
neckline "ring" + NECK_BASE_DROP 0.0445 re-place j15 / shirt (BROKER=1 run.py) and run $G/strchk.py on the job;
(c) only if < 3% over and 0 past: one approved j15; (d) read regr2_new / regr2_unc tails (shirt, unc) and the coat.

## HPS research (parked, 2026-10-15 s; coordinator: back to the last known good)
`tailor.measure`'s hps is "widest" again by default (the widest point of the loop 2 cm up the neck: j8's definition,
the one jacket that hung right). Since the switch to "base" a dozen sessions chased knock-on faults (length, balance,
armhole, neckline, start strain past ZOZO's limiter: j15 3.23-3.47% vs j8 2.27%); each fix exposed the next.
OPT-IN RESEARCH, kept and tested, not used by any default draft:
- `HP_HPS=base`: the ANSUR II / ISO side neck point on the base-of-neck ring (`tailor._neck_base_level`), with the
  ring's cb / cf (`cb_neck_base`, `cf_neck_base`), the ring tapes (napeBaseToWaistBack, cfBaseToWaistFront,
  hpsToWaistFront), the tilt solve `tailor.NECK_BASE_DROP` (None = fixed 32 deg) and the bodice block option
  `neckline: "ring"`. `HP_HPS=crest` (`_side_neck`, the shoulder crest's crossing) is older research.
- Tests pin HP_HPS=base: test_side_neck_point_meets_the_population_shoulder_length, test_neckline_is_drafted_on_the_base_ring.
Open questions before it can come back (handover r): (a) the back neck drop from the ring-cb tape is unstable (523 / 453
/ ~490 mm for rings 4-22 mm apart); (b) the worn placement maps pattern y to world z under the hps, so a ring whose cb is
35-50 mm ABOVE the hps needs a back neck RISE no flat block has: bn from the placement's geometry or a fixed tape is
undecided (the back-drop decision is deferred); (c) NECK_BASE_DROP 0.0445 puts dg_mh's shoulder length at 0.0754 of
stature (ANSUR p5 0.076) while 0.0425 fails the biacromial ratio: the two population checks pull opposite ways;
(d) everything drafted on it (length, balance, armhole depth) was retuned against base-hps starts and must be re-checked.

## dress-garrett 2026-10-15 s (back to the last known good)
- a8bef17a: HP_HPS default "widest" (see "## HPS research (parked)"). Cloth tests one file per process: all 15 green,
  incl. test_collar::test_made_lay (it failed under the base-hps default only: the collar's lay rides the hps).
- j15 = widest + current code + underarm 0.035 ($G/q_dg_j15w.sh / q_dg_j15u.sh, place only; $G/pfs.py = preflight +
  sew gaps): without HP_UNCRUSH the self check FAILS (under.L / side.R underarm corner edges crushed 9 -> 0.16-0.18 mm,
  1 pair 0.51 mm); with HP_UNCRUSH=1 preflight passes: strain 2.55% (j8 2.27%), 0 past, self ok, sew gap max 105 (j8 100).
- ONE rented sim (approved; $G/q_dg_j15us.sh, job_7aca63ae26eb8a5c, 460 s GPU): 0 crossings after clean-up, layered 42 (j8
  30). Hang (V, front edge |x| L/R mm) j15 vs j8: hem 47/80 vs 59/74, waist 60/61 vs 51/60, chest 84/83 vs 74/78.
  front.R within 6 mm; front.L's hem 27 mm HIGHER (z 858 vs 831), 60 mm FORWARD (y min -230 vs -168), 45 mm off the
  body (j8 26): the over front flares. X0 equals j8's both sides: the sim makes it. VERDICT FAIL (partial), STUCK.
- pdiff j8 / j15 ($G/pdiff.py, fixed for numpy 2's 2D cross): the pattern is j8's within 3 mm (length -3, all seams
  equal, collar carry 87 -> 79). Differences are the run's: the under (s6 result vs j8's own), mirror_mesh + mirror
  "mean", HP_UNCRUSH, sleeve placement code, collar carry. Untested which; needs a sim (coordinator's call).
- Shirt on widest (current code, s6's args, $G/dg_s9w.log job_e0d416238156d398): preflight ok, strain 2.71% (s6 2.65%),
  29 past all capped (s6 28), self ok, gap max 92 (s6 91).
- Regression (dt_tess_frz): jeans / sweater new == old; shirt new == old; UNCRUSH jeans == old (rest running at the time
  of writing: $G/regr2_unc.out). Coat: no baseline, its frozen spec has open_gap [0.15, 0.26] (a list) which no
  cloth.open_gap accepts (TypeError in old and new): a dress-tess spec question.
STATE: widest default in; j15 sim ran, front.L hem flares (FAIL), pattern = j8's. NEXT: coordinator picks the variable
(suggested: j15 without mirror_mesh / mirror "mean", front.L being the over side); armhole round (3) only after a PASS.

## Handover 2026-10-15 s (dress-garrett; 70-call clock)
- Coordinator: j15 IS the base (pattern = j8's, front.R within 6 mm of j8). No more jacket sims.
- Hand finish of front.L's hem on a COPY of the drape ($G/fg.py <tag>, dress-tess's guarded fin/finish.py: seams carried,
  clearance vs body + shirt surfaces, crossings / seam gaps checked). Move "match_side": front.L + side.L blended to the
  MIRROR of front.R + side.R (mirror_mesh gives a vertex-for-vertex match in uv), weight 1 below z 0.95, 0 above 1.15.
  - f1 (move + 3 smoothing iterations): accepted by the guard, but side.L crushed (faces < 70% of pattern area 3% -> 38%;
    side.R 11%): the smoothing pulls a small piece in. f2 (+ back.L) is no better.
  - f3 (NO smoothing; NOSMOOTH=1): 320 verts, max 109 mm; side.L 6.7%, front.L 1.6%; crossings body 0 -> 0, shirt and self
    unchanged, seams unchanged. front.L hem z 858 -> 840, y min -230 -> -153 (= front.R), off 45 -> 41 (R 38).
  - Applied as the garment's sculpt (offsets over the sim's V: $G/out/dg_j15us_sculpt_f3.npz, key 7aca63ae26eb8a5c),
    passed as a run.py override (NOT yet written into dg_garrett's spec): dg_j15f3 builds from the cache: 0 crossings,
    nothing crumpled, "hand sculpt applied (320 vertices moved)". Hang V |x| L/R: hem 74/80, waist 60/61, chest 84/83.
  - run.py GOTCHA: under_pin's pin-cache key reads the LAST argument's value (late-bound `v`): keep the arg order of the
    sim's run (underarm=0.035 last), or the shirt pin rebuilds and the jacket gets a new sim key.
- Renders: ONE NICO-TOP batch (rr.sh dg_j15f3, dgrr-235203, $0): cloth_renders/dg_j15f3*.png. They show jacket + shirt +
  body only (run.py's sheets have no trousers).
- Blind review ($G/rvjacket.sh dg_j15f3 r1 -> $G/rv_dg_j15f3.out): FAIL. MAJORs grouped by cause:
  - DESIGN / DRAFT (pattern): no waist suppression and the hem wider than the chest (box, flares); one button, low (the
    reference has two: waist + pocket line); no pockets (2 flap + chest welt); sleeves wide to the cuff with a soft,
    drooping shoulder (no sleeve head or pad); no visible notch, lapels long down to the low button. (MINOR: square
    hem corners, where the reference has a cutaway curve.)
  - HANG / FINISH (by hand on the drape): fronts a hand's width apart along the whole length (open_gap placement); a
    loose wing behind the right arm, armpit to hem (side.R: 11% of faces crushed; candidate for the next finish
    move); the collar stands up behind the neck (collar lay).
  - MATERIAL: white button; flat black cloth (charcoal weave in the reference) [other stage].
  - OTHER STAGES: shirt placket and collar crumpled or torn, the shirt tail gathered between the legs, shirt colour;
    body / head untextured.
  My own look agrees: the fronts are symmetric now; the side view shows the front hem still kicking forward, plus
  white flecks at the back neck.
- (3) SUSPECT, to A/B only if another jacket ever needs a sim: mirror_mesh + construct.mirror "mean" for j15's
  one-sided front.L flare (the start was symmetric; the flare came from the sim).
- (4) The coat's open_gap [0.15, 0.26] is dress-tess's placement extension (80c27897 on their branch). It is not on this
  branch, so it is not a bug here; left alone.
- UNCRUSH regression run (dt_tess_frz): jeans == old (0.042); sweater crossings 5 -> 4, rest equal; coat n/a.
STATE: j15 base + hand finish f3 (sculpt override) rendered and reviewed: FAIL, with 9 jacket MAJORs (5 design, 3 hang, 1 material).
NEXT: (a) write the f3 sculpt into dg_garrett spec cloth.jacket.sculpt (key 7aca63ae26eb8a5c); (b) finish moves for the
right-side wing (side.R) and the fronts' gap, measured against the concept's front-edge spacing; (c) the design MAJORs
(waist suppression, two buttons + heights, pockets, sleeve taper / head, notch) are a pattern round: the coordinator
decides whether it is worth a new sim; (d) armhole round (3) is still pending.

## dress-garrett 2026-10-16 t (the carry of the approved jacket)
- (1) Design diff, no sim: the j-series jacket has NOT drifted from the approved c12_n18c. su_gc's jacket + q_n18 line 1 vs
  dg_garrett's jacket: darts False; suppression = the same take_in (sideF 8, sideB 10 mm) + CB contour 12 mm + side hem
  spring 0; buttons n 2 (stance on front.R, closure front.L over, open); lapel break_y 0.455 / notch 0.025 / stand 0.012 /
  width 0.064 / gorge_drop 0.095 / roll 0.8; collar 0.011 / 0.028 / point 0.015 / height_front 0.028; sleeve cap_ease 0.03,
  hem_width 0.32, two_piece elbow 0.05; pockets "none", shoulder pad_and_head: ALL identical. Only differences: chest_ease
  0.06 (n18's override) -> 0.09 (stage 2 gate), underarm legacy -> 0.035, set_sleeves free -> into_armhole (the hang fixes).
  pdiff job_ddb2eb8a (n18c) vs job_7aca63ae (j15): same pieces / seams, body pieces +7 mm wide, +18 long (sides +27).
  The approved jacket had no pockets either (cloth12 wrap). Coordinator: NO sim, chest_ease stays 0.09, no pocket tool;
  j15 + finish = the carry; review target = the approved look (concept-level items = a design list for Joe, below).
- (d) "One low button": a construct-order fault. buttons_mesh ran BEFORE cloth_made.construct, whose lapel press moves
  front.R round the break: j15's top button anchor moved 22 mm up and ~2 cm forward after the button was built, so the
  button sat 2-4 cm behind the pressed front (hidden). n18c / j8: anchors unmoved, both buttons show. FIX cloth.build:
  after construct, buttons rebuilt on the final V if any anchor moved > 1 mm.
- Carry measures ($G/fin_t/meas.py; n18c | j15f3): fronts' edge |x| L+R at 15/35/55/75% of height 133/128/134/151 |
  151/112/122/160 (carried within ~2 cm); collar at CB 8 | 9 mm over the back neckline, off the body 22 | 14 mm (j15's
  collar sits CLOSER than the approved: no move); side panels' |x| max 228/232 | 260/260: the wing. j15us (sim) side.L 193
  / side.R 259 at the hem: f3 (front.L + side.L <- mirror of R) had copied the wing to BOTH sides.
- Finish t3 ($G/fin_t/fgt.py, guarded finish.py, no smoothing): front.L <- mirror front.R below 0.95..1.15 (f3), side +
  back pieces both <- mean(L, mirrored R) below 1.15..1.27, the fronts blended to that mean within 16 cm (uv) of the side
  seam (sewn groups move together: without it front.L's mirrored side seam dragged side.L back out, t1 260 mm). Result
  side |x| max 223 / 224 (approved 228 / 232), off body p90 54 / 54 (n18c 65 / 66); crossings body 0 -> 0, self 41 = 41,
  seam gap max unchanged, moved 1231 verts max 109 mm. COST: faces under 70% of pattern area front.L 5.8%, front.R 8.7%
  (from 2.7 / 0.6: the side-seam blend compresses the excess instead of folding it), side.R 10.8% (unchanged).
- The sculpt is NOT written into dg_garrett's spec: its key is the j15us sim key, which depends on run.py's under_pin (the
  pinned s6 shirt), so a plain spec build reports it stale. It rides as a run.py override ($G/q_dg_j16t.sh).
- run.py ($G, scratch): buttons drawn in cloth.button_color (jacket: tone 0.55 x cloth = charcoal horn, the approved
  one's), TROUSERS=<pkl> adds a finished trousers result (dg_t5) to every sheet. rvcarry.sh = the carry review
  (approved c12_n18 sheet | result, panel for panel + lapels) and carry_pairs.png for Joe.
- j16t = j15us drape (cache, NO sim, $0) + finish t3 + the button fix + trousers dg_t5 ($G/q_dg_j16t.sh): 0 crossings,
  "hand sculpt applied (1231 vertices moved)"; both buttons on the cloth now (top z 1.134 at the pressed front's
  surface, lower 1.024), drawn charcoal horn (#1f1e1d, kb jacket tone 0.55 = c12_n18c's own button data; the approved
  SHEET's white buttons were run.py's hard-coded shirt pearl). Hang (j16t | j8 | n18c): fronts' edge |x| L/R at 15%
  74/77 | 56/73 | 60/73; hem z 839 | 831 | 845; side |x| max 223/224 | 215/253 | 228/232. The swing did not come back
  (fronts symmetric, front hem y -153 both sides).
- Renders ONE NICO-TOP batch (dgrr-000213, $0): cloth_renders/dg_j16t*.png WITH trousers; pair sheet for Joe
  cloth_renders/dg_j16t_carry_pairs.png (approved c12_n18c | j16t: front, side, back, three-quarter).
- CARRY review ($G/rvcarry.sh dg_j16t r1 -> out/rv_dg_j16t/r1/review.md): FAIL, 2 jacket MAJORs + 1 other-stage:
  - MAJOR side profile: the fronts swing BACK below the top button (a kink at the top button, the hem 40-60 px behind the
    button line): reads as a cutaway; the approved falls plumb. My look agrees. Likely the pressed front round the break
    standing ~2 cm proud (the top button's anchor moved 22 mm up / 2 cm forward in construct) over a front that hangs
    to the body below; not measured further.
  - MAJOR back: white shirt specks through the jacket just below the collar at CB (also in j15f3). Jacket-side finish
    REFUSED twice ($G/fin_t/fgt2.py: finish.clear of the upper back off the shirt surface, 197 of 251 vertices under the
    shirt's margin by up to 22 mm; full and SHALLOW=8 mm both add 19 self crossings with the collar). The shirt's back
    neck sits OUTSIDE the jacket there: fix it on the SHIRT (its collar band / yoke pulled in under the jacket), not the
    jacket.
  - Other stage (reviewer MAJOR, not mine): dark buttons vs the approved sheet's white: per the coordinator's material
    call (horn); if Joe wants contrast, closure button.color.
  - MINORs: top of the opening wider (fronts further from the placket), collar ends stand up at the side neck / far
    collar, a dark spot on the near lapel, the back hem boxier, shirt collar crumpled, a shirt fragment at the fly.
- DESIGN LIST for Joe (concept items the approved c12_n18c also lacks; not carry faults): waist suppression (darts off,
  side take-ins 8 / 10 mm only) with the hem wider than the chest; flap pockets + a breast welt (no made-pocket builder:
  op_pocket drafts them as sim pieces, which made the fronts heavy in cloth12); sleeve taper / a firmer sleeve head;
  the notch read as an open gap; a cutaway curve at the front hem corners; charcoal weave instead of flat black.
STATE: j16t (carry: j15 drape + finish t3 + button fix) rendered with trousers; carry review FAIL (front swing-back
under the top button; shirt through the back neck). Sculpt t3 rides as a run.py override, not in the spec.
NEXT: (a) the shirt's back neck pulled in under the jacket (shirt finish, pinned dg_s6); (b) the pressed front round
the break: measure how far front.R/L stand off the shirt at the top button vs n18c, then a guarded move that lays it
back plumb to the hem; (c) Joe's call on the design list and button colour.

## dress-garrett 2026-10-16 u (finish of the carry j16t, no sims; scripts $G/fin_u/, $G = /mnt/data/hifipushie/dress_garrett)
- run.py ($G, scratch) now saves `under_V` (the shirt as pressed under the jacket, what the sheets draw) and
  `sculpt_offset` in <tag>.pkl, and takes three new keys: `under_sculpt=<npz offset, key>` (a hand finish of the shirt
  as drawn, applied AFTER the build: the jacket's sim key is untouched), `under_collar=<npz>` (made shirt collar + stand
  drawn instead of the simulated ones) and CACHED_ONLY=1 (env: cloth.build(cached_only=True), so a key slip can never
  start a sim). `freeze=<dir>` writes the shirt AS DRAWN (under_V + made collar parts in res["made"]).
- (1a) Shirt back neck ($G/fin_u/shm.py = measure; fgu.py shirt part = move). Shirt-vs-jacket crossings 99 (j16t) -> 7;
  shirt points outside the jacket at the back neck 20 -> 6. The shirt was pulled in toward the body (body-normal
  direction), clamped to the room above the body (>= 0.8 mm + its thickness), the displacement smoothed and carried
  across sewn pairs: 584 verts, max 5.2 mm; body crossings 100 = 100, self 750 = 750, seam gaps unchanged. A 3.5 mm
  target REFUSED (body crossings 100 -> 111): the jacket sits within ~3 mm of the body there, so there is no more room.
  -> $G/out/dg_j16_under_sculpt_u2.npz (key 7aca63ae26eb8a5c).
- (1b) Shirt collar / placket crumpling (shm.py, % interior edges with dihedral > 30 / 60 deg, % faces < 70% pattern
  area; pressed under the jacket | shirt alone s6): collar 22.5 / 15.4 / 9.1 | 17.2 / 11.0 / 4.3; fronts crushed 13.3
  / 9.5 | 1.5 / 1.4 (pressing compresses); stand 0 / 0 both. The sim collar is the crumple. REBUILT as a MADE piece:
  cloth_made.shirt_collar on the pressed shirt's neckline (seam_chain stand/collar, neck axis by SVD; SHIRT defaults),
  $G/fin_u/mc.py c1 -> out/dg_j16_shirtcollar_c1.npz: stand 0 / 0, collar 16.1 / 3.7 (> 60 deg 13.9 -> 3.7: the
  rest is the roll fold), crossings jacket 0, body 7 verts. shirt_collar is NOT wired into construct (only tests and
  cloth10 spikes call it): the run.py override draws it. The placket (part of front.L/R) is not rebuilt; its crush is
  the pressing (13% faces under 70%); not finished by hand this session.
- (2) Fronts plumb (fgu.py front part; prof.py = profile): the most forward y of each front per height, relative to the
  top button (mm behind it, button -> hem):
  n18c (approved) L 0 0 0 +5 +9 +10 +13 +16 +22, R 0 0 +2 +5 +8 +9 +12 +16 +33
  j16t            L 0 -10 -8 +1 +22 +32 +47 +54 +59, R 0 +3 +44 +26 +33 +39 +46 +54 +58
  j16w            L 0 -12 -2 +2 +5 +8 +11 +19 +25,   R 0 +1 +25 +1 +5 +4 +5 +19 +26
  Hem y min L/R -188 / -194 (n18c -189 / -194). Move: y per height band toward the approved's profile (median-filtered:
  n18c's own one-band blip is not a target), full at the edge, 0 at 18 cm toward the side seam, 0 at the top button
  (3 cm ease), 3 re-measured passes, ONE guarded apply: crossings body 0 = 0, shirt 22 = 22, self 41 = 41, seam gaps
  unchanged, clearance >= 8.8 mm. Squashed faces DOWN: front.L 6.3 -> 4.0%, front.R 8.7 -> 4.1%, side.R 10.8 -> 8.1%.
  LEFT: front.R's edge between the buttons (z 1.06) +25 mm (approved ~+2): the edge curls out and back there (|x| 89 vs
  68 at the lower button); band moves don't reach it (an edge-line straightening move would).
  -> sculpt $G/out/dg_j15us_sculpt_u4.npz = t3 + this move (offsets over the j15us sim V, key 7aca63ae26eb8a5c).
- (3) HOW TO REBUILD j16w (the carry candidate; NO sim, ~60 s from the cache): `bash $G/q_dg_j16w.sh`, i.e.
  CACHED_ONLY=1 RJOB=$G/rjobs/dg_j16w HP_UNCRUSH=1 TROUSERS=$G/out/dg_t5.pkl bash run.sh run.py dg_garrett jacket dg_j16w
  mirror_mesh=true 'construct.mirror="mean"' under_pin=$G/out/dg_s6.npz
  'sculpt={"file": "$G/out/dg_j15us_sculpt_u4.npz", "key": "7aca63ae26eb8a5c"}' under_sculpt=$G/out/dg_j16_under_sculpt_u2.npz
  under_collar=$G/out/dg_j16_shirtcollar_c1.npz freeze=$G/frozen_j16w design.block_options.underarm=0.035
  ARG ORDER: design.block_options.underarm=0.035 must stay LAST (under_pin's pin-cache key reads the last argument's
  value: any other order rebuilds the shirt pin and gives the jacket a new sim key; CACHED_ONLY then fails instead of
  simulating). The log must say "key 7aca63ae26eb8a5c", "hand sculpt applied (1317 vertices moved)", "under sculpt
  applied (584 vertices moved)". FROZEN for the assembly stage (once approved): $G/frozen_j16w/garrett_jacket.pkl and
  garrett_shirt.pkl (shirt AS DRAWN: under_V + made collar/stand in res["made"]["parts"], info.hides ["stand", "collar"]:
  the export must hide those sim pieces; untested in export_asset).
- TOOLING ITEM (why the spec can't hold it): dg_garrett's spec `cloth.jacket.sculpt` is keyed on the sim key, which
  depends on the under garment; the jacket was simulated over a PINNED shirt (run.py under_pin = dg_s6's finished V,
  not the spec's own shirt build), so a plain spec build sees another under, another key, and reports the sculpt stale.
  The spec also has no place for a hand finish of the under garment as pressed under the over one (under_sculpt), nor
  for a made shirt collar (cloth_made.shirt_collar is not called by construct). Needed: (a) a spec key
  `cloth.<g>.under = {"pin": <finished result>}` read by cloth.build (so the pin is part of the spec and its key),
  (b) `cloth.<over>.under_sculpt` applied to res["under_V"] after the build, (c) construct option `shirt_collar: "made"`.
- (4) Renders: ONE NICO-TOP batch (dgrr-003931, $0): cloth_renders/dg_j16w*.png with trousers; pair sheet for Joe
  cloth_renders/dg_j16w_carry_pairs.png (approved c12_n18c | j16w). CARRY review ($G/rvcarry.sh dg_j16w r1 ->
  $G/rv_dg_j16w.out): FAIL, but BOTH target MAJORs of j16t are gone. Side: "front edge projection at the button, the curve
  to the hem, hem height match within tolerance". Back: no shirt through the jacket (my look agrees: clean back neck).
  Remaining jacket MAJOR (was a MINOR on j16t): the fronts sit further apart at the chest (shirt gap ~42% of the chest
  width vs ~30%; carry measure: edge |x| at 75% height 80 / 80 mm vs n18c 73 / 78, the lapels sweep out toward the
  armholes). Buttons dark = Joe's call (unchanged). MINORs: lower fronts rippled below the lower button, a vertical
  fold near the near side seam, the far collar point standing up, a weak notch, the back hem wavy at the side panel.
  OTHER STAGE MAJOR (shirt): the MADE shirt collar stands open and up round the neck above the jacket collar (reference:
  folded points lying down). My look agrees: it reads ragged at the stand top; the made collar is WORSE to the eye than
  its numbers (dihedral) said. Not yet checked: whether the mixed faces kept on the shirt (front/stand faces with some
  verts in stand/collar) draw a sim remnant beside the made stand, and SHIRT params (open 22 deg, points 70 mm) vs the
  approved look (button-down points lying on the shirt front). The placket ruffle is in the approved sheet too.
- DESIGN LIST for Joe (unchanged, short): (1) button colour: horn (spec data) or light (the approved sheet's look);
  (2) waist suppression (darts off; hem wider than chest); (3) flap pockets + breast welt; (4) sleeve taper / firmer
  sleeve head; (5) a cutaway curve at the front hem corners; (6) charcoal weave instead of flat black.
STATE: j16w = j16t + fronts plumb (sculpt u4) + shirt back neck in (under sculpt u2) + made shirt collar (c1); carry
review FAIL on 1 jacket MAJOR (chest opening wider) + the shirt collar (other stage); side swing and back specks FIXED.
NEXT: (a) the chest opening: lay the lapels / fronts from the break up toward the approved (edge |x| at 75% height and
the lapel's outer edge vs n18c), guarded; (b) the made shirt collar: check the leftover mixed faces, then SHIRT params
(open, points, lay) toward lying points, or fall back to the sim collar (j16w without under_collar) if it doesn't
improve; (c) front.R's edge curl between the buttons (+25 mm at z 1.06); (d) wire the three run.py keys into the spec
(tooling item above).

## Handover 2026-10-16 u (dress-garrett; 70-call clock)
- Coordinator round 2: (1) the chest opening + front.R's curl, (2) made vs sim shirt collar, (3) one batch + review.
- (1) $G/fin_u/fgx.py x1 (on j16w): the measured front EDGE at the chest is only 0-8 mm wider than n18c's (|x| L 53..78 vs
  58..70 mm from the top button up 20 cm; R already under the approved), so the review's "42% vs 30% gap" is mostly the
  lapel's outer sweep (made by construct's press AFTER the sculpt) and the broader chest, not the edge. x1 laid the
  edge in (<= 8 mm) and front.R's edge onto the line between its buttons: guarded OK (crossings equal, front.R crushed
  4.1 -> 4.5%), but the curl only went from +25 to +20 mm, and BOTH reviews of x1 builds see a NEW MAJOR: a kink / point at
  the top button (the move's 3 cm ease above the button meets construct's lapel press). REVERT x1: u4 stays the jacket.
- (2) Made-collar tries ($G/fin_u/mc.py; edges > 30 / 60 deg %, crossings jacket / body): c1 (defaults) 16.1 / 3.7, 0 / 7;
  c2 (open 6, stand 24 mm, points 62, spread 20) 16.1 / 4.4, 0 / 5; c3 (open 2, stand 22, points 65, spread 15, fall_hug
  1.5 mm) 13.0 / 3.2, 0 / 12. Sim collar 21.9 / 13.9. One batch dgrr (NICO-TOP, $0): j16x = x1 + SIM collar, j16y = x1 +
  made c3. Reviews ($G/rv_dg_j16x.out, rv_dg_j16y.out): j16x's shirt MAJOR "collar broken up and jagged, points fold in
  on each other"; j16y raised NO shirt-collar fault. So c3 beats the sim collar; KEEP the made collar (c3), not the fallback.
  (j16w's c1 had "popped open, stands up": c3 lies lower.) j16y's review also says "shirt too short, ends at the waist"
  (other stage; not seen in the j16w review of the same shirt: check the crop before acting).
- Pair sheets: cloth_renders/dg_j16w_carry_pairs.png (best jacket: u4), dg_j16x_ / dg_j16y_carry_pairs.png (x1, rejected).
STATE: best = sculpt u4 + under sculpt u2 + made shirt collar c3 (NOT rendered as that combination: j16w had c1);
side swing and back specks fixed; jacket MAJORs left: the lapels' sweep at the chest (construct's press, not the edge),
front.R's edge curl (+25 mm at z 1.06); buttons = Joe's call.
NEXT: (a) q_dg_j16w.sh with shirtcollar_c3 -> render + carry review (that's the candidate); (b) the chest opening at the
LAPEL: measure the lapel's outer edge / roll line vs n18c and move it via construct's lapel options (lapel_lay / wedge)
or a post-construct sculpt hook (none exists: the sculpt is applied BEFORE construct - a tooling item), never with an
edge move that ends at the top button; (c) front.R's curl the same way (post-construct).

## dress-garrett 2026-10-16 v (baseline j16z, post-construct finish hook)
- (1) j16z = u4 + u2 + made shirt collar c3 (`bash $G/q_dg_j16z.sh`, cache only, key 7aca63ae26eb8a5c, 1317 / 584
  vertices moved as in j16w; freeze -> $G/frozen_j16z/; NOTE the j16w script's freeze dir was overwritten by this
  build (renamed to frozen_j16z): re-run q_dg_j16w.sh to get j16w's frozen pieces back). ONE NICO-TOP batch ($0),
  carry review ($G/rv_dg_j16z.out): FAIL on ONE jacket MAJOR: the FAR-side collar / lapel top stands up to ear level
  in the three-quarter view (popped collar; j16w's review had it as a MINOR). The chest-opening MAJOR of j16w is NOT
  raised (front: "front opening ... close to the reference"; my look agrees, the shirt gap at the chest is about the
  approved's). MINORs: collar ends standing at the neck sides (front / back / lapels), top button partly in the fold,
  hem narrower than the shoulders, a curl below the break on the wearer's left front, back without the hem kick.
  OTHER STAGES: buttons dark (Joe's call); "shirt too short" = DISPUTED with the crop: the shirt is tucked into the
  trousers (present only in the result; the approved sheet has no trousers, so its shirt runs to the crotch); shirt
  collar MINOR (crumpled), no MAJOR. Pair sheet: $G/out/rv_dg_j16z/carry_pairs.png. j16z = the baseline.
- (2) TOOLING: post-construct finish. `cloth.<g>.finish = {"file": npz with "offset", "key": <finish_key>}` is applied
  in _build right AFTER cloth_made.construct (lapel press, made pieces) and before the buttons are re-seated.
  `cloth.finish_key(V)` = sha1 of the constructed V at 0.01 mm (res["finish_key"] on every build: make the offset on
  that result and store that key; another construct result = "finish_stale", not applied). `cloth.finish_apply`
  = the guarded finish in the package (was scratch dress_tess/fin/finish.py): closed seam groups move by their
  largest member's move, crossings the move makes (self, body, the garment under) go back (alone, a ring, two rings,
  their seam groups with them); refused whole if crossings remain or a made part's seam opens > 0.5 mm. In NOT_SIM,
  GARMENT_KEYS and the scene's detail key. Test: tests/test_cloth_finish.py (synthetic sheets).
- (2b) The finish on j16z ($G/fin_v/fv.py v3 -> out/dg_j16z_finish_v3.npz, key 6a0f1933154fe18b = finish_key of j16z's
  constructed V). MEASURE FIRST: the "front.R curl +25 mm" of handover u was a SAMPLING ARTEFACT: the fronts have ~545
  verts, rows staggered ~2-3 cm, so a +-6 mm z slab often holds no edge vertex and min |x| picks an interior one (j16z
  slab readings alternate 53 / 87 / 53 mm). Measured on the piece's BOUNDARY vertices (|x| < 10 cm): front.R between the
  buttons is straight within 5 mm; front.L stands up to 11 mm FORWARD of the line between its buttons at z 1.08-1.11
  (the review's "curl below the break, wearer's left"). Chest opening on the front crops (shirt px / chest span, rows
  at 25-35% of the frame): approved 0.24 / 0.23 / 0.22, j16z 0.25 / 0.26 / 0.24 (~10% wider, NOT 42 vs 30%).
  Move: fronts + lapels from the top button up to the gorge laid 5 mm toward CF (vertical smoothstep ramp over 8 cm
  from the button, full within 9 cm of the edge, fading over 7 cm; the gorge / made collar seam out of it); each
  front's edge between the buttons onto the button line where it stands off > 3 mm (full at the edge, 0 at 10 cm).
  Guard (cloth.finish_apply): 439 verts, max 9.6 mm, crossings 41 = 41 (incl. body + shirt), made collar seam max 1.3 =
  1.3 mm. Chest edge |x| at +6/10/14/18 cm above the top button 58 63 69 76 -> 54 58 64 71 mm (both). front.L edge y
  laid back 4-9 mm between the buttons. EDGE CURVATURE at the top button (boundary polyline +-4 cm, 5 mm resampled):
  L 70.1 -> 69.9, R 70.2 -> 69.9 1/m: no kink (x1's kink came from a pre-construct move meeting the lapel press).
  j17a = j16z + finish v3 through the hook (`bash $G/q_dg_j17a.sh`, `finish=` before underarm): log "post-construct
  finish applied (439 vertices moved)", key 7aca63ae26eb8a5c.
- (3) TOOLING: the j16w/j17 setup is SPEC-DURABLE. New garment keys (all in NOT_SIM + GARMENT_KEYS: the sim key is unchanged
  by them): `under = {"pin": <pickled finished under result>}` (model_body: `under_pinned` loads it instead of building
  the spec's own shirt; its key "pin_..." is what goes into the jacket's sim key, so the key no longer depends on
  run.py's argument order / pin_cache file name); `under_sculpt = {"file", "key": <this garment's sim key>}` (added to
  res["under_V"] right where it is set; res["under_sculpted"] / "under_sculpt_stale"); `under_collar = {shirt_collar
  options}` (cloth.under_collar: the under garment's collar + stand made on its pressed neckline, neck axis by SVD of the
  seam chain; res["under_made"] = {"parts", "hides", "info"}); `finish` (step 2). dg_garrett's spec v7 holds them
  ($G/fin_v/spec_j17.py; pin = $G/out/dg_s6_pinned_under.pkl = the pin_cache file j16w/j17a used; c3 = open 2, stand
  0.022, points 0.065, spread 15, fall_hug 0.0015). TEST tests/test_cloth_spec_durable.py: the jacket built from the
  spec alone (cached_only) vs frozen_j17a: key 7aca63ae26eb8a5c, jacket V, jacket made collar, shirt as pressed, shirt
  made stand + collar all 0.0000 mm. run.py ($G, scratch) draws / freezes res["under_made"]; q_dg_j17b.sh = the spec
  alone (no garment overrides): frozen_j17b == frozen_j17a (0.0 mm). q_dg_j16w.sh's overrides are RETIRED (kept only to
  rebuild old tags).
  TOOLING LEFT: (a) HP_UNCRUSH=1 is still an ENV switch of the start (cloth.UNCRUSH / UNSTACK at import): a build
  without it places another start; should become a garment key. (b) store.save(checked=True) refuses dg_garrett's
  stored spec: the jacket's design compiles pattern key "kind", which the draft validator doesn't allow (pre-existing;
  saved with checked=False).
- (4) ONE NICO-TOP batch (dgrr-010144, $0): j17b (= j17a, the spec alone) -> cloth_renders/dg_j17b*.png; CARRY review
  ($G/rv_dg_j17b.out) vs approved c12_n18c: VERDICT PASS, no jacket MAJOR (the only MAJOR is OTHER STAGE: dark buttons =
  Joe's call). Pair sheet: $G/out/rv_dg_j17b/carry_pairs.png (approved | j17b). MINORs: notches soft; collar ends /
  far collar top stand a little high beside the jaw; side panel seam ridge heavier; lower fronts recede a bit more below
  the bottom button (33 vs 25 px); no hem flare; far front bows at hip / hem; near lapel rolls off the chest a little.
  CAVEAT: j16z's MAJOR (far collar standing up) is a MINOR here, but finish v3 did NOT touch the made jacket collar
  (made seam 1.3 = 1.3 mm): that flip is reviewer variance on the same collar; the collar ends are the next jacket item.
  My look agrees with the PASS at the sheet's scale: same jacket, comparable chest opening, side profile and hem.

## Handover 2026-10-16 v (dress-garrett; steps 1-4 done)
STATE: best jacket = j17b = dg_garrett spec v7 alone (under.pin s6, sculpt u4, under_sculpt u2, under_collar c3 options,
post-construct finish v3; `bash $G/q_dg_j17b.sh`, cache only, ~60 s; frozen $G/frozen_j17b/). Carry review PASS (no
jacket MAJOR); buttons = Joe's call. New tooling: cloth.<g>.finish (post-construct, keyed on the constructed result,
guarded), under.pin / under_sculpt / under_collar garment keys, tests test_cloth_finish + test_cloth_spec_durable.
NEXT: (a) approval of j17b for the assembly (coordinator / Joe; frozen_j17b holds the shirt as drawn: made collar +
stand in res["made"], hides ["stand", "collar"] - export_asset untested with it); (b) jacket MINORs: collar ends sitting
high at the neck sides (construct collar_options / show), lower fronts' recede below the bottom button, hem flare -
each through the finish hook or construct options, measured first ON BOUNDARY VERTICES (slab sampling lies on this mesh);
(c) tooling: HP_UNCRUSH -> garment key; the draft validator vs the design's pattern "kind".

## Handover 2026-10-16 w (dress-garrett; tooling cleanup, merge to main)
- `uncrush` is a GARMENT KEY (cloth.uncrush_on: key, else env HP_UNCRUSH as a fallback, else off). Default off keeps
  the jeans' start unchanged. Out of the sim key (it changes only the placed start, already keyed in `inputs`), so
  j17b's cached sim key 7aca63ae26eb8a5c holds. dg_garrett spec v8: jacket + shirt `"uncrush": true`;
  q_dg_j17b.sh no longer sets HP_UNCRUSH. test_cloth_spec_durable unsets the env var and reproduces frozen_j17b
  (0.0000 mm, jacket / made collar / shirt as pressed / made stand + collar), plus key-over-env and validator checks.
- The validator was wrong, not the producer: garment_design compiles pattern {"from": "draft", ..., "kind"}, which
  pattern_draft.build reads (the kind's drafting defaults). garment_blocks.WORDS["draft"] now has "kind";
  dg_garrett saves CHECKED (store.save v8).
- Full cloth / pattern set, one file per process ($G/tests.sh, now incl. finish, spec_durable, precache, tooling):
  19 files, all rc 0, no failures (test_tooling's notch-set sleeve tests pass).
- Merged to main squashed (see RESTART.txt for the commit). STATE: j17b waits on Joe's look. NEXT: jacket MINORs
  (handover v (b)).
