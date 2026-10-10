# GNM audit: what Google's head model is, how it is meant to be driven, how we drive it (2026-10-10)

Independent audit ("gnmaudit" agent). Joe: "really understand GNM and compare what it can do and how it's supposed
to be used against how we've used it so far." I read GNM from primary sources first (the repo at our pin and at HEAD,
the technical report, the model file) and measured it myself, then read our code and notes. I changed no code and no
shared model. Scratch (durable): /mnt/data/hifipushie/gnmaudit/ (scripts/, r/ renders, logs; its own small venv: numpy, h5py,
scipy, matplotlib). Sheets: workspace/human_renders/ga_01..ga_04. Scratch models only in a separate workspace
(/mnt/data/hifipushie/gnmaudit/ws, HIFIPUSHIE_HOME), never in the shared one.

## Verdict, ranked by what it costs likeness

1. **What we read as "GNM can't" is mostly "our evidence can't see it".** Our fits pin about 19 of GNM's 170 identity
   directions. That number is trace(I - posterior covariance) for MediaPipe-478 through our calibrated table, front +
   3/4 + profile clicks; scripts/g17_evidence_power.py. Everything else comes back as the population MEAN, which is
   what a MAP does with no evidence.
   - A real face sits at |c| ~ 13.0 +- 0.7 under GNM's prior. A MAP on our evidence is predicted to land at ~4.4
     (6.2 with the profile contour). Tess is stored at |c| 5.7 and Garrett at 4.5: exactly that.
   - On synthetic GNM faces our evidence returns |c| 3.6 (truth 13.0) and recovers crease HEIGHT at r = -0.17. On
     real (ICT) face variation it recovers the dorsum at r = 0.19.
   - The detail we then rebuilt by hand (lidfold, MakeHuman nose / lip extensions, hand sliders) is detail the
     evidence never asked GNM for.
2. **The upper-lid crease is in GNM.** It is a fold made by identity + eye-region EXPRESSION (lid state), not a
   groove. Tess's crease, driven as GNM intends, appears at her measured height for almost nothing:
   - **Evidence used:** her photo's lid margins against the iris (MediaPipe) and her crease line height (our own
     read_lid, TPS 4.95-5.15 mm).
   - **Cost:** |dc| 0.9-1.5. The change in the evidence the identity was already fitted to is chi2 0.27-0.83 over 890
     rows. Eye expression |e| ~1.
   - **Survives our pipeline:** it shows through one mesh, meshing and look (ga_01, ga_02).
   - **What faces5 did instead:** it fitted lidfold's groove FIELD, a ~1 mm-wide groove at GNM's mesh Nyquist, and
     got a broad roll at "8.4 / 14.8 sd". That is the wrong target, not a wall.
3. **"sd" costs were read on the wrong scale.** |dc| was reported as "sd" against 0, but a typical face is 13 from the
   mean and two random people are ~18 apart. What made the "walls" was asking for isolated, artist-made local shapes
   exactly (0.05 mm), not locality:
   - MakeHuman nose targets cost 25-67 at 0.05 mm even with the rest FREE (scripts/g10_locality.py), so this is not
     locality.
   - At photo precision (0.5-1 mm) they cost 3-17 and are 0.55-0.98 made, with side effects GNM's population attaches.
   - On REAL face variation (ICT-FaceKit's modes carried onto GNM) GNM reproduces nose / lip / orbit shape to 0.55-0.7 mm
     rms. Nose measures correlate 0.83-0.98 with truth. That is capability. Our evidence gets 1.3-1.6 mm and r 0.19-0.88.
     That is evidence.
4. **Expression is left out of the identity solve.** GNM is built so that identity = each person's RELAXED NEUTRAL
   (habitual carriage included) and expression = per-picture deltas. Its fitting solves both, with L2 priors.
   joint2 / humanfit_map solve identity only. Lids are then posed afterwards with our own mm offsets, measured
   against our own replacement eyeball.
5. **The eyeball replacement shifts the lid / iris relation.**
   - **What we do:** GNM places its two-sphere eyeball (cornea bulge) to fit the lids and moves it with identity. We
     put a plain sphere at 0.96x its size and push it back until the rims clear by 0.8 mm (base.py:531-532,
     2176-2191).
   - **Measured on Tess:** with GNM's own eye, her photo needs the upper lid UP ~1.3 mm (lid at 0.43 iris radii above
     the iris centre; photo 0.67). Our eye stage concluded it should go DOWN 1.0 mm (fs_te7 pose lid_upper +0.001).
     That is a 2.3 mm disagreement on the most identity-laden region.
6. **Our sex axis is not GNM's.** delta_sex (ANSUR / NIOSH size differences, minimum-norm) is almost orthogonal
   (cosine 0.10) to the male - female difference in GNM's own labelled data (its semantic sampler: 94% LDA-separable).
   Sampled women and men differ by only 0.22 along OUR axis, against the 2.1 we assume. Our "female mean" moves size,
   not female shape.
7. **Evidence weighting throws away what we do measure.** INFLATE x2 + FLOOR 0.7 + CUT 2.5 (humanfit_map.py:33-35)
   leave 306 front points at a median sigma of 3.6 mm. The nose keeps 44 of 106 points at 4.3 mm; the alar points
   (sd ~4 mm) are CUT, so nothing in the fit measures alar width. Dropping INFLATE alone takes the determined
   directions from 19 to 32.
