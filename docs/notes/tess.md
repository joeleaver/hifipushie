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

### Stage 2, face first, on S0urc3's approved head set (front, true left profile, 3/4 = director's pick)
- fit3.py: MAP on front + 3/4 (detector) + profile (8 clicked points: nose tip / base / bridge, lips, chin, outer
  canthus, mouth corner): 1.01 / 1.38 / 3.24 mm. addpts.py gives image-only views a few lm points (likeness() boxes
  the face from v["points"] and crashed without them). facesheet.py = reference | ours | 50/50 per view + close-up.
- Rounds (like with like tlid.py + likeness checklist): eyes 0.95, held macros brow_height 1.8 / eye_width -0.5 /
  eye_height -0.6 / lip_fullness -0.4 (ts_j); canthal_tilt 0.9 was WRONG (checklist: 7.2 deg vs the photo's 2.2):
  -0.9 -> in tolerance (ts_l); fit_human chin_height +2.5, philtrum +1.5, lip_height -1.5, nose_length +1.5.
- Skin: tone fitzpatrick 1, blood 0.3, undertone -0.45 (G/R and B/R stay ~0.80 / 0.68 vs the photo's 0.86 / 0.72
  whatever the undertone); brows thickness 0.9, density 0.8, soft 0.6, #5a4434, arch 0.2; iris #737862, size 0.0128.
- Bust: base.body.bust 0.7 -> 0.58: 34 -> 21 mm ahead of the breast bone (0.5 = 16, 0.3 = 11).
- STILL OFF (ts_l): face 5 mm narrow at the nose base / mouth / cheekbones (checklist, fit_outline not run); jaw angle
  3.5 mm high; lower lip 1.2 mm tall and the lips PART (a slit at rest: no pose or slider closes it); irises ringed
  by sclera and glassy; nose tip broad / round.
- Eye band (f3_dbg_eyeband.png): the painted upper LASH LINE ("near the eyeball" also covers the pretarsal lid). Fixed
  in skin.zone (tube through the margin landmarks base adds: lm_lid_upper_in/out, lm_lid_lower_in/out) + test.
- fit_outline moved nothing: onemesh.head_desc replaced base.head.warp with the features' warp (any human() with
  features). Fixed (ca5bd25, test_onemesh::test_stored_warp_survives_features). fit_likeness widths was hit too.
- Widths: wid.py (front detector oval below the eyes as the outline). 3 rounds: jaw_width 93.6 -> 100.5, jaw / cheek
  0.832 vs 0.793 (past tol, squarer); 1 round (ts_r): jaw/cheek 0.823 (tol edge), bizygomatic 113.9 vs 116.6,
  nose-base width 111.1 vs 113.4, bigonial 93.7 vs 92.4. Kept 1 round. jaw_square -0.8 held made the jaw WIDER.
- ts_t: shape.nose_tip round -0.6, nose_width -0.4 (held). ts_u/ts_v: lip_seal 1 (facesliders' robust seal, main
  7bdd956): lower lip 8.9 vs 8.3; lip_upper_height at its max (+1, 1.3 clamps) only 5.1 -> 5.5 vs 6.4 (a range
  limit); pose lid_upper 0.25 mm, brow_inner -0.9 mm. CANDIDATE ts_v, sheet out/f6_tess_face.png.
- Female read (ts_w, ts_x, ts_y): head.dimorphism 1.3 (default 0.8), sliders brow_ridge -0.8, held macros brow_ridge -1 /
  jaw_angle -1 / cheek_fullness +0.6, lid pose off (opening 8.3 / 8.2); brows thickness 0.7, density 0.65, arch 0.45,
  #5e4b3d; lip rolls 0.8 / 0.3, bow 0.6, tubercle 0.6, lips blood 1.4; lashes #1c1512 amount 1. No ageing slider set.
- Lip seal HOLES along the seam on ts_w / ts_x, in clay too (out/dbg_lipseal_holes.png; MOUTH=1 dbg_eye.py): with
  facesliders.

### Stage 3: hair (ts_h1 = ts_y + hs_tess's strand groom, regrown: h1.py)
- hs_tess's groom (hair2 era, a tie at [176 az, 30 el]) regrows on the one-mesh head as is (tie 59-74 locks, 4 s).
  Parting "centre" (not "center"), volume front 0.009 / top 0.011 / crown 0.014 / sides 0.013, tie escape 10, gather
  lift 0.014 -> 0.005 (the lift made a tall crest over the forehead), width 0.07, out 0.022; look lit #4a3528,
  sheen #76593f, gap #150d09. facesheet.py HAIR=1 renders the stage with the groom (hair_look job).
