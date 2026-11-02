# Hair: short cuts ship as shells (crops, short back and sides)

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

A cut with a mean lock under 6 cm (`hair.MASS_MIN`) is not built like long hair. Cards cut per clump read as torn paper
at bust distance, and a baked cap with sparse cards was rejected the same way: **shells won, across 8 rounds** on the one short
groom tried (Garrett sh1-8). That is one head, and the result is not approved.

1. **Groom it as strands**: `hair_from_reference` writes a combed short cut, or `groom_hair(name, groom={"loose": {...}})`
   with a recipe from `hair_loose`: lengths by region, wave 0, fine dense strands. Judge the strands first.
2. **Ask for shells**: `edit_model(name, [{"op": "set", "kind": "hair", "name": "export", "value": {"style": "shells"}}])`.
   Cards stay the export default; `groom_hair`'s reply says this when the cut is short. On a longer groom the key is
   ignored and the tools warn.
3. **Judge it**: `look_hair(name, tier="main")` beside the strand render, from every side. The cap wears strands combed
   along the lay, alpha-tested shells stand over it, cards only along the hairline.
4. **Add the edge fade**: the nape and sideburns thin into the skin as paint, not geometry: `hair.export.fade`
   `{"edge": [[fa, el], ...], "fade_mm": [[fa, mm], ...], "trim": [[fa, el], ...]}` (fa = deg from the front, el = deg
   round the scalp centre). The trim cuts the mesh hair up to meet the paint, or the fade ends in a hard block. Export
   writes the map and bakes it into the head's base colour.
5. **Ship it**: `export_asset(name, out_dir, role=...)`.

`hair.export.shells`: `{"heights": [.62, .85], "base": .4, "cover": 5, "tiers": {"hero": 2, "main": 2, "npc": 1, "far": 0}}`
(the defaults: heights and base are shares of the hair's height over the scalp; tiers = shells per tier).

Limits: the winning look also used tuned module constants that are NOT defaults yet, so a default shell export is
unjudged. Garrett's open faults were a short nape fade, a shelf behind the ear and a scraggly front hairline. Practice
and sources: guide(topic="hair_background").
