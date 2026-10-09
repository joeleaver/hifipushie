# hifipushie notes: topology

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Next session (agreed 2026-09-25): character topology spike

**Where things stand.** 2026-09-25 closed these backlog cards on Overboard (project "hifipushie"):
- painted looks with clip planes and close-ups;
- export quality (edge vs interior ray misses, chart growing);
- hand-painted masks;
- export time (the flatten pool, pre-collapse workers, parallel unwrap, anchor-interpolated projection).

It also added the rig step (`rig.py`, the `rig` tool, `export_asset(rig=True, fbx=True)`), the blade primitive,
the foot kit (fixed after the user saw toes sprouting mid-foot: the instep must slope into toes lying on the ground)
and scene-cache pruning. Rig standards are in memory (`rig-standards`): Mixamo-compatible humanoids, clean chains,
the rig separate from the modelling bones.

**Character topology spike: results (2026-09-25, `spikes/topology/`, README there).** Troll body, `rig.test_pose`,
the same `rig_weights` on every mesh; error = field -> mesh distance, by region (rest / head / hands).
- Skin modifier over the rig graph (+ skull, ears; radii by rays; rings at bending joints; shot onto the field along
  normals, relaxed): DROPPED. Its limbs were the cleanest, but hubs break (chest with neck + clavicles: a
  self-intersecting hull even after dropping the crowding nodes and building it thin; the arm/torso junction
  shreds at 8 segments around), every limb gets the same ring count (4 x 2^subsurf: fingers as many as the torso),
  and the head is a projected sphere with no vertices for nose or brow (63 mm max error).
- Blender QuadriFlow: clean quads flowing along the limbs, the best bends; beats decimation on broad forms per
  triangle (rest 1.2 vs 1.45 mm at 10k), but density is uniform: head and hands need ~4x the triangles (hands 2.2
  vs 0.9 mm at 10k). At 5k: mitten hands, and a web under the raised arm (big quads across the armpit take
  blended arm/torso weights). Loses the thin blade ears.
- QuadriFlow with our sizing field (patched build: `QF_SIZING` file of relative edge lengths; the stock `rho` is
  always 1, its `-adaptive` isn't density; also fixes a comma-operator bug in subdivide.cpp). Sizing = edge <=
  0.5 / max principal curvature (normal turn along edges: mean curvature cancels on a face's saddles and left the
  face coarser than the belly), shortened near bending joints, clamped 0.25-1.6, normalised to the budget, one
  calibration rerun. Head and hands 1.6-2x better than plain at the same budget, no armpit web, a readable face
  at 5k. Overall close to decimation (10k: mean 1.67 vs 1.36 mm, max 21 vs 10). Clenched fingers still merge
  and the ears are still lost.
- Decimation: the best detail per triangle (face, fingers, ears), but slivers along the limbs kink at elbow and knee.
- The dip on top of the raised shoulder is the same on every mesh, the dense one too: that's the weights (linear
  blend skinning), not topology.
- The user saw it first: QuadriFlow's quads aren't loops. `topo_loops.ring_check` (walk quad edge loops from the
  crease): skin mesh rings at all 4 elbows/knees; plain and sized QuadriFlow at 1-2 of 4, the rest spirals (open
  walks of 100-400 edges). Judge loops with the ring check, not by eye.
- Joint loops as features (patch `QF_FEATURES`: crease planes sliced into the high mesh, their edges constrained
  like boundaries: orientation + position): 4/4 rings exactly on the crease (0.1 mm), and the loops beside them close
  too (15/16 at +-0.6 and +-1.2 limb radii) with parallel flow, no poles against the ring. Three constrained loops a
  joint (0 and +-0.6 r) break at 5k (constraints closer than the quad size: the lattice can't fit) and work at 10k
  (4/4, error mean 1.33 mm, decimation 1.36). Rule: constrained loops no closer than ~1.5 local edges; at low
  budgets the crease loop alone, its neighbours follow.
- Shoulders (2026-09-26): a plane can't cut an armhole (a hanging arm's plane runs into the torso). Loops on the level
  curves of a harmonic field from the rig weights (patch `QF_FEATURE_IDS`: per-vertex curve ids, carried through
  QuadriFlow's subdivision) exposed bad weights instead: the arm owned 42% of its own shoulder (the collar cone's
  round end over the upper arm; the torso's radius set the blend width; the goblin's arm flesh sat 39 mm outside the
  arm: `_cone_piece` ignored bones reached from their far end). Fixed in `rig.py` (bisector cuts, thinner-bone blend
  width, piece direction; bones off every rig segment split in quarters). But constrained QuadriFlow runs on those
  level curves stall in the integer stage (>10 min, elbows/knees too; plane cuts took seconds): unresolved.
