# Godot hair cards: `hair_cards.gdshader`

A spatial shader for the hair card GLBs `export_hair` writes (`<name>_hair_<tier>.glb` + the shared `hair_*.png` beside
them). It is a REFERENCE: checked in this folder's scripts (look2.gd, Godot 4.7), not used in any game yet.

Why it exists: Godot's importer gives the cards a StandardMaterial with one GGX anisotropic lobe and ignores the aux
texture, so the hair reads as a uniform fine hatch ("steel wool"). Shipped real-time hair (UE groom cards, the
Scheuermann / Kajiya-Kay model, the EA / Sucker Punch / Naughty Dog talks) shades a strand with two highlights
shifted along it, a wrapped diffuse, and the hair's own depth (root, clump); that is what this does.

## Textures (all from the export folder; generate mipmaps)
| uniform | file | notes |
|---|---|---|
| `albedo_tex` | `hair_basecolor.png` | sRGB, straight alpha (alpha = coverage). Multiplied by COLOR_0 (the cards' root-to-tip ramp, a value per lock / card): the shader reads `COLOR` itself, no `vertex_color_use_as_albedo` needed |
| `normal_tex` | `hair_normal.png` | tangent space against the GLB's TANGENT |
| `aux_tex` | `hair_aux.png` | linear: R = root gradient (1 at the root), G = a value per strand, B = depth in the clump (0 deep), A = alpha |
`hair_orm.png` and `hair_flow.png` are not needed by this shader (the strand direction comes from the mesh's
TANGENT: its bitangent, the atlas's v, runs root to tip).

## Parameters (defaults in the shader)
- `alpha_cut` 0.33 (= the GLB's alphaCutoff), `a2c_edge` 0.3: alpha-to-coverage; turn MSAA on (2x or 4x). Without MSAA
  it is an alpha test; cards write depth like opaque geometry, so there is no sorting.
- `root_shade` 0.35, `inner_shade` 0.35, `value_vary` 0.12: the hair's own shade from aux R / B and per-strand value.
- `wrap` 0.45 (wrapped diffuse), `shadow_soft` 0.55 (share of the shadow map kept: hair lets light through).
- `spec1_*` (white, tight, shifted toward the tip by `spec1_shift`) and `spec2_*` (tinted by the albedo, broad,
  shifted the other way), `shift_jitter` 0.3 (aux G breaks the bands into strands).

## Back faces (the black fringe)
The cards are two-sided with ONE normal for both faces, bent toward the hair volume. Godot flips NORMAL on the back
face of a cull-disabled mesh; that lit every card seen from behind (outline, over the ears, the hairline) as if from
inside: a dark ragged fringe. The shader un-flips NORMAL / TANGENT / BINORMAL when `!FRONT_FACING`. Any engine
material for these cards must do the same (the export's recipe: "do not flip them on back faces").

## Use
```gdscript
var sm := ShaderMaterial.new()
sm.shader = load("res://hair_cards.gdshader")
sm.set_shader_parameter("albedo_tex", basecolor)   # with mipmaps
sm.set_shader_parameter("normal_tex", normal)
sm.set_shader_parameter("aux_tex", aux)
mesh.surface_set_material(0, sm)
```
`look2.gd` does exactly this for every surface of a hair GLB (`kk` mode; `std` = Godot's own material for comparison),
renders given cameras (`gdcams.json`, incl. an off-axis frustum for a fitted photo camera) and writes PNGs.
Run it through `/mnt/data/hifipushie/bin/godot-quiet` (no window on the desktop), with a timeout.
