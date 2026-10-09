extends SceneTree
# A field of grass in the game's shaders, judged: a SWARD (veg_sward tiles laid edge to edge, LOD by distance, faded
# into the ground past its fade distance) or the TUFT meadow (small plants on the game's 0.9 m grid, as meadow.gd),
# over a ground in the terrain's grass colour. Run in a project holding a copy of the game's plant shaders
# (game/style/: plant.gdshader, plant_double.gdshader, plant_sward.gdshader = the double-sided one + the fade).
#
#   godot --path <project> -s field.gd -- <out prefix> <style 0-4> <season> sward <sward dir> [near m] [mid m]
#   godot --path <project> -s field.gd -- <out prefix> <style 0-4> <season> tufts|tufts_full <grass dir> [<flower dir>]
#   godot --path <project> -s field.gd -- <out prefix> <style 0-4> <season> bare
#
# Writes <prefix>_eye.png (1.7 m up) and <prefix>_high.png (25 m up), <prefix>_eye_cov.png / _high_cov.png (ground
# magenta, grass green, unlit: field_measure.py turns them into the share of ground hidden by distance) and
# <prefix>.json (triangles drawn, tiles / clumps, GPU ms median per view, the cameras).

const RADIUS := 60.0
var SHADER: Shader
var SHADER_DOUBLE: Shader
var SHADER_SWARD: Shader
var SHADER_SWARD1: Shader
var season_ground = null


func rnd(cx: int, cy: int, salt: int) -> float:
	return float(hash(Vector3i(cx, cy, salt)) & 0xffff) / 65535.0


func tex(dir: String, ref) -> Texture2D:
	if ref == null or not ref is Dictionary or not ref.has("file"):
		return null
	var img := Image.load_from_file(dir.path_join(ref.file))
	if img == null:
		return null
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


