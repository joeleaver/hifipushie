extends SceneTree
# A field of terrain clutter as a game would draw it: clutter assets (hifipushie clutter.py folders: <stem>_seasons.json
# with a `clutter` block) loaded by Godot's own glTF importer at run time, scattered as MultiMeshes (one per variant per
# LOD per kind), LOD by distance x scale, yaw / scale / squash per instance, StandardMaterial3D from the json's files
# (albedo, normal, ORM; alpha scissor for bushes), mipmaps on.
#
#   godot-quiet --path spikes/godot_veg --resolution 1280x720 -s clutter_field.gd -- <config.json>
#
# config: {"out": prefix, "kinds": [{"dir": folder, "count": n, "scale": [lo, hi], "squash": [lo, hi]}], "radius": m (the
#   field's half size), "eye": [x, h, z], "look": [x, h, z], "views": {name: {"eye", "look"}}, "seed": 1, "lod": true}
# Writes <out>.json (triangles drawn by LOD rule, instances per LOD, GPU ms median per view) and <out>_<view>.png.

func _tex(path: String, srgb: bool) -> ImageTexture:
	var im := Image.load_from_file(path)
	im.generate_mipmaps()
	return ImageTexture.create_from_image(im)

func _load_mesh(path: String) -> ArrayMesh:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(path, st) != OK:
		push_error("can't read " + path)
		return null
	var scene := doc.generate_scene(st)
	var found: ArrayMesh = null
	var stack := [scene]
	while stack.size() > 0:
		var n: Node = stack.pop_back()
		if n is MeshInstance3D:
			found = n.mesh
			break
		if n is ImporterMeshInstance3D:
			found = n.mesh.get_mesh()
			break
		for c in n.get_children():
			stack.append(c)
	scene.free()
	return found

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var cfg: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var prefix: String = cfg["out"]
	var rng := RandomNumberGenerator.new()
	rng.seed = int(cfg.get("seed", 1))
	var R := float(cfg.get("radius", 120.0))
	var use_lod: bool = cfg.get("lod", true)
	var views: Dictionary = cfg.get("views", {"eye": {"eye": [0, 1.7, 0], "look": [0, 0.5, -20]}})
	var first: Dictionary = views[views.keys()[0]]
	var eye0 := Vector3(first["eye"][0], 0, first["eye"][2])
	var total := 0
	var per_lod := [0, 0, 0, 0]
	var tri_lod := [0, 0, 0, 0]
	var report := []
	for kd in cfg["kinds"]:
		var dir: String = kd["dir"]
		var jf := ""
		for f in DirAccess.get_files_at(dir):
			if f.ends_with("_seasons.json"):
				jf = f
		var J: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(dir + "/" + jf))
		var cl: Dictionary = J["clutter"]
		var slot: String = J["slot_list"][0]["slot"]
		var S: Dictionary = J["slots"][slot]
		var mat := StandardMaterial3D.new()
		mat.albedo_texture = _tex(dir + "/" + String(S["baseColorTexture"]["file"]), true)
		if S.has("normalTexture"):
			mat.normal_enabled = true
			mat.normal_texture = _tex(dir + "/" + String(S["normalTexture"]["file"]), false)
		if S.has("ormTexture"):
			var orm := _tex(dir + "/" + String(S["ormTexture"]["file"]), false)
			mat.ao_enabled = true
			mat.ao_texture = orm
			mat.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
			mat.roughness_texture = orm
			mat.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
		if String(S["alphaMode"]) == "MASK":
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
			mat.alpha_scissor_threshold = 0.5
		mat.metallic = 0.0
		var sw: Dictionary = cl["lod_switch_m"]
		var d1 := float(sw["lod1"])
		var d2: float = float(sw["lod2"]) if sw["lod2"] != null else 1e9
		var cull := float(sw["cull"])
		var variants: Array = cl["variants"]
		var groups := {}
		var n := int(kd["count"])
		var sc: Array = kd.get("scale", cl["size_range_m"])
		var sq: Array = kd.get("squash", [0.8, 1.25])
		var placed := 0
		for i in n:
			var p := Vector3(rng.randf_range(-R, R), 0, rng.randf_range(-R, R))
			var s := lerpf(float(sc[0]), float(sc[1]), pow(rng.randf(), 2.0))  # (many small, few big)
			var q := rng.randf_range(float(sq[0]), float(sq[1]))
			var yaw := rng.randf() * TAU
			var v := rng.randi() % variants.size()
			var d := p.distance_to(eye0) / s
			var lod := 0
			if use_lod:
				if d > cull:
					continue
				lod = 0 if d < d1 else (1 if d < d2 else 2)
			var lods: Array = variants[v]["lods"]
			lod = mini(lod, lods.size() - 1)
			var key := "%d_%d" % [v, lod]
			if not groups.has(key):
				groups[key] = []
			var b := Basis(Vector3.UP, yaw) * Basis.from_scale(Vector3(s, s * q, s))
			groups[key].append(Transform3D(b, p))
			per_lod[lod] += 1
			tri_lod[lod] += int(lods[lod]["triangles"])
			total += int(lods[lod]["triangles"])
			placed += 1
		for key in groups:
			var parts: PackedStringArray = String(key).split("_")
			var L: Dictionary = variants[int(parts[0])]["lods"][int(parts[1])]
			var mesh := _load_mesh(dir + "/" + String(L["file"]))
			if mesh == null:
				continue
			for si in mesh.get_surface_count():
				mesh.surface_set_material(si, mat)
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.mesh = mesh
			mm.instance_count = groups[key].size()
			for i in groups[key].size():
				mm.set_instance_transform(i, groups[key][i])
			var mmi := MultiMeshInstance3D.new()
			mmi.multimesh = mm
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if int(parts[1]) < 2 else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(mmi)
		report.append({"kind": J["kind"], "style": J["style"]["name"], "asked": n, "drawn": placed, "multimeshes": groups.size()})
		print(J["kind"], " ", J["style"]["name"], ": ", placed, " of ", n, " drawn in ", groups.size(), " multimeshes")
	print("TOTAL triangles ", total, " by LOD ", tri_lod, " instances by LOD ", per_lod)
	var gm := StandardMaterial3D.new()
	var gc: Array = cfg.get("ground", [0.2, 0.27, 0.1])
	gm.albedo_color = Color(gc[0], gc[1], gc[2])
	gm.roughness = 1.0
	var plane := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(4 * R, 4 * R)
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
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.light_energy = 1.1
	sun.light_color = Color(1.0, 0.96, 0.88)
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 120.0
	root.add_child(sun)
	sun.look_at_from_position(Vector3(-0.5, 0.75, 0.45).normalized() * 100.0, Vector3.ZERO, Vector3.UP)
	var cam := Camera3D.new()
	cam.fov = 70.0
	cam.far = 1000.0
	root.add_child(cam)
	cam.make_current()
	var vp := root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	var res := {"triangles": total, "triangles_by_lod": tri_lod, "instances_by_lod": per_lod, "kinds": report, "views": {},
		"size": [root.size.x, root.size.y], "lod": use_lod}
	for name in views:
		var v: Dictionary = views[name]
		cam.look_at_from_position(Vector3(v["eye"][0], v["eye"][1], v["eye"][2]), Vector3(v["look"][0], v["look"][1], v["look"][2]), Vector3.UP)
		for k in 40:
			await process_frame
		var acc := []
		for k in 80:
			await process_frame
			acc.append(RenderingServer.viewport_get_measured_render_time_gpu(vp))
		acc.sort()
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s_%s.png" % [prefix, name])
		var drawn := RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME)
		var calls := RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)
		res.views[name] = {"gpu_ms": acc[acc.size() / 2], "gpu_ms_min": acc[0], "primitives_in_frame": drawn, "draw_calls": calls}
		print("view ", name, " gpu median ", acc[acc.size() / 2], " ms, min ", acc[0], "; primitives in frame ", drawn, ", draw calls ", calls)
	var f := FileAccess.open(prefix + ".json", FileAccess.WRITE)
	f.store_string(JSON.stringify(res, " "))
	f.close()
	print("done")
	OS.kill(OS.get_process_id())
