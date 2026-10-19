# STATE: dress-garrett -- rewritten 2026-10-19 after session "am" (2026-10-18). THREAD PAUSED (coordinator); nothing in flight.

## Current best (frozen for export)
- **/mnt/data/hifipushie/dress_garrett/frozen_ae/**: jacket = seam_al/frz_v3 (collar draped alone over the frozen jacket:
  over.py build/submit/apply v3 'normal_at="notch"' ease_pow=2 contact_gap=0.001 start_rest=true surface=true; base jacket
  dg_ae_j18 + ah's fair_edge_runs), shirt = dg_ae_j18's, trousers = dg_af_t6f.
  Previous set kept at frozen_ae_pre_al_2026-10-18/ (also the source of the made collar for over.py).
- Commits it needs: 1b9ac8a2, 3b870bd9, 8a56a9a9 (cloth_over).
- Candidate not taken: seam_am/frz_m1 (lie_transition + tr_smooth 8: shoulder transition standoff 19 -> 6 mm; blind tie 5/5 MAJOR vs v3).
  Its levers live only in $G/seam_am/over.py (scratch): fold into cloth_over if m1 is ever taken.
- Target: Garrett's concept workspace/garrett_v20/concept_v8_front_apose.png (charcoal two-button notched jacket worn open,
  pale shirt top button open, flat-front trousers with a crease; seated in the game).

## Open faults (by game visibility)
1. 3 m (back): collar ends reach the shoulder silhouette ("wings" / "cape"): WIDTH, not standoff: the ends lie on the lapel
   past the gorge tilted up-out. Levers: the end's direction down-out along the gorge, and / or the jacket's gorge line
   (cfNeck high and wide). Judge on the back view.
2. 1 m (front-3q): notch unreadable ("two stuck-on tabs"); end edge-on 58 deg out of the lapel plane (measured, ak).
3. 1 m: white marks at the left lapel top / upper back seen in the EXPORT: not in the frozen draw (specks.py: back 0) ->
   export side (decimation / LOD / skinning). Next: specks.py on the exported GLB, rest + a walk frame.
4. Minor: stand-top spikes (back view); shirt collar points + placket; cuff flecks LOD1-2 (with the export thread); belt.
5. Spec: the frozen jacket's "over" key fails today's cloth.validate (Garrett export saves checked=False); frozen pickles carry
   their own chain (export falls back to it, Garrett s7).

## Decisions in force
- Construction before solver; the pressed rest / draft is the lever, never solver tuning. Made pieces built on the drape.
- Cloth sims rented (ZOZO via oxidegen, ~$0.02 per collar sim); ONE sim per brief unless the coordinator says more.
- cloth_job.preflight must read 0 body / self pairs before every submit.
- Re-freeze only when a blind review (fresh subagent, reference + 4 views, key file) prefers the candidate. Look first.

## Dead ends (don't retry)
- A plane through the notch as the pressed rest (ends float 20-29 mm). surf_pow 6 for the flare (19 -> 15 only).
- The pressed rest drawn without a sim as a candidate (ak frz_v1_rest: wings above the lapels).
- lie_ease 0.25 / 0.06, rest_passes 8, tr_smooth 30: fail preflight on self pairs.
- Hunting the export's white marks in the frozen cloth (they are not there).

## Commands (G=/mnt/data/hifipushie/dress_garrett)
- Collar: python $G/seam_am/over.py build|submit|apply <tag> [k=json] (build = draft + rest + TR per-step print; submit ~1 min).
- Export-style draw for review: bash $G/seam_am/xc.sh <abs frozen dir> <name>. Flare numbers: seam_am/flare.py; specks: seam_am/specks.py.
- Blind review: seam_am/blind*/ + *_key.json pattern.

## History (grep only)
docs/notes/cloth.md "dress-garrett 2026-10-18 ak" / "al" / "am" and their Handovers; "Suit" sections for the suit construction.
