# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 3

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: process carried, geometry didn't. Round 2: lessons made general (C103-C108). Round 3: unblock the arrangement.
Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE: round 3 stopped at the BASE FIT (STUCK, C110). The tuck is fixed (C109: line, no ring; hidden cloth slides):
fit f3a drawn p99 13.3 (r2 17.2), back 8.2 (28.8), but yoke 34 % and the start check 8.1 % over (3 % allowed), so the
collar arrangement still cannot run. First button 123 vs 83 is Simon's even spacing from cfNeck (C111, draft, unchanged).
Renders: shirt alone check/*_f3a.png; blind review rev_f3a FAIL 10 MAJOR. Jacket over the shirt NOT run (C85).
NEXT: (1) coordinator: the base fit's yoke / back strain is born in pattern_form relax1 (trace.py), 7 levers dead
(C110); the seam walk says the neckline's back / front split vs the body's HPS (back neck +12 %, front -1.5 %) and the
shoulder seam +7 % - look at relax1's neckline / shoulder targets (shared code: the parked jacket's tests); (2) a
sourced first-button rule in the button marks (C111); (3) arrange the collar once the start is under 3 %; (4) colour
lit 15 too bright vs the concept's shirt patch (now read on the shirt, C112); (5) cuffs once dressed.

## Big reads (concept | r1 f1b | r2 f2b | r3 f3a)
- V bottom below HPS: 60 | ~70-80 | 74 | 74 PASS. Front: closed | closed | closed | closed PASS. Collar button: open.
- Collar points apart: 147 | 53 | 57 | 57 FAIL; below HPS 50-61 | 78 | 84.5 | 84.5 FAIL; spread | closed x3 FAIL.
- First fastened button: 83 | 124 | 123 | 123 FAIL. Tuck stand-off: tucked | 12.6 | 6.0 | 6.0 PASS (line, no ring).
- Colour lit: 173/169/167 (r2 box on the lapel) | - | 178/174/171 | 192/188/185 vs shirt patch 177/174/171 FAIL.
- Strain p99 drawn: - | 11.3 | 17.2 | 13.3 FAIL (yoke 34). Start over-limit: - | - | 10.1 % | 8.1 % (untucked 6.7 %).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round3; run.sh runs THIS worktree's code)
where.py <tag> [untuck=1] [CONST=v] (SHIRT_PATCH=abs json); trace.py / trace_pins.py (HPSW SHW HPS_BACK_MM) bisect;
pmap.py / seams.py / neck.py / buttons.py read where_<tag>.pkl; fit4.py <tag> -> asm_<tag>.pkl;
RUNNER=bin/capped ./run.sh render5.py <asm> <tag> [crops]; rev3.sh <tag>.
