# STATE: draft_pattern (garment step 4, T5 + T5b) -> codified.md C285, C295, C300, C303, C304-C306
Tool draft_pattern(name, garment, design, declarations, options, sa): the agent's own FreeSewing design (Node, no network,
fs read-only, 60 s) + declarations in step 1's names -> draft_own.block (the one converter) -> cloth.mesh -> the flat
gate -> step 4 + flat sheet. pattern_check and chain_garment's gate read an own draft's step 4. The spec's pattern
carries a digest of draft + declarations + options (a redraft into the same dir is a new chain job).
T5b (C295): the flat gate checks SHAPE per role (draft_shape.py, its docstring the spec; targets on FreeSewing 4.10.2's own
parts, /mnt/data/hifipushie/t5b/scripts/ref_*.py): shape_fall (outer / stand seam >= 1.012), shape_cap ([0.47, 0.79] x
armhole depth), shape_seam_curve (no straight edge sewn to a curved one), shape_stand (below).
T5c (C300; draft_stand.py, its docstring the derivation): step 2's collar_top trace decides a stand's curve and heights
(h_side, T, f = T / D; rise, front ends, CB, lean targets); FAIL says which way to curve. No trace: INFO.
r-hussar (C303; HOME /mnt/data/hifipushie/r-hussar): D is the neckline's drop SEEN (collar_front traces' bottoms below
the hps marks, else the body's hps - cf_neck), D_back the body's; an upright level-top stand's neck edge FALLS at the
ends by (1 - f)(D - D_b). shape_stand is a verdict on the HEIGHTS (3 builds agree); the CURVE is report-only ("INFO
(curve would FAIL)"): no upright build backs the rise yet. Redraft r2 (examples/draft_own/hussar.mjs): fronts 82 / CB 48
/ side 53 mm, flat rows PASS; built, it lies out like a funnel (collar_upright 31 deg, want 76-94): a BUILD fault
(chain_roles' stand stage only asks its top 12 mm over its bottom; F1's thread, not this page's).

F2 (2026-11-02, fix run on blind trial t8's step-4 friction; HOME /mnt/data/hifipushie/f2/ws = t8 ws copy; proofs:
/mnt/data/hifipushie/f2/scripts/proofs.py -> /mnt/data/hifipushie/f2/proofs.txt):
- pattern_parts (new tool; pattern_parts.py + .mjs, run like draft_own: sandboxed Node): a pack design name or the
  agent's own source -> measurements it needs (patternConfig: every part it drafts), every part in draft order (HIDDEN,
  from / after), point / path counts, the seam outline as point names in order (aliases "a=b"), options (default
  [min..max]); part=: points (x, y mm) + every path in order; look=True: the part's outline, names large. name + garment:
  drafted with step 3, else stated DEFAULTS. Proven on jaeger (25 parts; jaeger.front / frontFacing visible, the bases
  HIDDEN), bent, brian, t8's own shirt v3 and jacket v2. The guide now points here, not at examples/*.mjs.
- draft_pattern: the design's full measurement list checked BEFORE drafting (pattern_parts.missing): t8's shirt v1 with
  step 3 lacking waistToArmpit -> "needs measurements step 3 hasn't taken: waistToArmpit" (was a NaN crash in simon.back).
- garment_plan step 1: seam length names must be body_tape.TAKES (= tailor.py's mm keys, test-held) or step 1's `define`
  {name: girth|arc|length|height}; else refused with the closest ('acrossBack' -> napeToWaistBack, hpsToWaistBack).
- Coordinates: every at / outline / points is PIXELS of the named view (said in the text, the guide, the tool doc); a
  [u, v] list all within 0..1 on an image > 2 px is refused with the factor (pixel_errors).
- Carry forward (garment_carry.py; garment_record T1 rule extended): after garment_plan rewrites step 0 / 1, each later
  done step whose SAVED content still validates is re-stamped (inputs = the new digest, `carried`; digest + approval
  kept); the first that doesn't gets `stale_why` (states() treats it as stale and shows the reason; a rewrite clears it).
  Validators: 1 check_parts, 2 check_style, 3 step 1's names all taken, 4 draft_own.validate; 5+ never carried.
  t8 shirt: a reworded piece -> "step 2 (style) carried forward ... step 3 still valid, step 4 still valid".
- shape_stand: ONE row per stand piece, its neck-sewn edges joined into one neck edge (draft_shape.full_arc: a fold-cut
  half cb>sh + sh>fe -> fe.m>cb>fe), its free edge likewise. t8 shirt: was two rows "near straight +0.9 / +0.8 mm"; now
  "collar_stand (band): neck edge rising (hugs) +18.0 mm = +0.26 x front drop 70 mm; heights front 34 / 34, back 32 mm".
  A piece sewn only on a stiff / stand piece's non-neck edge (and on no neck) is a FALL: t8's collar_fall (no role, no
  roll fold) was "no fall", now "outer edge 248 / stand seam 222 mm = 1.118 PASS".
Tests (targeted, all pass): test_draft_own (15), test_garment_plan (+3, one existing test updated: a changed reading now
carries parts), test_garment_record, test_body_tape (+1), test_toolsets (-m "": pattern_parts in ADDED). Not bin/suite.
UNVERIFIED: the running MCP server has the old code (restart to get pattern_parts); a blind agent using pattern_parts;
carry after a step-0 change on a real record; full_arc on a stand with no fold whose neck edges don't share a point
(falls back to the first arc); jaeger.backBase's moved points print as "(0,20)" (no name at that spot).
F3 (C310): `pieces.<n>.pair: true` = cut 2 as a mirrored pair (draft_pairs.py); half / sideless pieces refused at
step 4 with that declaration; t8 shirt + trousers redeclared draft and pass (f3/scripts/pairs.py).
NEXT: a blind re-run of t8's step 4 (shirt + jacket) with pattern_parts available: count the calls to name edges and the
refusals left; then the stand build (F1) and its rise rule.
