# Place where we measure (agreed with Joe, 2026-11-11)

Joe: "It feels like we should place where we measure." (memory: pieces start where their own tapes were measured.)

## Why
s5-2 (the suit jacket's step 5) laid the undercollar as a RING round the neck: stand_ring guesses a ring of the collar's
neck-edge length, tilted to clear the throat. That is shirt / hussar geometry: their necklines are rings. The jacket's
neckline runs round the back neck, over the shoulder and down the gorge with the lapel to the notch, so the ring pulled
the gorge up off the lapel (held_length 13415 %). The guess exists because:
- step 4's `piece_measurements` is EMPTY for all 16 jacket pieces: it is built from step 1's seam `length.body` names and
  the FreeSewing part's `measurements`, and an agent's own parts (`my.front`, extending jaeger) list none. Nothing
  refuses an empty list, so the build fell back to rings and torso fallbacks;
- step 3 never measured the line the collar sits on (only `neck`, the 406 mm loop; the collar's neck edge is 453 mm);
- the build places stiff pieces from rules (stand_ring, band_closed), never from tapes; tapes start soft pieces only.

## The rule
Every piece is placed where the body was measured for it. Nothing is placed from a rule about collars, shirts or limbs.
1. STEP 3 measures the lines the pattern hangs on (body_tape can already: `length` from / via / to over the surface; a
   jacket's neckline: back neck, via the shoulder point, to the front at the break).
2. STEP 4 says which tape each piece, and each edge laid on the body, was drafted on: declarations
   `tapes {piece: [tape, ...] | {edge: tape}}`, merged into `piece_measurements`. Gate row `piece_tapes`: every built
   piece names at least one step-3 tape with geometry; every name is a step-3 tape (else back to step 3, naming the line
   to measure); a stiff piece sewn to soft cloth names the tape its sewn edge lies on.
3. STEP 5 places every piece on its tapes, stiff pieces too: a stiff piece's edge named on a tape is laid along that
   tape's path by arc length from the end they share (CB for a collar; the .R side mirrored), then it rests and keeps
   its shape as now. stand_ring's ring and the torso / limb fallbacks go (R3e).

## Runs (one deliverable each; tests per slice, one suite at the end)
| # | Run | Size |
|---|---|---|
| P1 | Step 4: `tapes` declarations, piece_measurements merged, the `piece_tapes` gate row, guide text; the carry re-runs it (approved drafts without tapes go stale) | S-M |
| P2 | Step 5: stiff pieces placed on their edge tapes (the collar's neck edge on the neckline tape); a piece with no tape is refused, never guessed | M |
| P3 | Controls: the shirt's and the hussar's step 3/4 redone with tapes; their builds read no worse than today; the ring and fallbacks deleted | M |
| T | Jacket steps 3, 4, 5 blind (s3-6, s4-25, s5-3), judged beside the reference | trials |