func load_plant(dir: String, season: String, sward := false) -> Dictionary:
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
		for mi: MeshInstance3D in sc.find_children("*", "MeshInstance3D", true, false):
			var mesh: ArrayMesh = mi.mesh.duplicate()
			for s in mesh.get_surface_count():
				tris += mesh.surface_get_array_index_len(s) / 3
				var base := mesh.surface_get_material(s) as BaseMaterial3D
				if base == null or not slot_of.has(String(base.resource_name)):
					continue
				var slot: String = slot_of[String(base.resource_name)]
				var spec: Dictionary = js.seasons.get(season, {}).get(slot, js.slots[slot])
				var m := ShaderMaterial.new()
				m.shader = (SHADER_SWARD if spec.get("doubleSided", false) else SHADER_SWARD1) if sward else (SHADER_DOUBLE if spec.get("doubleSided", false) else SHADER)
				var c: Array = spec.get("baseColorFactor", [1, 1, 1, 1])
				var col := Color(c[0], c[1], c[2], c[3])
				if sward:  # (COLOR_0 is stored / color_gain: the factor carries it back)
					var g: float = js.sward.color_gain
					col = Color(c[0] * g, c[1] * g, c[2] * g, 1.0)
				m.set_shader_parameter("colour", col.linear_to_srgb())
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
				if sward:
					m.set_shader_parameter("fade_start", js.sward.fade.start)
					m.set_shader_parameter("fade_end", js.sward.fade.end)
					var gg: Array = js.sward.ground_srgb
					var fg := Color(gg[0], gg[1], gg[2])
					if js.sward.has("season_ground_linear") and js.sward.season_ground_linear.has(season):
						var sg: Array = js.sward.season_ground_linear[season]
						fg = Color(sg[0], sg[1], sg[2]).linear_to_srgb()
					if season in ["winter", "snow"] and js.sward.has("winter"):
						m.set_shader_parameter("winter_flatten", js.sward.winter.flatten)
						m.set_shader_parameter("winter_height", js.sward.winter.height)
					if season == "snow" and js.sward.has("snow"):
						var snc: Array = js.sward.snow.color_linear
						fg = Color(snc[0], snc[1], snc[2]).linear_to_srgb()
						m.set_shader_parameter("snow_depth", js.sward.snow.depth_m)
					season_ground = fg
					m.set_shader_parameter("fade_ground", fg)
					m.set_shader_parameter("fade_blend", js.sward.fade.get("blend_from", js.sward.fade.start))
					if js.sward.has("lod") and OS.get_environment("FIELD_NOLOD") == "":
						var ld: Array = js.sward.lod.dist
						var ls: Array = js.sward.lod.share
						m.set_shader_parameter("lod_dist", Vector4(ld[0], ld[1], ld[2], ld[3]))
						m.set_shader_parameter("lod_share", Vector4(ls[0], ls[1], ls[2], ls[3]))
						m.set_shader_parameter("lod_band", js.sward.lod.band)
						m.set_shader_parameter("lod_blades", true)
						m.set_shader_parameter("demo_path", OS.get_environment("FIELD_PATH") != "")
					else:
						m.set_shader_parameter("lod_blades", false)
				mesh.surface_set_material(s, m)
			parts.append(mesh)
		lods.append({"parts": parts, "tris": tris})
		k += 1
	return {"stem": stem, "lods": lods, "js": js}


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var style := int(a[1])
	var season: String = a[2]
	var mode: String = a[3]
	SHADER = load("res://game/style/plant_mip.gdshader")
	SHADER_DOUBLE = load("res://game/style/plant_double_mip.gdshader")
	SHADER_SWARD = load("res://game/style/plant_sward.gdshader")
	SHADER_SWARD1 = load("res://game/style/plant_sward1.gdshader")
	var w := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	w.set_pixel(0, 0, Color(1 if style == 1 else 0, 1 if style == 2 else 0, 1 if style == 3 else 0, 1 if style == 4 else 0))
	RenderingServer.global_shader_parameter_set("style_map", ImageTexture.create_from_image(w))
	var grass: Array = []  # every MultiMeshInstance3D of grass
	var total := 0
	var count := 0
	var ground := Color(0.27, 0.42, 0.15)
	if OS.get_environment("FIELD_GROUND") != "":
		var gp := OS.get_environment("FIELD_GROUND").split(",")
		ground = Color(float(gp[0]), float(gp[1]), float(gp[2]))
	var groups := {}
	var kinds: Array = []
	if mode == "sward":
		var P := load_plant(a[4], season, true)
		kinds.append(P)
		var S: float = P.js.sward.tile_m
		var rings: Array = P.js.sward.lod_rings_m  # LOD k inside rings[k]; the last LOD out to the fade's end
		var far: float = P.js.sward.fade.end
		var gs: Array = P.js.sward.ground_srgb
		ground = Color(gs[0], gs[1], gs[2]) if season_ground == null else season_ground
		var n := int(ceil(minf(far, RADIUS) / S))
		for cy in range(-n, n + 1):
			for cx in range(-n, n + 1):
				var p := Vector2(cx, cy) * S
				var dist := p.length()
				if dist > minf(far, RADIUS):
					continue
				var lod := 0
				var near := maxf(dist - 0.7071 * S, 0.0)  # (LOD by the tile's nearest point: the per-blade recipe needs it)
				while lod < rings.size() and near >= float(rings[lod]):
					lod += 1
				var key := "0/%d" % lod
				if not groups.has(key):
					groups[key] = []
				var q := int(rnd(cx, cy, 5) * 4.0) % 4
				groups[key].append(Transform3D(Basis(Vector3.UP, q * PI / 2.0), Vector3(p.x, 0, -p.y)))
	elif mode.begins_with("tufts"):
		kinds.append(load_plant(a[4], season))
		if a.size() > 5:
			kinds.append(load_plant(a[5], season))
		var n := int(ceil(32.0 / 0.9))
		for cy in range(-n, n + 1):
			for cx in range(-n, n + 1):
				var p := (Vector2(cx, cy) + Vector2(rnd(cx, cy, 1), rnd(cx, cy, 2))) * 0.9
				var dist := p.length()
				if dist > 32.0:
					continue
				var keep: float = 1.0 if dist < 12.0 else lerpf(1.0, 0.3, (dist - 12.0) / 20.0)
				if rnd(cx, cy, 3) > keep:
					continue
				var ki := 0
				if kinds.size() > 1 and rnd(cx, cy, 4) < 0.12:
					ki = 1
				var lod: int = 0 if dist < 12.0 else kinds[ki].lods.size() - 1
				if mode == "tufts_full":
					var budget: float = 1200.0 if lod == 0 else 300.0
					if rnd(cx, cy, 7) > minf(budget / float(kinds[ki].lods[lod].tris), 1.0):
						continue
				var key := "%d/%d" % [ki, lod]
				if not groups.has(key):
					groups[key] = []
				groups[key].append(Transform3D(Basis(Vector3.UP, rnd(cx, cy, 5) * TAU).scaled(Vector3.ONE * (0.8 + 0.5 * rnd(cx, cy, 6))), Vector3(p.x, 0, -p.y)))
	for key in groups:
		var ki := int(key.get_slice("/", 0))
		var lod := int(key.get_slice("/", 1))
		var L: Dictionary = kinds[ki].lods[mini(lod, kinds[ki].lods.size() - 1)]
		count += groups[key].size()
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
			mmi.extra_cull_margin = 1.0
			root.add_child(mmi)
			grass.append(mmi)
		print("group ", kinds[ki].stem, " LOD", lod, ": ", groups[key].size(), " x ", L.tris, " triangles")
	print("TOTAL triangles ", total, " placed ", count)
	# the ground in the terrain's grass colour, lit by the same style shader
	var gm := ShaderMaterial.new()
	gm.shader = SHADER
	gm.set_shader_parameter("colour", ground)
	gm.set_shader_parameter("roughness", 1.0)
	var plane := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(600, 600)
	plane.mesh = pm
	plane.material_override = gm
	root.add_child(plane)
	if OS.get_environment("FIELD_PATH") != "":  # the demo path's earth (the same curve as the shader's density)
		var stt := SurfaceTool.new()
		stt.begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
		var z := -70.0
		while z <= 70.0:
			var cx := 1.5 + 3.0 * sin(z * 0.15)
			stt.set_normal(Vector3.UP)
			stt.add_vertex(Vector3(cx - 1.0, 0.02, z))
			stt.set_normal(Vector3.UP)
			stt.add_vertex(Vector3(cx + 1.0, 0.02, z))
			z += 0.5
		var em := ShaderMaterial.new()
		em.shader = SHADER
		em.set_shader_parameter("colour", Color(0.42, 0.33, 0.22))
		em.set_shader_parameter("roughness", 1.0)
		var pmi := MeshInstance3D.new()
		pmi.mesh = stt.commit()
		pmi.material_override = em
		root.add_child(pmi)
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
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
	var vp := root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	var cov_ground := StandardMaterial3D.new()
	cov_ground.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	cov_ground.albedo_color = Color(1, 0, 1)
	var res := {"triangles": total, "placed": count, "views": {}, "size": [root.size.x, root.size.y], "fov": cam.fov}
	for v in [["eye", Vector3(0, 1.7, 0), Vector3(0, 0.0, -9)], ["high", Vector3(0, 25.0, 12.0), Vector3(0, 0, -18)]]:
		cam.look_at_from_position(v[1], v[2], Vector3.UP)
		for k in 30:
			await process_frame
		var acc := []
		for k in 60:
			await process_frame
			acc.append(RenderingServer.viewport_get_measured_render_time_gpu(vp))
		acc.sort()
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s_%s.png" % [prefix, v[0]])
		# coverage: the ground magenta and unlit, the grass flat green (same geometry, same alpha cuts)
		plane.material_override = cov_ground
		env.background_mode = Environment.BG_COLOR
		env.background_color = Color(0, 0, 1)
		env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
		for g in grass:
			for s in g.multimesh.mesh.get_surface_count():
				var m: ShaderMaterial = g.multimesh.mesh.surface_get_material(s)
				if m != null:
					m.set_shader_parameter("flat_colour", Vector3(0, 1, 0))
		for k in 4:
			await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s_%s_cov.png" % [prefix, v[0]])
		plane.material_override = gm
		env.background_mode = Environment.BG_SKY
		env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
		for g in grass:
			for s in g.multimesh.mesh.get_surface_count():
				var m: ShaderMaterial = g.multimesh.mesh.surface_get_material(s)
				if m != null:
					m.set_shader_parameter("flat_colour", Vector3(-1, -1, -1))
		res.views[v[0]] = {"gpu_ms": acc[acc.size() / 2], "gpu_ms_min": acc[0], "eye": [v[1].x, v[1].y, v[1].z], "look": [v[2].x, v[2].y, v[2].z]}
		print("view ", v[0], " gpu median ", acc[acc.size() / 2], " ms")
	var f := FileAccess.open(prefix + ".json", FileAccess.WRITE)
	f.store_string(JSON.stringify(res, " "))
	f.close()
	print("done")
	OS.kill(OS.get_process_id())  # (quit() hangs for minutes under a hidden compositor: the files are written, go)
