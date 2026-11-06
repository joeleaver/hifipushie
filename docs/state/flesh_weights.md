# Flesh weights (soft forms, the torso loft, a limb's seam): STATE 2026-11-06

Branch flesh-visibility (worktree .claude/worktrees/flesh-visibility), from main 769fbff2 (WIP c78e10d7 + the fix).
Asked for by Baynard Racing: Puddles' (pud2 v74) side rose with his raised arms. Not pushed; coordinator lands.

## What the tools hold now (rig.py, rig_join.py; their comments are the spec; ledger C384)
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

## Open, ranked by what shows in the kart
1. ARMPIT NOT SMOOTH: the mesh WELDS the inner arm to the side along a strip z 0.25-0.35 (x 0.18-0.20): there the
   sculpted gap is ~1 mm, not 5, and upperarm's 7 mm blend closes it. Raising the arm must tear that strip
   (sliver triangles, max 40x); weights can only choose who stretches. Fix is the sculpt: open the inner-arm gap
   past the arm's blend (or a smaller blend), then re-export; or a general meshing feature (a later layer's blend
   doesn't weld across air). Re-run flesh_measure after; expect the band to do the rest.
2. The headball (super, Head) now reaches the shoulder tops (175 verts at z 0.41-0.44 weighted to Head): check a
   head turn before Baynard relies on it.
3. No unit test of limb_join yet (proved on Puddles + the bit-identical check, spikes/flesh_same.py).

## Dead ends
- Bones reached through the solid only (WIP `solid_see`, straight path inside `field_at`): cleft hooves and a foot
  bone poking out of the toe lost their own bone (seated 131 -> 1138), changed troll / fox, and Puddles' side was
  fixed without it (soft flesh did that). Removed.
- A symmetric seam band (split 0.5): side 4-7 % moving for p99.9 4.6-6; the body side must stay put.

## Commands
HIFIPUSHIE_HOME=~/dev/hifipushie/workspace capped uv run python spikes/flesh_measure.py pud2 <c3.npz> <outdir> <tag>
spikes/flesh_same.py <out.npz> examples/troll.json goblin fox_rig (each checkout), then --diff a b.
spikes/flesh_wire.py out.png a.npz [b.npz] (CENTER / SCALE / VIEWS env).

NEXT: coordinator lands flesh-visibility after bin/suite; Baynard opens Puddles' inner-arm gap (open 1) and
re-exports; then judge the armpit raised.
History: this page + commits on flesh-visibility; ledger row C384.
