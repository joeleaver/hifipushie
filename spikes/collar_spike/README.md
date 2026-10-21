# Collar spike (2026-10-21): Simon's band + collar on a primitive neck

Thread page: docs/state/collar_spike.md. Outputs on /mnt/data/hifipushie/collar_spike/ (form_c0 pieces from
/mnt/data/hifipushie/drape_band1/form_c0.pkl). Superseded by spikes/shirt_spike (the real shirt on an average body).

- `wrap.py`: home-made position-based settle (crumples). Kept for the record.
- `bsim.py` + `bl_cloth.py`: Blender 5.1 cloth (flat rest shape key, wrapped start, sewing springs, pins). Every run
  crumpled once the seam springs pulled (b7-b10); fixes on the way: a stretch-free start and the body below the band.
- `geo.py`: no sim: each flat piece wrapped onto the developable surface its own outline makes (band on a cylinder,
  collar on its own cone, half-angle 11.6 deg): 0 % strain closed. Open by rigid turns at the hinge marks: stretches.
- `arap.py`: handles + hifipushie.correctives.arap; a1 open at ~12 % strain; the fall delaminated off the band
  (ARAP holds only the seam) until laid on it (a1L), which then dented.
Lessons that carried into the shirt: a flat piece's start pose must be stretch-free; the collar's own outline sets
its cone; hinge marks are where a band end turns; never take a side from a point at CF.
