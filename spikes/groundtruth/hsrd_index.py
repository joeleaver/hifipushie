"""hsrd_index.py: (re)write $HIFIPUSHIE_GROUNDTRUTH/hsrd100/index.json from the poses that are in the set: subjects
(age, sex, as the dataset gives them: person_meta.json), each pose's summary and what the dataset says the pose is,
the FIXED split by subject (chosen once, 2026-10-13: 7 train-candidate / 3 held out, balanced by sex and age; never
change it: a network tuned on the train side must not have seen the held-out people), the attribution and licence,
and sources (sha256 of every original archive that was read). Prints the set's table."""
import json
import shutil
import gt

SET = gt.ROOT / "hsrd100"
HELDOUT = ("HSR0023", "HSR0027", "HSR0102")        # a man of 62, a woman of 41, a woman of 22; train: 4 men (24, 25, 50, 64), 3 women (21, 23, 60)
ATTR = ("HSRD-100: 100 High-Quality 3D Human Scans Dataset, Digital Reality Lab, 2025, https://huggingface.co/datasets/digitalrealitylab/HSRD-100, "
        "licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Photos cut, scans cut and decimated, GNM fits and landmark labels added by hifipushie.")
subjects, poses, src = {}, {}, {}
for d in sorted(SET.glob("HSR*/HSR*-Body-*")):
    if not (d / "summary.json").exists():
        continue
    s = json.loads((d / "summary.json").read_text())
    pm = json.loads((d / "person_meta.json").read_text())
    po = json.loads((d / "pose_meta.json").read_text())
    sid = d.parent.name
    subjects[sid] = {"age": int(pm["age"]), "sex": pm["sex"], "split": "heldout" if sid in HELDOUT else "train",
                     "hair": f"{pm.get('hair_type', '')}, {pm.get('hair_color', '')}", "beard": pm.get("beard"), "expression_stated": pm.get("expression")}
    poses[d.name] = {"subject": sid, "pose_type": po.get("pose_type"), "activity": po.get("activity"), "upper_clothing": po.get("upper_clothing"),
                     "head_accessory": (po.get("accessories") or {}).get("head"), "face_accessory": (po.get("accessories") or {}).get("face"), **s}
    src[d.name] = {ln.split()[1]: ln.split()[0] for ln in (d / "SHA256SUMS").read_text().splitlines() if ln.strip()}
if (SET / "CC-BY-4.0-legalcode.txt").exists():
    shutil.copy(SET / "CC-BY-4.0-legalcode.txt", SET / "LICENSE_CC-BY-4.0.txt")
idx = {"what": "HSRD-100 rig photos of heads with scan truth: per pose the head photos (cut), their calibrated cameras, the scan's head, the direct GNM fits, projected landmark labels with visibility and quality",
       "attribution": ATTR, "licence": "CC BY 4.0 (LICENSE_CC-BY-4.0.txt; the dataset card: README_dataset_card_2026-10-13.md)",
       "split_note": "by SUBJECT, fixed 2026-10-13; heldout = " + ", ".join(HELDOUT), "subjects": subjects, "poses": poses, "sources_sha256": src,
       "landmark_sets": {"dl3": "landmark_sets/denselm_v3.npz (756 GNM vertices; branch worktree-agent-a2e75a7e571826c88 @ 67548ea)", "lm68": "GNM's head_sparse_68 (barycentric rows)",
                         "mp": "landmark_sets/mp_gnm.json (readmix @ e53688d: MediaPipe 468 -> GNM triangle + weights)"},
       "bytes": sum(p["bytes"] for p in poses.values())}
(SET / "index.json").write_text(json.dumps(idx, indent=1))
print(f"{len(subjects)} subjects, {len(poses)} poses, {sum(p['photos'] for p in poses.values())} photos, {idx['bytes'] / 1e9:.2f} GB")
print("| pose | subject (sex, age, split) | the dataset's words | head photos (front / 3q / profile / rear) | face px (median, range) | fit: face mean / p90 mm (+ expression) | registration rms mm |")
print("|---|---|---|---|---|---|---|")
for n, p in poses.items():
    s = subjects[p["subject"]]
    b = p["bins"]
    print(f"| {n} | {p['subject']} ({s['sex'][0]}, {s['age']}, {s['split']}) | {p['pose_type']}, {p['activity']}; {p['upper_clothing']}; head: {p['head_accessory'] or 'None'} | {p['photos']} ({b['front']} / {b['three-quarter']} / {b['profile']} / {b['rear']}) | "
          f"{p['face_px']:.0f} ({p['face_px_range'][0]:.0f}-{p['face_px_range'][1]:.0f}) | {p['fit_face_mean_mm']:.2f} / {p['fit_face_p90_mm']:.2f} ({p['fit_expr_face_mean_mm']:.2f}){' FLAG' if p['flag'] else ''} | {p['register_rms_mm']:.2f} |")
