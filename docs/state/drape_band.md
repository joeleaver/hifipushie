# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, round 1

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). Draped in ONE state (closed); the other state's
sweep is the arrangement target, with a reach check. Notes: docs/notes/cloth.md "drape band round 1" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130)
- garment key "drape": [{name, along: [edges, CB in the middle], state, layers: [{piece, kind: stand|fall, height /
  ext | rise / land / end_in / point; values number or {"cb", "end"}}], source}]. `draft(entry, base)` -> pieces with
  the table piece's names (bottomMid, *BottomCf, *TopEdge...), notches, button marks, the fall's roll fold; `record`
  writes entry["out"] (worn key, outlines, report, drape mesh npz in workspace/<model>/drape/).
- base_from_form(form result, X, along, under pieces, "yoke:cbNeck"): curve (half, CB -> CF), skin, cloth under.
- Fall = ruled from its roll to its landing line; band above the stand = its mirror (curved fold); turn of cloth =
  hairpin extra (pi/2 - 1) w; LSCM start + ARAP flatten (CB held straight); develop(): flatten <-> lift rounds.
- Pipeline: cloth.pieces replaces the table pieces (drape.replace_pieces; spring_fall skips a draped fall; the drape's
  roll fold replaces the table's); cloth.place starts draped pieces on the drape (drape.draped_start -> _made_as);
  gate rows drape_band_current (worn key) + drape_band_flat (p99 <= 2 %); drape.reproduced = the fit self-check.
- KATs tests/test_drape.py (4 pass): cylinder neck + cone (stand p99 0.0 %, fall 0.01 %, outer = analytic landing
  path within 0.2 %, relaxed flat stays on the drape < 2 mm), cuff (band rectangle; turn-back on a sleeve), closed vs
  open (straighten 0.05 reachable 2.5 %; deep spread flagged 42 %), gate refuses a changed worn spec.

## Garrett shirt collar (spec sh_garrett v11, drape entry "shirt collar", key 4d7bf2ec17869327)
- Base: closed form c0 ($S/form_c0.pkl: v10, collar buttoned, no worn_open). Worn spec $S/worn.json (d1): stand 32 ->
  29, rise 6, land 8 -> 14, end_in 12, ext 9.
- Flat: stand p99 2.6 % (max 7.2), collar p99 4.2 % (max 15): drape_band_flat FAILS (2 %). Stand top 530.7 vs neck
  edge 473.9 (FLARES: the band follows the skin's offset onto the chest; Simon r12: top 3.7 mm SHORTER). Collar sewn
  493.4 vs stand top 530.7 (no seam match), outer 492.8 (< sewn). Worn reads: stand CB 32.0, fall CB 50.7 (concept
  ~44), edge 5 mm below the seam at CB, points 18.5 apart closed / 38 open (concept 147).
- Reach to the open sweep (k12a base): stand 10.8 %, collar 27.7 % p99: NOT reachable (k12a's neckline half is 222 vs
  231.6 mm closed: the two forms' necklines differ by 4 % before any collar).
- Form fit with the draped pieces: REFUSED at placement (front.L triangle 0.28 m: the open fronts' roll-back under the
  new collar). Rendered the drape itself on c0 instead: check/collar_d1.png, point_L/R_d1.png, wholefront_d1.png.
  Blind review FAIL (mandarin funnel up to the jaw, no fall turned, closed neck, CF flaps spiked). Own read: same.
- Levers spent on the stand (stop-loss): (1) skin-following stand: flares; (2) LEAN_SOLVE (one lean to the top
  length + skin floor): p99 13 %, top 507: DEAD, opt-in off.

## Tests: tests/test_drape.py 4 passed; 22 cloth files: see the commit line.

NEXT: (a) MEASURE FLAT (M12) the closed form's neckline: stand-off from the neck skin CB -> CF (the flare's cause);
the stand must be built on the NECK (a neck section fit, not the nearest skin) with its top edge length from the spec;
(b) then the collar's sewn edge trues itself (it is the stand top); (c) the open base: the same neckline length
(arc-matched), else reach is measuring the forms; (d) the form fit's placement refusal with draped pieces (front.L
roll-back vs the collar), on the closed garment; (e) an MCP tool to run drape.draft (now: garment key only); (f) jacket.
## Commands ($S = /mnt/data/hifipushie/drape_band1; run.sh = this worktree): form_closed.py <tag> (capped);
drape_garrett.py <closed.pkl> <open.pkl> [save]; dbg5.py <drape pkl> (strain by row / col); fit_d1.py <tag> (capped);
DRAPE=<npz> FORM=<pkl> render_d.py - <tag> <views> (capped); rev_d.sh <tag>.
