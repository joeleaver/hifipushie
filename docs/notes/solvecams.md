# solvecams (2026-10-12, "solvecams" agent, branch `solvecams`, worktree .claude/worktrees/solvecams, from main 19c2a02)
The joint solve (face_ruler.compare / blockin.solve_step / MCP block_in_solve) gets outlines and feature positions right
and the inside of the face wrong; the evidence pointed at CAMERAS and READ WEIGHTS. This thread: measure on ground truth
first (PART 1), a gate, then the fix (PART 2). Scratch DURABLE in /mnt/data/hifipushie/solvecams: env.sh, run.sh <script>
(light slot), heavy.sh <gb> <script> (capped; the script takes resources.heavy), synth/ (the benchmark's pictures), out/
(logs, one json per chain). Scripts spikes/solvecams. Models sc_* (main's workspace).

STATE: PART 1 in progress (benchmark being built).
NEXT: the tables below, then the gate message to the coordinator.

## The benchmark (spikes/solvecams/common.py, mk.py)
- FOUR GNM-NATIVE heads (block_in_start's default spec from a views list: nothing of ours on the surface, default
  dressing), identity = the sex's class mean + 0.6 sd of a seeded GNM draw (+ mm moves): a male, b male narrow
  (chin_width -6, jaw_width -6), c female wide (chin_width +5, jaw_width +6), d female. All four are native.
- NINE pictures a head, dressed EEVEE (stage.shoot, FRONT_LIGHT), 1152 x 1536, through KNOWN cameras: f (front), q23,
  q45, s72, s90, fu / fd (front, the camera pitched +8 / -8 deg), fn / ff (front through a 40 mm / 200 mm lens at the
  matching distance; the rest 85 mm), each jittered by a seeded +-2 deg yaw / pitch, +-1.5 roll, +-40 px: the jittered
  camera is the truth (sc_<h>_T/human_refs.json). 72 / 90 views carry 8 "clicks" (+-2 px); the others the detector's points.
- SETS (one view per kind, as the solve needs): A = f, q45, s90; B = f, q23, s72; P / M = fu / fd + q45, s90; N / F =
  fn / ff + q45, s90. sc_<h>_<set>T = the truth with its true cameras; sc_<h>_<set>00 = block_in_start on the pictures.
- Camera error (common.cam_err): the relative rotation in the camera's frame as pitch / yaw / roll, scale f / z,
  distance, focal, where the head's centre falls (mm). Shape error: chinread's errmap (after a similarity).

## Found on the way: base.template_joints cached a body's joints WITHOUT its head (FIXED here, tests/test_solvecams.py)
`base._source_key` keyed the injected template joints (head, eyes, lm_*, verm_*: what the build seats eyeballs / corneas
on and poses the head by) on [template, body] alone. For the one mesh they follow the HEAD (identity, attach, size). In
one process the FIRST head evaluated for a body gave every later head of that body its joints: after block_in_start +
a new identity (or a native attach) in one process, the BUILD (store.build, scene.sync, the dressed stage) stood off the
model the solve reads (face_ruler.model_head / humanfit.state): my first benchmark pictures were of a head 3.4-3.9 %
larger with the face 6-14 mm lower (a: scale 1.038, -13.7 mm; b: 1.034, -6.5 mm; c: 0.895, 5.6 deg), and an
identity-only change moves the head joint 3-4 mm and the eyes' seats with it. A fresh process was right. A long-lived
process (the MCP server: block_in_solve then look / render) does exactly this. Fix: the key is onemesh._tkey(base) for
body.source "human". Repro scripts: /mnt/data/hifipushie/solvecams/t10.py, t11.py.
(My first results on those pictures, a front camera "fitted 8 deg pitched at half the distance" and a jaw 12-14 mm
wide with every sigma x7, were this artefact: thrown away.)
