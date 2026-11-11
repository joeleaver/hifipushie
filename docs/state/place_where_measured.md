# STATE: place where we measure (docs/proposals/place_where_measured.md)

P1 landed (C421). P2 on branch p2-place (C423): a stand's neck edge is laid on the tape step 4 names for it
(piece_start.lay_on_tape: from CB, -X half mirrored; sided pieces from their centre-line end, .R mirrored); a built piece
with no step-3 tape is refused by name first in GarmentBuild.run; stand_ring's neck ring and top_tied deleted; a piece
sewn to itself is a tube only round girths on its side (the jacket's fronts had started round the arm's axis).

Jacket proof (scratch /mnt/data/hifipushie/trials/p2-proof, step 3 + `neckline` tape cb_neck > hps.L > cf_waist, no
break landmark; step 4 redrafted with tapes, PASS): undercollar neck laid 452.5 of 544 mm, ends at the gorge 110 mm
under the hps. Fails next: stand top edge 581.5 vs 474.6 mm (worst link 202 %: the upright-stand top suits a shirt stand,
not a notch collar lying on the lapel); top collar (ply) held_length 2569 % 64 mm from cbN; sleeves not round biceps at
the start (99 deg gap); lapel roll crease turns 63-91 of 170 deg. Fronts now sit like the back (0.21 m max radius).

Kept for P3 (reachable with tapes of the wrong kind): panel_dz's hps fallback, axis_for's LimbAxis fallback, band_closed's
neck ring (a band under a fall).

NEXT: coordinator runs bin/suite on p2-place and lands it; then the notch collar's top edge (a stiff piece's top laid on
what it lies on, not stood upright) and the ply collar's 2569 % link, before P3.
