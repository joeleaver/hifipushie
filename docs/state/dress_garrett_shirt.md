# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 4

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: process carried, geometry didn't. Round 2: lessons made general (C103-C108). Round 3: base fit STUCK (C110).
Round 4: neck split (C113, opt-in), first-button rule (C114), colour PASS. Start strain still 7.2 % (3 % allowed).
Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE: the base fit is still the blocker. C113 (garment key neck_split: the neck pins split the neck as the shirt's own
neckline does) moved the neck point 9.6 mm back: untucked start over-limit 1988 -> 1696, tucked 8.1 % -> 7.2 %; the yoke
stays 31 % over (p99 28). On the parked jacket the same rule regressed the front-view hip 406 -> 360 (so: opt-in, off
by default; jacket unchanged = r26g). Arrangement NOT run (refused at preflight). Shirt alone r4b: blind review FAIL
(wf 6 MAJOR, collar 5 MAJOR: standing ring collar, no V, boxy torso, square shoulders, flared hem).
NEXT: (1) the yoke strain is not the neck pin: 11 pin / slope levers move it 0-20 % (C110, C113). Next suspect: the
stand ring pulling the yoke's neck edge up the neck (stand placed strained, relaxed in relax1 by stretching the yoke)
and the HPS landmark itself (tailor "widest", 2 cm up the neck; HP_HPS research is parked: a coordinator call);
(2) the under front's open-neck roll drafted from the V so a high first button can coexist with it (C114 CONFLICT),
then put Garrett's spacing back (first 28 mm read 64 below HPS on the form: re-target from the form, ~47 mm);
(3) arrange the collar once the start is < 3 %; (4) dress under the jacket and read the cuffs (C85) after that.

## Big reads (concept | r1 f1b | r2 f2b | r3 f3a | r4 r4b)
- V bottom below HPS: 60 | ~70-80 | 74 | 74 | 62.4 PASS. Front closed x5 PASS. Collar button: open PASS.
- Collar points apart: 147 | 53 | 57 | 57 | 45 FAIL; below HPS 50-61 | 78 | 84.5 | 84.5 | 82 FAIL; spread | closed x4.
- First fastened button: 83 | 124 | 123 | 123 | 64 FAIL (rule 28 mm below cfNeck flat; now off, see NEXT 2).
- Tuck stand-off: tucked | 12.6 | 6.0 | 6.0 | 6.0 PASS.
- Colour lit: 177/174/171 | - | 178/174/171 (lapel box) | 192/188/185 | 177.5/174.3/171.2 PASS (#bdb8b4 -> #aeaaa6).
- Strain p99 drawn: - | 11.3 | 17.2 | 13.3 | 13.4 FAIL (yoke 27.8). Start over-limit: - | - | 10.1 % | 8.1 % | 7.2 %.

## Spec sh_garrett: v4 spacing, v5 neck_split + colour, v6 spacing off (r4b = v5).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round4; run.sh runs THIS worktree's code)
where.py <tag> [untuck=1] (prints the C114 gate rows); trace.py / trace_pins.py (HPSW SHW HPS_BACK_MM HPS_DOWN_MM
MOD_OVR) bisect; seams.py / neck.py / buttons.py read where_<tag>.pkl; probe_split.py <pkl> [mesh key];
fit4.py <tag>; RUNNER=bin/capped ./run.sh render5.py <asm> <tag> [crops]; rev4.sh <tag> (one view per review).
Jacket regression: jfit.sh <tag> [K=V] (r26g recipe -> asm_<tag>.pkl), jcmp.sh <tags> (sideline + gorge + lapel).
