# solvecams (2026-10-12, "solvecams" agent, branch `solvecams`, worktree .claude/worktrees/solvecams, from main 19c2a02)
The joint solve (face_ruler.compare / blockin.solve_step / MCP block_in_solve) gets outlines and feature positions right
and the inside of the face wrong; the evidence pointed at CAMERAS and READ WEIGHTS. This thread: measure on ground truth
first (PART 1), a gate, then the fix (PART 2). Scratch DURABLE in /mnt/data/hifipushie/solvecams: env.sh, run.sh <script>
(light slot), heavy.sh <gb> <script> (capped; the script takes resources.heavy), synth/ (the benchmark's pictures), out/
(logs, one json per chain). Scripts spikes/solvecams. Models sc_* (main's workspace).

STATE (2026-10-13, PART 2 DONE as far as it goes; branch `solvecams`, NOT merged, NOT pushed; dense OFF by default):
cameras are priors with a distance freedom and no clips, block_in_start's fit has a pitch / lens prior, every call
starts with a cameras-first round, the sticky sigma inflation is a bound, the reply has CAMERA / DISAGREE / AT THE BOUND
lines, the dense read has measured per-region sigmas and an effective N. ACCEPTANCE: NOT MET without dense (the jaw's
width differs 7-13 mm between six camera starts; main: 14-18), MET FOR REPEATABILITY with dense (1.1-2.7 mm, face 1.28 mm)
but with a width bias of +3.5 mm and the lower face at 1.8 (target 1.6). What is fixed for good: "trust" no longer
freezes a wrong front pitch (head c: jaw +15.8 -> +8-10, face 4.70 -> 2.0), no chain stalls at x15, block_in_start no
longer puts a camera at half or twice its distance. What is not: outlines + detector anchors do not read a camera's
DISTANCE, and the solve now keeps the lens prior (70 mm unless lens_mm / EXIF): on pictures through a 126 mm lens
(chinread's heads) that costs: 2.27 / 2.76 mm against main's 2.0-2.2 / 2.2-2.5. Tess, looked at: no visible change.
NEXT (for the coordinator / Joe): (1) the held-out test belongs to that line: run it with cameras "free", once with
dense, read the CAMERA lines; (2) a LENS per reference picture (lens_mm in the brief / file name) is the cheapest fix
of the distance ambiguity; (3) the dense network's biases (narrow jaws answered with the average; pitch +2-3 deg on
male heads, +3.9 under hair; a true profile's lids) are training-data matters for denselm's full run; (4) guide topic
block_in_solve still describes clips and the inflation: rewrite; (5) merge the base.template_joints cache fix on its
own if this branch waits.
PART 1's state, as it stood at the gate: (2026-10-13, PART 1 DONE, at the GATE; no solver code changed; one cache bug fixed, below): on four GNM-native
known heads the solve's lower-face error is the CAMERAS': with true camera rotations the widths come out to 1.0-1.6 mm
and the face to 1.5 mm rms; from block_in_start's own cameras, "trust" leaves the heads WORSE than the class mean they
started from (face 2.56 against 2.10, jaw / gonial width 5.4 / 5.7 mm, one head +15.8 / +17.9) and "free" no better than
it (2.16). The two camera errors that cost width are the FRONT camera's PITCH (1.4 mm of jaw width per degree; the start
fit is 4.6 deg rms / 8.7 worst off, "trust" caps the correction at 1.67) and every camera's DISTANCE (a front camera at
half the distance: jaw +6.6, gonial +6.3, cheekbone +9.6 mm; the start fit is 38 % rms off, -78 .. +94 %, and the solve
has NO distance freedom). The side view's yaw, where the brief looked, costs under 1 mm. The sigma inflation is a cliff
(a component at 3.11 instead of 3.00 sd -> every sigma x15, sticky), not a measure of inconsistent pictures. The dense
read is 2.3-3.0 mm rms off at the TRUTH (ears, scalp / neck, forehead; a true profile's lids), is fitted to 1.6-1.9 mm
(below its own error) and biases every width +4 to +6 mm.
NEXT: the coordinator's go on PART 2 (proposal at the end).

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

## PART 1: measured (2026-10-12/13; 209 chains of blockin.solve_step, spikes/solvecams/chain.py; records
## /mnt/data/hifipushie/solvecams/out/<tag>.json, tables out/summary.md = summ.py; everything COMPUTED, nothing judged by eye
## except the nine pictures of head a and the clay / picture blend used to validate the benchmark's cameras)
Chain codes: fr = block_in_solve defaults with cameras "free" (the first call becomes "refit" by itself), tr = "trust" on
every call, ..d = the dense read on (pilot hm18), tc = TRUE cameras with every camera freedom frozen, r0 = true yaw /
pitch frozen and shift / scale / roll free, tf / tt = true cameras as the start then free / trust. 4 calls (fr, tr), else 3.
The benchmark's cameras were validated: the clay render through each true camera lies on its picture to 1 px (t4.py).

### a(i). block_in_start's camera fit (blockin.fit_cameras; refit.py, 36 pictures; errors against the true camera)
| view | yaw deg (a b c d) | pitch deg | distance % | scale % |
|---|---|---|---|---|
| front f | -0.1 -0.4 -0.7 +0.1 | +2.7 -0.9 +8.7 +0.3 | -4 +45 -59 +15 | -2.0 -3.0 -4.4 -3.0 |
| front, camera +8 deg (fu) | -0.4 +0.4 +0.4 +0.2 | +3.8 +1.6 +2.7 +1.7 | -28 +9 -55 -0 | -2.2 -3.9 -3.0 -3.0 |
| front, camera -8 deg (fd) | -0.9 -0.1 -1.6 +0.4 | +2.5 -0.2 +10.4 -1.2 | +35 +94 -54 +61 | -3.1 -4.1 -4.8 -3.6 |
| front, 40 mm lens (fn) | +0.1 -0.1 -0.2 +0.4 | +2.9 +1.4 +8.4 +0.6 | +30 +90 -32 +91 | -2.4 -4.2 -5.4 -3.0 |
| front, 200 mm lens (ff) | -0.5 -0.6 +0.1 -0.5 | +3.6 +0.2 +8.2 -1.6 | -54 -30 -78 -37 | -2.3 -3.4 -3.7 -2.4 |
| q23 | +4.2 +3.3 +5.1 +2.6 | +1.5 -1.1 +3.2 -1.4 | -8 -1 -16 -3 | -3.7 -5.1 -0.6 -4.3 |
| q45 | +0.4 -2.7 +1.0 -4.2 | -1.2 -0.9 +0.6 -1.5 | -10 -16 -13 -13 | -2.9 -5.7 +0.3 -5.0 |
| s72 (8 clicks) | +1.0 -4.9 +0.9 -5.3 | -1.8 +1.0 +3.2 -2.3 | -16 -14 -20 -17 | -2.0 -4.3 +2.5 -0.9 |
| s90 (8 clicks) | -0.1 -4.2 -0.8 -1.9 | +0.6 +1.5 +2.2 -0.4 | -16 -14 -20 -17 | -2.3 -4.5 +3.6 -0.7 |
rms over the 36: yaw 2.2 deg, pitch 3.5, roll 0.8, DISTANCE 41 %, scale 3.5 %; centre 1-4 mm.
- The STATED yaw does not matter to this fit (off by 5 / 10 / 15 deg: the same camera to 0.0 deg; only q23 has two
  minima, 5-6 deg apart). So "pictures stated as 45 fit at 33-38" is not the start's doing.
- DISTANCE is not found: the 8-click views sit at the lens prior (70 mm against the true 85: -17 %), the detector views
  go anywhere between -78 and +94 %. A 40 mm and a 200 mm picture of one head are fitted the same lens +- noise.
- On the TRUE head (no shape misfit) the front pitch is still +0.9 .. +5.0 deg and the distance -7 .. +52 %: it is the
  detector's 51 inner-face points (its landmark is not our vertex), not the class mean's shape, that cannot tell pitch
  and lens.

### a(ii, iii), c. After the chains
### Shape after the chain (mean over the heads; mm after a similarity; widths: mean |error| (mean error))

set A
| run | n | face | lower face | chin | jaw body | jaw angle | jaw_width abs (bias) | gonial_width | chin_width | cheekbone_width | sigma x | \|c - ct\| |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| start (class mean) | 4 | 2.10 | 3.25 | 2.40 | 3.19 | 4.25 | 5.5 (+5.0) | 6.7 (+5.4) | 3.5 (+3.4) | 3.4 (+1.9) | 1.00 | 7.8 |
| free (first call refit) | 4 | 2.16 | 2.66 | 1.61 | 2.57 | 3.76 | 4.1 (+0.4) | 4.5 (+2.0) | 2.9 (+1.6) | 4.0 (+2.8) | 1.24 | 10.6 |
| trust | 4 | 2.56 | 3.62 | 2.36 | 3.28 | 5.31 | 5.4 (+2.5) | 5.7 (+3.5) | 4.6 (+1.4) | 5.8 (+4.8) | 2.29 | 9.9 |
| free + dense | 4 | 1.55 | 2.44 | 1.34 | 2.39 | 3.35 | 5.3 (+5.3) | 5.6 (+5.6) | 4.1 (+4.1) | 2.7 (+1.4) | 1.09 | 9.4 |
| trust + dense | 4 | 1.93 | 2.78 | 1.75 | 2.82 | 3.68 | 6.4 (+6.4) | 6.6 (+6.6) | 4.9 (+4.9) | 3.6 (+2.7) | 2.07 | 9.7 |
| TRUE cameras, frozen | 4 | 2.11 | 2.15 | 1.59 | 1.97 | 2.96 | 1.4 (-0.3) | 1.3 (-0.4) | 1.3 (+0.2) | 1.4 (+1.4) | 5.46 | 9.8 |
| TRUE cameras, frozen + dense | 4 | 2.90 | 2.26 | 1.67 | 2.02 | 3.17 | 1.6 (+0.9) | 1.2 (+0.7) | 2.1 (+1.5) | 2.6 (+2.1) | 5.57 | 11.6 |

set B
| run | n | face | lower face | chin | jaw body | jaw angle | jaw_width abs (bias) | gonial_width | chin_width | cheekbone_width | sigma x | \|c - ct\| |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| start (class mean) | 4 | 2.10 | 3.25 | 2.40 | 3.19 | 4.25 | 5.5 (+5.0) | 6.7 (+5.4) | 3.5 (+3.4) | 3.4 (+1.9) | 1.00 | 7.8 |
| free (first call refit) | 4 | 1.85 | 2.37 | 1.55 | 2.36 | 3.21 | 3.4 (+0.5) | 4.0 (+1.4) | 2.5 (+2.5) | 3.2 (+2.2) | 1.24 | 9.7 |
| trust | 4 | 2.50 | 3.23 | 1.96 | 2.85 | 4.89 | 5.6 (+3.0) | 6.2 (+3.4) | 4.2 (+3.9) | 4.2 (+3.7) | 2.04 | 9.8 |
| free + dense | 4 | 1.52 | 2.28 | 1.24 | 2.31 | 3.13 | 5.0 (+5.0) | 5.2 (+5.2) | 4.1 (+4.1) | 1.7 (+0.8) | 1.13 | 9.3 |
| trust + dense | 4 | 1.78 | 2.55 | 1.65 | 2.60 | 3.30 | 5.0 (+5.0) | 5.5 (+5.5) | 4.5 (+4.5) | 2.2 (+1.2) | 1.86 | 9.5 |
| TRUE cameras, frozen | 4 | 2.13 | 1.99 | 1.54 | 1.78 | 2.74 | 1.1 (-0.2) | 1.2 (-0.2) | 1.2 (+0.4) | 1.8 (+1.3) | 4.90 | 9.3 |
| TRUE cameras, frozen + dense | 4 | 2.87 | 1.98 | 1.25 | 1.75 | 2.94 | 1.6 (-0.7) | 2.1 (-0.8) | 1.9 (+1.6) | 2.3 (-1.2) | 5.58 | 11.4 |

per head, set A: face / lower face / jaw_width error / gonial_width error
| run | a | b | c | d |
|---|---|---|---|---|
| start | 1.42 / 2.09 / -1.0 / -1.0 | 1.75 / 2.37 / +0.5 / -1.5 | 2.91 / 4.34 / +9.8 / +12.3 | 2.33 / 4.21 / +10.7 / +11.8 |
| fr | 2.71 / 2.15 / -0.1 / +1.3 | 1.68 / 2.15 / -4.5 / -4.5 | 3.03 / 4.70 / +9.0 / +11.7 | 1.22 / 1.63 / -3.0 / -0.6 |
| tr | 2.64 / 3.51 / -0.4 / +0.4 | 1.62 / 2.32 / -2.1 / -4.4 | 4.70 / 6.71 / +15.8 / +17.9 | 1.30 / 1.96 / -3.3 / -0.2 |
| frd | 1.50 / 1.81 / +1.9 / +2.7 | 1.53 / 2.30 / +4.1 / +2.4 | 2.05 / 3.62 / +11.5 / +13.0 | 1.12 / 2.03 / +3.6 / +4.4 |
| trd | 1.41 / 1.65 / +2.1 / +2.7 | 1.43 / 2.14 / +3.7 / +1.8 | 3.76 / 5.38 / +16.5 / +17.7 | 1.13 / 1.95 / +3.3 / +4.4 |
| tc | 1.84 / 2.17 / -2.0 / -0.8 | 1.57 / 1.45 / -0.2 / -1.3 | 2.12 / 1.31 / -1.2 / -1.3 | 2.93 / 3.68 / +2.3 / +1.9 |
| tcd | 2.06 / 1.42 / -0.7 / +0.8 | 2.85 / 2.48 / +3.1 / +1.3 | 2.46 / 1.18 / -0.6 / -0.9 | 4.22 / 3.96 / +1.9 / +1.7 |
| r0 | 2.48 / 2.15 / -0.4 / +1.0 | 1.52 / 1.72 / -0.2 / +0.4 | 0.98 / 1.01 / +2.7 / +2.5 | 1.20 / 0.94 / +0.8 / +2.3 |
| tf | 2.48 / 1.97 / -0.2 / +1.7 | 1.50 / 1.48 / +0.0 / -0.0 | 0.96 / 1.03 / +2.3 / +2.4 | 1.04 / 1.23 / -0.7 / +1.8 |
| tt | 2.47 / 3.08 / -1.8 / -1.3 | 1.57 / 2.04 / -0.3 / -1.6 | 1.05 / 1.04 / +2.1 / +2.4 | 1.57 / 2.02 / +1.6 / +2.2 |

### Camera recovery (rms over the heads of each view's error; deg, %, mm)
| set | view | stage | yaw | pitch | roll | scale % | distance % | centre mm | worst yaw | worst pitch |
|---|---|---|---|---|---|---|---|---|---|---|
| A | f | block_in_start refit (4) | 0.4 | 4.6 | 0.4 | 3.2 | 38 | 2.3 | -0.7 | +8.7 |
| A | f | after trust chain (4) | 0.4 | 3.9 | 0.2 | 1.9 | 38 | 2.5 | -0.7 | +7.5 |
| A | f | after free chain (4) | 0.3 | 1.2 | 0.1 | 2.4 | 38 | 3.1 | -0.6 | -1.9 |
| A | f | trust + dense (4) | 0.4 | 3.7 | 0.2 | 2.7 | 38 | 1.7 | -0.6 | +7.1 |
| A | f | free + dense (4) | 0.3 | 2.0 | 0.1 | 2.7 | 38 | 1.5 | -0.5 | +3.1 |
| A | q45 | block_in_start refit (4) | 2.5 | 1.1 | 0.8 | 4.0 | 13 | 3.0 | -4.2 | -1.5 |
| A | q45 | after trust chain (4) | 1.9 | 0.9 | 0.9 | 2.5 | 13 | 2.8 | +3.4 | -1.2 |
| A | q45 | after free chain (4) | 1.3 | 1.1 | 0.8 | 3.3 | 13 | 3.3 | +2.2 | +2.1 |
| A | q45 | trust + dense (4) | 1.0 | 0.8 | 0.7 | 2.5 | 13 | 2.1 | +1.2 | +1.2 |
| A | q45 | free + dense (4) | 0.8 | 1.9 | 0.7 | 2.8 | 13 | 2.3 | -1.2 | +2.8 |
| A | s90 | block_in_start refit (4) | 2.4 | 1.4 | 1.3 | 3.1 | 17 | 2.8 | -4.2 | +2.2 |
| A | s90 | after trust chain (4) | 2.9 | 1.5 | 1.2 | 2.9 | 17 | 2.7 | -4.1 | +2.2 |
| A | s90 | after free chain (4) | 4.1 | 5.7 | 1.0 | 3.0 | 17 | 3.2 | -4.9 | +8.7 |
| A | s90 | trust + dense (4) | 3.1 | 1.9 | 1.0 | 3.1 | 17 | 2.6 | -3.8 | +2.1 |
| A | s90 | free + dense (4) | 4.0 | 2.3 | 1.0 | 2.9 | 17 | 2.6 | -4.8 | +2.9 |
| B | f | block_in_start refit (4) | 0.4 | 4.6 | 0.4 | 3.2 | 38 | 2.3 | -0.7 | +8.7 |
| B | f | after trust chain (4) | 0.4 | 3.9 | 0.3 | 1.6 | 38 | 2.5 | -0.6 | +7.3 |
| B | f | after free chain (4) | 0.4 | 1.2 | 0.3 | 2.1 | 38 | 2.3 | -0.5 | -2.2 |
| B | f | trust + dense (4) | 0.4 | 3.8 | 0.2 | 3.0 | 38 | 1.9 | -0.5 | +7.1 |
| B | f | free + dense (4) | 0.3 | 2.2 | 0.0 | 3.1 | 38 | 1.6 | -0.4 | +3.3 |
| B | q23 | block_in_start refit (4) | 3.9 | 2.0 | 1.3 | 3.8 | 9 | 3.1 | +5.1 | +3.2 |
| B | q23 | after trust chain (4) | 3.1 | 1.8 | 1.0 | 2.1 | 9 | 2.8 | +6.2 | +3.1 |
| B | q23 | after free chain (4) | 2.0 | 1.4 | 0.7 | 2.3 | 9 | 2.3 | +3.8 | +2.3 |
| B | q23 | trust + dense (4) | 1.0 | 1.9 | 1.0 | 2.9 | 9 | 2.2 | +1.8 | +3.0 |
| B | q23 | free + dense (4) | 0.6 | 2.0 | 0.6 | 3.3 | 9 | 2.2 | -1.1 | +2.9 |
| B | s72 | block_in_start refit (4) | 3.7 | 2.2 | 1.0 | 2.7 | 17 | 2.6 | -5.3 | +3.2 |
| B | s72 | after trust chain (4) | 1.6 | 1.8 | 1.0 | 3.2 | 17 | 2.3 | -2.7 | +3.1 |
| B | s72 | after free chain (4) | 1.4 | 2.5 | 1.0 | 4.6 | 17 | 1.6 | -1.7 | +4.1 |
| B | s72 | trust + dense (4) | 2.5 | 1.6 | 0.7 | 2.8 | 17 | 2.0 | -3.8 | +2.8 |
| B | s72 | free + dense (4) | 2.9 | 1.8 | 0.6 | 2.8 | 17 | 2.5 | -3.4 | +2.4 |

### Start-error sweep (set A, TRUE cameras as the start, one freedom moved; the moved freedom's error after 3 calls, per head a / c)
| start error | free: end error a / c | trust: end error a / c | free: face, jaw_width a / c | trust: face, jaw_width a / c | free + dense | trust + dense |
|---|---|---|---|---|---|---|
| none | +0.0 -> -0.2 / +0.0 -> -2.4 | +0.0 -> +0.0 / +0.0 -> -1.8 | 2.48, -0.2 / 0.96, +2.3 | 2.47, -1.8 / 1.05, +2.1 | -3.4; 1.45, +2.0 / -2.6; 1.35, +3.3 | -3.0; 1.38, +1.0 / -1.9; 1.46, +4.1 |
| s90 yaw -5 | -5.0 -> -0.5 / -5.0 -> +0.0 | -5.0 -> -1.0 / -5.0 -> -2.6 | 2.48, +0.2 / 0.87, +1.8 | 2.33, -0.1 / 0.88, +1.2 | - / - | - / - |
| s90 yaw -10 | -10.0 -> -4.1 / -10.0 -> -1.9 | -10.0 -> -5.4 / -10.0 -> -5.5 | 2.41, -0.0 / 0.92, +2.1 | 2.31, -1.2 / 1.00, +1.4 | -3.4; 1.43, +2.6 / -2.4; 1.39, +3.5 | -5.0; 1.37, +1.4 / -5.0; 1.41, +3.8 |
| s90 yaw -15 | -15.0 -> -13.0 / -15.0 -> -6.9 | -15.0 -> -13.4 / -15.0 -> -10.0 | 2.27, -1.4 / 0.96, +2.7 | 2.51, +0.3 / 0.97, +3.0 | - / - | - / - |
| s90 yaw +10 | +10.0 -> +6.3 / +10.0 -> +2.9 | +10.0 -> +8.0 / +10.0 -> +6.8 | 2.46, +0.8 / 1.08, +2.8 | 2.44, +0.6 / 1.11, +2.0 | - / - | - / - |
| q45 yaw -5 | -5.0 -> +1.1 / -5.0 -> +0.4 | -5.0 -> -1.7 / -5.0 -> -1.7 | 2.26, -0.5 / 0.97, +2.1 | 2.38, -2.9 / 0.91, +1.5 | - / - | - / - |
| q45 yaw -10 | -10.0 -> +0.0 / -10.0 -> -0.0 | -10.0 -> -6.7 / -10.0 -> -6.7 | 2.02, -0.8 / 0.82, +1.5 | 1.62, +0.7 / 1.11, +1.1 | +0.0; 1.44, +2.6 / -0.8; 1.33, +3.9 | -6.7; 1.43, +0.6 / -6.7; 1.28, +3.5 |
| q45 yaw -15 | -15.0 -> -5.0 / -15.0 -> -5.0 | -15.0 -> -11.7 / -15.0 -> -11.6 | 1.73, +0.7 / 1.12, +1.7 | 1.70, +0.4 / 1.63, +1.9 | - / - | - / - |
| q45 yaw +10 | +10.0 -> +1.3 / +10.0 -> +0.3 | +10.0 -> +6.7 / +10.0 -> +6.6 | 2.01, -0.6 / 0.98, +3.1 | 2.48, -2.4 / 1.95, +2.6 | - / - | - / - |
| front pitch +5 | +5.0 -> +0.7 / +5.0 -> +1.1 | +5.0 -> +3.6 / +5.0 -> +3.3 | 2.33, +0.6 / 1.24, +3.5 | 2.42, +4.6 / 1.71, +4.8 | +2.2; 1.43, +1.8 / +0.0; 1.33, +3.6 | +3.3; 1.41, +1.7 / +3.3; 1.60, +4.3 |
| front pitch +10 | +10.0 -> +5.0 / +10.0 -> +5.0 | +10.0 -> +8.3 / +10.0 -> +8.3 | 3.13, -0.3 / 1.76, +7.3 | 2.95, +8.0 / 2.46, +8.2 | - / - | - / - |
| front pitch -5 | -5.0 -> -1.0 / -5.0 -> -1.0 | -5.0 -> -3.3 / -5.0 -> -3.3 | 2.10, -1.5 / 1.34, -1.1 | 1.70, -6.3 / 1.21, -4.3 | - / - | - / - |
| front distance -50 % | -50.0 -> -50.0 / -50.0 -> -50.0 | - / - | 2.94, +8.4 / 2.88, +11.2 | - / - | - / - | - / - |
| front distance -30 % | -30.0 -> -30.0 / -30.0 -> -30.0 | - / - | 2.51, +1.1 / 1.14, +5.0 | - / - | - / - | - / - |
| front distance +40 % | +40.0 -> +40.0 / +40.0 -> +40.0 | - / - | 1.74, +3.8 / 1.07, -1.6 | - / - | - / - | - / - |
| front distance +100 % | - / +100.0 -> +100.0 | - / - | - / 2.70, +9.0 | - / - | - / - | - / - |

### Shape per unit of camera error (set A, TRUE cameras, the error FROZEN in: yaw / pitch frozen, shift / scale / roll free; change against the same chain with no error; mm)
| camera error | heads | face rms | lower face | jaw_width | gonial_width | chin_width | cheekbone_width | chin_length | eyes_forward | sigma x |
|---|---|---|---|---|---|---|---|---|---|---|
| s90 yaw -5 | 4 | -0.07 | -0.03 | -0.14 | -0.02 | -0.35 | -0.21 | +0.00 | +1.09 | 1.03 |
| s90 yaw +5 | 2 | +0.07 | +0.02 | +0.79 | +0.59 | +0.61 | +0.39 | -0.34 | -0.15 | 1.08 |
| s90 yaw -10 | 2 | +0.13 | -0.05 | +0.74 | +0.45 | +0.15 | -0.05 | -0.37 | +0.34 | 1.00 |
| q45 yaw -5 | 4 | +0.91 | +1.07 | -0.71 | -0.58 | -0.91 | -3.56 | +0.85 | -1.86 | 2.92 |
| q45 yaw +5 | 2 | +0.38 | +0.46 | +0.86 | -0.03 | +1.74 | +3.67 | -1.27 | +1.29 | 1.15 |
| q45 yaw -10 | 2 | +1.83 | +2.20 | -2.25 | -1.21 | -2.14 | -6.62 | +3.23 | -1.32 | 2.31 |
| front pitch +5 | 4 | +0.57 | +1.57 | +6.90 | +5.71 | +3.42 | +1.57 | +0.20 | +0.40 | 1.94 |
| front pitch -5 | 2 | -0.21 | +0.87 | -7.56 | -5.16 | -5.05 | -0.32 | -0.72 | -0.37 | 2.12 |
| front yaw 5 | 2 | +0.06 | +0.58 | -0.38 | -1.75 | +0.32 | +4.83 | -0.44 | +1.23 | 2.26 |
| front distance -50 % | 4 | +0.90 | +1.94 | +6.59 | +6.34 | +2.24 | +9.64 | +0.56 | +1.17 | 4.95 |
| front distance -30 % | 2 | -0.00 | +0.55 | +0.62 | +0.64 | -0.24 | +3.01 | +0.38 | +0.54 | 1.84 |
| front distance +40 % | 2 | -0.54 | -0.26 | -2.56 | -1.62 | -0.72 | -0.53 | -0.04 | +0.34 | 2.34 |
| front distance +100 % | 3 | +0.24 | +1.36 | +1.56 | +3.36 | -1.44 | +0.12 | -3.23 | -0.89 | 5.16 |
| q45 distance -30 % | 2 | -0.08 | +0.49 | -1.11 | -1.40 | +0.77 | +2.76 | -0.52 | +0.64 | 1.65 |
| s90 distance -30 % | 2 | +0.85 | +1.63 | -2.15 | -1.20 | -1.08 | +0.02 | -2.05 | -2.83 | 1.00 |
| DENSE: s90 yaw -5 | 2 | -0.01 | -0.01 | +0.34 | +0.34 | +0.07 | -0.00 | +0.17 | +1.57 | 1.03 |
| DENSE: q45 yaw -5 | 2 | +0.71 | +0.85 | -1.01 | -0.84 | -1.07 | -2.74 | +0.89 | -0.27 | 1.02 |
| DENSE: front pitch +5 | 2 | +0.43 | +0.88 | +4.18 | +1.51 | +2.99 | -0.19 | +1.73 | +0.42 | 1.20 |
| DENSE: front distance -50 % | 2 | +0.34 | +0.89 | +5.60 | +6.78 | +1.20 | +1.71 | +0.69 | +0.06 | 1.08 |
| DENSE: front distance +100 % | 1 | +0.23 | +0.74 | -4.83 | -0.83 | +0.31 | -1.22 | -0.94 | +0.16 | 1.80 |

the no-error chain itself (r0):
| run | n | face | lower face | chin | jaw body | jaw angle | jaw_width abs (bias) | gonial_width | chin_width | cheekbone_width | sigma x | \|c - ct\| |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| true yaw / pitch frozen, shift / scale / roll free | 4 | 1.54 | 1.45 | 1.10 | 1.48 | 1.83 | 1.0 (+0.7) | 1.6 (+1.6) | 1.3 (+0.6) | 1.4 (+0.7) | 1.14 | 9.1 |
| the same + dense (a, c) | 2 | 1.31 | 1.55 | 0.87 | 1.63 | 2.11 | 2.0 (+1.8) | 2.6 (+2.6) | 1.5 (+1.5) | 1.6 (+1.6) | 1.00 | 9.6 |

### Other front views (heads a, c; sets P = camera pitched +8, M = -8, N = 40 mm lens, F = 200 mm): front camera error at the start -> end, face / jaw_width
| set | run | a | c |
|---|---|---|---|
| P | fr | pitch +3.8 -> +0.6, dist -28 % -> -28 %; face 1.42 -> 1.80, jaw_width +5.3 | pitch +2.7 -> +3.8, dist -55 % -> -55 %; face 2.91 -> 4.13, jaw_width +15.0 |
| P | tr | pitch +3.8 -> +3.7, dist -28 % -> -28 %; face 1.42 -> 2.98, jaw_width +7.9 | pitch +2.7 -> +3.3, dist -55 % -> -55 %; face 2.91 -> 4.83, jaw_width +13.3 |
| P | tc | pitch +0.0 -> +0.0, dist +0 % -> +0 %; face 1.42 -> 1.92, jaw_width -0.9 | pitch +0.0 -> -0.0, dist +0 % -> +0 %; face 2.91 -> 1.67, jaw_width -1.9 |
| M | fr | pitch +2.5 -> +0.7, dist +35 % -> +35 %; face 1.42 -> 2.17, jaw_width -0.5 | pitch +10.4 -> +2.5, dist -54 % -> -54 %; face 2.91 -> 3.15, jaw_width +10.9 |
| M | tr | pitch +2.5 -> +2.3, dist +35 % -> +35 %; face 1.42 -> 2.48, jaw_width -0.4 | pitch +10.4 -> +9.3, dist -54 % -> -54 %; face 2.91 -> 4.65, jaw_width +18.7 |
| M | tc | pitch +0.0 -> +0.0, dist +0 % -> +0 %; face 1.42 -> 2.39, jaw_width -3.5 | pitch +0.0 -> +0.0, dist +0 % -> +0 %; face 2.91 -> 2.61, jaw_width -3.1 |
| N | fr | pitch +2.9 -> -1.9, dist +30 % -> +30 %; face 1.42 -> 2.82, jaw_width -7.6 | pitch +8.4 -> +0.1, dist -32 % -> -32 %; face 2.91 -> 2.62, jaw_width +4.0 |
| N | tr | pitch +2.9 -> +1.8, dist +30 % -> +30 %; face 1.42 -> 2.75, jaw_width -0.7 | pitch +8.4 -> +8.2, dist -32 % -> -32 %; face 2.91 -> 4.04, jaw_width +12.6 |
| N | tc | pitch +0.0 -> +0.0, dist +0 % -> +0 %; face 1.42 -> 1.47, jaw_width -0.9 | pitch +0.0 -> -0.0, dist +0 % -> +0 %; face 2.91 -> 2.78, jaw_width -0.4 |
| F | fr | pitch +3.6 -> -0.0, dist -54 % -> -54 %; face 1.42 -> 2.74, jaw_width +3.7 | pitch +8.2 -> -2.1, dist -78 % -> -78 %; face 2.91 -> 1.78, jaw_width +8.7 |
| F | tr | pitch +3.6 -> +3.8, dist -54 % -> -54 %; face 1.42 -> 2.88, jaw_width +4.0 | pitch +8.2 -> +7.4, dist -78 % -> -78 %; face 2.91 -> 4.95, jaw_width +16.8 |
| F | tc | pitch +0.0 -> +0.0, dist +0 % -> +0 %; face 1.42 -> 2.50, jaw_width -4.0 | pitch +0.0 -> -0.0, dist +0 % -> +0 %; face 2.91 -> 2.03, jaw_width -3.4 |

- CAMERAS FROM block_in_start, sets A and B alike: "trust" leaves the front pitch where the start put it (3.9 of 4.6 deg
  rms; its cap is 1.67 deg) and the heads come out worse than the class mean (face 2.56 / 2.50 against 2.10; head c:
  jaw_width +15.8, gonial_width +17.9 mm: the slab). "free" takes the front pitch to 1.2 deg rms and the 3/4's yaw to
  1.3, but lets the PROFILE camera wander (pitch 1.4 -> 5.7 deg rms, +8.7 on head a; yaw 2.4 -> 4.1): the reads see a
  profile's pitch only to +-2 deg. DISTANCE never moves in any chain (38 % rms): the solve has no such freedom.
- THE CEILING (c): true yaw / pitch frozen, shift / scale / roll free (r0): face 1.54, lower face 1.45, chin 1.10 mm;
  jaw / gonial / chin / cheekbone width 1.0 / 1.6 / 1.3 / 1.4 mm mean |error|, sigma x1.14. True cameras as a START,
  then free (tf): 1.50 / 1.43 the same. So with true cameras the lower face IS right to ~1.5 mm, and the widths to
  1-1.6 mm: the cameras are the problem for the lower face, the reads for what is left (head a stays at 2.5 mm face
  from any camera, and every solve moves FURTHER from the truth in identity space, |c - ct| 7.8 -> 9-11, while the
  outlines close: the unread directions).
  "tc" (every freedom frozen at the truth) is NOT the ceiling: worse (2.11, sigma x5.5), because the head's SIZE is
  held at the class mean's and a frozen true scale then contradicts it; head d stalled at x15-18 (below).
- REPEATABILITY: the same pictures of head c, by camera start: jaw_width error +2.1 (tt), +2.3 (tf), +9.0 (fr), +15.8
  (tr), +11.2 (front distance -50 %, free), +8.2 (front pitch +10, trust). Head a: -1.8 .. +8.4. Two starts, two jaws:
  reproduced, and it is the front camera's pitch and distance.

### b. Millimetres per unit of camera error (the "Shape per unit" table above; error frozen in, everything else re-settled)
| camera error | costs |
|---|---|
| FRONT pitch, per degree | jaw_width 1.4 mm, gonial_width 1.1, chin_width 0.7-1.0 (sign: the camera pitched + = wider); with dense on 0.8 / 0.3 / 0.6 |
| FRONT distance -50 % (-30 %) | jaw +7.5 (+3.9), gonial +8.2 (+4.0), cheekbone +11.1 (+2.3), chin_width +3.0; +40 %: jaw -2.4, gonial -2.9; +100 %: -5.1 / -6.2; sigma x3.9 at -50 % only. With dense on: jaw +4.8, gonial +6.2 (little better: distance is no freedom). CORRECTED 2026-10-13: the first run of these chains also slid the picture (the whole t was scaled, not its depth); rerun, tables above are the rerun |
| 3/4 yaw, per degree | cheekbone_width 0.7 mm, jaw_width 0.15-0.2, chin_width 0.2-0.35, chin_length 0.2-0.3, eyes_forward 0.3; face rms +0.9 mm at 5 deg, +1.8 at 10 |
| SIDE view yaw, per degree | widths under 0.15 mm; eyes_forward 0.2 mm |
| front yaw 5 deg | cheekbone +4.8, gonial -1.8 |
| 3/4 or side distance -30 % | under 1 mm on every width (cheekbone +1.6 for the 3/4): only the FRONT camera's distance matters (corrected, as above) |
So 5 deg of yaw error on the SIDE view costs ~0.7 mm of jaw width; on the 3/4, ~1 mm of jaw and 3.6 mm of cheekbone;
5 deg of FRONT pitch costs 7 mm of jaw width. (The linearised numbers at the truth, ident.py, agree: front pitch +0.96
mm of jaw_width per degree, 3/4 yaw -0.5 jaw / -0.9 cheekbone, side yaw 0.06.)

### a. Does the solve recover a wrong start? (the sweep table above; true cameras with ONE freedom moved)
- 3/4 yaw: FREE recovers 5 and 10 deg fully (-10 -> 0.0), 15 to -5 (its clip is 10); TRUST stops at its clip of 3.33
  (-10 -> -6.7, -15 -> -11.7). SIDE yaw: free -5 -> -0.5 / 0.0, -10 -> -4.1 / -1.9, -15 -> -13 / -7 (weakly read;
  neither runs away nor recovers); trust -10 -> -5.4 (clip 5). FRONT pitch: free 5 -> ~1, 10 -> 5.0 (clip 5); trust 5 ->
  3.3-3.6, 10 -> 8.3 (clip 1.67). Distance: stays (no freedom).
- Nothing RAN AWAY from a true start except the profile's pitch under "free" on the fitted starts. Every limit hit was
  a CLIP at 2.5 x the freedom's sd of the START, not the reads' doing: "a trust camera pinned at its cap" is the clip.
- With dense on the same clips bind (q45 -10 -> -6.7 trust; 0.0 free); the side yaw is pulled to -3.4 .. -5 deg even
  from the TRUE start (dense reads a true 90 as ~85-87 here; the held-out photos' 75 was worse).

### d. Read balance (ident.py at the truth with true cameras, mean of 4 heads; resid.py)
| read | n | total weight (sum 1 / sigma^2) | rms at the TRUTH mm (sigmas) | share of the identity's information | of the view's yaw / pitch information |
|---|---|---|---|---|---|
| outline front / 3q / profile | 45 / 124 / 130 | 497 / 1383 / 1439 | 0.17 / 0.15 / 0.16 (0.5) | 19.7 / 30.3 / 42.0 % | 97 / 96 / 100 % yaw; 55 / 88 / 100 % pitch |
| lips (front) | 18 | 203 | 0.24 (0.8) | 5.1 % | 36 % of the front pitch |
| lids | 16 | 287 | 0.56 (1.9) | 0.1 % | - |
| iris front / 3q | 4 / 4 | 100 / 14 | 0.15 (0.8) / 0.88 (1.7) | 0.2 / 0.0 % | 0.7 / 0.5 yaw; 3.8 / 1.9 pitch |
| limbus 3q | 2 | 19 | 0.29 (0.8) | 0.0 % | 1 % |
| anchors (MediaPipe, differential) front / 3q | 102 / 102 | 99 / 99 | 0.81 (0.8) / 1.57 (1.6) | 0.9 / 1.1 % | 1.5 / 2.6 yaw; 5.4 / 10 pitch |
| DENSE front / 3q / profile | 1134 / 1058 / 778 | 271 / 167 / 79 | 2.70 / 2.99 / 2.28 (0.8 / 0.7 / 0.6 at x2 sigma) | 2.9 / 2.3 / 1.3 % | 13 / 7 / 49 yaw; 38 / 25 / 56 pitch |
- Without dense the OUTLINE is 92 % of what the identity is read from and nearly all of every camera's rotation; the
  eight iris reads are 0.2 %. Nothing else holds a camera: a camera error is paid in outline, i.e. in WIDTH.
- THE DENSE READ'S OWN ERROR at the truth (dres.py): 2.3-3.0 mm rms per view, not 1.4: ears 4-6 mm (y bias +-4-5),
  scalp / neck 6-10, forehead 2.4-3.2, cheeks 1.9-4.2, chin +2.3 .. +2.7 mm sideways in the 3/4, and in the TRUE
  profile the lids / eyes 3-4.5 mm (front 0.5-0.9); inner face front: lids 0.5-0.7, eyes 0.6-0.9, lips 1.2-1.4, nose
  1.5-1.8. As a camera its residual field asks for scale -0.5 .. -2.8 %, roll up to -1.3 deg.
- Residuals after the chains (rms mm, 4 heads; truth in brackets): iris front 0.73 free / 0.94 trust / 0.49 free +
  dense / 0.98 trust + dense (0.15); lids 0.32-0.44 (0.56); 3/4 limbus 0.89 / 1.09 / 0.77 / 1.71 (0.29); outline
  0.5-0.9 (0.16), profile outline 0.48 trust -> 1.32 trust + dense; DENSE itself 3.5-4.5 without it in the solve ->
  1.6-1.9 with it "free", BELOW its own error at the truth (2.3-3.0): the solve fits the network's biases. Result:
  with dense the face rms is better (1.55 against 2.16) and EVERY width is biased wide: jaw_width +5.3, gonial +5.6,
  chin_width +4.1 mm (mean error, every head +), and +1.8 / +2.6 / +1.5 even with true cameras. No iris read is ever
  satisfied (3-8 of its sigmas in every chain): on this benchmark the dense read does not make the irises worse
  under "free", it does under "trust" (limbus 1.09 -> 1.71).
- THE SIGMA INFLATION (infl.py, head d, TRUE cameras frozen: no inconsistency in the pictures at all): round 1's solve
  goes to 2.52 sd, no inflation; the same reads plus the SIZE hold and the NECK prior rows (exempt from the factor)
  go to 3.11 sd in two components; bringing 3.11 under 3.00 by down-weighting every read takes x15.3, and the factor
  is sticky (relax0: 15 % down a call). The step falls from |dc| 14.4 to 4.9 and head d ends WORSE than its start
  (face 2.33 -> 2.93). Leaving out the front lips or the front outline: x1.00. So: a hard threshold a hair crossed, on
  a head far from the mean (a wide jaw is +10 mm from the class mean = 5-7 mm outline misfit = 16-24 sigmas at the
  start), answered by turning every read down 15-fold. On the fitted starts it reads x2.3 ("trust") / x1.2 ("free");
  with a front camera at half distance x5-7. It says "the first linearisation overshot" or "a camera is wrong", never
  which, and its cure stalls the solve.

### e. Identifiability (ident.py: the solve's own linear system at the truth, camera priors taken off, identity prior kept)
| freedom | sd from the READS ALONE | today's prior sd (free; trust = a third) | which read holds it (sd without it) | with dense |
|---|---|---|---|---|
| front yaw | 0.16 deg | 2.0 | outline (0.44) | 0.11 |
| front PITCH | 0.58 deg | 2.0 | anchors (0.95), outline (0.83), iris (0.71) | 0.21 |
| 3/4 yaw / pitch | 0.36 / 0.41 deg | 4.0 / 2.0 | anchors (0.51 / 0.63), outline (0.47 / 0.61) | 0.21 / 0.21 |
| side yaw | 1.14 deg | 6.0 | the outline alone (unread without it) | 0.36 |
| side PITCH | 1.98 deg | 2.0 | the outline alone | 0.32 |
| scale, per view | 0.4-0.6 % | 2.5 | outline, anchors | 0.2-0.3 |
| DISTANCE front / 3q / side (no freedom today) | 20 / 13 / 63 % | - | anchors and outline together (34-37 % without either) | 5 / 6 / 9 % |
- At the right head every rotation is READ (0.2-0.6 deg; the side view 1-2 deg): there is no flat yaw-against-width
  valley in the linear system. The softest directions are the side camera's pitch with its shift / roll (no shape in
  them). The ambiguities are (1) DISTANCE against face / jaw / cheekbone width (unread by outlines: 13-63 %; dense
  reads it to 5-9 %; with the other freedoms at their priors 2-7 %), and (2) NONLINEAR: from a class-mean head and a
  wrong camera the outline's nearest-silhouette matches, the clips and the inflation hold a wrong camera in place (c:
  front pitch +8.7 kept by "trust", the outline read at 7.3 mm rms and down-weighted x3.8 by `adapt`).
- So the brief's suspects in order of what they cost: front pitch (clipped) > distance (absent) > the 3/4's yaw
  (clipped under trust) >> the side view's yaw.

## Proposal for PART 2 (waiting for the coordinator's go; no solver code touched yet)
1. CAMERAS AS PRIORS, NOT CLIPS, + DISTANCE: per view shift / scale / roll / yaw / pitch / log-distance solved with the
   identity under a Gaussian prior on the whole move (stated yaw +- its sd, pitch 0 +- ~6 deg front, lens / distance
   +- ~30 %), the 2.5 sd clips and the "trust = a third" mode replaced by prior widths; block_in_start's fit regularised
   the same way (pitch prior, lens held unless EXIF: the detector's 51 points do not read them).
2. THE FIRST ROUNDS CAMERAS-FIRST WITH THE OUTLINE (as "refit" does) for every start, wide, then joint: a wrong pitch is
   corrected before it is paid in jaw width.
3. THE INFLATION replaced by a step limit (trust region on the identity step, cmax as a bound on the STEP, hold rows
   included) and a per-camera, per-read-type consistency line (which camera, how far from its prior, which reads
   disagree) instead of one factor on everything; no stickiness.
4. DENSE: per-region sigma from its measured error at the truth (ears, scalp / neck out; forehead, cheeks, chin and a
   90 deg view's lids x2-3), an effective-N weight (its 3,000 reads are ~a few hundred), a floor so it cannot be fitted
   under its own error; its strength is the camera (pitch 0.2 deg, distance 5 %), so it may drive cameras before shape.
5. VALIDATE on this benchmark: per head and set, from four starts (fitted, true, pitch +-8, distance x0.5 / x2): the
   jaw's width within 2 mm between starts, face <= 1.6 and lower face <= 1.6 mm (today's ceiling with true cameras),
   cameras to 1 deg / 10 %; then chinread's heads c-h, then Tess by tiles.

## Notes for whoever runs this benchmark
- chain.py pert `dist:+100` on head a is REFUSED by solve_step's own stale-camera guard (blockin.cameras_fit: 0.34 off
  centre): three chains missing in the tables, said there.
- All four light slots were mine for ~3 h (176 + 32 chains, 45-90 s a call; dense doubles a call).
- Chain tags are also model prefixes (sc_<h>_<set><code>NN): keep codes free of trailing digits.

## PART 2 (after the coordinator's go, 2026-10-13; suites = mkv.py <letter>: per head a-d, set A, six starts free (fitted
## by today's block_in_start fit, TRUE, true with the front pitched +8 / -8, true with the front camera at x0.5 / x2 the
## distance) + fitted and pitch +8 under "trust"; 3 calls; acc.py <letter>; all tables /mnt/data/hifipushie/solvecams/out/acc_abc.md)
### What was built
1. face_ruler: PHOTO_CAM_SD7 (shift, shift, scale, roll, yaw, pitch, DISTANCE: the prior sd of each camera's whole move
   since the start; "free" = these, "trust" = a third), cam_moved(dist=) (log distance, the lens to match), the distance
   column (finite differences), NO clip on the whole move (CAM_STEP limits one round's step), view_pitch / lens_mm /
   camera_lines: a CAMERA line per picture in the reply (turn / pitch / distance start -> end, whole move against its
   prior, FAR FROM ITS START past 1.5 sd). blockin.fit_cameras: pitch 0 +- 5 deg and the lens +- 5 % of its prior
   (humanfit_map.fit(cam_prior=)): block_in_start's front distance error -59 .. +45 % -> -17 .. -14 % (= 70 mm against
   the true 85), its pitch +8.7 -> +6.8 on head c (the detector insists; the solve then corrects it).
   Distance priors: front 15 %, 3/4 12 %, side 8 % without the dense read (see "what does not work"), 40 % with it.
2. read(cam_first=, cam_reset=): one cameras-first round (head held) on EVERY call under the mode's own prior, the whole
   move tracked; "refit" as before (2 rounds, wider, the new start). Distance is HELD in these rounds.
3. solve(cmax=): an active-set BOUND (components that would pass cmax are held at it, the rest solved again); no sigma
   factor, nothing carried between calls (relax is always 1.0 now; the size hold and the neck prior cannot trigger
   anything). disagreement(): DISAGREE (read groups left past 2 of their own sigmas, by type and picture) and AT THE
   BOUND lines.
4. (built, suite running) dense: DENSE_REGION_SIG (the measured per-axis error by view kind and region as the sigma's
   floor), ears / scalp / neck out, DENSE_NEFF 80 (sigma x sqrt(n / 80)), block_in_solve(dense=); still OFF by default.
### Measured (3 calls; jaw_width error mm per start: fitted / true / pitch +8 / pitch -8 / distance x0.5 / x2)
| head (class mean's jaw error) | main "free" (nearest starts: fitted, true, pitch +10, pitch -5, x0.5, x2) | main "trust" (fitted, true, pitch +10, -5) | a: step 1 (distance prior 30 %) | b: + step 2 (distance 15 / 12 / 8 %) | c: + step 3 |
|---|---|---|---|---|---|
| a (-1.0) | -0.1 / -0.2 / -0.3 / -1.5 / +8.2 / -6.1 | -0.4 / -1.8 / +8.0 / -6.3 | -0.8 / -0.5 / +1.3 / -1.5 / +3.8 / -4.3 | +1.9 / +1.2 / +7.0 / +0.3 / +3.3 / -3.5 | +1.9 / +1.2 / +7.0 / +0.3 / +5.9 / -3.5 |
| b (+0.5) | -4.5 / +0.0 / - / - / +9.4 / -3.5 | -2.1 / -0.3 | -4.2 / +0.8 / +0.3 / +0.2 / +0.6 / +0.5 | +3.5 / +0.9 / +2.1 / +2.6 / +6.0 / -2.2 | +3.5 / +4.5 / +2.1 / +5.3 / +4.2 / -2.2 |
| c (+9.8) | +9.0 / +2.3 / +7.3 / -1.1 / +10.7 / -4.2 | +15.8 / +2.1 / +8.2 / -4.3 | +7.8 / -0.1 / +0.8 / -5.0 / +5.5 / -5.9 | +8.6 / +2.9 / +5.0 / -2.0 / +7.0 / -4.5 | +8.6 / +3.6 / +5.0 / -2.0 / +5.4 / -4.2 |
| d (+10.7) | -3.0 / -0.7 / - / - / +9.2 / -8.9 | -3.3 / +1.6 | -7.5 / +0.2 / +2.4 / +0.7 / +1.9 / -6.9 | -2.3 / -2.0 / -1.8 / -2.2 / +8.4 / -9.7 | -2.3 / -2.0 / -1.8 / -2.2 / -0.1 / -9.7 |
| SPREAD of the jaw over the six starts, a / b / c / d (target 2) | 14.3 / 13.9 / 14.9 / 18.1 | - | 8.1 / 5.0 / 13.7 / 9.8 | 10.5 / 8.2 / 13.1 / 18.1 | 10.5 / 7.4 / 12.9 / 9.7 |
| ... over fitted / true / pitch +-8 only | 1.4 (a) / 10.1 (c) | 14.3 (a) / 20.1 (c) | 2.8 / 5.0 / 12.8 / 9.8 | 6.6 / 2.5 / 10.6 / 0.5 | 6.6 / 3.2 / 10.6 / 0.5 |
| face / lower face, mean of the 24 free chains | - | - | 1.70 / 1.89 | 1.81 / 2.08 | 1.86 / 2.00 |
(main's fitted-start chains for comparison, 4 heads: free 2.16 / 2.66, trust 2.56 / 3.62; class mean 2.10 / 3.25.)
- STEP 1 HELPED where main failed: under "trust" a wrong front pitch is now corrected (pitch +8 trust: front pitch ends
  +1.1 .. +1.5 deg, was +8.3 at +10; head c fitted + trust: jaw +15.8 -> +8.2, face 4.70 -> 2.13), distance moves the
  right way from x0.5 (-50 -> -21 .. -44 %; jaw +9 -> +0.6 .. +5.5) and the start fit no longer puts a camera at half
  or twice its distance. It did NOT make starts agree: 8-14 mm of jaw between them after 3 calls.
- STEP 2 (cameras first; measured together with the tighter distance prior): head d's four non-distance starts now end
  within 0.5 mm of each other (9.8 before) and b's within 2.5; a and c got no better (6.6, 10.6). The tight distance
  prior costs the x0.5 / x2 starts (they stay at -35 / +70-100 %): expected, see below.
- STEP 3 (bound instead of inflation): changes only the chains that were inflating: head d from a x0.5 camera: face
  3.14 -> 2.38, distance -37 -> -7 %, jaw +8.4 -> -0.1 (it had stalled at x7-9). Nothing else moved.
- STILL WORSE THAN THE CLASS MEAN (face or lower face): 10 of 24 chains, 9 of them heads a and b, whose class mean is
  already 1.4-1.75 mm from the truth; with TRUE frozen rotations (Part 1, r0) head a ends at 2.48 too: the reads'
  ceiling on that head, not the cameras. Heads c and d (class mean 2.9 / 2.3 mm off, jaw +10) end better from every
  start except c fitted + trust (lower face 3.57 against 4.34: better, but 8-10 mm of jaw).
- MORE CALLS (8, suite c's code): head a pitch +8: jaw +7.0 at call 3 -> +1.5 at call 8 (true start: +1.2); head c
  fitted: +8.6 -> +6.1 (pitch +2.0, distance -9 %), true start +3.6 -> +2.2 (pitch 0.0, distance +9 %). So 3 calls is
  not converged (steps are halved from the first see-saw on), and what is left on c is 2 deg of front pitch and ~18 % of
  distance between the two chains = the 4 mm.
### What does not work (measured)
- DISTANCE from outlines and detector anchors: at the truth 20 % (1 sd); in chains it wanders +-10-20 % from call to
  call, a TRUE camera drifted to +28 %, a x2 start went to +129 % (suite a, prior 30 %). Hence the tight prior without
  dense: a wrong lens is then simply kept (x0.5 start: jaw +3 .. +8 mm).
- CAMERAS ONLY WITH DENSE on a class-mean head (camfit.py): from any start (true, pitch +8, x0.5, x2) the cameras land
  on the SAME place (start-independent: good) but a biased one: head c (wide jaw): front distance -54 %, pitch +2 .. +4,
  side +72 %; head a: front +22 %, pitch +2.4. A held head's shape misfit is read as perspective. So distance is never
  solved in the cameras-first rounds; it has to be solved WITH identity.

### Step 4: dense (suite d = steps 1-3 + the dense read with DENSE_REGION_SIG / DENSE_NEFF / ears, scalp, neck out, distance
### prior 40 % and solved WITH identity only; 3 calls, cameras "free"; tables out/acc_def.md)
| head | jaw_width error from fitted / true / pitch +8 / pitch -8 / distance x0.5 / x2 | SPREAD (without dense; target 2) | front pitch error at the end | front distance error at the end | face / lower face (range over the starts) |
|---|---|---|---|---|---|
| a | +1.0 / +1.5 / +0.9 / +1.4 / +1.9 / +0.8 | 1.1 (10.5) | +1.2 .. +2.3 | -6 .. -12 % | 1.36-1.47 / 1.51-1.68 |
| b | +6.8 / +5.1 / +6.6 / +5.8 / +6.9 / +5.4 | 1.8 (7.4) | +1.7 .. +3.1 | -3 .. +9 % | 1.36-1.55 / 2.11-2.58 |
| c | +4.6 / +3.1 / +4.1 / +4.1 / +3.4 / +1.8 | 2.3 (12.9) | -0.5 .. -0.1 | -13 .. -24 % | 1.06-1.17 / 1.13-1.51 |
| d | +2.1 / +1.3 / +3.6 / +3.9 / +3.5 / +3.6 | 2.7 (9.7) | -1.2 .. -0.8 | -13 .. -19 % | 1.01-1.18 / 1.50-1.98 |
Mean of the 24 free chains: face 1.28 (1.86 without dense), lower face 1.79 (2.00). "trust" from the fitted and the pitch
+8 start ends inside the same ranges (c fitted + trust: jaw +6.4, face 1.35; the worst cell).
- DOES DENSE CLOSE THE DISTANCE AMBIGUITY: PARTLY. From x0.5 and x2 the front camera comes back to the same place as
  from the true start (to within ~10 %), and so does the pitch: the START no longer matters (spread 1.1-2.7 mm against
  7-13). But the place it comes back to is BIASED: distance -6 .. -24 % (too close) on three heads, pitch +1.2 .. +3.1 deg
  on the two male heads. Both biases widen the jaw.
- WIDTH BIAS: mean error over the 24 chains jaw_width +3.5, gonial_width +3.9, chin_width +2.6, cheekbone +1.3 mm (old
  dense weighting, Part 1: +5.3 / +5.6 / +4.1; no dense, suite c: +1.2 / +2.0 / +0.9 / +1.6 with a scatter of 3-4 mm).
  Head b (the NARROW jaw and chin) is the worst: +5 .. +7: the network answers a featureless jaw with the average one
  (denselm's known gap), now also through the camera (pitch +2-3 deg).
- VARIANTS of which dense reads may move IDENTITY (all of them always move the cameras; 4 starts each):
  | variant | face / lower face | jaw spread a / b / c / d | note |
  |---|---|---|---|
  | all regions (KEPT, DENSE_IDENTITY "all") | 1.28 / 1.79 | 1.1 / 1.8 / 2.3 / 2.7 | the table above |
  | none (cameras only) | 2.20 / 2.75 | 14.7 / 3.9 / 5.5 / 2.3 | head a runs away: front pitch +5 .. +7, distance -45 %, jaw +11 .. +16 |
  | inner face only (lids, eyes, lips, brows, mouth, nose) | 1.49 / 1.86 | 2.5 / 1.1 / 4.7 / 2.2 | c and d better (jaw -1 .. +4, lower face 0.8-1.5), a and b worse (a face 2.0, b jaw +6) |
  "all" is kept: best mean and the only one no head loses with; "none" shows again that a camera read against a head
  that cannot follow is read as perspective.
- ACCEPTANCE with dense: jaw spread 1.1 / 1.8 / 2.3 / 2.7 (target 2: two heads just over); face <= 1.6 on every chain;
  lower face <= 1.6 NOT met (b 2.1-2.6, d 1.5-2.0); worse than the class mean: only b's lower face from some starts
  (2.1-2.6 against 2.37) and a's face by 0.05. Without dense: repeatability not met (7-13 mm). DENSE stays OFF by default.

### Wider benchmark, older sets, Tess (suite w = heads e, g, four starts; q3.txt; all on the final code)
- HEAD e (another dressing: dark skin, age 60, a hard TOP light; bald), no dense: jaw_width -1.7 / -5.9 / -4.3 / -7.9
  (fitted / true / pitch +8 / distance x2), face 2.1-2.8, lower face 1.4-2.3: WORSE than its class mean (1.69 / 2.01)
  from every start; front pitch -1.6 .. -3.5 deg. With dense: +2.1 .. +3.2 (spread 1.1), face 1.47-1.57, lower face
  1.94-2.35, pitch -0.2 .. +1.3, distance -3 .. -9 %. The hard top light costs the plain solve ~0.7 mm of face.
- HEAD g (tess_n1's body, skin and strand HAIR tied back: the scalp's outline and the ears' tops under hair), no dense:
  jaw +0.1 / -0.6 / -0.8 / -2.8, face 1.22-1.42, lower face 1.24-1.60 (class mean 1.69 / 1.99): the BEST head of the
  six; front pitch +0.8 .. +1.3 deg, distance -8 .. +5 % (x2 start stays +91 %). Hair over the scalp outline did NOT
  degrade the cameras here (the skin outline that is left, the cheeks / jaw / chin and the profile line, is what holds
  them; one head, one hairstyle, tied back: not loose hair over the jaw). With dense: jaw +3.9 .. +4.8, front pitch
  +3.9 deg from every start: under hair the network's pitch bias is its largest.
- CHINREAD's heads c-h (body-carried, old attach; NOT re-rendered: they ran as they are; pictures through a ~126 mm
  lens; fitted start, 3 calls): no dense 2.27 / 2.76 (start 2.62 / 3.13; main today 2.0-2.2 / 2.2-2.5): a little WORSE
  than main: the start fit now holds the 70 mm prior (-45 % of distance) where main's free lens happened to land nearer,
  and the wide heads pay (g: jaw +11.0, h +1.5, f +7.6). With dense 1.49 / 1.81 (denselm's D: 1.46 / 1.80): the same.
- SOLVEREADS' set (sx a_x, a_n, b_x, b_n): no dense 2.72 / 2.07 (start 2.87 / 2.69); dense 2.37 / 2.45.
- TESS (sc_T00 = block_in_start("tess_a1", sex female) on the new path; 6 calls; sc_TN06 no dense, sc_TD06 dense;
  logs out/tess_*.log). LOOKED AT, tiles one at a time (feature tour, clay: /mnt/data/hifipushie/tour/<model>/), sheet
  workspace/human_renders/sc_tess_cameras.png (REFERENCE | sc_TN06 | tess_n1):
  | tile | after against before (tess_n1) | against her |
  |---|---|---|
  | jaw + chin, front | SAME: I cannot tell the two apart | on her outline where hair leaves it; her chin is smaller and more pointed than either |
  | chin, front | SAME | a broader, rounder chin pad than hers |
  | eyes, front | SAME placement (the overlay is sharp at both irises) | openings narrower than hers in both |
  | jaw + chin, three-quarter | SAME | the model's chin and jaw line lie a few mm outside hers (a ghost edge under the chin) |
  | jaw + chin, profile | SAME (the under-chin perhaps 1 mm nearer) | chin's front on her line; under-chin fuller / lower than hers |
  Cameras: 4.7 / 39.0 / 74.3 deg (tess_n1: 4.6 / 39.2 / 70.7), front pitch -4.7, distances +6 / +5 / -1 % from the
  start, no FAR FROM ITS START line at the end, DISAGREE: lids 2.4 sigma (0.9 mm). With priors and no clip the 3/4 still
  sits at 39 and the "profile" at 74: that is what the reads say those two pictures are, not a cap. Dense (sc_TD06):
  5.2 / 39.5 / 71.2, the profile's distance +43 %; the lower face a little BROADER than without (looked at: worse).
  So on Tess the camera work changes nothing visible: her cameras were not what was wrong.
### What changed by default (exactly), tests
- face_ruler: PHOTO_CAM_SD7 / CAM_STEP / PHOTO_CAM_DIST_DENSE, cam_moved(dist=), the distance column, no whole-move
  clip, cameras-first on every call (read(cam_first, cam_reset)), solve(cmax) = bound (out["bound"], "resid"),
  disagreement(), camera_lines(), view_pitch(), lens_mm(); compare(cam_sd=PHOTO_CAM_SD7, dense=). Dense: DENSE_SIG_SCALE
  1, DENSE_REGION_SIG, DENSE_REGIONS (no ears / scalp_neck), DENSE_NEFF, DENSE_IDENTITY; DENSE still False.
- blockin: fit_cameras under FIT_LENS_SD / FIT_PITCH_SD (humanfit_map.fit(cam_prior=)), solve_step(dense=), CAM_FIRST 1,
  cam_done has 7 columns (older models' 6 are padded), rep["solve"] gains camera_lines / bound / disagree; relax is
  always 1.0 (RELAX_KEEP inert). base._source_key: the cache fix (top of this note).
- Tests (one file a process, HIFIPUSHIE_ASSETS set, none skipped): test_solvecams 3, test_refread 9 (two rewritten:
  the bound, 7 camera numbers), test_solvereads 11 (one rewritten: the bound), test_face_ruler 4, test_blockin 19,
  test_chinread 7, test_denselm 4, test_nativedefault 6, test_orbit 10, test_headbody 6.
