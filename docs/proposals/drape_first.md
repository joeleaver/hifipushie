# Drape first: shape the garment in 3D, then cut and flatten it (approved by Joe, 2026-11-16)

## Why
Twenty-odd step-5 runs (N1-N2j, D1-D4, Z1) tried to find a soft garment's 3D shape from its flat pattern's edges alone.
That is an inverse problem with a free bend at every link: each run added a constraint (tapes, folds, contact, lines
across, body lines) and the solve still found spaghetti, because spaghetti satisfies them too. Chains worked for the
collar (one stiff piece, few freedoms), not for a whole soft garment, whose shape comes from the cloth surface on the
body. Joe: "I have serious doubts about our ability to construct a garment from this spaghetti ... maybe it's time to
rethink." A draper works the other way round: shape the cloth on the dress form, mark the seam lines on it, take it off
and true the flat pieces. Pieces then start in 3D where they belong; nothing has to be placed.

## The steps (0-3 unchanged)
0 read, 1 parts, 2 style plan (incl. the panel shares: where seams fall round the body), 3 body tapes.
4 TOILE: the garment's 3D surface on the body, from the plan: the body offset by the plan's ease at each girth level,
  shaped by the style (length, hem flare, the front's opening to the break, the lapel turned back on the chest, the
  collar's stand and fall round the neck, sleeves round the arms with their own ease). hifipushie's SDF tools build it
  (an offset body, blended, with the style's own blobs). Gate: girths = body + plan ease by construction; the silhouette
  beside the reference (blind look); Joe approves.
5 MARK: the seam lines drawn on the toile (D4's body lines: centre front / back, shoulder, side-body seams at step 2's
  shares, armhole, neckline / gorge, roll lines, darts, hems), each a closed or end-to-end curve on the surface.
6 CUT AND FLATTEN: the toile cut along the marked lines into pieces; each piece flattened with least distortion; the
  strain left over shows where a dart, ease or a seam is needed (a draper's reading); seams trued (both sides equal, or
  the declared ease). Output: the flat pattern in today's step-4 form, so today's step-4 gates run on it, and each
  piece keeps its 3D position from the toile (no placement step).
7 on: details, the hang (ZOZO: folds only, from pieces already in place), look, export, as today.

## What survives
Steps 0-3; the step-4 gates (girths, panels, caught, seams, vents, cap); D4's body lines (they become step 5's marks);
the chain network and chain_solve for stiff pieces and for truing; ZOZO for the hang. The FreeSewing drafting route
stays for pattern output and checks, no longer as the source of the 3D shape.

## Runs
| # | Run | Size |
|---|---|---|
| R1 | Proof: the jacket's body + sleeves toile (no collar), D4's lines marked, cut, flattened; pieces compared with s4-31's approved pattern (shapes, girths, seam lengths); renders: toile, lines, flat pieces | M |
| R2 | Lapel and collar on the toile (turned flaps); flatten a folded piece by unfolding it about its roll line | M |
| R3 | Steps 4-6 as tools with their gates; the old step-5 placement code retired | L |
| T  | Blind trials of steps 4-6 on the jacket, then the shirt and hussar | trials |
