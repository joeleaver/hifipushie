# Game-ready export

Read guide(topic="") (the playbook) first: describe the reference, then work big to small.

### Game-ready export

`export_asset(name, out_dir)` writes a GLB plus every map (per atlas) as its own PNG (basecolor, normal, roughness, metallic,
specular, ao, orm, 16-bit height) and a json with the conventions. Nothing is baked from a high-poly mesh: every
texel is projected onto the exact surface, so detail the low poly drops (warts, wrinkles, creases) lives in the
normal and height maps, and paint is as sharp as the texture. Faces buried inside another part (skin under
solid clothing, eyeball backs) are removed first.
- Give materials their numbers in paint: `parts.<p>.roughness/metallic/specular` for defaults, layers for
  variation (wet lips `roughness: 0.2`, metal buckle `metallic: 1, roughness: 0.3`). The clay views don't show
  these; the exported GLB in EEVEE does.
- Budgets follow from ROLE and TARGET: state them, never invent them. The default target is a mainstream gaming
  PC (RTX 3060/4060 class, 8 GB VRAM, 1080p-1440p at 60 fps, about a PS5). The profile (`budgets.json`, every
  number with its sources; `hifipushie.budgets` reads it) for characters, LOD0 triangles:

  | role | LOD0 (range) | head / body / clothing / hair cards / eyes+lashes | maps | face / body px/m |
  |---|---|---|---|---|
  | hero (player, close-ups) | 100k (60-150k) | 25k / 15k / 25k / 25k / 5k | 2K head, 2K body+clothes, 2K hair | 2048 / 1024 |
  | main NPC (dialogue) | 50k (35-70k) | 15k / 8k / 12k / 10k / 3k | 1K head, 2K body+clothes, 1K hair | 1024 / 512 |
  | secondary NPC | 20k (12-30k) | 5k / 4k / 5k / 4k / 1k | one 2K atlas | 512 |
  | crowd | 6k (3-10k) | 1.5k / 1.5k / 1.5k / 1k / 0.3k | one shared 1K atlas | 256 |

  LODs: 1 / 0.5 / 0.25 / 0.12 of LOD0 above the neck and for props; below the neck 1 / 0.25 / 0.11 / 0.05; hair
  cards end in a hair mesh. Face shapes on LOD0 (hero LOD0-1) only. Switch screen sizes 1 / 0.5 / 0.25 / 0.12 are a
  starting point to tune in the engine. Hero prop ~8k at 1024 px/m; other props 512 px/m.
  To override, say the role and the target (e.g. "secondary NPC on a handheld: 10k") and pass the numbers:
  `triangles=`, `parts.<p>.triangle_weight`, `parts.<p>.texel_density`, `texture=`. `triangles` counts drawn
  triangles (a prefab once per instance); a furnished building runs 50-100k. `texture=1024` for quick checks.
- Prefabs with 2+ instances export once: one mesh (a primitive per part) and one set of texels, placed by a
  glTF node per instance, meshed in a box of their own (finer than the scene's voxel when small). Each is baked
  at its first instance (its paint, AO and sky as it stands there), so every chair gets that chair's grime. When
  copies must differ (one chair by the fire, sooty), set `prefabs.<p>.export: "unique"` or make it a second
  prefab. `lumpy`/`chips` on prefab elements are the same on every instance, in look too.
- Triangles follow geometric error, not area: one decimation of all parts together decides each part's share,
  so flat walls get few and small round things (eyes, pots, pillows) enough; every part gets at least
  max(300, triangles/100). Steer it per part with `parts.<p>.triangle_weight` (x its share).
- Texels: every part gets the same texels per metre unless `parts.<p>.texel_density` says otherwise (2 = twice
  as sharp, four times the atlas area). `parts.<p>.texel_focus: [{"at": "head", "radius": 0.15, "density":
  2.5}]` gives a region more (a character's face: e.g. 1.5 -> 0.8 mm/texel at 1024).
- Read the log: the atlas fill and mm/texel per part. A creature fits one atlas (troll ~58% filled); a big
  environment doesn't (the cabin's 380 m^2 of logs and shingles gives ~30 mm/texel on one 1024 atlas). For
  environments ask for a density: `export_asset(texel_density=512, texture=2048)` opens as many atlases as it
  takes (texels per metre x each part's `texel_density`; 512/m = 2 mm/texel, for close interiors; 256/m for
  walls seen from a few metres), each the smallest power of two that holds its parts, a prefab's parts together.
  `parts.<p>.atlas: "interior"` still pins a part to a named atlas; `atlases=n` is the manual split.
  A part too big for one atlas at that density (a whole log wall, a roof, the ground) is cut into slabs along
  its longest side ("roof~0", "roof~1", ...: the log says so), an atlas's worth each; `hide=["roof"]` hides all
  of them. A prefab can't be split: the log names one that won't reach the density.
- Density costs texels, texels cost time and file size: the furnished four-room cabin (100k triangles) at 256/m
  is ~40 atlases of 2048 (250 MB GLB) and ~40 min; at 128/m about a quarter of the texels. Low poly ~8 min,
  per-atlas projection most of the rest, the Cycles paint/AO bake a few minutes. Progress goes to
  workspace/<model>/progress.log.
- Detail thinner than about a voxel at the export resolution (22 mm shingles at 256 across a 6 m cabin) makes
  a broken high mesh: inverted faces and normals the bake can't use. Those texels keep the low-poly surface
  (the log says how many per part). Build at a higher resolution or make the detail thicker.
- Judge the preview and close-ups (`asset.preview` focus/zoom; `hide=["roof", "walls"]` to see inside) for
  seams and the normal map's read.
