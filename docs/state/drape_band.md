# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, round 2

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). Draped in ONE state (closed); the other state's
sweep is the arrangement target, with a reach check. Notes: docs/notes/cloth.md "drape band round 1/2" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130, C131)
- garment key "drape": [{name, along, state, layers: [{piece, kind: stand|fall, height / ext / gap | rise / land /
  end_in / point}], source}]; draft / record / gate rows drape_band_current + drape_band_flat (p99 <= 2 %); reach.
- r2 STAND ON THE NECK (STAND_MODE "neck", neck_stand): rises along the neck axis (the neckline plane's normal;
  Garrett 25.5 deg forward), leans in so its inner face is `gap` off the neck at its top (ray in toward the axis,
  skin facing the ray only). r1's "skin" mode kept opt-in (stand_mode). worn_key includes the mode (r1 pieces stale).
- r2 TRUED NECKLINE (true_curve, base_from_form true_sigma 8 mm): the form's neck edge has corners (CB V 50 deg,
  yoke|front 36 deg); trued as a whole loop, length kept. curve_side: drape on the half that keeps its flat length.
- r2 develop: pull 0.05 -> 0.005, rounds 4 -> 12 (module-read; the old defaults were bound at def time: dead plumbing).
- KATs tests/test_drape.py 5: + neck cylinder with chest bulge + chin (leans in, top 27 mm shorter, never in the
  chin; r1 mode flares on the same body). Its fall flattens at 2.4 % (bound 3 %: open item).

## M12 measured flat (round 2 step 1; $S/m1.json, m2-m5)
- Closed vs open half 231.6 vs 222.1: the closed form's +X half is the OVER front (front.L), its neck edge held 133.0
  vs flat 125.9 (+5.6 %), yoke 98.6 vs 95.0; the under front 124.7 (-1 %); open k12a within 1 % of flat (125.3 / 96.9).
  Flat half = 220.9. => drape on c0's under-front half mirrored (219.0) vs open 221.7: 1.2 % apart (was 4 %).
- Stand-off of the seam from the skin (closed): CB 5, side 4-10, CF 12.5 mm. Neck: axis 25.3 deg fwd; girth
  perpendicular to it 383-406 mm (neck base -> +25 mm); above that the jaw cuts in. Chin underside at z ~1535,
  CF seam z 1501: the stand's CF top (z 1529) sits ~6 mm under the chin.
- r1's flare cause: the stand top's nearest skin at the front was the JAW'S UNDERSIDE (normals n_z -0.5..-0.97), not
  the chest.

## Garrett shirt collar (spec sh_garrett v12: drape d2c; v11 = d1; v10 = Simon's)
- Worn spec $S/worn_d2.json: d1's rows + gap 2 mm (collar size = neck + 1/2 in -> 2 mm radial; Aldrich band top
  ~1 cm shorter). Gap 5 -> top 3.6 mm LONGER than the neck edge; 3 -> 1.8 shorter; 2 -> 7.0 shorter.
- d2c: stand p99 0.16 % (d1 2.6), top 448.8 vs neck edge 455.8 (leans in; d1 531 vs 474). Collar p99 1.98 % (d1 4.2):
  drape_band_flat PASS. Reach to open k12a: stand 2.6 % ok, collar 11.7 % FAIL (d1 27.7). Lean CB -20 / side +10 /
  CF +6 deg off the axis (CB: the nape is upright, the axis tilted). Fall CB 49.7, points 35.9 apart closed.

- Step 3: the closed form fit (inside pattern_gate) is STILL REFUSED at placement: front.R triangle 0.29 m (r1:
  front.L). The broken piece is the front whose neckline the drape was taken from (r1 L, r2 R mirrored). 14 verts at
  front.R's CF neck corner (uv ~ cfNeck +-9 mm) are fine after _place_folds and scattered by the start's relax loop
  (cloth.place ~4204-4266). Uncrush off: no change (lever 1 dead). Stop-loss: no fit, no fold rows / collar_corners.
- Rendered the drape on c0 (diag now shows the draped pieces: render_d2.py gives them a mesh): check/collar_d2c.png,
  point_L/R_d2c.png, wholefront_d2c.png. No funnel; band hugs the neck, fall turned flat over it, closed. Blind
  review FAIL (wrong type: closed band vs open spread collar; placket jagged / CF knot = c0's closed form; no point).

NEXT: (a) placement: dump Xp after each step of place()'s relax loop for front.R's CF neck corner (_relax_stretch /
_relax_strain / _clear_of_body / _clear_of_worn, made_v): find the step that flings it; (b) then fit closed + rows;
(c) reach collar 11.7 %: the open sweep needs the fronts' roll-back in the base, not k12a's curve alone; (d) jacket.
## Commands ($S = /mnt/data/hifipushie/drape_band2; run.sh = this worktree): m1..m5.py (measure); drape_d2.py
<worn.json> [save]; sweep_*.py (levers); dbg_hot.py <pkl> (hot edges).