- The user then called the real problem: shoulders were balls pasted on bodies (troll and goblin), bad geometry to
  rig. Asked for general modelling lore rather than kits: `anatomy.py` (see Layout). Next: the hinge rule (bony
  point on the extensor side, flexor crease, flesh narrowing at the joint); hands and feet as presets over it;
  loops placed from the anatomy (the cap's and folds' edges are the armhole); sheets skinned smoothly along their
  length (four pieces hand over in steps: a fold on the pec's edge when the arm lifts); the pit still streaks under a
  raised arm (LBS, as before anatomy). Face rings, ears QuadriFlow drops, the QuadriFlow stall: still open.
- Loops from the anatomy (2026-09-26, `anatomy.loop_planes`, `spikes/topology/topo_anat.py`): hinge crease planes
  constrained alone give exact rings (elbows, knees, ankles 0.0 mm; 8.4k tris, mean 1.55 mm). Limb-root planes
  (through the cap top and both pits) cut open curves (they run onto the torso at the pit); slid down the limb to
  the first closed cut (shoulder 0.6 r, hip 0.4 r) they close, but constraining them breaks other loops, differently
  left and right and per budget: QuadriFlow's integer layout drops feature loops unreliably past a few. Sized runs also
  overshoot their face target ~4x with cuts (the calibration rerun then lands on a coarse lattice).
- Template wrap (2026-09-26, the user agreed; `spikes/topology/wrap.py`, template notes in `spikes/topology/template/`):
  Blender Studio's CC0 "Human Base Meshes" stylized male (12.5k quads, A-pose) carried onto troll_anat through
  matching skeletons (per segment: rotation, stretch, radius ratio per angle at 5 stations along the bone; hands and
  feet scaled uniformly by wrist/ankle thickness), face landmarks by a Gaussian RBF (face kit eyes, nose tip, mouth,
  ear joints), shot along normals onto each vertex's own region (the target prims nearest its segment and the
  neighbours: hands landed on thighs otherwise), relaxed. Deep interiors in the face (mouth bag, eye sockets) are
  kept, not projected. Result: 10/10 closed rings at shoulders, hips, elbows, knees, ankles, symmetric; the shoulder
  deforms with a real armhole loop; mean error 1.85 mm. Open: ears (human ears onto blade ears make flaps by the
  neck), eyelids tangle, the mouth interior pokes through the lips, toes collapse on club feet, two flaps behind
  the armpits; hands need finger correspondences (the goblin has 3 fingers); a quadruped needs its own template;
  25k tris is dense for a game (un-subdividing the template isn't clean).
  Then (2026-09-26): toes smoothed away on toeless feet; `untangle` (turned faces smoothed and re-projected: armpit
  and mouth-corner spikes gone); template eye openings follow instead of projecting (the troll's squint opening is
  ~4x2 template quads: still a small tangle); region-limited projection only for the first placement, whole body
  after (a finger cone buried in the palm left vertices inside); template finger/thumb chains measured
  (`male_stylized_joints.json`) and mapped onto the hand kit's chains, missing fingers smoothed into the palm.
  Goblin: body, arms, legs, face clean; its blade ears are lost (the template's ears are human). Hands are the open
  problem: the troll's fat fingers touch (no gaps for the template's finger sides: stubs), the goblin's thin ones
  collapse into strings. Fixed by digit tubes (`spikes/topology/tubes.py`): each template digit is cut at the
  closed quad loop nearest its base (every 45 deg sector round the axis, cutting off < 400 verts), the loop is moved
  onto the model's finger a finger radius past the knuckle, rings (the loop's count, angles carried along the
  chain, spacing = circumference / count, extra rings either side of each knuckle) are placed by rays from the kit's
  chain onto that digit's own prims (touching fingers keep their sides), a 45 deg ring and a quad fan close the tip;
  template digits the model lacks are capped; 4 rings of palm round each loop relaxed onto the surface. Result, all
  quads: troll 12.6k, goblin 13.0k faces, 10/10 joint rings, hand error < 1 mm, clean in the rig test pose.
  Open: blade ears (goblin: lost, most of its 3.1 mm mean error), eye-corner tangles, a small tangle at a capped
  finger's web, then a lower-poly version and wiring into export_asset/rig.
- Decimation stays for environments and props either way.
- 2026-09-28: the wrap moved to `src/hifipushie/retopo.py` (see Layout): blade ears, eye patches, fixed patches, the
  cavity rule. Then the user's priority moved to the base (`base.py`): the template as an SDF body, GNM as a head
  source (evaluated vs the template: realistic, 17.8k verts, 253 identity / 383 regional-PCA expression components,
  linear, so blendshapes are possible but not ARKit-named: card "Facial blendshapes"), the golfer rebuilt on it. User
  corrections on the golfer, in order: head 1/7 of the height (not the fit's), beard as stubble paint (not a shell),
  hair as a mass (not a shell), middle-aged soft body (not the heroic template; MakeHuman deferred: interim `soften` +
  `push`), clothes with volume and folds (card "Garments with volume and folds": next).

**Then, in the order the user saw them:**
1. **Rig check in a real engine:** the rigged goblin FBX in Unity or Unreal with a Mixamo animation. This decides
   whether we need a T-pose rest or bone orientations; joints are currently unrotated, rest pose as modelled. It
   needs the user or an engine on this machine.
2. **Export time** (card "Export time: texel projection and Cycles map bake"): at 256/m texel projection is
   ~26 min and the Cycles map bake ~15 min. Skip texels on triangles already on the surface (probe each triangle
   on a voxel lattice). Find why the roof's shingle-array field is slow. Merge parts per Cycles pass. Benchmark
   with nothing else running.
3. **Face kit quality:** cheeks and nose read as stuck-on balls.
4. **Cabin:** the weathering restraint pass, then its final export.

**Gotchas from 2026-09-25:**
- Keep heavy exports alone on the machine, or the timings mean nothing.
- Exports and scene caches can fill the disk. The scratchpad lives in /tmp, which is on the root disk: clear old
  export folders.
- Background shell jobs can start minutes after launch.

