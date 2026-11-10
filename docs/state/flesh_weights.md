# Flesh weights (soft forms, the torso loft, a limb's seam): STATE 2026-11-06 (round 2)

Branch flesh-visibility (worktree .claude/worktrees/flesh-visibility), from main 769fbff2 (WIP c78e10d7 + the fix).
Asked for by Baynard Racing: Puddles' (pud2 v74) side rose with his raised arms. Not pushed; coordinator lands.

## What the tools hold now (rig.py, rig_join.py; their comments are the spec; ledger C397)
- `skeleton()`: soft forms (`SOFT` super / loft / sheet) are flesh like any blob, placed by their box's middle.
- `_chain_pieces`: a soft blob holding 2+ rig segments of one end-to-end chain (Puddles' torso loft round
  Hips..Neck) is shared as slabs cut at bisector planes; the chain's ROOT slab also stops at its head
  (`CHAIN_ROOT_CAP`): the loft hanging below the hips (over the thighs and knees) stays the legs'.
- `rig_join.limb_join` (last pass of `rig_weights`): for an arm (`JOIN_ROOTS`) sculpted as a layer above the body,
  each vertex is labelled limb / body by whose sculpted flesh is nearer; the seam is where labels meet along mesh
  edges (none cross an air gap); the limb's share runs 0 -> 1 over `JOIN_BAND` 2.5 x girth of surface distance,
  `JOIN_SPLIT` 0.2 on the seam, 90 % of the band on the limb's side (the body's side stays put).
- People and limbs in the body's own layer: untouched (troll, goblin, fox_rig weights bit-identical to main).

## Proof (Puddles, export c3.npz of pud2 v74; spikes/flesh_measure.py; renders in the Baynard notes folder flesh_weights/)
| | main | WIP c78e10d7 | now |
|---|---|---|---|
| arms 80: body side moving > 3 cm | 25.6 % | 1.3 % | 0.2 % |
| arms 80: edges > 3x / p99.9 / max | 3283 / 5.18 / 8.4 | 3028 / 6.70 / 23 | 1871 / 7.00 / 40 |
| seated: edges > 3x / > 2x / p99.9 | 131 / 1170 / 2.23 | 1138 / 4889 / 4.37 | 126 / 1142 / 2.23 |

pud2 v75 (Baynard's sculpt fix: inner-arm gap >= 4.5 mm below the armpit, upperarm / forearm blend 0.003 / 0.002),
export d1.npz, this branch: arms 80: side moving > 3 cm 0 %, edges > 3x 268 (> 2x 1445), p99.9 2.45x, max 15x;
seated: 101 > 3x (> 2x 1076), p99.9 2.21x. The armpit now stretches over the band instead of tearing.

Head (spikes/flesh_headturn.py, d1; "shoulder tops" = the body's own skin at x > 0.12, z 0.38-0.46):
| | main | now |
|---|---|---|
| shoulder tops: mean Head weight | 0.07 | 0.37 |
| turn 45: shoulder tops moving > 1 cm / edges > 3x / p99.9 | 12 % / 5731 / 7.28 | 65 % / 2902 / 5.60 |
| nod 30: shoulder tops moving > 1 cm / edges > 3x / p99.9 | 10 % / 1284 / 3.71 | 44 % / 258 / 2.82 |
Render (head_turn45_rows_main_now.png): main tears the neck open (a gash where the head ball meets the body);
now the turn is clean, spread into the shoulder tops with a light crease along the shoulder line. The head ball
holding the shoulder tops is what this neckless pig needs: kept.

## Open, ranked by what shows in the kart
1. Head turn: a light crease along the shoulder line (front view, where the turn's spread ends). Small; judge it in
   the kart before tuning.
2. The p99.9 2.45x arms-raised peak sits in the band's limb half (z 0.30-0.40); the band (JOIN_BAND / SPLIT) was
   swept on the welded v74 mesh, not re-swept on v75.

## Dead ends
- Bones reached through the solid only (WIP `solid_see`, straight path inside `field_at`): cleft hooves and a foot
  bone poking out of the toe lost their own bone (seated 131 -> 1138), changed troll / fox, and Puddles' side was
  fixed without it (soft flesh did that). Removed.
- (v74) The armpit tore because the mesh welded the inner arm to the side (gap ~1 mm, closed by a 7 mm blend):
  a sculpt fault, fixed in v75. Weights can't fix a weld; check the gap before the band.
- A symmetric seam band (split 0.5): side 4-7 % moving for p99.9 4.6-6; the body side must stay put.

## Commands
HIFIPUSHIE_HOME=~/dev/hifipushie/workspace capped uv run python spikes/flesh_measure.py pud2 <c3.npz> <outdir> <tag>
spikes/flesh_same.py <out.npz> examples/troll.json goblin fox_rig (each checkout), then --diff a b.
spikes/flesh_headturn.py pud2 <npz> <outdir> <tag> (head turn 45 / nod 30). Unit: tests/test_rig_join.py.
spikes/flesh_wire.py out.png a.npz [b.npz] (CENTER / SCALE / VIEWS env).

NEXT: coordinator lands flesh-visibility (suite passing); Baynard re-exports Puddles (v75) and judges arms raised and
a head turn in the kart.
History: this page + commits on flesh-visibility; ledger row C397.
