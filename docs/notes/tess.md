# hifipushie notes: tess

## Tess, the S0urc3 dive technician, on the default human path (2026-10-09, "tess" agent)

First woman on the one-mesh path. Scripts `spikes/tess/`, scratch DURABLE /mnt/data/hifipushie/tess/ (run.sh <script>:
worktree code on the main workspace, capped, one BLAS thread; ref/ = reference crops; p/ = like-with-like patches;
out/ = sheets). References (read only): /home/joe/dev/s0urc3/docs/img/tess_ref_full/ (v1 painting, v4 / v5 A-pose).
NOTE: v5 ("headturn") faces the camera; v4 has the head turned ~45 deg to her right. v5 = the front face and the
figure camera, v4 = a second (turned) face view.

Head reference brief sent to S0urc3: /mnt/data/hifipushie/tess/tess_head_brief.txt (reference_brief("head") +
addendum: conditioned on v1's face, a front smile, the hair as worn).

### Stage 1: body + head (models ts_a .. ts_e; candidate `ts_e`)
- `human("ts_a", age=22, sex="female", weight=0.35, height=1.65, outfit="underwear", source="human", tone=2)`.
- Body toward v5 (sheet.py: long lens at 8 m, v5's crown px 92 / floor px 1402 = 1.65 m): base.body weight 0.15,
  muscle 0.4, height 1.636 (gives stature 164.9 with the style sliders), base.style.human head_size 0.95 (heads 8.5;
  v5 measures ~8.5, a fashion figure; a smaller head also reads more adult, against the old "doll" complaint),
  legs 1.03, hips 0.92, limbs 0.9, waist 0.95.
- fit_human(free=["body"]) cannot narrow hips or waist: body freedom is weight / muscle / height only, and
  hip_breadth (at the joints) does not move with weight. Hips / waist exist only as style sliders.
- Face: human_reference (method map) on v5 + v4 face crops (x3 upscales, 900 px), read face_length +1, jaw_square
  -0.6, under_chin 0.8, ... The evidence overrode most of the read (face_length got +0.06): the painting's face is
  not long. Front 1.18 mm rms, v4 1.73 mm.
- Like with like (tlid.py = garrett3's lidcmp with the box from the detector): humans.face's default
  `expression` (eye_region_000 0.6) + `pose` (lid_upper -2.6 mm, smile, brow_inner) opened her eyes 2.2-2.6 mm MORE
  than the reference (staring, the old model's doll look). Removing both: opening 8.6 / 8.7 vs 8.5 / 8.5; brows then
  2.5-3.2 mm low; macro brow_height +1.5 (held): brows -0.1 / -0.6 mm. Saved as ts_e (p/p5s.json).
- Sheet: /mnt/data/hifipushie/tess/out/s1_e.png (v5 | ours clay | blend | v4; face row: crops | ours through the
  fitted cameras, default procedural skin).
- After merging facesliders (main 86b110a): base.head.sliders canthal_tilt 0.9, eye_crease_depth 0.8, eye_platform 0.4, eye_crease_height 0.3, brow_lateral -0.3 (p/p8.json) -> ts_f; like-with-like opening / brows unchanged (within 0.4 mm). At sheet resolution the change is subtle. CANDIDATE ts_f. Sheet out/s1_tess_body_head.png.
- Missing / male-leaning (reported): humans.face's default open-lid expression + pose (staring); fit_human body freedom lacks hips / waist / shoulders; the A-pose arm angle can't match the picture (45 deg vs ~25); the default procedural skin (tone 2) renders orange-tan and the painted brows thin and arched (stage 2).
