# Collar from the pattern's outline (2026-10-29): Joe "the best it's ever looked ... we've finally nailed the shape"

No simulation, no stretch: band + collar built as CHAINS of the pattern's own link lengths; only bends are chosen.
Data / renders: /mnt/data/hifipushie/folds_ab/D/ (refs in ../refs). Body / pattern: shirt_spike v1 (wf_simon, Simon).

## Recipe (best: open collar Q5S; closed collar O15S)
1. `build2.py` closed base (smooth symmetric neckline, back rested on the neck base) - used as the start.
2. Closed outline: `outline.py O15 '{"bend":0.4,"nfev":300,"stiff":10,"rest":0.1}'` (~20 s).
3. Open band alone: `band_open.py U1 '{"relax":1.0,"swing0":55,"ramp":0.12,"nfev":300,"bend":8}'` - the band keeps its
   pressed curve round the back and relaxes STRAIGHT past the side neck (an open U); start from a swung-open guess.
4. Collar on the open band: `outline.py Q5 '{"bend":0.4,"nfev":300,"stiff":10,"rest":0.1,"band_from":"U1",
   "front_stiff":4,"edge_stiff":6,"back_full":true}'`.
5. Surfaces between the fixed chains: `surfaces.py Q5` (Laplace fill on each piece's pattern mesh); look: `lookc.py Q5S plain`.

## Rules learned (each from a visible fault)
- Lengths are given (hard), only bends are free; never place points and measure lengths after.
- Stiff parts keep their own shape (C259): rest on high points, can't sink in, never "follow the surface".
- Lines across a piece: may shorten where the cloth curves (leaves), full width where it lies flat (the fall on the band at the back).
- Point corner triangles rigid. Worn straight: mirror symmetric. Outside faces out; the band stays upright.
- The band and collar edges are stiff ALL along (front-only stiffness left a wobble: the points need room to come forward).
- Open state = the stiff band/collar's own shape when unbuttoned; the soft fronts hang from it (not the other way round).
- Look at the piece alone, large, 4 sides, curves drawn; judge against the reference photos for the IDEA of the style.

## Open
Dimples along the top fold; the leaf's front corner at the band end is mangled; fronts not yet hung from the band.

LIBRARY NOW (2026-11-01): `src/hifipushie/chain_net.py`, `chain_garment.py`, tools chain_garment / look_chain; these spike scripts are history.
