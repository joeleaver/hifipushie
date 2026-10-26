# hifipushie playbook

hifipushie models characters, creatures, props and environments as a skeleton (joints + bones) with SDF blobs hung
on it, smooth-blended into one surface, meshed and rendered for you to look at. Realistic humans, hair, cloth,
terrain, plants and clutter have their own tools and guides. Read this once before modelling; come back to the
section you're in.

Conventions: metres, Blender axes, Z up; a creature FACES -Y and its left side is +X. Names ending ".L" are mirrored
to ".R" across X: store only the centre line and the left side. Every change is checkpointed (history / revert).

Tools: a small core is native; every other tool (plan, scene, export, human, likeness, hair, cloth, terrain, plants,
clutter) runs through `call_tool(name, args)`. `find_tool("<job>")` names the tool with its parameters and an
example call; guide(topic="<tool>") gives any tool's full text.

Sub-topics of this playbook (guide(topic=...)): `spec` (the spec format: joints, bones, blobs, kits, anatomy, parts,
seated joints, strokes, paint, prefabs; the workflow in brief), `looking` (seeing and showing: views, close-ups,
hiding and clipping, cameras), `blockout` (blockout pitfalls, strokes, parts), `props` (props and environments),
`style` (stylised models and style sheets), `story` (history and weathering), `paint` (paint layers, masks,
materials, images), `game_export` (export_asset), `rigging` (the export rig). Domains: `block_in` (a person's head
from pictures), `human`, `likeness`, `skin`, `hair`, `cloth`, `terrain`, `vegetation`, `clutter`.

## Which path

| Subject | Start from | Read |
|---|---|---|
| A realistic human | `spec["base"]` (MakeHuman body + GNM head, by parameters), never blobs | `human`, then `block_in` for a person from pictures |
| A real or drawn person from pictures | the artist block-in (THE DEFAULT) | `block_in` |
| A creature, a cartoon character | skeleton + blobs + kits (hand, face, foot) + strokes | this playbook, `spec`, `blockout` |
| A prop, a building, a room | prefabs, arrays, hard solids, `walls` | `props` |
| Hair / clothes / skin | their own tools on the model | `hair`, `cloth`, `skin` |
| Terrain, trees and plants, clutter | their own tools | `terrain`, `vegetation`, `clutter` |

## Stage 0: describe the reference first (every subject)

