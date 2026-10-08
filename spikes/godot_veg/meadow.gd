extends SceneTree
# A meadow of small plants as pushieworld scatters them (groundcover.gd, note 102): a 0.9 m grid with jitter within
# 32 m of the eye, LOD 0 within 12 m and the coarsest LOD past it, thinning to 30% at 32 m, flowers 12% of the cells,
# each clump turned and scaled 0.8-1.3. Mode "full" thins each kind to the game's budgets (1,200 triangles a clump
# near, 300 far) as the game does with the full plants; "gc" draws the groundcover grade unthinned.
# Run it in a project holding a COPY of the game's plant shaders (game/style/*.gdshader*, style_map / style_rect /
# style_ambient / wind as shader globals): the plant lit by the style's own light (cel bands, ambient tone).
#
#   godot --path <project> -s <this> -- <out prefix> <style 0 realistic|1 blobby|2 cartoon|3 pixar|4 anime> <season>
#        <mode full|gc> <grass dir> [<flower dir>]
# Writes <prefix>_eye.png (standing, 1.7 m) and <prefix>_high.png (6 m up), prints triangles and clumps drawn.

var CELL := 0.9  ## env MEADOW_CELL: denser cover (the groundcover grade spending the budget the full plants were thinned to)
const RADIUS := 32.0
const NEAR := 12.0
const FAR_SHARE := 0.3
const FLOWER_SHARE := 0.12
const NEAR_TRIS := 1200.0
const FAR_TRIS := 300.0

var SHADER: Shader
var SHADER_DOUBLE: Shader


func rnd(cx: int, cy: int, salt: int) -> float:
	return float(hash(Vector3i(cx, cy, salt)) & 0xffff) / 65535.0


func tex(dir: String, ref) -> Texture2D:
	if ref == null or not ref is Dictionary or not ref.has("file"):
		return null
	var img := Image.load_from_file(dir.path_join(ref.file))
	if img == null:
		return null
	img.generate_mipmaps()  # (as a game imports a texture used in 3D)
	return ImageTexture.create_from_image(img)


