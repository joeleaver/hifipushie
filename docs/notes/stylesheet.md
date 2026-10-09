# hifipushie notes: stylesheet

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- Style sheets (`stylesheet.py`, `styles/*.json`, guide 5c; 2026-09-29, the golfer): the user's verdict was "stylization
  is an artistic decision, not just make the eyes bigger", so a style is a bundle of decisions. `spec.style.sheet` names
  a sheet whose partial spec (base.style incl. `simplify`/`simplify_keep`, head fit/pose defaults, part `subsurface`,
  paint layers on the `lm_*` landmarks, `style.look` lights) sits under the model: `store.load` resolves (model wins
  key by key, null deletes), `store.save` strips back to the model's own. `style_check` measures the sheet's `rules`:
  posed face ratios (`base.posed_measures`), the eye opening seen from the front (`base.eye_opening`: the skin runs
  on into the socket, so there's no edge loop; where the eyeball stands in front of the skin), iris share via
  `IRIS_SPOT` (a spot's front diameter is 1.83 x its width on the eyeball), skin HSV lit vs shadow sampled from a
  render in the sheet's look (sample off the stubble). GNM: `fit` gained nose_width/mouth_width/eye_seam, but the
  identity space can't make a short philtrum (chin/philtrum stuck at ~2.2): `head.pose` (least change of the
  regional expressions on landmark moves: smile, mouth_raise, lids, brows) does it. `look` lighting: `style.look`
  (suns, world, AgX look); a pink-warm bounce fill is what turns skin shadows red (hue shift 2 -> 5 deg). Paint
  `outline` (a closed polygon of landmarks seen along a view dir: lips, a beard border) replaced paths for lips and
  stubble: paths through the mouth crease seated into the seam and painted blobs at their control points. The
  written sheet: `workspace/character_renders/style_sheet.html`; renders s01-s0x there.

