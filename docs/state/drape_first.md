# STATE: drape first (docs/proposals/drape_first.md; approved 2026-11-16)

Steps 4-6 rebuilt the draper's way: TOILE (the garment's 3D surface on the body), MARK (seam lines on it), CUT AND
FLATTEN (pieces from the toile, already in 3D where they belong). Runs R1 (body + sleeves) -> R2 (lapel, collar) ->
R3 (tools) -> blind trials.

## R1 (2026-11-16): proof on the suit jacket's body + sleeves (spike; /mnt/data/hifipushie/r1: ws, toile/, run.sh)
Code: `spikes/r1_common.py` (exact clip by a scalar, components, CPU 4-view rasterizer: no GPU), `spikes/r1_toile.py`
(toile + marks), `spikes/r1_flat.py` (cut, LSCM + ARAP flatten, seams, girths, compare). `run.sh [flat]` runs both.
TOILE: body SDF on a 6 mm grid, closed by 25 mm (a jacket bridges hollows), minus an ease field: torso k(z) w(theta),
w = 0.35 + 0.65 cos^2 (full front / back, 35 % under the arm), k per step-0 level CALIBRATED so the section as a tape
(convex hull, sleeves out) = step 0's garment girth; sleeves 18 -> 22 mm. SDF not a mesh offset: an offset mesh folds
in the armpit / spine / crotch; the field rounds them and joins the sleeves by itself. Cuts exact: hem = grid floor,
neck along D4's body neckline (by angle), opening along step 2's roll line (gorge -> break) + front edge (break -> hem),
sleeve square to the forearm at step 0's sleeve_hem.
Girths (toile, as a tape): chest 1108.5 / plan 1108.2, waist 988.0 / 987.6, hips 1103.3 / 1103.1, hem 1138.7 / 1138.8.
Offsets that took: front 36 / 50 / 40 / 52 mm (chest / waist / hips / hem), sides 13 / 17 / 14 / 18 mm.
LOOK (toile_sheet.png beside the reference): reads as the jacket: length to the crotch, open front to the break, waist
suppression, sleeves to the wrist. Faults: no shoulder pad (shoulders slope with the body); sleeves follow the arm's
bumps (ripples; a sleeve should hang as a smooth tube); the back neck rises as a short stand (the neck base line).
MARK: D4's lines out onto the toile: body normal for neck / shoulder / armhole, horizontal from the torso axis for CB
and side seams (the body normal swings sideways in the seat cleft: CB was spaghetti), square out from the arm axis
for the sleeve seams. Armhole = the plane of D4's body armhole (off its plane 4 mm mean, 9 max) through the toile.
CUT AND FLATTEN (flat.json, cut_sheet.png, flat_sheet.png). Strain = max(s1 - 1, 1 - s2):
| piece | area cm2 | mean | area > 2 % | area > 5 % | where |
| front.L | 970 | 1.1 % | 14 % | 0.9 % | compression over the chest at the armhole (z 1.38): a chest dart / canvas |
| side.L | 490 | 0.3 % | 0.3 % | 0 | flat: a side body is developable |
| back.L | 1476 | 2.1 % | 42 % | 2.6 % | blade and back neck: a shoulder dart / ease into the shoulder seam |
| sleeve_top.L | 1106 | 2.4 % | 52 % | 6.3 % | crown stretch (z 1.45) + ripples from the arm's bumps |
| sleeve_under.L | 631 | 1.4 % | 20 % | 0.9 % | underarm; a flap where the cap's plane meets the web |
Seams (flat a / b): front+side 475.8 / 475.5, side+back 442.6 / 441.5, shoulder 195.5 / 198.0 (-1.3 %), sleeve seams
768.8 / 788.9 (-2.6 %), armhole 405 vs cap 450 (+11 %: the domed crown flattens long; s4-31 declares 8.8 %).
Girth row on the flat (pieces x 2): waist 843 (their 3D 841), hips 890 (893): flattening keeps girths within 0.5 %;
the rest of the plan (145, 213 mm) is the front opening (the lapel / wrap R2 adds). Chest taken at the underarm
(z 1.33, crosses the armholes: not comparable). Shares at the waist front / side / back 0.30 / 0.24 / 0.46.
vs s4-31 (half widths, mm): waist front 128 / 199, side 102 / 125, back 192 / 189; hips 115 / 203, 120 / 118,
210 / 236. Side and back agree; the front differs by the opening + lap + lapel (s4-31's front runs to CF + lap).
The today's step-4 gate(B) was NOT run: it needs step 4's edge arcs and declarations; the girth / seam / share rows
were computed in their own terms (draft_girths' underarm rule, PLAIN_TOL 1 %) on the flat.
Verdict: drape first gives sane body pieces (the side and back near s4-31's, seams true within 0.3 % except the
shoulder) and every piece in 3D where it belongs, with no placement and no solve. Not yet a jacket pattern: the
toile lacks the pad, the lapel / wrap, a smooth sleeve, and the sleeve fore / hind split (taken from D4's split) is
uneven (top 64 %); the left sleeve's marks did not cut it into two (the right one did: flattened mirrored).

## Open faults (ranked)
1. Toile style: shoulder pad (a style blob at the shoulder point), sleeves as a smooth hull round the arm (bridge
   the muscle bumps), a straight-hanging skirt below the seat (today it follows the hips).
2. R2: the front extension to CF + lap, the lapel turned about the roll line, the collar's stand and fall.
3. Cut robustness: a mark that does not separate a piece must be refused (left sleeve), not mirrored round.
4. Dart / ease reading as output: compression islands -> darts (front chest, back blade), crown stretch -> cap ease.

NEXT: R2 (lapel + collar on the toile, flatten a folded piece about its roll line) with fault 1's toile styling first.