func load_plant(dir: String, season: String) -> Dictionary:
	var stem := ""
	for f in DirAccess.get_files_at(dir):
		if f.ends_with("_seasons.json"):
			stem = f.trim_suffix("_seasons.json")
	var js: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join(stem + "_seasons.json")))
	var slot_of := {}
	var vcol := {}
	for slot in js.slots:
		slot_of[js.slots[slot].material] = slot
	for e in js.slot_list:
		vcol[e.slot] = "COLOR_0" in e.channels
	var lods: Array = []
	var k := 0
	while FileAccess.file_exists(dir.path_join("%s_LOD%d.glb" % [stem, k])):
		var doc := GLTFDocument.new()
		var st := GLTFState.new()
		doc.append_from_file(dir.path_join("%s_LOD%d.glb" % [stem, k]), st)
		var sc: Node = doc.generate_scene(st)
		var parts: Array = []
		var tris := 0
		var top := 0.0
		for mi: MeshInstance3D in sc.find_children("*", "MeshInstance3D", true, false):
			var mesh: ArrayMesh = mi.mesh.duplicate()
			top = maxf(top, mesh.get_aabb().end.y)
			for s in mesh.get_surface_count():
				tris += mesh.surface_get_array_index_len(s) / 3
				var base := mesh.surface_get_material(s) as BaseMaterial3D
				if base == null or not slot_of.has(String(base.resource_name)):
					continue
				var slot: String = slot_of[String(base.resource_name)]
				var spec: Dictionary = js.seasons.get(season, {}).get(slot, js.slots[slot])
				var m := ShaderMaterial.new()
				m.shader = SHADER_DOUBLE if spec.get("doubleSided", false) else SHADER
				var c: Array = spec.get("baseColorFactor", [1, 1, 1, 1])
				m.set_shader_parameter("colour", Color(c[0], c[1], c[2], c[3]).linear_to_srgb())
				m.set_shader_parameter("roughness", spec.get("roughnessFactor", 0.85))
				m.set_shader_parameter("use_vertex_colour", vcol.get(slot, false))
				var al := tex(dir, spec.get("baseColorTexture"))
				if al == null and base.albedo_texture != null:
					var img := base.albedo_texture.get_image()
					img.generate_mipmaps()
					al = ImageTexture.create_from_image(img)
				if al != null:
					m.set_shader_parameter("albedo_tex", al)
				var nm := tex(dir, spec.get("normalTexture"))
				m.set_shader_parameter("has_normal", nm != null)
				if nm != null:
					m.set_shader_parameter("normal_tex", nm)
				var cut := 0.0
				if spec.get("alphaMode", "OPAQUE") == "MASK":
					cut = spec.get("alphaCutoff", 0.5)
				if spec.get("hidden", false):
					cut = 1.01
				m.set_shader_parameter("alpha_cut", cut)
				mesh.surface_set_material(s, m)
			parts.append(mesh)
		for p in parts:
			p.resource_name = stem
		lods.append({"parts": parts, "tris": tris, "top": top})
		k += 1
	return {"stem": stem, "lods": lods}


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var style := int(a[1])
	var season: String = a[2]
	var mode: String = a[3]
	if OS.get_environment("MEADOW_CELL") != "":
		CELL = float(OS.get_environment("MEADOW_CELL"))
	SHADER = load("res://game/style/plant.gdshader")
	SHADER_DOUBLE = load("res://game/style/plant_double.gdshader")
	var w := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	w.set_pixel(0, 0, Color(1 if style == 1 else 0, 1 if style == 2 else 0, 1 if style == 3 else 0, 1 if style == 4 else 0))
	RenderingServer.global_shader_parameter_set("style_map", ImageTexture.create_from_image(w))
	var kinds: Array = [load_plant(a[4], season)]
	if a.size() > 5:
		kinds.append(load_plant(a[5], season))
	# placement, as the game's groundcover.gd
	var groups := {}  # "kind/lod" -> [Transform3D]
	var n := int(ceil(RADIUS / CELL))
	for cy in range(-n, n + 1):
		for cx in range(-n, n + 1):
			var p := (Vector2(cx, cy) + Vector2(rnd(cx, cy, 1), rnd(cx, cy, 2))) * CELL
			var dist := p.length()
			if dist > RADIUS:
				continue
			var keep: float = 1.0 if dist < NEAR else lerpf(1.0, FAR_SHARE, (dist - NEAR) / (RADIUS - NEAR))
			if rnd(cx, cy, 3) > keep:
				continue
			var ki := 0
			if kinds.size() > 1 and rnd(cx, cy, 4) < FLOWER_SHARE:
				ki = 1
			var lod: int = 0 if dist < NEAR else kinds[ki].lods.size() - 1
			if mode == "full":
				var budget: float = NEAR_TRIS if lod == 0 else FAR_TRIS
				if rnd(cx, cy, 7) > minf(budget / float(kinds[ki].lods[lod].tris), 1.0):
					continue
			var key := "%d/%d" % [ki, lod]
			if not groups.has(key):
				groups[key] = []
			var yaw := rnd(cx, cy, 5) * TAU
			var size := 0.8 + 0.5 * rnd(cx, cy, 6)
			# the game's x (east), y (north) -> Godot x, -z
			groups[key].append(Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3.ONE * size), Vector3(p.x, 0, -p.y)))
	var total := 0
	var clumps := 0
	for key in groups:
		var ki := int(key.get_slice("/", 0))
		var lod := int(key.get_slice("/", 1))
		var L: Dictionary = kinds[ki].lods[lod]
		clumps += groups[key].size()
		total += groups[key].size() * L.tris
		for mesh in L.parts:
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = mesh
			mm.instance_count = groups[key].size()
			for i in groups[key].size():
				mm.set_instance_transform(i, groups[key][i])
			var mmi := MultiMeshInstance3D.new()
			mmi.multimesh = mm
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(mmi)
		print("group ", kinds[ki].stem, " LOD", lod, ": ", groups[key].size(), " clumps x ", L.tris, " triangles")
	print("TOTAL triangles ", total, " clumps ", clumps)
	# ground, sky, sun (summer palette, mid-morning)
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.36, 0.47, 0.22)
	gm.roughness = 1.0
	var plane := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	plane.mesh = pm
	plane.material_override = gm
	root.add_child(plane)
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_density = 0.002
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.light_energy = 1.1
	sun.light_color = Color(1.0, 0.96, 0.88)
	sun.shadow_enabled = true
	root.add_child(sun)
	sun.look_at_from_position(Vector3(-0.5, 0.75, 0.45).normalized() * 100.0, Vector3.ZERO, Vector3.UP)
	var cam := Camera3D.new()
	cam.fov = 70.0
	cam.far = 500.0
	root.add_child(cam)
	cam.make_current()
	for v in [["eye", Vector3(0, 1.7, 0), Vector3(0, 0.6, -8)], ["high", Vector3(0, 6.0, 4.0), Vector3(0, 0, -14)]]:
		cam.look_at_from_position(v[1], v[2], Vector3.UP)
		for k in 4:
			await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s_%s.png" % [prefix, v[0]])
	print("done")
	quit(0)
