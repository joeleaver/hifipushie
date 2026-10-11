# The GNM driving manual

The manual itself lives in src/hifipushie/gnm_driving_guide.md (guide topic "gnm_driving"; `gnm_controls(phrase=...)`
returns its matching entries, block_in_step puts them in its reply for the `seen` text; structured entries in
src/hifipushie/gnm_manual.py). This file only records how it was made and tested.

- v1 (2026-10-10): written from the baseline drivers' misses on set s1 (no manual: 2 / 14 pass) against the oracle,
  the couplings table (spikes/gnmdrive/couplings.py) and the mm readouts (readouts.py).
- Tested on set s2: the same 14 pairs, two fresh driver groups: without the manual 3 / 14, with v1 7 / 14.
- v2: the v1 drivers' corrections (ears, eye unit height, compounding free moves, step sizes once close, head_size and
  the muzzle move lengthening the chin, philtrum! needing ~2.5 sd, forehead_slope! judged against the nasion,
  relief:cheeks / sculpt:jawline / sculpt:parotid for the cheek and lower-face widths found by finder.py), then tested
  on set s3 (see docs/notes/gnm_atlas.md "## gnmdrive").