- Profile camera: the 8-click fit had wandered to a 60 deg view (fwd [-0.87, 0.5, 0]); refitprof.py refits it
  with yaw -90, f fixed 2600, r regularised (rms 11.5 px; old one kept as human_refs "camera_8pt"). Profile gate
  numbers before / after the refit are NOT comparable (0.48 vs 0.44 mm a px, and the brow band moved -6 mm).
- Hair trace: trace.py (mask, structure-tensor field, hand strokes) on front / 3/4 / profile; lift.py lifts strokes
  through a fitted camera; tri.py triangulates a point seen in two views. Tie: az 151, el -6, 36 mm off the scalp
  (rays miss 4.5 mm). ts_t1 = first groom from those numbers.
- Jaw (jawpts.py = likeness_points jaw.L / ear_lobe.L on 3/4 + profile): ts_h13's jaw angle 13-18 mm too low,
  ramus 36 deg too slanted (profile). shape.jawline {below_lobe 0.02, forward 0.002, sharp 0.008, tuck 0.002}
  (ts_j2): angle heights in tolerance in both views, profile ramus 15.2 vs 16.9; the gonial ANGLE disagrees
  between views (profile 124 vs 91, 3/4 122 vs 143): my traced corner, not trusted.
- Eye area (ts_e1): the refit profile camera shows the brow 5.9 mm BEHIND hers; sliders brow_ridge 0.3 (was -0.8),
  eye_sulcus -0.4, held macros brow_ridge +1.2, eye_depth +0.8: brow band -1.9 mm, profile ALL 2.17 mm (2.57).
  One identity component over 2.6 sigma.
