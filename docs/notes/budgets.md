# Export budgets from evidence (2026-10-14, "budgets" agent)

Why: our triangle and texture budgets were invented by agents ("40k for hair", "LOD0 ~104k", LOD shares
0.5/0.25/0.12, "2048 atlas", the export guide's "~15k suits a hero creature; 5k for a crowd"). Joe never set any;
his only guidance is to target MAINSTREAM gaming PCs, not the dev laptop's iGPU. This note is the research and the
derivation; the machine-readable profile is `src/hifipushie/budgets.json` (loader `budgets.py`, test
`tests/test_budgets.py`); the product summary is in guide topic `game_export` (`guide_export.md`).

STATE: profile v1 written, not wired into any exporter. NEXT: the export owner plugs it in (see "Where it plugs in").

## Target: what "mainstream PC" means

- Steam survey 2026: RTX 3060, RTX 4060 and the 4060 Laptop take the top spots most months (~3.5-4% each); the
  RTX 5070 led in September. VRAM: 16 GB 25.9% vs 8 GB 25.3% (July). So: RTX 3060/4060 class, **8 GB VRAM** as the
  conservative memory target, 1080p-1440p at 60 fps with upscaling.
  ([PCGamesN July 2026](https://www.pcgamesn.com/steam/hardware-survey-july-2026-gpus),
  [TweakTown March 2026](https://www.tweaktown.com/news/110834/geforce-rtx-3060-reclaims-top-spot-and-rdna-4-finally-appears-in-steams-latest-hardware-survey/index.html),
  [Club386](https://www.club386.com/steam-hardware-survey-july-2026/); secondary reports of Valve's survey.)
- Digital Foundry put the PS5 GPU between an RTX 2070 Super and a 2080 Super / 3060 Ti in Valhalla
  ([TheFPSReview, 2020](https://www.thefpsreview.com/2020/12/05/ps5-gpu-performance-similar-to-amd-radeon-rx-5700-xt-according-to-assassins-creed-valhalla-analysis)).
  So a mainstream PC is roughly a PS5: current-gen console budgets carry over, PS4-era budgets are a safe floor.
  PC differs mainly in memory (8 GB card vs the console's unified 16 GB) and in shipping scalable LOD/texture tiers.

## Evidence (characters)

| Source (kind) | Game / engine, year, platform | Numbers |
|---|---|---|
| [Epic: MetaHuman platform + LOD specs](https://dev.epicgames.com/documentation/metahuman/platform-support-and-lod-specifications-for-metahumans) (primary) | Unreal 5, PC/Mac/mobile | Head VERTICES 24000/12000/6000/2500/1300/560/270/130; joints 713->26; 669 blendshapes at LOD0 only; skin influences 12,12,12,8,...,4. Body vertices 30500/7600/3350/1507 (4 LODs), correctives LOD0-1, influences 8->4. Card hair vertices 30000/15000/10000/3000/1500, then a hair mesh 500/250/100; facial-hair cards 15000/7000/3000/1000/500; strands 50k/25k. PC best LOD 0 (max texture 8192); phones best LOD 3 (2048). Above-neck components switch twice per body switch (LODSync). "A guide", not fixed. |
| [Epic: MetaHuman materials and textures](https://dev.epicgames.com/documentation/metahuman/metahuman-materials-and-textures) (primary) | Unreal 5 | Cinematic assembly bakes maps up to 8K; the performance assembly ("UE Optimized") caps at 2K. |
| [Crytek: Character Budgets (HUNT: Showdown)](https://cryengine.com/docs/static/engines/cryengine-5/categories/23756816/pages/23307976) (primary) | Hunt: Showdown, 2019, PC/PS4/XB1 | Main characters LOD0 35-70k, LOD3 5-8k; non-primary 25-35k / 4-5k; bosses 25-45k / 4-7k. Hero maps: face 1024, eyeballs 2048 (512 some), lashes/hair/beard/brows 512, hands 4096x2048, legs 1024; gear 256-2048. Non-primary: 1024 per part. "Combine textures to keep draw calls down." |
| [PlayStation Blog 2019](https://blog.playstation.com/2019/12/16/the-polygonal-evolution-of-5-iconic-playstation-characters/) (primary, devs quoted) | God of War 2018, PS4 | Kratos 80,000 polygons, 32,000 in the face; 140+ textures. Tekken 7 Kazuya head 2,800, 6,000 with hair and mouth. |
| [PlayStation Blog 2024](https://blog.playstation.com/?p=390251) (primary) | FF7 Remake (PS4) / Rebirth (PS5) | Cloud ~110k -> ~220k; hair about half the model; Red XIII ~120k (card fur); Buster Sword ~8k. |
| [Digital Production, Ryse making-of](https://digitalproduction.com/2015/07/20/gladiatoren-in-der-pipeline/), GamesBeat DICE coverage (secondary) | Ryse, 2013, Xbox One | Marius 85,000 triangles, 770 joints (500+ deforming, 260 facial), 230 corrective face shapes, 8 skin influences. |
| [VRChat avatar ranks](https://creators.vrchat.com/avatars/avatar-performance-ranking-system/) (primary) | VRChat, PC/Quest, many avatars per room | PC Excellent/Good/Medium: 32k/70k/70k triangles, 40/75/110 MB textures, 4/8/16 materials, 75/150/256 bones. Quest 7.5k/10k/15k/20k. |
| [Apple ARKit blend shapes](https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapelocation) (primary) | ARKit | 52 shapes. |
| [Epic: City Sample](https://dev.epicgames.com/documentation/en-us/unreal-engine/city-sample-project-unreal-engine-demonstration) (primary) | Matrix Awakens, 2022, PS5/XSX | Nearest crowd are full MetaHumans; far crowd are vertex-animated static meshes; "hundreds" on screen. No triangle numbers. |
| [Unity: Mesh LOD generator](https://docs.unity3d.com/Manual/lod/mesh-lod-generator.html) (primary) | Unity 6 | Each LOD ~half the indices of the previous. |
| [Epic: static mesh auto LOD](https://dev.epicgames.com/documentation/en-us/unreal-engine/static-mesh-automatic-lod-generation-in-unreal-engine) (primary) | Unreal 5 | LOD groups default 50%; walkthrough 75/25/12%. |
| [Epic: skeletal LOD ScreenSize](https://docs.unrealengine.com/4.26/en-US/API/Runtime/Engine/Engine/FSkeletalMeshLODGroupSettings/ScreenSize/index.html) (primary) | Unreal | Screen size = projected bounding-sphere diameter / screen max dimension; hysteresis. No default values documented. |
| [Crytek: Texels Per Meter](https://www.cryengine.com/docs/static/engines/cryengine-5/categories/23756816/pages/52199429) (primary) | Crysis 3, Ryse | Most assets ~512 texels/m; hero assets (main characters, cutscene assets) get more; presets 256/512/1024. |
| Polycount / ArtStation / Rookies (anecdote) | portfolio pieces | Hair cards 20-28k on 45-70k portfolio characters; "50k for hair" one forum opinion; HZD Aloy ~100k hair (forum, unverified). Recorded, not used. |

Unit caveat: MetaHuman gives render vertices. Closed skinned meshes run ~1.5-2 triangles per render vertex (UV
seams split vertices); card strips ~1. So MetaHuman LOD0 is an ESTIMATED ~150-200k triangles head+body+cards.
"Polygons" in the PlayStation posts are not defined as triangles.

## Derivation

Roles and how many share the screen (an assumption; say so when a game differs): hero 1, main NPCs up to 4,
secondary up to ~15, crowd ~100 (beyond ~30 of them, vertex-animated meshes, as City Sample).

| Role | LOD0 default (range) | head | body | clothing | hair cards | eyes/mouth/lashes | acc. | maps | face / body px/m | materials | LODs |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hero | **100k** (60-150k) | 25k | 15k | 25k | 25k | 5k | 5k | 2048 head, 2048 body+clothes, 2048 hair, 512 eyes | 2048 / 1024 | 6 (max 8) | 4 |
| main NPC | **50k** (35-70k) | 15k | 8k | 12k | 10k | 3k | 2k | 1024 head, 2048 body+clothes, 1024 hair | 1024 / 512 | 4 (max 6) | 4 |
| secondary NPC | **20k** (12-30k) | 5k | 4k | 5k | 4k | 1k | 1k | one 2048 atlas | 512 | 2 (max 3) | 4 |
| crowd | **6k** (3-10k) | 1.5k | 1.5k | 1.5k | 1k | 0.3k | 0.2k | one 1024 atlas, shared | 256 | 1 (max 2) | 3 + vertex-anim |

Reasoning:
- Hero 100k: the hero range runs from Hunt's 35-70k (PS4-era PC game) through Kratos 80k and Marius 85k to
  Cloud's 220k on PS5 (half of it signature hair) and MetaHuman's ~150-200k estimate. A mainstream PC is about a
  PS5, but Cloud is one stylised outlier and MetaHuman LOD0 is Epic's top PC tier; 100k is the conservative middle,
  with 150k allowed for a hero whose look is the hair or the costume.
- Head 25k: Kratos' face 32k (PS4); MetaHuman's 24k head vertices (estimate 35-45k triangles, incl. eyes and mouth
  interior). 25k is conservative and holds a close-up with normal maps carrying wrinkles and pores.
- Body 15k: only what clothing doesn't cover is exported; MetaHuman's bare body is 30.5k vertices.
- Hair cards 25k: MetaHuman cards are 30k vertices at LOD0 (+15k facial hair). Card triangles are cheap; overdraw
  is the cost (alpha-tested layers over the head). 50k is the top of the range, for hair that IS the character.
- Clothing 25k and eyes/mouth/lashes 5k: THIN (no per-garment or per-lash source found); remainder of the total.
- Main NPC 50k: Hunt's bosses / non-primary 25-45k, VRChat's PC "Good" cap 70k with many in a room; dialogue
  close-ups keep the head at ~MetaHuman LOD0-1, the rest about halved.
- Secondary 20k: about MetaHuman LOD2; below Hunt's 25-35k because many share the screen; VRChat "Excellent" 32k.
- Crowd 6k: Hunt's far LOD3 (4-8k), MetaHuman LOD3 (Epic's phone tier), VRChat Quest 7.5-10k.
- LOD ratios: 1 / 0.5 / 0.25 / 0.12 is SUPPORTED (Unity halves per level; MetaHuman head 1/0.5/0.25/0.1; UE 50%
  groups). Below the neck MetaHuman drops faster: 1 / 0.25 / 0.11 / 0.05, and switches half as often. Hair cards
  1 / 0.5 / 0.33 / 0.1 / 0.05, then a hair mesh. Morph targets (face shapes) on LOD0 (hero: LOD0-1) only; correctives
  to LOD1; skin influences 8 on the hero face, 4 elsewhere and at far LODs.
- Switch screen sizes 1 / 0.5 / 0.25 / 0.12 (crowd 0.25 / 0.12 / 0.06): DERIVED, no engine documents defaults. For
  curved surfaces the triangles needed for a fixed error in pixels scale about linearly with projected size, so
  halving triangles per halving of screen size keeps the pixel error constant. Tune with a distance test + hysteresis.
- Textures: Epic's own performance pipeline caps MetaHuman at 2K per map; Hunt's hero face is only 1024 (eyes 2048,
  hands 4096x2048). Crytek: 512 px/m for the world, heroes more. Chosen: hero face 2048 px/m (~0.5 mm/texel), body
  and clothes 1024 px/m; main NPC 1024 / 512; secondary 512; crowd 256. Memory: a 2K set of basecolor + normal + ORM,
  BC-compressed with mips, is ~16 MB; a hero's four sets ~60-70 MB, under VRChat's 75 MB "Good" and fine on 8 GB.
- Materials: VRChat 4/8; Crytek "combine textures"; hair needs its own alpha-tested material, eyes often their own.
- Skeleton: Mixamo-compatible body (~65 bones, commonly cited, not from a primary source) + twist bones; face by
  ARKit's 52 shapes (MetaHuman / Ryse use joint faces with hundreds of joints, which glTF consumers rarely want).

## Props, vegetation, terrain (brief)

- Hero prop 8k (3-15k), 2048, 1024 px/m (Buster Sword ~8k on PS5; Hunt gear 256-2048). Ordinary props: size by
  geometric error; 512 px/m; LODs 1/0.5/0.25/0.12 (UE groups, Unity halving). THIN on counts.
- Trees: THIN. Default 15k (5-30k) LOD0, 4 LODs ending in a billboard, 3-5 variants per species. SpeedTree's GPU
  guidance: LOD is the biggest lever, trim interior leaf triangles (overdraw), keep draw distance short. One
  Polycount anecdote: trunk ~570, leaves 12k+. Guerrilla's HZD vegetation talk is behind GDC Vault.
- Terrain: Unreal's recommended landscape sizes (505..8129 vertices per side), max 1024 components, each section a
  draw call. Our tile budgets (12000 / 3000 / 800 per LOD) have no external source to check against.

## Where the evidence is thin

- Clothing per garment, lashes/brows/teeth, hair-card counts in shipped games (only MetaHuman and FF7), crowd triangle
  counts (only Hunt LOD3 and MetaHuman LOD3), all LOD switch distances (no engine publishes defaults), vegetation and
  terrain triangle counts. Naughty Dog, Insomniac, Guerrilla and CDPR numbers are in GDC Vault talks we can't read.

## Against our current exports (Tess, 2026-10)

Tess: head 23k, body 17k, hair cards 40k, jeans 9.4k, sweater 6.9k, lashes 4.9k (~101k); one 2048 atlas, face ~0.4
mm/texel; LOD shares 0.5/0.25/0.12.
- Total ~101k = the hero default. Head 23k and body 17k are on target.
- Hair 40k: inside the hero range (15-50k) but 1.6x the default; overdraw, not triangles, is the risk. 25k default.
- Clothing 16.3k: under the 25k allowance (fine; a knit or folds could use more).
- Lashes 4.9k alone fill the whole eyes/mouth/lashes allowance (5k). Likely over (thin evidence; MetaHuman doesn't list).
- One 2048 atlas for everything: the face at ~0.4 mm/texel (~2500 px/m) is at/above the hero face target, so the
  body and clothes get far less than 1024 px/m. The profile wants separate sets (head 2048, body+clothes 2048,
  hair 2048, eyes 512).
- LOD shares 0.5/0.25/0.12: supported for the head and hair; below the neck the evidence (MetaHuman) drops faster
  (0.25 at LOD1). Face shapes should stop after LOD0/1.
- Product defaults that were invented: `export_asset(triangles=15000)` and the guide's "~15k hero creature / 5k
  crowd" (a 15k hero is a PS3-era budget; the guide now points at the profile); `hair.CARD_TIERS` hero 40k / main
  16k / npc 6k / far 1.5k (hero above the default; main and npc near it).

## Where it plugs in (for the export owner)

- `server.export_asset(triangles=15000, texture=2048)` -> take `role=` (default "hero") and fill `triangles` /
  per-part `triangle_weight` and `texel_density` from `budgets.role(role)`; explicit arguments still win.
- `hair.CARD_TIERS[...]["triangles"]` -> `budgets.triangles(role, "hair_cards")`; card LODs from
  `budgets.lod_ratios("hair_cards")`.
- Character LOD chain (the assembly's 0.5/0.25/0.12 shares) -> `budgets.lod_ratios(part)` per part, face shapes on
  LOD0(-1) only, `characters.lod_screen_size` written into the export json as switch hints.
- `veg_export.LODS` / `veg_tools.export(triangles=)` and terrain tile budgets: keep, mark as unsourced (thin).
