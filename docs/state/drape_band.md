# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, after round 6

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). DRAPE ON THE FORM IT IS PLACED INTO (r4).
COORDINATOR (end of r5, C135): a collar is draped CLOSED, as it is cut; the open state is the INFO reach row, never
the draft source. Notes: docs/notes/cloth.md "drape band round 1..6" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130-C135)
- garment key "drape": [{name, along, worn, layers: [{piece, kind: stand|fall, ...}], source}]; gate rows
  drape_band_current + drape_band_flat (p99 <= 2 %) + drape_band_reach (INFO).
- r2 stand ON THE NECK; r3 ONE FRAME (flat_frame); r4 measured stations {"at": ...}, stand lean, fall land_dir,
  leftTopJoin / rightTopJoin seams. KATs tests/test_drape.py.
- r5 (C134): THE OPEN NECK turned back flat on the chest (fold angle 10, kb shirt wear.no_tie).
- r5 (C135): the OPEN drape is a NEGATIVE spring; drape closed.

## Garrett shirt (sh_garrett v19: drape d6c CLOSED on c0, GATE PASS)
- d6c worn ($S/worn_d6c.json): stand 32/31/29 (CB/side/CF), rise 6, land 13 CB / 16 side / 30 at the point, point 0.
- Flat: stand 0.16 / collar 1.89 % p99; collar_fall_spring +24.6 PASS (outer 527.7 vs need 503.1); cover 5.7 PASS;
  fall CB 54.1; seams PASS. Closed drape: points 46 apart, 65 below HPS. Reach to the open sweep (INFO): 14 / 30.7 %.
- Measured flat (M12): the cloth round the closed neck offsets like its flat pattern; the fall lies where asked. A fall
  landing 13-16 all round sits on a ~450 line; the spring need counts CF to CF + rings: the points must land deeper.
- concept | d2c | d4o | d5o | d6c: spread 147 | 36 (closed) | 151 | 100 | 46 (closed drape); collar flat p99
  <=2 | 1.98 | 1.71 | 2.88 | 1.89; spring - | - | short | short 129 | PASS +24.6.

- Closed fit d6c: fit vs drape 3.0 / 5.2 mm p50 (stand / collar), roll turn 150 PASS, corners FAIL (11.4 %).
- OPEN (d6o, C134 rolls 146 / 171, V 57): the collar STANDS (roll 130), 64 apart / 66 below HPS. Arranged a6c (pins
  on the 2 points only, ZOZO local): held 20 / 36 mm short, springback 1 mm; 94 apart (147), 56 below HPS (PASS), V 71,
  roll 122, twist 28, right open-neck roll undone (85). The stand DOES open at the throat (61 / 119 mm): the fall
  stands up with it as a funnel. Reviews: collar FAIL, wholefront FAIL. Jacket skipped. Ledger C136.
- Renders: open arranged $S/check/{collar,wholefront,point_L,point_R}_d6.png; closed fit {collar,wholefront}_d6c.png
  (reads as a real closed collar); reviews $S/rev_collar_d6.log, rev_whole_clay_d6.log.

NEXT (coordinator stopped sims this round; needs a call): the closed piece passes every flat row; the open state is the blocker. Point pins
can't turn a fall down. Candidates: (a) arrangement pins spread along the fall's whole outer edge (patch per station
on the yoke / rolled fronts, landing line read from the concept), (b) the open neck turning the fall with it (the
fall's ends tied to the rolled fronts' turn), (c) check the concept's 147 is reachable at all (C81: ask first).
## Commands ($S = /mnt/data/hifipushie/drape_band6; run.sh = this worktree): arr6.py <tag> [submit] (SEP, LOW); reads6.py <tag>; render6.py <seen> <tag> <views> (FORM=); m3.py; sweep6.py <worn> '<overrides>' (closed c0,
spring + cover reads); m1.py / m2.py (measure flat: cloth offset loop, fall landing drop); drape_d6.py <worn> save;
gate6.py <tag>; fit6.py <tag> closed|open (RUNNER=bin/capped).
