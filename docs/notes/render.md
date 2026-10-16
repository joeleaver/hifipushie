# hifipushie notes: render

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `render.py` + `blender_render.py`: headless Blender workbench/matcap renders, contact sheet with rulers.
  `look(strokes=True)` draws stroke paths (visibility by raycasting the field); `shading="raking"` uses a
  generated low-side-light matcap, `"curvature"` colours vertices by the field's Laplacian (convex warm).
  `smin` is cubic (C2): the quadratic one left curvature jumps at every fillet edge, visible in highlights.
  `look(hide_parts/only_parts/clip)` goes through `store.view_mesh` (`<stem>_view.npz`: a face subset, verts
  beyond a clip plane pulled onto it, `src` = indices into the base mesh) and `store.section_caps` (grid cells
  on each plane inside a shown part's exact field, part colour darkened; shell parts only fill what solid parts
  don't, so clothes cut as a rim), loaded by Blender as an extra object. `camera` panels are perspective
  (`render.camera_frame`, `blender_render` switches the camera type per view; no rulers, no stroke overlay);
  an eye [x, y] stands on `measure.stand_height`. Camera-only looks also cull faces outside the frusta.
  Painted looks go to the Blender scene (`scene.look`, see "Next session"); these views are clay per part.
  `measure.clearance` (tool `clearance`): walkability
  from vertical columns of `field_at` (floors, headroom), a capsule clearance test and horizontal width rays.


## One Blender per job (2026-10-16)
NICO-TOP render jobs spent most of their time on set-up (hair job G48r: 581 s = stage sync 178 s, mesh 174.0 of it,
then 5 frames at 70-88 s each, every frame a fresh Blender: blend load + groom build + EEVEE shader compile + 1 render).
- Per-view lighting (commit e40d4b76): a job's views may carry their own `"lighting"` (`blender_scene._light_rig`: the
  hp_sun*/hp_window* rig removed and rebuilt, view transform / look / exposure reset to the blend's then applied, world
  set); in a job where any view has one, a view without one goes back to the job's. The older per-view `"lights"`
  (re-aim the same suns) still works; jobs without per-view lighting behave as before. `@@phase open|groom|setup`
  and `@@frame` lines time each job. stage.shoot takes frames with "lighting" (a shared light's windows aimed at the
  first frame using it, as when each light was its own call). hgshots (one=1 default; one=0 = a Blender per view),
  projskin cu.py (all reference views in one call), skintour (all views, own + projected: 2 calls instead of 2 per
  view), projskin shots.py (photo + side + top sets in one call) send every view in one job.
  Tests: tests/test_view_lighting.py (Cycles CPU, 24 px: two views in one job == each alone; a view without lighting
  gets the job's; stage.shoot's job builder). All pass.
- Packed stage (`spikes/tour/pack_model.py --stage <_g3_name>`, `pack_stage`): the built stage's scene.blend re-saved
  zstd (images repointed to `//../_images/<file>`, copied into ws/_images) + spec.json, g3_stage.key, hair_*.npz.
  stage.ensure on the machine finds key == mark and skips the sync. _g3_hg_h6: blend 162 MB -> 72 MB; the G48r job
  folder with it 117 MB (cap 128 MiB: ONE stage per job fits, two do not; skin jobs with a posed stage too need a
  job per stage). The key hashes the pipeline sources: pack from a clean tree at the commit the job runs, after a
  local stage.ensure; a stale key only costs the old sync. Any blender_scene.py change re-syncs every stage once.
- Measured locally (laptop, scratch copy of jf_G48r): the stage sync cold = 291 s (mesh 285.0, blender 5.8, peak RSS
  3.7 GB); with the packed stage the same run got past ensure with no sync (51 s to the hair build, which then failed:
  see below).
- NOT DONE (handover): the phase split and old-vs-new pixel equality on the real groom. hg_G48r's spec uses groom keys
  this branch (main) lacks (`loose.length.top_el`, `loose.fade.front`, ...: hair-garrett's branch): run on that branch
  after cherry-picking e40d4b76: /mnt/data/hifipushie/render1b/after.sh (scratch jf/jf2, run.sh <worktree|old>,
  oldkey.py for the old code's stage key; drop fixspec.py there). Expected from the G48r log: frames 2..5 lose
  scene load + groom + compile (~65 s each of ~71), so a 5-view job ~ 1 x 88 + 4 x (render only) instead of 5 x ~75,
  plus the 178 s sync gone: ~581 s -> ~110-130 s (estimate, not timed).
- Cloth-only sync (coordinator's item, dt_tess COPY in /mnt/data/hifipushie/render1b/cloth, prof.py): scene_job
  464 s for ONE simulated garment (jeans; sweater / coat unsimulated), blender cloth_sync 0.5 s. cProfile: 6
  `cloth.build(cached_only=True)` calls = 418 s; `place` 361 s of it (`_relax_strain` 303 s, numpy svd 243 s over
  21k calls); body_mesh 42 s (6 calls, base.inject/template_joints each time). Causes: (1) the sim cache key
  (cloth.py ~6581) hashes the PLACED start, so a cache lookup runs the whole placement; (2) model_body rebuilds the
  under garment for every layered garment (jeans built for itself, under sweater, under coat), and unsimulated
  garments pay placement just to find no cache. Fixes to do: memoise a pre-placement key (garment spec + body mesh
  hash + code) -> sim key file in _cache/cloth, so cached_only loads without placing; memoise build / body_mesh
  within one garments() call. Not implemented here.