Before choosing a template, kit, preset or default, write what the reference shows, as items you can measure on your
model, with a tolerance; mark what no reference shows as inferred. At least:
1. **What it is and its style**: realistic, or stylised and how (which proportions are pushed, what is simplified,
   how it's shaded). "Stylised" is ambiguous: name the reference look.
2. **Proportions and silhouette**: overall size (from something of known size), heights of landmarks in head
   heights or metres, widths and depths at a few sections, the silhouette from front and side.
3. **Big masses and their structure**: how the main forms join, where they bend, which way they lean.
4. **Secondary forms and details** that identify it (and which ones matter at the distance it's seen from).
5. **Materials, colour, history**: surfaces, wear, age, what has happened to it.
Then pick the starting point from the description and say which item justifies it. A clean result that doesn't
match the description is wrong, however good its numbers.

## The stages (check and look after each)

| # | Stage | Tools | Gate |
|---|---|---|---|
| 1 | Plan | `set_plan` (front / side outlines, landmark heights, 3-4 sections), `set_reference` | Proportions match the description: fix them here, where it costs one edit |
| 2 | Blockout | `put_model`, kits, `fit` (against the plan), `check` | Silhouette IoU > 0.95, sections within ~5 %, landmarks on their joints |
| 3 | Secondary forms | strokes (`look(strokes=True)`, `shading="raking"`) | Masses read; the silhouette barely moved |
| 4 | Detail | strokes with repeat / scatter, in close-ups | Details at the right scale, judged in close-ups |
| 5 | Parts | parts (eyes, teeth, clothing shells), seated joints | Each part its own mesh, nothing cutting into another |
| 6 | History | `spec["story"]`, weather ops, lumpy, chips | `check`'s realism audit: nothing reads pristine (restraint for realism) |
| 7 | Paint | `spec["paint"]`, materials | Flat colour and each mask alone read right |
| 8 | Export | `export_asset`, `rig` | The exported GLB in Blender EEVEE set up like a game reads as the model |

Big to small, like an artist: get each stage right (against the reference and a measured gate) before the next.
Detail put on a wrong mass hides the problem and is thrown away when the mass changes. Without a plan: put_model ->
look -> edit_model in small batches -> look.

## Craft rules (each once; details in the sub-topics)

Seeing
- Judge from the right view: clay for the overall read, `shading="raking"` for masses and planes,
  `shading="curvature"` for blobbiness and defects, `strokes=True` for placement before form. Faces, hands and every
  detail in close-ups (`focus` + `zoom`), never from a full-body render.
- Tool images may be invisible to the person you work with: `save=` and share the file at each milestone, with a
  short honest read of what works and what doesn't.
- Renders mislead about thickness: `measure` gives cross-sections.

Forms
- A joint no bigger than the bones meeting there (or it shows as a ball); chains (tails, tentacles) in one `group`
  with a small `join`.
- Strokes are broad and shallow, taper to 0 at the ends, creases at least 3 voxels wide, addressed from the skeleton
  or kit features, never raw coordinates.
- Separate digits, tusks and horns are geometry (bones, kits, seated joints); strokes only push skin in and out;
  strokes can't fix proportions.
- Anything with its own material is its own part.
- Nothing made or grown is uniform: arrays get `vary` / `jitter` / `flip`; identical copies at even spacing read as CG.

Surface
- Paint last, broad to fine; weathering from the surface (mask stacks), each effect its own layer, looked at alone.
- Restraint: weathering is noticed second, after the form. Push it until it reads, then back off by a third.
- Judge the export as the GLB re-imported into Blender EEVEE set up like a game (its own materials, alpha clip /
  hashed cards, no ray tracing).

## Self-review loop (every round)

1. Render yours at the reference's framing (same view, same distance; `set_reference` + `compare` for outlines),
   and put it BESIDE the reference, region by region (silhouette, each big mass, secondary forms, details, surface).
2. List what reads wrong, concretely (where, what, how far off; measure where you can). Mark each MAJOR (wrong
   proportion, silhouette, structure or style; a visible defect) or MINOR. Order: form before material, material
   before colour.
3. Fix the worst MAJOR at its stage (often the plan or the blockout). Re-render.
4. Repeat until no region has a MAJOR. Then the next stage.
Argue a MAJOR away only with evidence that the reference doesn't show it.

## When something looks wrong

- Don't guess and pile on fixes. Isolate: render the region with `shading="curvature"` and remove suspects one at a
  time (history makes it cheap) until the defect goes.
- Stripes or speckle across a stroke: its path crosses busy features or it is deep for its width: widen it, make it
  shallower, or move the path.
- Cracks and zigzags: something is thinner than ~2 voxels at that resolution: widen it or look closer.
- A flat grey cap at the edge of a close-up is the close-up box's cut, not a hole.

## Common mistakes

| Mistake | Instead |
|---|---|
| Starting from the nearest template / preset / default | Describe the reference first; choose from the description |
| Fixing proportions with strokes or detail | Back to the plan or blockout |
| Judging a face or hand from a full-body view | Close-ups |
| Realistic humans built from blobs and kits | `spec["base"]` + the block-in |
| Speculative fixes stacked on a defect | Isolate it first |
| Heavy-handed weathering | Restraint: a shift of tone, centimetres of sag |
| Calling it done on numbers | The self-review beside the reference |

## 4d. Realistic humans start from a base, not blobs

Start from `spec["base"]`: a MakeHuman body (parametric age / weight / muscle / height) with a GNM head (realistic
faces, identity and expression components), e.g.
`"base": {"body": {"source": "makehuman", "age": 45, "weight": 0.72, "muscle": 0.3, "height": 1.78}, "head":
{"source": "gnm", "scale": 1.12}, "eyes": "eyes"}`. Shape it with parameters (body macros, `base.head` fit / regions /
pose / shape, a style sheet), not sculpting. A person from pictures: the artist block-in (guide(topic="block_in")).
Feature detail, skin, hair and clothes come after it, on the head it produces. `check` warns when a spec looks
humanoid but has no base.

## Resolution and time

- `look` at 160-200 while blocking out, 256-300 for full-body judgement, close-ups at 200-240.
- Batch several edits per `edit_model` and look once, like a sculptor stepping back.