- Front jaw kink (e1): jawline sharp 0.008 + tuck made a corner under the ears in front. Front widths like with like are all NARROWER than hers (every level), so it is the contour's shape, not width. sharp 0.014 / out -0.002 / tuck 0 (e2): smooth front but profile ramus 33.8 vs 16.9 (out). Compromise ts_e3: sharp 0.01, out -0.002, tuck 0: front kink mostly gone (out/jaw_front_cmp.png), profile ramus 23.9 (1.7 tol), heights in tolerance, profile ALL 2.17. Conflict = missing control: the gonion's corner sharpness in profile independent of its lateral flare in front.
- Hair scored against the traces (hscore.py: our hair mask by colour on the dressed stage through each fitted camera vs the trace mask; IoU, outline chamfer, extra / missing and structure-tensor flow difference per region). ts_t2 (ts_t1's groom on ts_e3): IoU front 0.44 / 3q 0.59 / profile 0.62. Rounds: volume top 0.004, crown 0.006, front 0.004, gather lift 0.002 (the top sat ~1 cm high), tail dir / stiff / length bracketed (t3 too far back, t4 too long, t5 too short). ts_t6: tail dir [0.4, 0.5, -0.75], stiff 0.25, length 0.2, fullness 0.042, curtain left over 6: IoU 0.56 / 0.56 / 0.65, chamfer 10.8 / 9.6 / 12.0 mm. NB: the stage's blend keeps its groom whatever a render job hides (hide ['hair'] showed hair): hscore masks by colour.
- t14-t16 (coordinator: t13 read as hair worn DOWN, dense wet sheets): curtain over 12 / left 16 / right 8, along 22, gather rows 3 / 60 locks, frame [2, 1] width 3-5 mm; look specular 0.15, roughness 0.65; strands clump 0.2, frizz 0.45, flyaway 0.5, stray 0.8, flat 1.4 (1.8 = a bulge on top, 1.0 = flat), gather lift 0.005, curtain lift 0.003. ts_t16: IoU 0.63 / 0.59 / 0.65; hscore now reports coverage (opacity 0..1 per region, ours vs hers): ours too opaque at the 3/4's top, too thin at her left top (-0.4). Hairline band bare 20 / 26 / 10% (was 8%: the trade for pulling the sides back). Wisps still render as dense comb strips.
- tj2 (facesliders' joint solve) adopted as ts_j2a: profile ALL 3.59 vs e3 2.15 (brow -6.6 mm): fs_tj2's own profile camera looks from ~58 deg. Kept e3; facesliders re-runs through the refit camera (ts_t18 cameras[2]). adopt.py = a head onto a dressed model.
- t19 / t20: gather wave 0.01, flat 1.5, strands thickness 0.65, stray 0.9; curtain span 75, along 28; strands soft 0.016, baby 3. Profile hairline band bare 1.9%, front 22.5%, 3q 26%. Top coverage stays +0.15..+0.33 over hers: the coverage measure reads value as well as opacity, and her hair is lighter, warmer brown with highlights (her top ~0.66-0.71); NOT a clean opacity number on dark hair. CANDIDATE hair ts_t20 on face ts_e3.
- hscore: our hair mask now from an ID pass (blender_scene id_parts: the stage's parts flat white, the hair's objects black, transparent bg; hair = opaque and black), coverage = share of the region's pixels that ARE hair (ours from the ID pass, hers from the trace's pixel classifier without hole filling), colour = luminance bands (shadow 0-20 %, mid 40-60, highlight 85-98) inside each mask.
- ts_t21: look lit #58473a, gap #221a13, sheen #6e5d4e, eevee_sat 0.45, eevee_gain 1.35: colour bands within ~1-2 levels of hers in all three views (front mid #3f3128 vs #3f3226; t20 was #28170b, too dark and red).
- t22-t24: global strands wave 0.02 put crimped ridges on the head (t22); new general key tie.tail.strands (dials for the tail alone, test) gives tail waves (t23 wave 0.025, t24 0.012 + fullness 0.036) but the waved tail hangs longer and further back: 3q / profile IoU 0.55 / 0.71 (t21) -> 0.46 / 0.59. Fewer gather locks (38) left the top as dense (+0.5 coverage) with gaps. BEST so far on numbers: ts_t21.
- BUG in my h1.py (fixed): its groom patch merged only one level deep, so a patch of tie.gather / tail / curtain REPLACED that dict: from t17 on, rounds that patched one of them silently dropped the others' keys to defaults (t25's tie had gather = {strands} only, tail = {length}). Deep merge now. ts_t26 = the intended full tie restated + gather.strands (density 0.6 = new general key strands.density, absolute x a lock's strands, test) + tail.strands waves 0.012: IoU 0.61 / 0.57 / 0.70; reads closest to her so far (airier top, waved tail, wisps).
- t27/t28: hairline lies down: global flyaway 0.12 / frizz 0.2 / baby 2, gather.strands flyaway 0 / frizz 0.15, curtain lift 0, NEW tie.curtain.hug 0.9 (general, test: the first row's row height taken away where it leaves the hairline; it stood 8 mm off as a frayed rim). Brows (browgap on t28): tail lift +1.8 mm (lift [0, 0.0018]), #55453a, density 0.6: outer gap -1.1 / -0.2 mm vs hers (was -1.4 / -1.8), tail darkness 0.35 / 0.41 vs 0.37 / 0.44. CARD GROOM = ts_t28.
- Cards from ts_t28 (exph.py = export_hair hero + main; 140 s): hero 39,996 tris / 2.7 MB, main 15,988 tris / 1.1 MB; check_tiers IoU vs strands 0.85-0.96, bare 0.04-0.14, value 0.92-1.08, sat 2.2-3.5 (cards more saturated than the strand look). Godot 4.7 (look2.gd kk shader, gd.sh, gdcams.py from the fitted cameras, bodyglb.py = a hand-written GLB of the head for occlusion): out/gd_t28_sheet.png (hero row, main row). Exports in /mnt/data/hifipushie/tess/exp_t28/.
- ts_f1 = ts_t28 + eyedetail's base.head.fold {crease_height 4.7, crease_width 1.0, crease_depth 0.6, fold_overhang 0.4, inner 0.95, outer 1.0}; eye_crease_* / eye_platform dropped. Like with like: opening 8.7 / 8.7 vs 8.2 / 8.1, brows +1.6 mm. Garrett: gc_c1 = gc_fit + look lit #5d5047, sheen #7a6d62, gap #2a221d, grey #8a7e74, eevee_sat 0.6, gain 1.1, specular 0.25: front bands #372e26 / #5b5149 / #bcb5b0 vs concept #483e37 / #6a5e54 / #b39681.
- Stage 4 start: shoes (shoes.py from su_om_garrett, x0.894), jeans = suit_trousers classic denim length shoe crease/belt none (all pre-sim checks pass). Broker: coarse sim batch a69b7a48 done ($0.058; first submit's 502 was on the poll, the job ran), pulled into res_a69b7a48 and handed back by have.sh (HIFIPUSHIE_ZOZO_REMOTE); the fine_settle upload PUT 502s repeatedly (reported). Jumper: knit block + op sleeve + generated rib bands fails the band seam / fold / cuff checks: asked cloth10.
- Jumper (ts_c1): knit block + op sleeve, generated rib bands (cuffs wrap arm.L/R follow the sleeve's wrist), fitted side shaping, eases chest 0.16 / waist 0.25 / hips 0.2: waist +44% fails the hoodie regular band (her 62.6 cm waist; side shaping capped 25 mm per quarter). Band ease / fold / ring fixes come from cloth10's branch (mine dropped). ts_f1 has no mouth interior: facesliders' sealed-interior fix (1f54697) changes nothing on it.
- Waist band from the body (cloth_workflow.waist_band_for_body, test): straight garments (waist girth >= 0.9 x chest girth) get the band top (1 + chest band top) x chest / waist - 1 on this body: Tess 0.69, a man (1000 / 900) 0.39. Jumper passes design / pattern / construction / place: neckband align [s, back, cbNeck], cuffs arm.L/R follow the sleeve wrist, hem band align [n, front, cfHem] (torso + level put it at the hips and doubled the hip girth: +124%). Hem band seam starts 'turned' 25 cm apart (WARN). Waiting on the broker.

### HANDOVER (tess agent, 2026-10-09, context full)
Branch `worktree-agent-a20b3004240dc1659` (everything committed; main merged often; coordinator merges). Stages 1-3
done (face held, hair + cards + Godot done), stage 4 (cloth) in progress, stage 5 (rig / ARKit / export) not started.

**Models (workspace/):**
- FACE: `ts_e3` is the face (head held until facesliders' joint solve re-runs through MY refit profile camera; adopt
  only if it beats e3 in all three views: run prof.py + facesheet ONLY=0,1,2). `ts_j2a` = tj2's head on the dressed
  model: lost the profile (fs_tj2 was fitted through a ~58 deg "profile" camera).
- `ts_f1` = the current dressed head + hair candidate: ts_t28 (face ts_e3 + hair t28) + eyedetail's lid fold
  base.head.fold {crease_height 4.7, crease_width 1.0, crease_depth 0.6, fold_overhang 0.4, inner 0.95, outer 1.0}
  (old eye_crease_* / eye_platform sliders DROPPED), + shoes (grey trainers), + skin2's skin (below).
- `ts_c1` = ts_f1 + cloth: garments "jeans" (suit_trousers version, simulated, superseded), "jeans3" ({kind: jeans},
  coarse in batch tess_b2), "jumper" (coarse in tess_b2).
- Hair: groom in ts_t28 / ts_f1 (tie at az 151 el -6 triangulated, curtain {span 75, along 28, hug 0.9, per-side
  to/over}, frame [2, 1], gather.strands {wave 0.01, density 0.6, ...}, tail.strands waves 0.012, hairline
  front_points traced, look colour matched to her photo bands). Cards: /mnt/data/hifipushie/tess/exp_t28/ (hero 40k /
  main 16k tris: ship main), Godot sheet out/gd_t28_sheet.png.
- Skin (on ts_f1 / ts_c1): tone {fitzpatrick 1, blood 0.25, undertone 0.15}, features {flush {0.3, cheek /
  cheekbone}, freckles {amount 0.08, dark 0.1}} (NO moles), zones {nose_red 0.75, midface_red 0.8, under_eye 2.0,
  eyelids 1.4}, lips {blood 1.0, melanin 2.8, roughness 0.5}, iris #4b4033 (her photo; brief said light hazel-green:
  director may override), brows {color #55453a, density 0.6, thickness ~1.0, tilt 2, fall 0.35, drop 0.004,
  lift [0, 0.0018], apart 0.0015, soft 0.25}.
- Garrett hair: `gc_c1` = fs_gj8 + h7_garrett's groom carried with groom.fit (+ look toward the concept's colour).

**Cloth state:** jeans (suit_trousers) simulated: clean but read as tailored trousers -> new kind `jeans`
(garment_kb: yoke, scoop + back patch pockets, mid rise, straight, break). Jumper: knit block + op sleeve + generated
rib bands (chains start/end at CB; cuffs wrap arm.L/R follow the sleeve wrist), passes every pre-sim check; the first
coarse jumper (tess_b1) failed the fine-settle start (twisted hem band) -> re-placed, re-simmed in tess_b2.
NEXT: judge tess_b2 (look_cloth through dressg.py with stage.sh handing back results), then the fine settles as one
batch, then the LAB COAT (kind coat, open, mid-thigh, notched lapels, 2 hip pockets + chest pocket; constructed collar
/ lapels after the drape per cloth10; over the jumper with tucked(keep_shown) / cut what's hidden), then the badge +
lanyard, then stage 5 (rig v1 contract: 65 Mixamo + 14 twist bones, 53 ARKit shapes, node names tess_*; see the task's
CONTRACT). Clothed bust check vs v4/v5 (director: smaller) once the jumper is on (bust 0.58 = 21 mm).

**Broker workflow (GPU fleet, HIFIPUSHIE_GPU bundle):** write jobs without running them, then ONE batch:
`HIFIPUSHIE_ZOZO_REMOTE=/mnt/data/hifipushie/tess/stage.sh HIFIPUSHIE_ZOZO=/mnt/data/hifipushie/assets/zozo/release
/mnt/data/hifipushie/tess/run.sh dressg.py <model> <garment> final 900` queues the next job in queue.txt (fails on
purpose); `batch.sh <name>` submits queue.txt as one batch and pulls into res_<name>/; re-running dressg.py with
stage.sh hands the results back and queues the next stage. blist.sh = list batches (check before resubmitting after a
502), bpull.sh <batch> <dir> = pull. Spend: b0 $0.058, b1 $0.2025, b2 (see below).

**Scripts (spikes/tess/, run as `/mnt/data/hifipushie/tess/run.sh <script> args`: capped, nice, 1 BLAS thread):**
face: fit3.py (MAP on the approved head set), tlid.py (like with like eyes / mouth + patches p/*.json, "save"),
facesheet.py (ONLY= views, HAIR=1; hers | ours | 50/50), prof.py (profile gate), refitprof.py, youth.py / browgap.py /
lipcol.py / neckw.py (like-with-like tables), jawpts.py + lkr.py (checklist), adopt.py (a head onto a dressed model),
sk.py, setb.py, fh.py, dbg_eye.py (MOUTH=1 for the mouth). Hair: h1.py (regrow with deep-merged patches; HAIR_FROM=),
trace.py (photo trace), lift.py / tri.py (lift / triangulate through fitted cameras), hairline.py (traced front
points), hscore.py (ID-pass mask, coverage, colour bands, flow vs the traces), roots.py, haircol.py, carry.py +
gscore.py (Garrett), exph.py + gdcams.py + bodyglb.py + gd.sh (cards + Godot). Cloth: shoes.py, jeans.py, garm.py
(design + checks), dressg.py.

**General code from this thread (all tested):** lash line on the lid margin; head_desc keeps stored warps; brows
tilt / fall / lift / apart and the shadow following a moved brow; hair: tie curtain (to / over / along / hug, per side),
frame, gather.strands / tail.strands, strands.density, WISP_FAN, parting "center", groom.fit; cloth: waist ease band
from the body, declared start stretch, jeans kind, ops by kind+name, leg-ease / hem measure fixes, _clear_of_body guard.
**tess_b2 result ($0.9886; stage 4 total $1.25):** both coarse sims succeeded (jumper 1201 s, jeans3 after it). Neither
fine settle could start yet (nothing sent):
- jumper: 77 triangles over 1.6x, worst 5.0x, in the bands (cuff.L 5.0, neckband 4.3, hem_band 2.8, cuff.R 2.1, back
  1.9). Was 571 triangles / 19x in tess_b1: the CB-start chains fixed the twist. Next: the bands' start (cuffs / neckband
  stretched by the coarse sim beyond their declared rib stretch?) or a looser FINE_START limit for declared bands.
- jeans3: 4 triangles over 1.6x (worst 1.8x) on back.R near the yoke / patch pocket: nearly clean. Next: find those 4
  (likely the pocket's tacks pulling the back), then the fine settle of both in one batch, then judge by eye.
