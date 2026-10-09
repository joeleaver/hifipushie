# Models that can measure a face / head from a photo: licence-verified survey

Date of checks: 2026-10-09. Purpose: commercial 3D character tool that fits Google's GNM head to reference pictures
(we already use MediaPipe Face Landmarker).

How each claim was checked (so you can re-run it): `hf.sh`, `ghl.sh`, `lic.sh` in this folder.
- "HF tag" = the `license:` tag returned by `https://huggingface.co/api/models/<id>` on the date above.
- "GH" = the repository's LICENSE file read through the GitHub API, plus the README's licence section.
- File sizes are the largest weight file in the HF repo (or HTTP Content-Length for DAViD's ONNX files).
- "unverified" = I did not read a primary source for it in this session. Not legal advice.

Verdict key: **OK** = COMMERCIAL-OK (permissive licence on code AND weights), **NC** = NON-COMMERCIAL,
**UNCLEAR** = permissive label but a real caveat (training data, dependency, use restriction, territory, missing licence).

A general caveat that applies to nearly every "OK" row: the authors put a permissive licence on weights that were
trained on mixed public datasets, some of which are research-only. That is the authors' representation; nobody
warrants it. The rows where this risk is lowest are the ones trained only on synthetic / owned data (DAViD,
MediaPipe, Ear_Landmarker v2).

---

## (a) Tables

### 1. Monocular geometry (depth, point map, normals)

| name | outputs | code licence | weights licence | data caveat | size | CPU ok? | how to load | verdict |
|---|---|---|---|---|---|---|---|---|
| **DAViD** (Microsoft, ICCV 2025) | relative depth, surface normals, soft foreground alpha; human-centric (face / upper body / full body) | MIT (`LICENSE-MIT.txt`) | MIT (README "Model License": "DAViD models and runtime code are licensed under the MIT License"; each model card says MIT) | Trained only on Microsoft's synthetic SynthHuman data (dataset itself is CDLA-2.0). Cleanest provenance in this table. | ONNX: ViT-B 449 MB each task, ViT-L 1.38 GB each task, multi-task ViT-L 1.38 GB | Yes: ONNX only, 512 x 512 input. ViT-B realistic on CPU, ViT-L slow but fine for stills | clone `microsoft/DAViD`, `onnxruntime`; files at `https://facesyntheticspubwedata.z6.web.core.windows.net/iccv-2025/models/<name>.onnx` | **OK** |
| **MoGe-2** (Microsoft) | metric point map, metric depth, normals (the `-normal` checkpoints), FOV, mask | MIT; DINOv2 part Apache-2.0 | MIT (HF tag) on `Ruicheng/moge-2-vitl`, `-vitl-normal`, `-vitb-normal`, `-vits-normal` | General scenes, mixed training sets (authors' MIT). Normal head was trained from depth-derived normals (docs/normal.md). | ViT-L 331 M params, ViT-B 104 M, ViT-S 35 M; ONNX exports `Ruicheng/moge-2-vit{l,b,s}-normal-onnx` (vitb 419 MB; no licence tag on the ONNX repos) | ViT-S / ViT-B yes (ONNX, dynamic resolution); ViT-L slow | `pip install git+https://github.com/microsoft/MoGe.git`; `from moge.model.v2 import MoGeModel` | **OK** |
| **MoGe-3** (Microsoft, released 2026-08-18) | as MoGe-2 with finer point-map detail (sparse volumetric refinement) | MIT | MIT (HF tag) `Ruicheng/moge-3-vitl` (1.48 GB), `Ruicheng/moge-3-vitg` (5.0 GB) | as MoGe-2 | 370 M / 1.25 B params | No: needs FlexGEMM (MIT) which builds on Triton; GPU, no macOS | `from moge.model.v3 import MoGeModel` | **OK** |
| MoGe-1 | affine-invariant point map, depth, FOV | MIT | MIT `Ruicheng/moge-vitl` | as above | 314 M | slow | `from moge.model.v1 import MoGeModel` | **OK** |
| **Depth Anything V2 Small** | relative (affine-invariant inverse) depth | Apache-2.0 | Apache-2.0 (HF tag) `depth-anything/Depth-Anything-V2-Small(-hf)` | Trained on synthetic + pseudo-labelled real images | 99 MB (ONNX `onnx-community/depth-anything-v2-small`, Apache tag) | Yes | `transformers` pipeline `depth-estimation` | **OK** |
| Depth Anything V2 Base / Large | same | Apache-2.0 | **CC-BY-NC-4.0** (HF tag) | | 390 MB / 1.3 GB | | | **NC** |
| Depth Anything V2 Giant | same | Apache-2.0 | unverified (not checked) | | | | | unverified |
| **Depth Anything 3**: DA3-SMALL, DA3-BASE | multi-view depth + camera pose (any number of views, 1 works) | Apache-2.0 (`ByteDance-Seed/Depth-Anything-3`) | Apache-2.0 (HF tag + README table) | | 0.08 B / 0.12 B params | Small / Base plausible on CPU | `from depth_anything_3.api import DepthAnything3` | **OK** |
| **DA3MONO-LARGE**, **DA3METRIC-LARGE** | monocular relative depth / metric depth (+ sky mask) | Apache-2.0 | Apache-2.0 (HF tag + README table) | | 0.35 B | slow | same API | **OK** |
| DA3-LARGE, DA3-GIANT, DA3NESTED-GIANT-LARGE (and the -1.1 versions) | multi-view depth, pose, (GS) | Apache-2.0 | **CC-BY-NC-4.0** (HF tag + README table) | | 0.35-1.4 B | | | **NC** |
| Apple Depth Pro | metric depth, focal length | Apple sample-code licence (GH LICENSE) | `apple-amlr` on HF: "exclusively for Research Purposes ... does not include any commercial exploitation, product development or use in any commercial product or service" | README says weights are under the repo LICENSE, but the LICENSE file shipped with the weights on HF (`apple/DepthPro/LICENSE`) is the Apple ML Research Model licence | 1.9 GB | no | `apple/DepthPro-hf` | **NC** |
| Metric3D v2 | metric depth + normals | BSD-2-Clause | no licence tag on `JUGGHM/Metric3D`; README: "For further commercial inquiries, please contact" the authors; an ONNX re-export `onnx-community/metric3d-vit-small` is tagged CC0 by a third party | Weights licence never stated by the authors | ViT-S 150 MB, ViT-L 1.65 GB, ViT-g 5.5 GB | ViT-S ONNX yes | `torch.hub.load('yvanyin/metric3d', ...)` | **UNCLEAR** |
| UniDepth v2 | metric depth, camera | CC-BY-NC-4.0 (GH LICENSE) | none stated on HF; README: "released under Creatives Common BY-NC 4.0" | | 137 MB - 1.4 GB | | `lpiccinelli/unidepth-v2-vitl14` | **NC** |
| UniK3D | metric 3D, any camera | LICENSE file is CC-BY-NC-**SA**-4.0 (README says BY-NC 4.0) | same | | 1.4 GB | | `lpiccinelli/unik3d-vitl` | **NC** |
| **Marigold v1-1** (depth, normals, IID) | affine-invariant depth; normals "3-dimensional unit vectors in the screen space camera"; intrinsic images | Apache-2.0 (`prs-eth/Marigold`) | **CreativeML Open RAIL++-M** (HF tag `openrail++`) on `prs-eth/marigold-depth-v1-1`, `marigold-normals-v1-1`, `marigold-iid-*-v1-1`; the LCM variants (`marigold-depth-lcm-v1-0`, `marigold-normals-lcm-v0-1`) are tagged Apache-2.0 | RAIL++ permits commercial use but carries use restrictions that must be passed on; fine-tuned from Stable Diffusion 2 on synthetic data | ~1.7 GB fp16 UNet + 1.4 GB text encoder + VAE | No (diffusion; GPU) | `diffusers.MarigoldNormalsPipeline.from_pretrained("prs-eth/marigold-normals-v1-1")` | **OK** (with RAIL++ use restrictions) |
| Lotus (v1 / v2) | depth (disparity), normals | Apache-2.0 | Apache-2.0 (HF tag) `jingheya/lotus-depth-g-v2-1-disparity`, `jingheya/lotus-normal-g-v1-1` | Fine-tune of SD 2 (whose own weights are OpenRAIL++): authors' Apache label on a derivative of RAIL-licensed weights | 3.5 GB UNet | No | Lotus repo scripts | **UNCLEAR** (label says Apache; base model is RAIL++) |
| StableNormal / YOSO normal | normals (sharp, stable) | Apache-2.0 (`Stable-X/StableNormal`) | Apache-2.0 (HF tag) `Stable-X/stable-normal-v0-1`, `Stable-X/yoso-normal-v1-8-1` | Same SD-derivative note as Lotus | 1.7 GB fp16 UNet + 0.7 GB controlnet | No | `torch.hub.load("Stable-X/StableNormal", "StableNormal")` | **UNCLEAR** (as Lotus); used by Hi3DGen |
| DSINE | normals | Imperial College licence: "solely for non-commercial, internal or academic research purposes" | same | | | | | **NC** |
| GeoWizard | depth + normals | **no LICENSE file** in repo | no licence on HF `lemonaddie/Geowizard` | no licence = no rights granted | 3.5 GB | No | | **UNCLEAR** (treat as not usable) |
| Sapiens (v1, Meta 2024) | human depth, normals, 308-keypoint pose, 28-class seg | CC-BY-NC-4.0 (GH LICENSE; "Sapiens License" was replaced) | CC-BY-NC-4.0 (HF tag, all `facebook/sapiens-*`) | | 0.3 B: 1.3 GB; 1 B: 4.7 GB | No | | **NC** |
| **Sapiens2** (Meta, ICLR 2026; released 2026-04-24) | normals ("unit vectors in the camera coordinate frame"), pointmap, 308 keypoints (274 on the face, incl. ~24 per ear), 29-class seg, matting | "Sapiens2 License" (GH `LICENSE.md`) | same (HF `license:other`, `license_name: sapiens2-license`, not gated) | Licence has **no non-commercial clause** (grant: "use, reproduce, distribute, copy, create derivative works"), BUT section 1.b.vi forbids use "(ii) for biometric processing", "(i) for purposes of surveillance", inferring "health, demographic, or other sensitive personal ... information"; Meta may audit and demand deletion (1.c). Measuring a face from a photo to build a likeness is arguably "biometric processing": get a legal read before using. | 0.4 B: 1.7-2.1 GB; 0.8 B; 1 B; 5 B | No (1024 x 768 ViT, GPU) | clone `facebookresearch/sapiens2`; `facebook/sapiens2-{normal,pointmap,pose,seg}-{0.4b,0.8b,1b,5b}` | **UNCLEAR** (commercial not forbidden; "biometric processing" is) |
| **VGGT-1B-Commercial** (Meta) | multi-view (1..N) point maps, depth, cameras, tracks | "VGGT License v1" (2025-07-29): README "permit commercial use (excluding military applications)" | `facebook/VGGT-1B-Commercial`: `license_name: vggt-aup-license`, **gated: manual approval**. README: "only the newly released checkpoint VGGT-1B-Commercial is licensed for commercial usage" | Acceptable-use policy (no military etc.) | 5.0 GB | No | `VGGT.from_pretrained("facebook/VGGT-1B-Commercial")` after access is granted | **OK** (gated, AUP) |
| VGGT-1B (original) | same | VGGT License | **CC-BY-NC-4.0** (HF tag) | | 5.0 GB | | | **NC** |
| DUSt3R / MASt3R (Naver) | pairwise point maps, matching | CC-BY-NC-**SA**-4.0 | same (no HF tag; LICENSE in repo covers checkpoints) | | 2.3-2.8 GB | | | **NC** |
| **MapAnything (apache)** (Meta) | multi-view metric point maps, depth, rays, intrinsics, poses; accepts optional known cameras / depth | Apache-2.0 | `facebook/map-anything-apache`: Apache-2.0 (HF tag); `facebook/map-anything`: CC-BY-NC-4.0 | README lists both; the Apache model is trained on the commercially usable subset | 4.9 GB | No | `pip install` from `facebookresearch/map-anything`; `MapAnything.from_pretrained("facebook/map-anything-apache")` | **OK** |
| Pi3 / π³ | multi-view point maps | BSD-3-Clause | README: weights **CC BY-NC 4.0, "Strictly Non-Commercial"** (HF tag on `yyfz233/Pi3` says bsd-2-clause: the README is the authors' statement, follow it) | | 3.8 GB | | | **NC** |
| Fast3R (Meta) | multi-view point maps | "FAIR Noncommercial Research License" (repo archived) | same | | | | | **NC** |

Face-specific multi-view point-map models with commercially usable weights: none found.

### 2. Landmarks (frontal, profile, ears, whole body with face)

| name | outputs | code licence | weights licence | data caveat | size | CPU ok? | how to load | verdict |
|---|---|---|---|---|---|---|---|---|
| **MediaPipe Face Landmarker** (in use) | 478 3D landmarks, 52 blendshapes, transform | Apache-2.0 | Apache-2.0 per Google's model card (card PDF not re-read this session) | Google-owned data. Weak on full profile | ~4 MB | Yes | `mediapipe` | **OK** |
| **XR Blocks MediaPipe <-> GNM correspondence** | 473 pairs (MediaPipe landmark index -> GNM v3.0 vertex), a reference cloud, a 166-point "rigid" flag | Apache-2.0 (`google/xrblocks`) | n/a (a table) | Derived from `edualvarado/gnm-webcam-puppet` (Apache-2.0) | 12 KB | n/a | see section 3 | **OK** |
| **Ear_Landmarker** (shameem4), current version | 55 ear landmarks (iBUG ordering) on an ear crop | Apache-2.0 | README: "The shipped model weights are Apache-2.0 too ... trained on `data/manual` alone ... No iBUG or FFHQ data is in it" | **Disclosed judgment call**: annotation was seeded with predictions of an earlier model trained on iBUG ears, then hand-corrected; iBUG's terms reach "any portion of derived data". 1-star personal repo. The copy vendored in `shameem4/headSize-gnm/ear/EarLandmarker_web.onnx` is the OLD research-only weight. | 1.4 MB ONNX, 340 K params | Yes | `shameem4/Ear_Landmarker` `docs/EarLandmarker_web.onnx` | **UNCLEAR** leaning OK (read NOTICE section 3) |
| **BlazeEar** (shameem4) | ear bounding box detector, 128 x 128 | Apache-2.0 | Apache-2.0 (README: "replaces the earlier CC BY-NC 4.0 terms"); trained on Open Images (CC BY 2.0 photos) + a Roboflow CC BY 4.0 set | small personal repo | 0.5 MB ONNX | Yes | repo | **OK** |
| face-alignment (FAN, 1adrianb) | 68 points 2D and "3D" (2D + depth) | BSD-3-Clause | not stated separately | Trained on 300W-LP / LS3D-W, which derive from 300-W (iBUG, research only). dlib's README records iBUG's position that models trained on 300-W "can't be used in a commercial product" | ~100-200 MB | Yes | `pip install face-alignment` | **UNCLEAR** (data) |
| dlib 68-point predictor | 68 points | Boost (dlib), CC0 (dlib-models repo) | README: "The license for this dataset excludes commercial use ... the trained model therefore can't be used in a commercial product" | iBUG 300-W | 100 MB | Yes | `dlib` | **NC** |
| SPIGA | 98 / 68 points + head pose; has a MERL-RAV model (handles profile, self-occlusion labels) | BSD-3-Clause | none stated (`aprados/spiga`, no tag) | WFLW, 300W, COFW, MERL-RAV(AFLW): research datasets | 255 MB each | Yes-ish | `pip install spiga` | **UNCLEAR** (data) |
| STAR loss | 98 / 68 points | **no licence file** | none | WFLW / 300W / COFW | | | | **UNCLEAR** (no licence) |
| ORFormer | 98 points, occlusion robust | **no licence** (`ben0919/ORFormer`) | none | | | | | **UNCLEAR** (no licence) |
| OpenFace 2.x / 3.0 | landmarks, gaze, AUs | "ACADEMIC OR NON-PROFIT ORGANIZATION NONCOMMERCIAL RESEARCH USE ONLY" (both) | same | | | | | **NC** |
| InsightFace (buffalo_l: 2d106, 3d68, SCRFD...) | detection, 106 2D / 68 3D landmarks, recognition | MIT | README: "models trained with these data ... are available for non-commercial research purposes only", including auto-downloaded packs | | | Yes (ONNX) | `insightface` | **NC** |
| 3DDFA_V2 | 3DMM (BFM) params, 68 + dense landmarks, pose, depth, PNCC | MIT | not stated | Uses Basel Face Model 2009 (research-only licence) and 300W-LP | small, ONNX | Yes | repo | **UNCLEAR** (BFM + data) |
| 3DDFA-V3 | BFM-based reconstruction + part masks | MIT | not stated | BFM 2009 | | | repo | **UNCLEAR** (BFM) |
| SynergyNet | 3DMM, 68 3D landmarks, pose | MIT | not stated | 300W-LP / BFM | | Yes | repo | **UNCLEAR** (BFM + data) |
| PIPNet | 68 / 98 / 29 points | MIT | not stated | 300W / WFLW / COFW / AFLW | small | Yes | repo | **UNCLEAR** (data) |
| DWPose | 133 whole-body keypoints (68 face, 1 point per ear) | Apache-2.0 | Apache-2.0 (HF tag `yzd-v/DWPose`) | Trained on COCO-WholeBody ("ONLY for research and non-commercial use", annotations CC BY-NC per its README) + UBody | 130-400 MB, ONNX | Yes | `rtmlib` (Apache-2.0) | **UNCLEAR** (data) |
| RTMPose-face (Face6, 106 pts) / RTMW (Cocktail14) | 106 face points / 133 whole body | Apache-2.0 (mmpose) | Apache-2.0 by repo; no separate weight terms | Face6 mixes COCO-WholeBody-Face, WFLW, 300W, COFW, Halpe, 300VW, LaPa (LaPa: "non-commercial purposes") | 20-230 MB ONNX | Yes | `rtmlib` | **UNCLEAR** (data) |
| Sapiens v1 pose | 308 keypoints | CC-BY-NC-4.0 | CC-BY-NC-4.0 | | 4.7 GB | No | | **NC** |
| **Sapiens2 pose** | 308 keypoints: 274 face incl. named ear points (tragus top / bottom / protruding, antitragus, helix x 8, antihelix x 5, crus of helix, concha, lobe tip and attachment, per side) | Sapiens2 License | Sapiens2 License | see Sapiens2 above ("biometric processing") | 0.4 B: 1.7 GB | No | `facebook/sapiens2-pose-0.4b` + DETR detector | **UNCLEAR** |
| YOLO pose / YOLO-face (Ultralytics) | boxes, 5 or 17 keypoints | **AGPL-3.0** (or paid Enterprise licence) | AGPL-3.0 | | small | Yes | `ultralytics` | **NC** unless you buy the licence or open-source the product |
| Microsoft dense landmarks (703 points) | dense face landmarks | no public release (project page has paper + video only) | - | | | | | not available |
| Menpo 39-point profile models | profile landmarks | no maintained open model with a clear licence found | - | Menpo 2D benchmark data is iBUG research-only | | | | unverified / not found |

Profile and ears, summary: the only profile-capable, ear-detailed landmark model with a known licence is Sapiens2 pose
(UNCLEAR). For ears alone, BlazeEar + Ear_Landmarker is the permissively labelled option. Otherwise use dense geometry
(DAViD / MoGe normals + depth) on the profile photo and fit the GNM silhouette, which needs no landmark model.

### 3. MediaPipe <-> GNM correspondence (asked specifically)

- **Yes, a table exists**, but not in Google's GNM repo. It is in Google's XR Blocks:
  `https://github.com/google/xrblocks/blob/main/samples/avatar_lab/gnm/FaceCorrespondence.js`
  (raw: `https://raw.githubusercontent.com/google/xrblocks/main/samples/avatar_lab/gnm/FaceCorrespondence.js`).
  Apache-2.0. Header: "MediaPipe FaceLandmarker <-> GNM vertex mapping. GENERATED by tools/export_face_correspondence.py",
  "derived against the same GNM 3.0 head". `COUNT = 473`. One base64 blob `PACKED`:
  `reference` float32 x 473 x 3 at byte 0 (where the landmarker puts each point on a neutral GNM face; fit
  displacements from this cloud, not from template vertices, to cancel MediaPipe's own depth bias), `landmarks`
  uint16 x 473 at byte 5676 (MediaPipe index), `vertices` uint16 x 473 at byte 6622 (GNM vertex index), `rigid`
  uint8 x 473 at byte 7568 (166 skull-fixed points; solve identity on those only).
- Upstream of it: `https://github.com/edualvarado/gnm-webcam-puppet` (Apache-2.0),
  `webcam_puppet/assets/correspondence.npz` and `webcam_puppet/correspondence.py`.
- `https://github.com/google/GNM` (Apache-2.0) itself ships only `gnm/shape/data/landmarks/head_sparse_68.txt`
  (the 68-point set we already use) and `gnm/shape/gnm_landmarks.py`. No MediaPipe table there.
- `https://github.com/shameem4/headSize-gnm` (Apache-2.0, NOTICE lists third parties): a browser demo that fits GNM
  to MediaPipe through that table; `experiments/fetch_data.py` decodes it (code below), `experiments/export_web.py`
  shows the fit data layout. Its `ear/EarLandmarker_web.onnx` is marked research-only in `ear/LICENSE.md`.
- Caveat for us: vertex indices are GNM v3.0 template indices (`gnm/shape/data/versions/v3_0/gnm_head.npz`); check
  they match the GNM commit hifipushie pins (915aa35, 2026-09-25) before use.

### 4. Parametric reconstructors (reference)

| name | outputs | code licence | weights / model licence | caveat | verdict |
|---|---|---|---|---|---|
| FLAME 2017 / 2019 / 2020 / 2023 | head model | MPI "non-commercial scientific research" licence | same | | **NC** |
| **FLAME 2023 Open** | head model (shape + expression + pose) | - | **CC-BY-4.0** ("Open Model License ... applies ONLY to the FLAME 2023 Open model") | Exists and is commercially usable with attribution. But almost every FLAME regressor below was trained with, and distributes, the NC FLAME versions | **OK** (the model only) |
| DECA | FLAME params + detail | MPI non-commercial | same | | **NC** |
| EMOCA v2 | FLAME params (expression) | MPI non-commercial | same | | **NC** |
| MICA | metric FLAME shape | MPI non-commercial | same | uses ArcFace (InsightFace, NC) | **NC** |
| SMIRK | FLAME params | MIT | not stated | needs FLAME (registration); trained on LRS3, MEAD, CelebA, FFHQ (research / NC data) | **UNCLEAR**, effectively NC |
| Pixel3DMM | per-pixel normals + UV, FLAME fit | CC-BY-NC-4.0 | same | | **NC** |
| SHeaP | FLAME params | CC-BY-NC-4.0 | same | | **NC** |
| TokenFace | FLAME | no public code / weights found | - | | unverified |
| Deep3DFaceRecon_pytorch | BFM params | MIT | not stated | Basel Face Model 2009 (research) + Expression basis (FaceWarehouse) | **UNCLEAR**, effectively NC |
| HRN | BFM + detail | Apache-2.0 | not stated | BFM | **UNCLEAR**, effectively NC |
| FaceVerse | own 3DMM | BSD-2-Clause | model download needs a request; terms not read | | unverified |
| AlbedoMM | albedo model | no licence file | - | built on BFM | **UNCLEAR** |
| ICT-FaceKit | face model (identity PCA + 53 blendshapes), light version | MIT | MIT (README: "released under the MIT license"; the "full model will be released under a different USC specific license") | No regressor ships with it | **OK** (model only) |
| MHR (Meta Momentum Human Rig) | full-body parametric model with head | Apache-2.0 | Apache-2.0 | used by SAM 3D Body | **OK** |
| **SAM 3D Body** (Meta, 2025-11) | full-body MHR mesh + keypoints from one image | SAM License | SAM License (`facebook/sam-3d-body-dinov3`, `-vith`; `license_name: sam-license`, **gated: manual**) | SAM License has no non-commercial clause (forbids ITAR / military / weapons uses, must pass the licence on). The `-dinov3` checkpoint's backbone falls under the DINOv3 licence (not read here). Head shape is coarse (a body model). | **OK** for the `vith` checkpoint (gated); dinov3 variant unverified |

No face reconstructor with a commercially clean model + weights was found. GNM itself (Apache-2.0) is the only
commercially usable detailed head prior in this list; that is why per-pixel geometry models rank above reconstructors.

### 5. Image-to-3D generators as a shape prior

| name | outputs | code licence | weights licence | caveat | size | verdict |
|---|---|---|---|---|---|---|
| TRELLIS (v1) | mesh / 3DGS / radiance field from an image | MIT | MIT (`microsoft/TRELLIS-image-large`) | Submodules with other terms: diffoctreerast (derived from Inria's diff-gaussian-rasterization, non-commercial), modified FlexiCubes (NVIDIA licence); nvdiffrast / kaolin in the pipeline | ~2.5 GB fp16 | **UNCLEAR** (dependencies) |
| **TRELLIS.2** (4B) | mesh with PBR, up to 1536^3 | MIT | MIT (`microsoft/TRELLIS.2-4B`) | README: nvdiffrast and nvdiffrec "governed by [their] own License" (NVIDIA source code licence: non-commercial research). Shape generation alone does not need the texture renderer, but check what you import | 4 x 2.6 GB | **OK** model; **UNCLEAR** if nvdiffrast / nvdiffrec are in the code path |
| **Hi3DGen / Stable3DGen** | high-detail geometry via a normal-map bridge (good on faces) | MIT (Bytedance) | MIT (`Stable-X/trellis-normal-v0-1`); normal stage `Stable-X/yoso-normal-v1-8-1` Apache-2.0 | README: "we have specifically removed its dependencies on certain NVIDIA libraries (kaolin, nvdiffrast, flexicube) to ensure this adapted version can be used commercially". Normal stage is an SD derivative (see StableNormal) | ~2.5 GB + 2.6 GB | **OK** (authors' stated intent) |
| Hunyuan3D 2.0 / 2.1 / 2mini | mesh (+ PBR texture) | Tencent Hunyuan 3D Community Licence | same (`license_name: tencent-hunyuan-community`) | "DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"; over 1 M monthly active users needs a separate licence; outputs may not be used outside the Territory or to improve other AI models | 4-7 GB | **UNCLEAR** (territory); NC in EU / UK / KR |
| SAM 3D Objects | object mesh / 3DGS from image + mask | SAM License | SAM License (gated manual) | objects, not heads | 6.7 + 4.9 GB | **OK** (gated) |
| TripoSR | mesh (LRM) | MIT | MIT (`stabilityai/TripoSR`) | low detail | 1.7 GB | **OK** |
| TripoSG | mesh (rectified flow) | MIT | MIT (`VAST-AI/TripoSG`) | | 5.8 GB | **OK** |
| InstantMesh | mesh via multi-view diffusion | Apache-2.0 | Apache-2.0 (`TencentARC/InstantMesh`) | uses Zero123++ multi-view model (own licence, not read); nvdiffrast | 1.5 GB + 1.7 GB | **UNCLEAR** (dependencies) |
| Stable Fast 3D, SPAR3D | mesh | Stability AI Community Licence | same (gated auto) | Free commercial use only under US $1 M annual revenue, registration required | 4 / 7.3 GB | **UNCLEAR** (revenue cap) |
| Direct3D-S2 | high-res mesh | MIT | MIT (`wushuang98/Direct3D-S2`) | | 1.1-1.5 GB per stage | **OK** |
| PartCrafter | part-aware meshes | MIT | MIT (`wgsxm/PartCrafter`) | | 2.9 GB | **OK** |
| CraftsMan3D | mesh | repo path not resolved | unverified | | | unverified |
| LAM (Alibaba) | animatable Gaussian head from one image | Apache-2.0 | no licence tag on `3DAIGC/LAM-20K` | FLAME-based; trained on VFHQ + NeRSemble (research data) | 2.4 GB | **UNCLEAR**, effectively NC |
| GAGAvatar | Gaussian head avatar | MIT | no licence tag | FLAME + VFHQ | 0.75 GB | **UNCLEAR**, effectively NC |
| FaceLift (Adobe) | 3DGS head from one face image | Apache-2.0 | **Adobe Research License**: "noncommercial research purposes only" | | | **NC** |
| Pippo (Meta) | multi-view human generation | CC-BY-NC-4.0 | same | | | **NC** |
| Arc2Avatar, HeadGAP | head avatars | not verified | not verified | | | unverified |

### 6. Parsing / segmentation

| name | outputs | code licence | weights licence | data caveat | size | CPU ok? | how to load | verdict |
|---|---|---|---|---|---|---|---|---|
| **MediaPipe Image Segmenter, SelfieMulticlass 256** | 6 classes: background, hair, body-skin, face-skin, clothes, others | Apache-2.0 | Apache-2.0 per Google's model card (not re-read this session) | Google data | ~16 MB | Yes | `mediapipe` tasks, `selfie_multiclass_256x256.tflite` | **OK** |
| MediaPipe hair segmenter | hair mask | Apache-2.0 | Apache-2.0 (same note) | | small | Yes | `mediapipe` | **OK** |
| **DAViD soft foreground** | human alpha matte incl. hair strands | MIT | MIT | synthetic | 449 MB / 1.38 GB ONNX | Yes | DAViD runtime | **OK** |
| **BiRefNet** (general, portrait, HR-matting) | foreground mask / matte | MIT | MIT (HF tag) `ZhengPeng7/BiRefNet`, `BiRefNet-portrait`, `BiRefNet_HR-matting` | Trained on DIS5K / P3M-10k etc. (some research-only); do NOT use `briaai/RMBG-2.0` (CC BY-NC) | 444-885 MB | slow | `transformers` `AutoModelForImageSegmentation(..., trust_remote_code=True)` | **OK** by label; data UNCLEAR |
| **SAM 2 / 2.1** | promptable masks (click hair, ear, skin) | Apache-2.0 | Apache-2.0 (`facebook/sam2.1-hiera-large`) | SA-1B / SA-V | 898 MB (large) | small variants yes | `sam2` | **OK** |
| SAM 3 | text / exemplar promptable masks ("ear", "hair") | SAM License | SAM License (gated manual) | no NC clause; ITAR / military ban | 3.4 GB | No | `facebook/sam3` | **OK** (gated) |
| face-parsing.PyTorch (BiSeNet) | 19 face classes incl. hair, ears, neck | MIT | not stated | CelebAMask-HQ: non-commercial research only | 50 MB | Yes | repo | **UNCLEAR**, effectively NC |
| jonathandinu/face-parsing (SegFormer B5) | 19 classes | - | **no licence tag** on the HF repo | CelebAMask-HQ; base `nvidia/mit-b5` is NVIDIA's research licence | 340 MB, ONNX 89 MB quantized | Yes | `transformers` | **NC** in practice |
| FaRL / `facer` | face parsing (LaPa 11 cls / CelebAMask 19 cls), alignment | MIT | not stated | LAION-Face pretrain; heads trained on LaPa ("non-commercial purposes") / CelebAMask-HQ | 350 MB | Yes | `pip install pyfacer` | **UNCLEAR**, effectively NC |
| Sapiens v1 seg | 28 body parts | CC-BY-NC | CC-BY-NC | | | | | **NC** |
| Sapiens2 seg / matting | 29 parts (hair, face-neck, lips, teeth...), alpha matte | Sapiens2 License | same | see Sapiens2 | 1.7 GB+ | No | | **UNCLEAR** |
| MODNet | portrait matte | Apache-2.0 | not stated separately | | 25 MB | Yes | repo | **UNCLEAR** (unstated weights) |
| Ear segmentation | - | no dedicated model with a clear licence found; use BlazeEar box -> SAM 2 box prompt | | | | | | - |

---

## (b) Top candidates to try, commercially usable (ranked)

Ranked by how likely each is to give person-specific face depth / normals / profile shape that the 68 + 478
landmarks cannot.

1. **DAViD (MIT, synthetic data, ONNX)**: human-centric normals + relative depth + alpha, trained on face / upper-body
   / full-body renders. Best licence story and best subject match. Depth is relative (no scale), fine for a profile.
2. **MoGe-2 ViT-L normal / MoGe-3 (MIT)**: metric point map + normals + FOV in one pass; the point map gives the
   profile curve directly in camera space and the FOV helps our camera fit.
3. **Depth Anything 3 (Apache checkpoints only: DA3MONO-LARGE, DA3METRIC-LARGE, DA3-BASE / SMALL)** and
   **Depth Anything V2 Small**: fallback / cross-check depth; DA3-BASE takes several reference photos at once.
4. **XR Blocks MediaPipe <-> GNM table (Apache-2.0)**: 473 correspondences + bias-cancelling reference cloud + rigid
   flags. Not a model; it upgrades what we already run.
5. **BlazeEar + Ear_Landmarker (Apache-2.0, with a disclosed data caveat)**: 55 ear points on profile photos.
6. **MapAnything-apache (Apache-2.0)** or **VGGT-1B-Commercial (gated)**: when several photos of the same person
   exist, joint metric point maps + cameras.
7. **Marigold normals v1-1 (OpenRAIL++-M)**: diffusion normals, sharper wrinkle / nose-wing detail; GPU only.
8. **Parsing set: MediaPipe SelfieMulticlass (hair / face-skin) + SAM 2.1 (ear, hairline by box / click) +
   BiRefNet-portrait or DAViD alpha (silhouette)**: masks to keep hair out of the skull fit.

Also worth one try: **Hi3DGen (MIT)** and **TRELLIS.2 (MIT, mind nvdiffrast)** as whole-head shape priors for the
back of the skull; **SAM 3D Body (SAM License, gated)** for neck / shoulder proportions. **Sapiens2** would be the
strongest single model (face normals, pointmap, 274 face keypoints incl. ears) but its licence bans "biometric
processing": do not adopt without legal sign-off.

### Snippets (not run here: nothing was installed or downloaded, per the task)

**1. DAViD** (`pip install onnxruntime opencv-python numpy`; clone `https://github.com/microsoft/DAViD`)
```python
import sys, cv2, numpy as np
sys.path.insert(0, "DAViD/runtime")
from multi_task_estimator import MultiTaskEstimator
# https://facesyntheticspubwedata.z6.web.core.windows.net/iccv-2025/models/multi-task-model-vitl16_384.onnx  (1.38 GB)
# single-task: depth-model-vit{b,l}16_384.onnx, normal-model-vit{b,l}16_384.onnx, foreground-segmentation-model-vit{b,l}16_384.onnx
est = MultiTaskEstimator(onnx_model="multi-task-model-vitl16_384.onnx", providers=["CPUExecutionProvider"])
img = cv2.imread("face.jpg")                 # BGR uint8; runtime scales to [0,1], pads to square, resizes to 512
out = est.estimate_all_tasks(img)            # dict: "depth" (H,W), "normal" (H,W,3), "foreground" (H,W)
```
Conventions: input BGR float [0,1], 512 x 512; raw outputs depth (1,512,512), normal (1,3,512,512), foreground
(1,1,512,512); the runtime un-pads and resizes to the image. Depth is RELATIVE (affine-ambiguous;
`RelativeDepthEstimator` has an `is_inverse` flag). Normals are unit XYZ in camera space; **the axis signs are not
documented** in the README or model card: test on a known render before trusting them.

**2. MoGe-2 / MoGe-3** (`pip install git+https://github.com/microsoft/MoGe.git`, Python >= 3.10)
```python
import cv2, torch
from moge.model.v2 import MoGeModel           # v3: from moge.model.v3 import MoGeModel (needs CUDA + FlexGEMM)
model = MoGeModel.from_pretrained("Ruicheng/moge-2-vitl-normal").to("cuda").eval()   # or -vitb-normal / -vits-normal
img = cv2.cvtColor(cv2.imread("face.jpg"), cv2.COLOR_BGR2RGB)
x = torch.tensor(img / 255, dtype=torch.float32, device="cuda").permute(2, 0, 1)     # (3,H,W) RGB in [0,1]
out = model.infer(x)   # optional: fov_x=<degrees> if the camera is known (see the infer() docstring)
# out["points"] (H,W,3) METRIC point map, OpenCV camera coords (x right, y down, z forward)
# out["depth"] (H,W) metric; out["normal"] (H,W,3) in OpenCV camera coords; out["intrinsics"] (3,3) normalised; out["mask"] (H,W)
```
ONNX (CPU): `Ruicheng/moge-2-vit{s,b,l}-normal-onnx`, opset >= 14, dynamic resolution; the ONNX graph is the raw
forward pass (affine point map, normal, mask, metric scale): focal / shift recovery is post-processing in Python
(docs/onnx.md). Metric scale on a tight face crop is a guess: trust shape, re-scale by interocular distance.

**3. Depth Anything 3 (Apache checkpoints) / Depth Anything V2 Small**
```python
# clone https://github.com/ByteDance-Seed/Depth-Anything-3 ; pip install xformers "torch>=2" torchvision ; pip install -e .
import torch
from depth_anything_3.api import DepthAnything3
m = DepthAnything3.from_pretrained("depth-anything/DA3MONO-LARGE").to("cuda")   # Apache-2.0. Also DA3METRIC-LARGE, DA3-BASE, DA3-SMALL
p = m.inference(["front.jpg"])              # DA3-BASE / SMALL: pass several views of the same head
# p.depth [N,H,W] float32, p.conf [N,H,W], p.intrinsics [N,3,3], p.extrinsics [N,3,4] (OpenCV world-to-camera), p.processed_images
```
```python
from transformers import pipeline           # Apache-2.0, 99 MB, CPU fine
depth = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf")("face.jpg")["predicted_depth"]
# relative INVERSE depth (larger = nearer), affine-invariant
```
Do not load DA3-LARGE / GIANT / NESTED or DA-V2 Base / Large: CC-BY-NC.

**4. MediaPipe <-> GNM correspondence** (Apache-2.0; decoding as in headSize-gnm `experiments/fetch_data.py`)
```python
import base64, re, urllib.request, numpy as np
js = urllib.request.urlopen("https://raw.githubusercontent.com/google/xrblocks/main/samples/avatar_lab/gnm/FaceCorrespondence.js").read().decode()
b = base64.b64decode(re.search(r"PACKED =\s*'([^']+)'", js).group(1))
n = int(re.search(r"const COUNT = (\d+)", js).group(1))            # 473
ref   = np.frombuffer(b, np.float32, n * 3, 0).reshape(n, 3)       # MediaPipe's points on a neutral GNM face
lm    = np.frombuffer(b, np.uint16, n, 5676)                       # MediaPipe landmark index (0..477)
vx    = np.frombuffer(b, np.uint16, n, 6622)                       # GNM v3.0 vertex index
rigid = np.frombuffer(b, np.uint8,  n, 7568)                       # 1 = skull-fixed (166 points)
```
Pin a commit of xrblocks and vendor the decoded arrays with the Apache NOTICE; verify `vx` against our GNM commit.

**5. Ears: BlazeEar + Ear_Landmarker** (`onnxruntime`)
```python
import onnxruntime as ort
det = ort.InferenceSession("BlazeEar_web.onnx")        # github.com/shameem4/BlazeEar ; 128x128 BlazeFace-style detector, 896 anchors
lmk = ort.InferenceSession("EarLandmarker_web.onnx")   # github.com/shameem4/Ear_Landmarker docs/EarLandmarker_web.onnx (NOT the copy in headSize-gnm/ear)
# 55 points: 0-19 outer helix, 20-34 inner helix, 35-49 concha border, 50-54 superior crus. Test NME 0.029.
```
Input tensor layouts, crop factor and anchor decoding are in each repo's `inference.py` / `*_inference.js`; I did
not verify them (the ONNX contract changed between versions: read the README of the version you pin).

**6. Multi-view: MapAnything (Apache model)** (install from `https://github.com/facebookresearch/map-anything`)
```python
import torch
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")     # NOT "facebook/map-anything" (CC-BY-NC)
preds = model.infer(load_images(["front.jpg", "threeq.jpg", "profile.jpg"]), memory_efficient_inference=True, use_amp=True)
# per view: pred["pts3d"] world points (B,H,W,3) metric, pred["pts3d_cam"], pred["depth_z"], pred["intrinsics"],
# pred["camera_poses"] cam2world, OpenCV axes (+X right, +Y down, +Z forward), pred["conf"]
```
Alternative: `facebook/VGGT-1B-Commercial` (request access on HF first; `from vggt.models.vggt import VGGT`).

**7. Marigold normals** (`pip install diffusers transformers accelerate`; GPU)
```python
import torch, diffusers
pipe = diffusers.MarigoldNormalsPipeline.from_pretrained("prs-eth/marigold-normals-v1-1", variant="fp16", torch_dtype=torch.float16).to("cuda")
img = diffusers.utils.load_image("face.jpg")
n = pipe(img).prediction          # (1,H,W,3) unit vectors, screen-space camera frame; confirm axis signs with pipe.image_processor.visualize_normals
```
Licence CreativeML Open RAIL++-M: commercial use allowed; ship the use restrictions with any redistribution.

**8. Parsing**
```python
import mediapipe as mp                                    # Apache-2.0
from mediapipe.tasks.python import vision, BaseOptions
seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
    base_options=BaseOptions(model_asset_path="selfie_multiclass_256x256.tflite"), output_category_mask=True))
cat = seg.segment(mp.Image.create_from_file("face.jpg")).category_mask.numpy_view()
# 0 background, 1 hair, 2 body-skin, 3 face-skin, 4 clothes, 5 others
```
```python
from transformers import AutoModelForImageSegmentation   # MIT
birefnet = AutoModelForImageSegmentation.from_pretrained("ZhengPeng7/BiRefNet-portrait", trust_remote_code=True)
# 1024x1024 RGB, ImageNet mean/std; mask = birefnet(x)[-1].sigmoid()
```
SAM 2.1 (`facebook/sam2.1-hiera-large`, Apache-2.0): prompt with the BlazeEar box for an ear mask, or with clicks on
the hairline. DAViD's foreground output gives a soft alpha with hair strands for the silhouette.

---

## (c) Sources per licence claim

Monocular geometry
- MoGe code MIT + DINOv2 Apache: https://github.com/microsoft/MoGe (LICENSE, README "License"); weights MIT: https://huggingface.co/Ruicheng/moge-2-vitl-normal , /moge-2-vitb-normal , /moge-2-vits-normal , /moge-2-vitl , /moge-vitl , /moge-3-vitl , /moge-3-vitg ; ONNX: https://github.com/microsoft/MoGe/blob/main/docs/onnx.md ; FlexGEMM MIT: https://github.com/JeffreyXiang/FlexGEMM
- DAViD: https://github.com/microsoft/DAViD (README "Model License", "Dataset License"; `model_cards/*.md`; `LICENSE-MIT.txt`, `LICENSE-CDLA-2.0.txt`)
- Depth Anything V2: https://github.com/DepthAnything/Depth-Anything-V2 ; https://huggingface.co/depth-anything/Depth-Anything-V2-Small (apache-2.0), /Depth-Anything-V2-Base and /Depth-Anything-V2-Large (cc-by-nc-4.0); https://huggingface.co/onnx-community/depth-anything-v2-small
- Depth Anything 3: https://github.com/ByteDance-Seed/Depth-Anything-3 (README model table with a licence column); https://huggingface.co/depth-anything/DA3-SMALL , /DA3-BASE , /DA3MONO-LARGE , /DA3METRIC-LARGE (apache-2.0); /DA3-LARGE , /DA3-GIANT , /DA3NESTED-GIANT-LARGE (cc-by-nc-4.0)
- Depth Pro: https://github.com/apple/ml-depth-pro (LICENSE, README "License"); https://huggingface.co/apple/DepthPro/blob/main/LICENSE (Apple Machine Learning Research Model licence, tag `apple-amlr`)
- Metric3D: https://github.com/YvanYin/Metric3D (LICENSE BSD-2, README "License and Contact"); https://huggingface.co/JUGGHM/Metric3D ; https://huggingface.co/onnx-community/metric3d-vit-small
- UniDepth: https://github.com/lpiccinelli-eth/UniDepth (LICENSE); UniK3D: https://github.com/lpiccinelli-eth/UniK3D (LICENSE)
- Marigold: https://github.com/prs-eth/Marigold ; https://huggingface.co/prs-eth/marigold-normals-v1-1 , /marigold-depth-v1-1 (openrail++; card links https://huggingface.co/stabilityai/stable-diffusion-2/blob/main/LICENSE-MODEL ); /marigold-depth-lcm-v1-0 , /marigold-normals-lcm-v0-1 (apache-2.0)
- Lotus: https://github.com/EnVision-Research/Lotus ; https://huggingface.co/jingheya/lotus-normal-g-v1-1 , /lotus-depth-g-v2-1-disparity
- StableNormal: https://github.com/Stable-X/StableNormal ; https://huggingface.co/Stable-X/stable-normal-v0-1 , /yoso-normal-v1-8-1
- DSINE: https://github.com/baegwangbin/DSINE/blob/main/LICENSE ; GeoWizard (no licence): https://github.com/fuxiao0719/GeoWizard , https://huggingface.co/lemonaddie/Geowizard
- Sapiens v1: https://github.com/facebookresearch/sapiens/blob/main/LICENSE ; https://huggingface.co/facebook/sapiens-normal-1b (cc-by-nc-4.0)
- Sapiens2: https://github.com/facebookresearch/sapiens2/blob/main/LICENSE.md (section 1.b.vi, 1.c); https://huggingface.co/facebook/sapiens2-normal-0.4b ; docs/NORMAL.md, docs/POSE.md, `sapiens/pose/configs/_base_/keypoints308.py`
- VGGT: https://github.com/facebookresearch/vggt (README news 2025-07-29 and "License", LICENSE.txt); https://huggingface.co/facebook/VGGT-1B (cc-by-nc-4.0); https://huggingface.co/facebook/VGGT-1B-Commercial (gated)
- DUSt3R / MASt3R: https://github.com/naver/dust3r/blob/main/LICENSE , https://github.com/naver/mast3r/blob/main/LICENSE
- MapAnything: https://github.com/facebookresearch/map-anything (README "License" lists both models); https://huggingface.co/facebook/map-anything-apache (apache-2.0), /map-anything (cc-by-nc-4.0)
- Pi3: https://github.com/yyfz/Pi3 (README "License" table); Fast3R: https://github.com/facebookresearch/fast3r/blob/main/LICENSE

Landmarks
- MediaPipe: https://github.com/google-ai-edge/mediapipe (Apache-2.0); model cards via https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker and /image_segmenter (cards not re-read: weights line is "per model card")
- GNM: https://github.com/google/GNM (Apache-2.0; `gnm/shape/data/landmarks/head_sparse_68.txt`)
- XR Blocks table: https://github.com/google/xrblocks/blob/main/samples/avatar_lab/gnm/FaceCorrespondence.js ; https://github.com/edualvarado/gnm-webcam-puppet (`webcam_puppet/assets/correspondence.npz`)
- headSize-gnm: https://github.com/shameem4/headSize-gnm (LICENSE, NOTICE, ear/LICENSE.md, experiments/fetch_data.py)
- Ear models: https://github.com/shameem4/Ear_Landmarker (README "Data", "Licence", NOTICE section 3); https://github.com/shameem4/BlazeEar (README "License"); iBUG ears terms: https://ibug.doc.ic.ac.uk/resources/ibug-ears/
- face-alignment: https://github.com/1adrianb/face-alignment ; dlib note on 300-W: https://github.com/davisking/dlib-models (README)
- SPIGA: https://github.com/andresprados/SPIGA , https://huggingface.co/aprados/spiga ; STAR: https://github.com/ZhenglinZhou/STAR ; ORFormer: https://github.com/ben0919/ORFormer
- OpenFace: https://github.com/TadasBaltrusaitis/OpenFace/blob/master/OpenFace-license.txt ; https://github.com/CMU-MultiComp-Lab/OpenFace-3.0/blob/main/LICENSE
- InsightFace: https://github.com/deepinsight/insightface (README "License")
- 3DDFA_V2: https://github.com/cleardusk/3DDFA_V2 ; 3DDFA-V3: https://github.com/wang-zidu/3DDFA-V3 ; SynergyNet: https://github.com/choyingw/SynergyNet ; PIPNet: https://github.com/jhb86253817/PIPNet
- DWPose: https://github.com/IDEA-Research/DWPose , https://huggingface.co/yzd-v/DWPose ; COCO-WholeBody terms: https://github.com/jin-s13/COCO-WholeBody (README) ; RTMPose / RTMW: https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose ; rtmlib: https://github.com/Tau-J/rtmlib ; LaPa terms: https://github.com/JDAI-CV/lapa-dataset
- Ultralytics AGPL-3.0: https://github.com/ultralytics/ultralytics
- Microsoft dense landmarks (no release): https://microsoft.github.io/DenseLandmarks/

Parametric
- FLAME licences incl. "FLAME 2023 Open" CC-BY-4.0: https://flame.is.tue.mpg.de/modellicense.html , https://flame.is.tue.mpg.de/ (news item)
- DECA: https://github.com/yfeng95/DECA/blob/master/LICENSE ; EMOCA: https://github.com/radekd91/emoca/blob/release/EMOCA_v2/LICENSE ; MICA: https://github.com/Zielon/MICA/blob/master/LICENSE
- SMIRK: https://github.com/georgeretsi/smirk ; Pixel3DMM: https://github.com/SimonGiebenhain/pixel3dmm ; SHeaP: https://github.com/nlml/SHeaP/blob/main/LICENSE.txt
- Deep3DFaceRecon: https://github.com/sicxu/Deep3DFaceRecon_pytorch ; HRN: https://github.com/youngLBW/HRN ; FaceVerse: https://github.com/LizhenWangT/FaceVerse ; AlbedoMM: https://github.com/waps101/AlbedoMM ; ICT-FaceKit: https://github.com/USC-ICT/ICT-FaceKit
- MHR: https://github.com/facebookresearch/MHR ; SAM 3D Body: https://github.com/facebookresearch/sam-3d-body (LICENSE "SAM License", 2025-11-19), https://huggingface.co/facebook/sam-3d-body-vith

Image-to-3D
- TRELLIS: https://github.com/microsoft/TRELLIS (README "License"), https://huggingface.co/microsoft/TRELLIS-image-large ; TRELLIS.2: https://github.com/microsoft/TRELLIS.2 , https://huggingface.co/microsoft/TRELLIS.2-4B ; nvdiffrast: https://github.com/NVlabs/nvdiffrast/blob/main/LICENSE.txt
- Hi3DGen: https://github.com/Stable-X/Stable3DGen (README "License"), https://huggingface.co/Stable-X/trellis-normal-v0-1
- Hunyuan3D: https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE , https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/LICENSE , https://huggingface.co/tencent/Hunyuan3D-2.1
- SAM 3D Objects: https://github.com/facebookresearch/sam-3d-objects ; TripoSR: https://huggingface.co/stabilityai/TripoSR ; TripoSG: https://huggingface.co/VAST-AI/TripoSG ; InstantMesh: https://huggingface.co/TencentARC/InstantMesh
- SF3D / SPAR3D: https://github.com/Stability-AI/stable-fast-3d/blob/main/LICENSE.md , https://huggingface.co/stabilityai/stable-point-aware-3d
- Direct3D-S2: https://huggingface.co/wushuang98/Direct3D-S2 ; PartCrafter: https://huggingface.co/wgsxm/PartCrafter
- LAM: https://github.com/aigc3d/LAM , https://huggingface.co/3DAIGC/LAM-20K ; GAGAvatar: https://github.com/xg-chu/GAGAvatar ; FaceLift: https://github.com/weijielyu/FaceLift ("Adobe Research License v1.2.txt") ; Pippo: https://github.com/facebookresearch/pippo/blob/main/LICENSE

Parsing
- BiRefNet: https://github.com/ZhengPeng7/BiRefNet , https://huggingface.co/ZhengPeng7/BiRefNet-portrait ; RMBG-2.0 (NC): https://huggingface.co/briaai/RMBG-2.0
- SAM 2: https://github.com/facebookresearch/sam2 , https://huggingface.co/facebook/sam2.1-hiera-large ; SAM 3: https://github.com/facebookresearch/sam3/blob/main/LICENSE , https://huggingface.co/facebook/sam3
- face-parsing.PyTorch: https://github.com/zllrunning/face-parsing.PyTorch ; https://huggingface.co/jonathandinu/face-parsing ; FaRL: https://github.com/FacePerceiver/FaRL , https://github.com/FacePerceiver/facer ; MODNet: https://github.com/ZHKKKe/MODNet

## What I could not verify (stated plainly)

- MediaPipe model-card PDFs (Face Landmarker, SelfieMulticlass, hair) were not re-read; "Apache-2.0" for those weights
  rests on Google's published model cards from memory plus the Apache-2.0 repo.
- Depth Anything V2 Giant, CraftsMan3D, Arc2Avatar, HeadGAP, TokenFace, FaceVerse model terms, Menpo profile models,
  the DINOv3 licence text, Zero123++ terms (InstantMesh), 300W-LP / LS3D-W / WFLW / MERL-RAV / CelebAMask-HQ licence
  pages themselves (their restrictions are quoted from secondary repos: dlib-models, COCO-WholeBody, LaPa, Ear_Landmarker).
- VGGT-1B-Commercial's licence file on HF is gated; the commercial statement is from the public GitHub README and LICENSE.txt.
- DAViD's normal-map axis convention; Ear_Landmarker / BlazeEar tensor layouts.
- No model was run. Quality claims ("good on faces") are from the projects' own descriptions.