8. Smaller items: 120 of 170 comps used; component and readout walls at 2.5 sd (a typical face's largest comp is
   ~2.8, and real faces often exceed 2.5 on some attribute: the walls clip distinctiveness); the semantic sampler is
   unused; ARKit targets come from our landmark tables rather than data (their coefficients are in range, max |c| <= 4);
   random humans are seeded at spread 0.6 (60% of the population's variation).

**Answers to Joe's questions**
- **Could GNM make the crease all along?** Yes, as a fold, at a given person's height, consistent with their other
  evidence (section 4.1, ga_01 / ga_02).
- **Is GNM's identity prior too tight on fine shape?** No. faces5's own M3 already retracted faces4's ICT claim, and
  GNM's sampler, trained on real coefficients, puts comps 40-169 at sd 0.85-1.24. We did not misuse its scaling.
  We misread a MAP of weak evidence as the model's reach.
- **Are we using the expression basis correctly?** Mechanically yes (pose, ARKit). Strategically no: it is absent from
  the identity solve, and "habitual expression" in GNM is identity by construction.

## 1. GNM from primary sources

Sources:
- Repo github.com/google/GNM at our pin 915aa35 (2026-09-25) and at HEAD a67464a (2026-10-08). Clones:
  /mnt/data/hifipushie/gnmaudit/GNM_pin, GNM_head.
- Technical report arXiv 2607.23687v3 (Ploumpis, Bednarik et al., Google, 2026): paper/paper.txt there.
- The model file gnm_head.npz v3.0. It is byte-identical to ours, sha256 e3710378...

### 1.1 Components (measured from the npz: scripts/g1_structure.py, inspect_npz.py)

| part | what | numbers |
|---|---|---|
| mesh | 17,821 verts, 17,662 quads, 35,324 tris; 6 components | skin, left_eye, right_eye, upper / lower teeth+gums, tongue |
| vertex groups | 46 | skin, skin_exterior, hockey_mask, lips, mouth_sock, eye_sockets, scleras, irises, pupils, ears, the per-region expression masks, 22 anatomical *_region groups; mirror_indices |
| UVs | quad_uvs and triangle_uvs, 5 regions | left / right eye UVs overlap |
| resolution (mean edge) | skin 3.8 mm, hockey mask 2.6, orbital 1.5, nose 1.9, lips 2.0-2.2, temples 5.9 | the upper lid has ~12-14 rows lash line to brow, ~1 mm apart, so a 2-3 mm fold is drawable and a <1 mm groove is not |
| identity | 253 = head 170 + eyes 3 + teeth 80 | head: PCA of ~5000 subjects' NEUTRAL scans, Procrustes-aligned; each vector scaled by its sd so the coefficients are unit variance (report section 3.5; README "typical range -3 to +3"). First 10 comps hold 91.6% of the head variance, 40 hold 98.7%, 120 hold 99.89%. RMS displacement over the skin per unit: comp 0 4.8 mm, comp 20 0.36, comp 120 0.044, comp 169 0.027. Not exactly orthogonal (max abs cos 0.136): the eyeball / teeth / tongue backfill (report 3.5 / 3.8) adds rigid offsets |
| eyes | two-sphere sclera + cornea model; 3 identity comps (limbus 6.0 +- 0.44, cornea 8.5 +- 0.73 mm) + 1 pupil expression comp (-3 point, 0 half the iris, +3 full) | eyeball translation with identity is backfilled so the eyes stay seated in the lids (report 3.5, 3.7.3) |
| teeth | 80 comps from 5000 procedurally rigged artist shapes | |
| expression | 383 = left eye region 100 + right eye 100 (mirrored copies) + lower face 150 (incl. jaw opening with the lower teeth moved rigidly) + tongue 32 (comp 0 is the dataset mean, so 0 = a retracted tongue) + pupil 1 | uncentred per-region PCA of per-subject deltas (each expression scan minus that subject's own neutral), sd-scaled, regions blended by soft masks (report 3.6). Expression 0 = that person's neutral |
| skeleton | joints neck, head, left_eye, right_eye (parents -1, 0, 1, 1); artist skinning weights; joint_identity_basis moves the joints with identity | standard LBS. pose_correctives_regressor (36 x 53463) is present but ALL ZERO in v3.0: no pose correctives |
| landmarks | head_sparse_68.txt: iBUG-68 as barycentric (vertex, weight) triples (jaw order fixed in 0ae8cc7, before our pin) | the ~600 dense landmarks Google fits with are NOT released ("future work", report section 5) |
| semantic sampler | two Keras CVAEs (data/semantic_sampler/*.h5) | identity: 64-d latent + 6-d label (female / male x Middle Eastern / Asian / White / Black) -> 253 coefficients. Expression: 64-d latent + 20 classes (surprise, disgust, suck, compress / stretch face, happy, squint, platysma, blow, funneler, smile_wide, corners_down, pucker, wink L/R, mouth L/R, lips_roll_in, snarl, tongue_center) -> 383. Trained on 12K samples. I re-implemented the decoders in numpy (scripts/cvae.py: Dense ReLU 64-128-256-512, linear out) |
| texture / albedo / detail | NONE | the registration used RGB textures, but no appearance model is released. No hair, brows, lashes, pores or displacement |
| fitting code released | fitting_utils: project_on_pca (regularised least squares of a REGISTERED mesh on the basis, lambda * norm(c)^2) and regularized_least_squares | no image-fitting code |

### 1.2 The prior and its scale (scripts/g2_prior_scale.py)

Each component is scaled by its standard deviation (report 3.5: "scaled proportionally to the dataset variance it
explains, which unifies the effective range"). So the intended prior is N(0, I) on beta (report 4.2: "a simple L2
prior on the identity and expression coefficients"). Check on Google's own data:
- The identity sampler was trained on 12K real coefficient vectors. Its decoded faces have norm(beta_head) = 13.4,
  where sqrt(170) = 13.0.
- Per-component sd is 0.44-0.66 for comps 0-20 (a VAE decoder under-disperses its leading modes), 0.85 for comps 40-80,
  0.98 for 80-120 and 1.24 for 120-169.
- So the fine components are NOT tighter than N(0, I) in Google's data, if anything wider.

Consequences:
- A real face is at |c| ~ 13.0 +- 0.7 from the template. Two random people are ~18 apart.
- The largest single |c_i| of a typical face is ~2.8 (expected maximum of 170 standard normals).
- The posterior MODE (our MAP) is NOT a typical face: in every direction the evidence doesn't see, it is the mean.

### 1.3 Expression and identity

- **Linear and additive, before skinning:** bind = T + I beta + E phi (report eq. 1); then LBS. Expression deltas are
  identity-INDEPENDENT: the same delta is added to every identity. There is no identity x expression term, so a
  blink on a deep-set lid and on a prominent lid is the same displacement. Google's fitting penalises
  eyeball / skin intersections for this reason (report 4.2, E_anat).
- **Habitual expression is identity:** the identity basis is the PCA of each subject's relaxed neutral. Resting brow
  height, lid aperture and mouth set are therefore identity in GNM, and the expression basis is deltas from that
  person's own neutral (report 3.1, 3.5, 3.6).
- **Eye regions are local and mirrored:** a left-eye comp moves only the left periocular mask (1,900 vertices); right
  = mirrored left. They span lid opening and closing, squint, brow raise / lower and the fold.

Measured on the template (scripts/lids.py; upper / lower lid in iris radii from the iris centre; template 0.51 / 1.05):

| comp | value | upper lid | lower lid |
|---|---|---|---|
| left_eye_region_000 | +2 | 1.07 | 1.39 |
| left_eye_region_000 | -2 | closed | |
| left_eye_region_001 | +2 | 1.42 | 0.87 |
| left_eye_region_003 | +2 | 0.87 | 0.85 |

### 1.4 How Google intends it to be fitted (report 3.2, 4.1, 4.2)

- **Scans (to build and evaluate):** stage 1, a least-squares fit to the registered mesh; stage 2, ICP to the scan
  with "no regularization ... to allow both ... to be maximally expressive". Result: 0.748 mm mean scan-to-mesh on
  15K held-out scans (FLAME 0.97).
- **Images (single, multi-view, video):** minimise w_lan E_lan + w_prior E_prior + w_anat E_anat + w_temp E_temp.
  - E_lan: ~600 dense 2D landmarks from Google's detector (Chandran et al. 2023 / 2024), including lid, lip, teeth
    and tongue points.
  - E_prior: L2 on identity AND expression.
  - E_anat: skin / eyeball and skin / mouth-interior intersection penalties.
  - Unknowns: identity, expression, joint rotations, translation, camera intrinsics.
  - Multi-view: one identity shared across views, expression per frame. Weighting per Wood et al. 2022.
  - Synthetic test with 7000 ground-truth landmarks: 1.68 mm.
- **The registration pipeline that built the model used much richer evidence:** inverse rendering with RGB, normals
  (multi-view stereo), semantic segmentation (eyes, ears, lips) and dense landmarks, plus per-vertex offsets.
- In short, GNM expects DENSE, feature-level evidence (contours of lids, lips, alae), not sparse points.

### 1.5 How it was built, what it doesn't capture, licence

- **Data:** ~5000 subjects, ~150K samples, 22 cameras at 6144x4096, neutral + ~30 static expressions (visemes, lip
  rolls, winks, squints, gaze, brows, cheeks, tongue).
- **The cranium is not measured:** hair hides it, so it is regressed from 200 artist-sculpted heads (report 3.2).
  Expect skull and back-of-head variation to be weak and inferred.
- **Teeth:** synthetic. **Tongue:** artist rig fitted to scans and to Medina et al.'s keypoints. **Eyes:** a
  physiological model, not scanned.
- **Limitations stated by Google:** binary gender and four broad ethnic groups.
- **Licence:** Apache 2.0, code and model, commercial use allowed. Unchanged at HEAD.

### 1.6 HEAD vs our pin (git diff 915aa35..a67464a, 42 files)

Packaging only:
- The model npz was REMOVED from git (ca7ed5b, 2026-09-29). `GNM.from_remote` now fetches from Hugging Face
  `google/gnm-3` or Kaggle; `from_custom_file` loads a local npz. Anonymous HF access returned 401 today.
- Testing mixins, loader refactors, Mitsuba renderer bumps.
- No model, landmark, fitting or sampler change. Still v3.0 with the same component counts.

Keep the pin: our assets.json URLs point at the pinned commit, which still serves the npz.

## 2. How we use it (map; file:line in this worktree)

**Loading and coefficients**
- Loader: base._gnm_data (base.py:1240-1255) keeps template, identity basis, expression basis, joints, joint identity
  basis, quads, names, the lm68 rows, skin / eye / groups.
- Never read: skinning_weights, joint_regressor, correctives, semantic sampler.
- Coefficients are used raw as N(0, 1). That is correct; there are no scaling bugs (base.py:1930; humanfit_map.py:8-10).

**Identity components**
- headfit / humanfit / faceatlas / faceext / humanfit_map / joint*.py use comps 0-119. Seeds draw all 170
  (base.py:1258-1266).
- The graft path keeps a seed's random 120-169 under fitted 0-119 (base.py:1914). One-mesh zeroes them.
- Eye and teeth comps: never.

**Priors and walls**

| fit | prior / walls |
|---|---|
| humanfit_map | lambda 1 (norm(c)^2) |
| joint2 | within-sex Mahalanobis about sex * delta / 2 (joint2.py:363-364; faceatlas.py:176-190); component wall CAP 2.5 at weight 25 (joint2.py:35, 365-368); readout wall ACAP 2.5 within-sex sd on every R2 > 0.9 atlas attribute (joint2.py:56, 380-383); one-sided SEXDIR walls for women |
| headfit | ridge 1.5e-6 with an active-set clip at +-2.6 |
| humanfit | clip 2.6 |
| fit_identity | +-2.5 |

**Evidence**
- MediaPipe 478 read through mp478_gnm.npz (36 calibration heads), with CUT 2.5 / FLOOR 0.7 / INFLATE 2.0
  (humanfit_map.py:33-35).
- Clicks at CLICK_SIGMAS; the 68 at 4 mm without an image.
- joint2 adds checklist ITEMS (eye_opening, canthal_tilt, brow_eye, lips; joint2.py:45), traced outlines and the
  true profile's contour.
- No per-picture expression ("Not used, on purpose", humanfit_map.py:18; refstudy.md:25).

**Expression basis**
- **pose_expression** (base.py:1296-1349): lid_upper / lid_lower / smile / brows as LANDMARK moves (4 lid points per
  eye), a ridge over 60 lower-face + 40 + 40 eye comps, lambda 1e-6 (= ~1 mm landmark noise with a unit prior).
  Applied after identity, sliders and warp.
- **mouth_gap:** 40 comps.
- **faceshapes ARKit** (faceshapes.py:1085-1099): hand-written landmark-move tables, ridge 1e-6, all 150 / 200 comps.
  jawOpen is landmarks rotated 14 deg (GNM_OPEN, :960). Coefficients are in range (scripts/g18_arkit.py: max |c| 0.2-4.0,
  mostly < 2.6).
- Tongue and pupil: never used.

**Eyes, teeth, joints and mesh**
- Eyes: our own spheres, 0.96x GNM's eye, pushed back to clear the rims by 0.8 mm (base.py:531-532, 2176-2191).
- Teeth and tongue: our kit.
- Joints: eye positions only. No GNM LBS (Mixamo rig: rig.py).
- Mesh: one-mesh keeps GNM's skin topology and UVs above ring 13 (onemesh.py). The graft path Catmull-Clarks it and
  makes it an implicit surface (base.py:439-440, 2171).

**Our additions over GNM**

| addition | what it is |
|---|---|
| lidfold | SDF fold modifier: platform / crease / overhang; overhang partly through faceatlas |
| faceslide | hand mm fields |
| faceext | MakeHuman targets minus GNM's cheap directions |
| faceatlas | coupled sliders = GNM conditional means. A correct use of GNM |
| delta_sex | from ANSUR / NIOSH |
| headage, humanmacro | |
| headfit | MakeHuman age / sex / weight fields + RBF warp |

## 3. Capability vs use

| GNM capability | our use | verdict | evidence |
|---|---|---|---|
| identity, 170 sd-scaled comps, N(0,I) | 120 comps, raw N(0,1) | as intended (scale right), truncated (low cost) | 1.2; base.py:1258 |
| identity prior = L2 | L2 / Mahalanobis + walls at 2.5 + readout walls + a sex mean | differently: walls clip distinctive faces, sex mean not GNM's | joint2.py:35-56, 363-383; ga_03 |
| per-picture expression in the fit | not fitted (identity only; lids posed later in mm) | unused | humanfit_map.py:18; joint2.py |
| eye-region expression (lid state, fold) | pose lid_upper / lower ridge, ARKit eyes | used differently (after the fit, on our eyeball) | base.py:1296-1349 |
| lower-face expression (jaw, lips) | pose / mouth_gap / ARKit via landmark tables | used differently (targets ours), technically sound | faceshapes.py:1085-1099; g18 |
| habitual carriage | faces5 design 8 puts it in the EXPRESSION basis | misreads GNM: in GNM it is identity | report 3.1 / 3.5 |
| two-sphere eyeballs fitted to the lids | replaced by back-set spheres | reimplemented; shifts the lid / iris relation by ~2.3 mm on Tess | 4.1 |
| teeth (80 comps), tongue (32), pupil | kit interior | unused (fine for likeness) | |
| neck / head / eye LBS | cameras + Mixamo rig | bypassed (justified) | |
| semantic sampler, sex / ethnicity | own ANSUR axis (cos 0.10 to GNM's) | reimplemented, and not GNM's axis | ga_03 |
| semantic sampler, 20 expression classes | own ARKit tables | reimplemented | |
| head_sparse_68 | used, plus MediaPipe calibrated to GNM | as intended | |
| ~600 dense landmarks | not released; MediaPipe at a median 3.6 mm sigma | weak substitute | 4.4 |
| upper-lid fold / crease | lidfold SDF modifier | reimplemented a capability GNM has | ga_01 / ga_02 |
| nose shape variation | MakeHuman extensions, hand nose widths | reimplemented; GNM reaches real noses to ~0.6 mm | 4.2 |
| lower-lip pad | MakeHuman volume / middle / width extensions | GNM has the direction (prior sd 1.46 mm) | 4.3; ga_04 |
| conditional-mean sliders | faceatlas coupled mode | as intended (good) | faceatlas.py:193 |
| pose correctives | n/a (zero in v3.0) | n/a | |

## 4. Per region: capability, evidence, fitting method, pipeline

**Shared measurements**
- **Synthetic** (GNM truths, scripts/g7_synth.py, 40 faces): our evidence returns |c| 3.6 (truth 13.0) and 1.9 mm face
  rms. Dense 600 points at 1 mm gives 9.7 and 0.63 mm; 7000 at 0.5 mm gives 12.2 and 0.16 mm.
- **Real variation** (ICT-FaceKit identity modes carried onto GNM by faces4 M1, around ICT's neutral;
  scripts/g22_ict_split.py, 30 faces): mm rms by region (nose / lips / orbits / face).

| fit | |c| | nose | lips | orbits | face |
|---|---|---|---|---|---|
| CAPABILITY (GNM fitted to every face vertex at 0.3 mm) | 34 | 0.55 | 0.68 | 0.65 | 0.62 |
| CAPABILITY (same at 1 mm) | 19.7 | 0.59 | 0.72 | 0.70 | 0.67 |
| OURS (MediaPipe table + profile clicks) | 4.6 | 1.29 | 1.61 | 1.58 | 2.17 |
| OURS + PROFILE contour | 8.1 | 1.25 | 1.48 | 1.53 | 1.98 |
| OURS + feature CONTOURS (lid margins, lip borders, alar rims, brows at 0.5 mm) | 15.3 | 1.22 | 1.27 | 1.19 | 1.78 |
| DENSE 600 at 1 mm, 3 views | 14.4 | 0.81 | 0.98 | 1.02 | 0.89 |

The ICT neutral itself costs |c| 19 under GNM, so ICT faces are somewhat atypical for GNM. faces5 notes some of
ICT's fine variance may be scan noise. Simulated noise is sigma / 2: for OURS that is the calibrated scatter without
INFLATE.

**Evidence power per measure** (scripts/g17_evidence_power.py). Each cell is the share of the population's variance
the evidence pins, with the posterior sd in brackets.

| measure (prior sd) | OURS | OURS no INFLATE | + profile contour | + feature contours | dense 600 |
|---|---|---|---|---|---|
| fissure height (0.98 mm) | 52% | 74% | 57% | 98% | 91% |
| canthal tilt (0.94) | 72% | 85% | 77% | 99% | 94% |
| brow over eye (2.68) | 83% | 93% | 87% | 99% | 99% |
| alar width (4.08) | 77% (1.97 mm) | 88% | 85% | 97% | 98% |
| tip projection (2.55) | 81% | 86% | 96% | 98% | 96% |
| tip width (1.76) | 53% | 71% | 70% | 92% | 93% |
| dorsum at 50% (1.01) | 37% | 53% | 91% | 93% | 90% |
| nostril show (1.10) | 57% | 70% | 73% | 93% | 92% |
| upper / lower vermilion (1.24 / 1.35) | 79% / 78% | 88% / 89% | 95% / 94% | 98% / 99% | 97% / 96% |
| cupid's bow depth (0.39) | 54% | 64% | 77% | 87% | 85% |
| lip projection (2.47 / 3.01) | 84% / 82% | 89% / 87% | 98% / 98% | 99% | 97% |
| face width (9.19) | 57% | 71% | 78% | 89% | 97% |
| chin projection (3.99) | 58% | 73% | 99% | 99% | 99% |
| effective directions determined | 19 | 32 | 38 | 74 | 94 |

Changing a measure by t at fixed evidence costs (t / posterior sd)^2 (posterior Mahalanobis). So with OURS, alar
width can move about 2 mm and the dorsum about 0.8 mm "for free": the fit does not know them.

### 4.1 Eyes, including the crease

**Capability: yes.**
- GNM faces have folds as configurations: a pretarsal platform recessed under preseptal skin.
  - Random faces from N(0, I) give local valley depth p50 0.23 mm, p90 0.58, and 17% have > 0.5 mm, at heights
    2.4-9.4 mm (scripts/crease2.py, g9_profiles.py).
  - Eye expression comps form and deepen it: comp 000 at +3 gives 0.71 mm with a 35 deg turn (template 0.15).
- **Tess, driven as intended** (scripts/g11_crease_fit.py): one Gauss-Newton over identity (170) + 20 symmetric eye
  comps. The prior is the Laplace approximation of her existing fit, H = I + our evidence's information at her
  views. Two pieces of evidence were added:
  - The lid margins against the iris from her photo: MediaPipe, upper 0.666 r, lower 0.88 r.
  - Her crease line height from read_lid (TPS 4.95-5.15 mm at an 11.7 mm iris = 0.86 r = 4.5 mm in GNM's iris
    units), plus "a line is there" (local depth >= 0.7 or 1.0 mm).

  | | |dc| | evidence chi2 change | crease depth / height | lids (upper / lower, iris radii) | |e| |
  |---|---|---|---|---|---|
  | fit A | 0.91 | 0.27 | 0.74 mm at 4.46 mm, 37 deg turn | 0.662 / 0.886 | 0.98 |
  | fit B | 1.52 | 0.83 | 1.01 mm at 4.1 mm, 51 deg | | 1.1 |

  |c| goes 5.69 -> 5.86. Garrett with eyedetail's 3.0 mm and eyesolve's lid offsets: |dc| 1.09, chi2 0.26,
  0.77 mm at 2.9 mm.
- **Renders:** ga_01 (raw GNM clay) and ga_02 (the SAME identities through our one mesh, meshing and server.look).
  - The fold reads as a fold: a pale platform under a soft line.
  - It is softer than the photo's crease line and softer than lidfold's carved double line.
  - What's left is the sub-mm groove and the line's shading (skin, AO, lashes), which GNM's ~1 mm rows can't hold.

**Is the crease "not in the identity" (atlas R2 0.13)?** The crease is a deterministic function of the identity: it
is read off the mesh. I get the same linear R2 (height 0.17; local depths 0.22-0.59 over 1500 faces,
scripts/g21_crease_r2.py), so the reading is reproducible. But it means "not LINEAR": no coupled slider can carry
it. It does not mean "noise to the identity". It needs a non-linear evidence term in the solve, which is cheap
because GNM is linear and the reader runs in ms on the raw mesh. It also depends on expression (lid state).

**Evidence: the gap.**
- Our fits see the fissure at 52% and nothing of the crease. The crease is only judged (likeness item
  upper_lid_show is "judge") or measured in a separate later stage against a different eyeball.
- MediaPipe's eye contours (~16 points per eye) and its iris points are the right evidence for lid state, at sub-mm
  in a front photo.

**Fitting method: the gap.**
- Lids are posed after the identity with mm offsets (pose_expression), on our eyeball.
- The eyeball shift explains why the two pipelines disagree about her lids (finding 5).
- No eye-region expression is solved with the identity.

**Pipeline: not the cause.** GNM's fold survives one mesh, meshing and the look renderer (ga_02 column 3). The
eyeball replacement (finding 5) is the pipeline issue that matters here.

### 4.2 Nose

**Capability: yes, to ~0.6 mm.**
- On real ICT variation GNM reaches the nose region at 0.55-0.59 mm rms.
- Per measure (error mm / correlation with truth): alar width 0.53 / 0.98, tip projection 0.67 / 0.95, dorsum
  0.36 / 0.94, tip width 0.75 / 0.87, nostril show 0.63 / 0.83 (the weakest).
- GNM's own spreads are of real-population size: alar width sd 4.1 mm, tip projection 2.6, nose length 3.4.

**The "locality wall" is an artefact of the test** (scripts/g10_locality.py, 12 raw MakeHuman nose targets carried by
faceext.carry). Each cell is |dc| (made share).

| target | rest FREE | rest HELD at 0 | rest held only where our evidence looks |
|---|---|---|---|
| at 0.05 mm | 25-67 (0.95-1.00) | 1.2-8.4 (0.20-0.87) | ~ FREE |
| at 0.5 mm | 5.9-17 (0.67-0.99) | | |
| at 1 mm | 2.9-11 (0.55-0.98) | | |

- MakeHuman targets are artists' isolated morphs. Matching one exactly is expensive even with the face free, so the
  cost is precision on an off-distribution shape, not locality.
- GNM attaches 1.5-13 mm rms of whole-face change to them (at 1 mm precision): that is how its population makes such
  noses.
- Real noses (ICT) come in whole-face configurations, and GNM makes them at ~0.6 mm.

**Evidence: the gap.**
- With OURS, alar width is 77% pinned (posterior sd 1.97 mm; the alar MediaPipe points are CUT), the dorsum 37%
  (r 0.19 on ICT truths), tip width 53%, nostril show 57%.
- The true profile contour fixes the dorsum and tip projection (91-96%, ICT dorsum error 1.03 -> 0.33 mm).
  Front contours fix alar and tip width (97% / 92%).
- The checklist has the profile items (8 nose contours) but joint2 solves only 7 ITEMS and none of them is nose.

**Prior: not the gap.** Posterior costs of plausible nose changes at our evidence are ~1 per posterior sd (2 mm alar,
0.8 mm dorsum).

### 4.3 Lips

**Capability: yes.**
- On ICT, lips 0.68-0.72 mm rms; vermilions 0.6 mm (r 0.84-0.92); lower-lip pad 0.80-0.87 mm (r 0.80).
- GNM's lower-lip "pad to corners" spread is 1.46 mm (prior sd), and the lower border's lateral extent 2.33 mm. The
  notes' "lower-lip width sd 0.022, hardly varies" is a ratio of a different definition: 0.022 x ~50 mm = 1.1 mm.
- Tess's central pad, +0.75 / +1.5 mm, conditional on all our evidence (scripts/g20_lips.py, ga_04): |dc| 0.75 / 1.5,
  posterior cost 0.9 / 3.5. Visible but subtle in clay.

**Evidence:**
- Vermilion heights are well seen (78-79%, 94-95% with the profile). The pad (54% for bow depth; pad r 0.70) and
  cushion depth need the photometric reader faces2 built (lipshade).
- faces2 / 3 drove that reader with 2-3 levers (one coupled slider + MakeHuman extensions). "Nothing makes the middle
  darker with the sides lighter" is a statement about those levers, not about GNM's space.

**Fitting:** lower-face expression is not modelled in the identity fit. A slight smile or press in a reference goes
into identity or into dropped items.

### 4.4 What our checklist and fits can see vs what GNM needs

- **likeness.json:** 85 items, mostly 2D distances, ratios and tilts of MediaPipe points, 8 nose and 2 lip profile
  contours, 7 shading "planes" items, and judge-only items. It does NOT measure:
  - crease height or platform show (only "judge")
  - lid margin against the limbus / iris (scleral show)
  - eye prominence (cornea apex vs the orbital rim in profile)
  - alar rim contour (the alar points are cut from the fit)
  - nostril / columella in front
  - philtrum depth, lower-lip pad depth (lipshade is outside the checklist)
  - per-picture expression (MediaPipe blendshapes are used only as flags)
- **joint2 solves 7 of the items.** The rest are read after.
- **What GNM needs to be driven well** (Google's own fitting and registration evidence, scaled to what we can read):
  - feature CONTOURS at <= 1 mm: lid margins + iris, crease line, brows, alar rims + nostrils, lip borders, the true
    profile (dorsum, tip, columella, lips, chin), jaw / cheek outlines with a known lens
  - per-picture expression unknowns
  - PHOTOMETRIC terms for depth shape (lip pad, fold shadow, dorsum) through our renderer
  - Google's ~600-landmark detector would replace most of the contour readers if it is released (report section 5
    promises it).

## 5. Mistakes and misreadings, ranked by impact on likeness and quality

1. **"GNM can't make X" from a MAP of weak evidence.** The posterior mode is the mean in the ~150 directions our
   evidence doesn't see (sections 4, 1.2).
   - Tess at |c| 5.7 and Garrett at 4.5 are predicted by the evidence alone.
   - The local layer (lidfold fold / overhang / height, MakeHuman nose / mouth extensions, hand nose / lip sliders)
     was built to add detail the solve never asked GNM for.
   - refstudy's "character has to come from evidence" (refstudy.md, round 2) was right, and then was not acted on for
     the features that matter.
2. **Costs in "sd" with no scale.** |dc| of 8-15 called a wall when a person is 13 from the mean (faces5 crease 8.4 /
   14.8; M3's "3-46 sd").
   - The right cost is the posterior Mahalanobis change at fixed evidence, or chi2 against its degrees of freedom.
   - Targets were whole displacement FIELDS at 0.05 mm (groove, MakeHuman shapes) instead of the features the photo
     shows.
3. **The crease treated as identity-only, linear and absent** (lidfold.py:1-3 "GNM's lids have no fold of their own";
   gnm_atlas.md "crease ... noise to the identity"). It is non-linear, partly expression, and present (4.1).
4. **No expression in the identity solve; habitual expression framed as an expression-basis offset.** GNM puts the
   resting face in identity and wants expression per picture, with an L2 prior (report 4.2).
   - refstudy's negative result (per-picture expression 2.69 vs 2.50 mm) was with sparse, inflated MediaPipe points
     and ~90 free comps per picture.
   - With lid-margin and iris evidence, 20 eye comps were identifiable at |e| ~1 (4.1).
5. **Eyeball replacement.** It changes the lid / iris relation that the eye stage then "corrects" in the wrong
   direction on Tess (finding 5).
6. **The sex prior's mean is not GNM's sex difference** (cos 0.10; ga_03). Every within-sex fit is pulled toward a
   smaller face, not a female one. humans.py:200 already notes "wide spreads masculinise a bald head".
7. **Over-hedged evidence** (INFLATE x2, CUT at 2.5 mm drops the alar / jaw / cheek points). Correlated detector
   errors should be modelled as correlation (or by thinning redundant points), not by halving all the information.
8. **Walls at 2.5 sd** (CAP, and ACAP over the atlas's 49 attributes with R2 > 0.9) clip exactly the distinctive features likeness needs. GNM
   documents -3..+3.
9. **Smaller items:**
   - 120 of 170 comps (cheap to include all; faces4 M0b found 120-169 the most identity-laden per mm).
   - The graft path mixes seed comps 120-169 with fitted 0-119.
   - Random humans at spread 0.6.
   - ARKit shapes from our landmark tables instead of data (GNM's expression classes; ICT's ARKit-named expressions,
     already registered to GNM by faces4).

## 6. What we built that GNM already provides

| ours | GNM's own |
|---|---|
| lidfold fold / overhang / height | identity + eye-region expression, driven by crease and lid evidence |
| faceext / faceslide nose and lip shapes at photo precision | the identity, driven by contours and profile |
| delta_sex | the semantic sampler's labelled sex difference (and ethnicity conditioning) |
| hand ARKit target design | data-learned expression comps + the 20-class expression sampler |
| our eye spheres | two-sphere eyeballs fitted to the lids, identity-seated, with pupil dilation |
| teeth / tongue kit | 80-comp teeth, 32-comp tongue (not needed for likeness) |
| faceatlas coupled sliders | the CORRECT way to expose GNM as sliders; keep |

## 7. What GNM genuinely can't do (where our additions are justified)

- **Sub-mm geometry:** the crease groove itself (FWHM 0.8-1.1 mm, at the lid rows' Nyquist), fine lip lines,
  wrinkles, pores. Keep lidfold's GROOVE only (crease_depth / width, ideally as a normal / displacement detail) on the
  line GNM's fold puts there.
- **Appearance:** no albedo, skin, brows, lashes or hair (all ours).
- **Body:** a head and neck only (one mesh is justified); the cranium is inferred, not measured.
- **Identity-dependent expression:** linear deltas can intersect the eyeball or teeth on unusual identities. Our lid
  seal, mouth seal and ARKit corrections are justified, but check them against GNM's eyeball.
- **Age:** no age axis or labels are released. Age ops are justified until a data-backed direction exists.
- **Style:** outside the human space by design. Rig: neck / head / eyes only (the Mixamo rig is justified).

## 8. Recommendations: how GNM should be driven

1. **One MAP over identity (all 170) + per-picture expression** (eye regions ~20 symmetric + a few asymmetric, lower
   face ~20), with N(0, I) on both, identity shared across views. Use non-linear readers as residuals in the same
   Gauss-Newton: finite differences on the raw GNM mesh (ms per evaluation; scripts/g11_crease_fit.py is a working
   template). Readers:
   - lid margins vs iris (MediaPipe refined contours, true sigma)
   - crease line height + presence (read_lid on the photo vs the mesh crease reader)
   - alar rims and alar width (a contour reader; stop CUTting the alar points)
   - nostril show, the true profile contour (have), lip borders, lipshade (photometric)
2. **Report |c|, the evidence's effective degrees of freedom (trace(I - C)) and posterior costs with every fit.**
   Judge "can GNM do it" by the posterior Mahalanobis change at fixed evidence, never by ||dc|| against zero.
3. **Shrink lidfold to the sub-mm groove**, seated on GNM's fold line. Fold, overhang, height and platform come from
   identity + expression. Same test for the MakeHuman extensions: keep one only if a reader shows a residual after the
   evidence-driven GNM fit.
4. **Fit and pose the lids against GNM's own eyeball** (or seat our sphere at GNM's identity-moved eye centre with
   GNM's cornea bulge), then re-read Tess's lids.
5. **Replace or validate delta_sex** with the sampler-derived sex difference (class means or the LDA direction, my
   numpy decoder in scripts/cvae.py). Test Tess's read.
6. **Re-model the evidence noise** (correlated covariance or per-region thinning instead of INFLATE x2; keep the
   points CUT now at their honest sd).
7. **Relax the walls to ~3-3.5 or make them soft chi2 gates.** Use 170 comps everywhere.
8. **ARKit:** check faceshapes against GNM's expression sampler classes. Consider projecting ICT-FaceKit's
   ARKit-named expressions (on GNM since faces4 M1) onto GNM's expression basis as data-backed targets.
9. **Watch google/GNM for the dense landmarks** (promised). They are the evidence GNM was designed around.

## 9. Corrections to our notes (verified)

- **lidfold.py:1-3 and eyes.md:160, "GNM's lids have no fold of their own":** false. Folds exist as identity +
  expression configurations (4.1, ga_01).
- **gnm_atlas.md:23-25, "crease ... where it sits is noise to the identity":** it is deterministic and non-linear,
  not noise. The R2 is also stale: the live table has 0.207, the note 0.13 (and the atlas has n = 2000, not 3000).
- **gnm_atlas.md faces4 section 0 / M1, "GNM's prior is TOO TIGHT on the fine / local comps":** wrong. faces5 M3
  retracted it; Google's sampler shows comps 40-169 at sd >= 0.85.
- **faces4 / faces5 "locality wall":** a test artefact (exact isolated fields at 0.05 mm; a scale-free "sd").
  GNM reaches real noses and lips at ~0.6-0.7 mm.
- **faces5 crease verdict, "not a crease you can put on a given face at identity cost":** false when the crease's
  evidence (height, presence) and the lid state are fitted instead of lidfold's field (4.1).
- **gnm_atlas.md:27, "lower-lip width ... the model hardly varies it":** definition-dependent. The lower border's
  extent varies with sd 2.3 mm and the pad-to-corners with 1.46 mm.
- **faces2, "nothing makes the middle darker with the sides lighter":** about 2-3 levers, not GNM's space.
- **The atlas's sex axis notes:** our axis moves size and is ~orthogonal to GNM's labelled sex difference.
- **human_guide.md:17, "253 components, in sigma":** we use 120 head comps. **base.md:18, head scale 1.12:** the code
  default is 1.4 (base.py:1998).

Caveats:
- My evidence model is idealised: orthographic, the calibrated scatter only, no detector bias. Real fits are worse,
  which strengthens finding 1.
- The ICT capability numbers carry ICT's possible scan noise and its |c| 19 neutral.
- The crease reader is mine (local valley depth over +-2.5 mm on the pupil planes). Its low linear R2 matches the
  atlas's.
- The clay renders have no AO, lashes or skin, so photo crease lines read darker than any clay can.

## Artefacts (/mnt/data/hifipushie/gnmaudit; run with its venv through bin/capped, OMP / OPENBLAS 4 threads)

**Scripts** (all in scripts/):

| script | what it does |
|---|---|
| gnm.py | minimal GNM evaluator (bind, LBS) + plane slicing |
| g1_structure | components, groups, resolution, spectrum |
| cvae.py + g2_prior_scale | the semantic sampler in numpy, coefficient scale, sex difference |
| crease.py / crease2.py + g5 / g9 / g21 | crease readers, crease across the space, R2 |
| lids.py | lid margins vs iris, GNM's eye |
| g7_synth | synthetic MAP recovery per evidence set |
| evid.py + g17_evidence_power | posterior sd per measure, effective degrees of freedom |
| g10_locality (+ dump_mh.py, main venv + faces5 src) | MakeHuman nose targets under FREE / HELD / EVID |
| g11_crease_fit | identity + eye expression Gauss-Newton with crease and lid evidence; env LIDS="up,lo" |
| g12 / g13 | crease renders, sheet ga_01 |
| g14 / g15 / g16 | the same identities through our pipeline in a scratch HIFIPUSHIE_HOME (ws/), sheet ga_02 |
| g18_arkit | faceshapes' ARKit coefficient magnitudes |
| g19_sex | ga_03 |
| g20_lips | ga_04 |
| g22_ict_split | capability vs evidence on ICT variation (uses faces4 out/ict_modes.npz) |
| mp_detect.py | MediaPipe through facerefs_venv; mp_refs.json = Tess's front |

**Sheets:**
- ga_01_tess_crease_intended_fit: photo | stored identity | fits A / B, raw GNM
- ga_02_tess_crease_through_pipeline: stored with lidfold | identity only | fit B, through one mesh + look
- ga_03_sex_axis_ours_vs_gnm_sampler
- ga_04_tess_lower_lip_pad_in_gnm
