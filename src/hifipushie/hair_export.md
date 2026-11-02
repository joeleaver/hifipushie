# Hair: game export (cards cut from the strands) and judging it

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

**Looking at strands**: `look_hair` renders the strands in EEVEE in seconds under a key, a fill and a rim light (`look.light`
   "salon"; "flat" = one sun). Judge in EEVEE (`engine="cycles"` path-traces them for reference only, 1-4 min: never the judging render). EEVEE draws every strand at least a pixel wide, Cycles at its true width:
   a groom that looks full in EEVEE and thin in Cycles needs more `count`, not more thickness.
**Export for a game**: `export_hair(name, out_dir, tiers=["hero", "main", "npc", "far"], save="sheet.png")`.
   Cards are CUT FROM THE STRANDS: the strands of a lock are clustered (hero: the groom's sub clumps; main: pairs;
   npc: whole locks; far: only hair off the head) and each card's centre line is the mean of its clump's strands,
   its width their spread, so cards wave, part and end where the hair does, and a lower tier has fewer, WIDER cards,
   not the same cards thinned out. Under them: the cap (the scalp's own chart, hairline painted in) and, in a tied
   tail, a solid core shaped by the tail's strands. Under a budget, fly-aways and baby hairs go first and coverage
   last. The groom itself goes out as Alembic (cm, Unreal) and USD (groom_* primvars).
**Judge the export as an engine draws it.** The sheet shows the strands, then every tier's GLB re-imported on
   the head under a hard alpha TEST and dithered, then the cards as solid quads by layer. The table per tier and
   view: `iou` / `bare` (strand silhouette the tier leaves uncovered), `value` and `sat` x the strands', `stamps`
   (detached rectangular blobs: a card's quad showing), `straight` (outline made of plank edges), plus WARNINGs for
   card vertices under the skin and wisps whose root lies on bare skin. To find what makes a fault, `look_hair(tier=
   "hero", debug=...)`: "layers" (solid quads by layer), "cap_only", "cards_only", "no_normal", "unlit". If a
   pattern survives "unlit" it is in the colour (atlas or vertex colour); if it survives "no_normal" but not
   "unlit" it is the cards' geometry and shading.

`export_asset` ships the character with its hair; `export_hair` is the hair alone. A short cut ships as shells
(guide(topic="hair_short")). The default tiers are main, npc, far: name "hero" for a close camera.

### Judging the cards
Judge game hair as the exported GLB re-imported into Blender and rendered in EEVEE set up like a game (the glTF importer's materials, alpha clip / hashed cards, no ray tracing).

## Limits today

Cards are still smoother than strands at bust distance (less strand-to-strand contrast), a few dark slits show
between cards on a combed-back top, npc cards lift at the crown like roof tiles, and the far tier is a helmet and a
solid tail without wisps. The atlas is a numpy raster of Blender-evaluated strands (alpha, per-strand id, depth,
root gradient, a normal from depth), not a Cycles bake; a short cut's cap has flow, depth and a normal from the
strands' heights, long hair's cards only a constant flow. Clearance is checked
against the head as the scalp's rays see it, not against a game's decimated skin. Loose long hair has no core
surface (only tied tails do): its coverage is the dense first layer.
