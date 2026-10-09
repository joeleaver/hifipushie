# hifipushie notes: retopo

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `retopo.py`: character topology by template wrap (from `spikes/topology/wrap.py`): the CC0 template
  (`templates/male_stylized*`) carried onto a humanoid by its skeleton (`_skeleton_warp`), face landmarks by RBF, then
  patches cut at closed template loops and generated from the model *before* the fit and held fixed (the template flows
  into them): digits as tubes on the hand kit's chains, ear bones as flat tubes with equal-arc rings (a blade ear keeps
  its rim), eyes as rings over the lids (rays from the lids' centre: star-shaped near the eye; the cut loop follows the
  lid edge's shape + `eye_phi`: at a fixed angle it crossed a wide almond opening). Ear/eye loops are carried to their
  targets first (`_carry`, and as RBF landmarks: left to the skeleton they sat behind the jaw / on the cheek). Mouth and
  nostril cavities (template verts whose normal ray hits the template again, in the face json) follow instead of
  projecting: the old "inside the model near the head" rule held the goblin's cheeks 15-25 mm inside. goblin_anat 3.11
  -> 0.85 mm mean, 10/10 rings; troll_anat 1.24 mm. Judge with `spikes/topology/wrap_eval.py` (error by region incl.
  ears, rings at `anatomy.loop_planes`, turned faces; `closeup` draws turned faces or, `ERR=3`, the model surface the
  mesh misses: the only view that caught the cheek bug). Export: `parts.body.topology = "wrap"` (asset.topology_parts:
  the wrap kept through the decimation, skin buried under other parts dropped). Base bodies (2026-09-29): digits are
  tubes on the base's own finger joints (`c["model"]` = the template's names), each base loop carried to its first
  ring, ring angles from the template's clean digit, `_stitch` winds tubes by a vote over the loop's edges (another
  cut's tip side took the face on loop[0]->loop[1]: an inside-out index finger); a grafted GNM head keeps its own quads
  (`graft_head`: un-subdivided once in Blender, 12k -> 6k quads with diagonal flow on the cranium; both meshes cut at
  clean neck loops, `_neck_cut`: plane cuts zigzagged and twisted the bridge; bridged, projected, relaxed; a closed
  mouth zipped, `_zip_mouth`). The template's face onto GNM's proportions folded round the mouth and jaw whatever the
  landmarks (tried RBF with lip/chin landmarks, a global similarity, a smoothed registration): dropped. dgf: 13.9k
  verts, 98% quads, mean error 1.34 mm, head 0.78.

