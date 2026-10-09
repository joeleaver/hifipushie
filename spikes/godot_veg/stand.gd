extends SceneTree
# A stand of one plant seen from INSIDE, as a game's forest draws it: GPU ms and overdraw per variant.
# Trees on a jittered grid (random yaw, 0.85-1.15 scale), the camera standing among them at eye height; trees within
# `lod0` m of the eye draw LOD 0, the rest LOD 1 (the consumer's tile rings). Materials as Godot's importer gives them
# (glTF MASK = alpha scissor), textures with mipmaps.
#
#   godot-quiet --path spikes/godot_veg --resolution 1280x720 -s stand.gd -- <config.json>
#
# config: {"out": prefix, "count": 64, "spacing": 3.5, "lod0": 40, "eye": [x, 1.7, z], "yaw": deg, "pitch": deg,
#          "fov": 70, "rounds": 3, "frames": 60, "warm": 30, "variants": [{"name", "lod0": glb, "lod1": glb, "spacing"?}]}
# Per variant: gpu ms (median of medians), triangles drawn, and two overdraw pictures counted additively:
#   raster = card fragments rasterised per covered pixel (what an alpha-tested card costs: every fragment fetches alpha)
#   passed = fragments that pass the alpha test per covered pixel.
# Writes <out>.json and <out>_<variant>.png / _raster.png / _passed.png.

var cfg: Dictionary

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _load(path: String) -> Array:
	# [{mesh, xform}] of a GLB's scene meshes (the -colonly collision node is not a MeshInstance3D)
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(path, st) != OK:
		push_error("glTF import failed: %s" % path)
		return []
	var sc := doc.generate_scene(st)
	var ms: Array = []
	_find(sc, "MeshInstance3D", ms)
	var out := []
	for m in ms:
		var mesh: ArrayMesh = m.mesh
		for s in mesh.get_surface_count():
			var mat := mesh.surface_get_material(s) as BaseMaterial3D
			if mat != null and mat.albedo_texture != null:
				var im := mat.albedo_texture.get_image()
				if im != null and not im.has_mipmaps():
					im.generate_mipmaps()
					mat.albedo_texture = ImageTexture.create_from_image(im)
		out.append({"mesh": mesh, "xform": m.transform})
	sc.free()
	return out

func _count_shader(discard_alpha: bool) -> Shader:
	var sh := Shader.new()
	sh.code = "shader_type spatial;\nrender_mode unshaded, blend_add, depth_test_disabled, cull_disabled, shadows_disabled;\nuniform sampler2D tex : source_color, filter_linear_mipmap;\nuniform float cut = 0.5;\nuniform float has_tex = 0.0;\nvoid fragment() {\n" + ("\tif (has_tex > 0.5 && texture(tex, UV).a < cut) { discard; }\n" if discard_alpha else "") + "\tALBEDO = vec3(1.0 / 1024.0);\n}\n"
	return sh

func _initialize() -> void:
	cfg = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	_run()

func _busy() -> int:
	var out := []
	OS.execute("sh", ["-c", "cat /sys/class/drm/card*/device/gpu_busy_percent | head -1"], out)
	return int(String(out[0]).strip_edges()) if out.size() > 0 else -1

func _run() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.55, 0.7, 0.9)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.75, 0.8, 0.9)
	env.ambient_light_energy = 0.6
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, -30, 0)
	sun.shadow_enabled = bool(cfg.get("shadows", false))
	root.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(2000, 2000)
	ground.mesh = pm
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.25, 0.2, 0.15)
	ground.material_override = gm
	root.add_child(ground)
	var cam := Camera3D.new()
	cam.fov = float(cfg.get("fov", 70.0))
	cam.far = 2000.0
	root.add_child(cam)
	var e: Array = cfg["eye"]
	cam.position = Vector3(e[0], e[1], e[2])
	cam.rotation_degrees = Vector3(float(cfg.get("pitch", 0.0)), float(cfg.get("yaw", 0.0)), 0)
	cam.make_current()
	var vp := root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	var res := {}
	var groups := []
	for v in cfg["variants"]:
		var holder := Node3D.new()
		root.add_child(holder)
		var s := float(v.get("spacing", cfg["spacing"]))
		var n := int(ceil(sqrt(float(cfg["count"]))))
		var rng := RandomNumberGenerator.new()
		rng.seed = 11
		var xf0 := []
		var xf1 := []
		for i in n:
			for j in n:
				var p := Vector3((i - 0.5 * (n - 1)) * s + rng.randf_range(-0.3, 0.3) * s, 0, (j - 0.5 * (n - 1)) * s + rng.randf_range(-0.3, 0.3) * s)
				var t := Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.85, 1.15)), p)
				if Vector2(p.x - e[0], p.z - e[2]).length() < 0.9:
					continue  # (nobody stands inside a trunk)
				if Vector2(p.x - e[0], p.z - e[2]).length() < float(cfg.get("lod0", 40.0)):
					xf0.append(t)
				else:
					xf1.append(t)
		var tris := 0
		var mmis := []
		for pair in [[v["lod0"], xf0], [v.get("lod1", v["lod0"]), xf1]]:
			if pair[1].size() == 0:
				continue
			for part in _load(pair[0]):
				var mm := MultiMesh.new()
				mm.transform_format = MultiMesh.TRANSFORM_3D
				mm.mesh = part["mesh"]
				mm.instance_count = pair[1].size()
				for k in pair[1].size():
					mm.set_instance_transform(k, pair[1][k] * part["xform"])
				var mmi := MultiMeshInstance3D.new()
				mmi.multimesh = mm
				mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if bool(cfg.get("shadows", false)) else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				holder.add_child(mmi)
				mmis.append(mmi)
				var mesh: ArrayMesh = part["mesh"]
				for si in mesh.get_surface_count():
					var arr := mesh.surface_get_arrays(si)
					tris += (arr[Mesh.ARRAY_INDEX].size() / 3) * pair[1].size()
		holder.visible = false
		groups.append({"holder": holder, "mmis": mmis, "tris": tris, "trees": [xf0.size(), xf1.size()]})
		res[v["name"]] = {"gpu": [], "busy": [], "triangles": tris, "trees": [xf0.size(), xf1.size()]}
	for r in int(cfg.get("rounds", 3)):
		for vi in groups.size():
			var g: Dictionary = groups[vi]
			var nm: String = cfg["variants"][vi]["name"]
			g["holder"].visible = true
			for k in int(cfg.get("warm", 30)):
				await process_frame
			var busy := _busy()
			var acc := []
			for k in int(cfg.get("frames", 60)):
				await process_frame
				acc.append(RenderingServer.viewport_get_measured_render_time_gpu(vp))
			acc.sort()
			res[nm]["gpu"].append(acc[acc.size() / 2])
			res[nm]["busy"].append(busy)
			print("round %d %-20s gpu median %.2f ms (busy %d%%) triangles %d trees %s" % [r, nm, acc[acc.size() / 2], busy, g["tris"], str(g["trees"])])
			if r == 0:
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png("%s_%s.png" % [cfg["out"], nm])
				# overdraw counts: black world, every FOLIAGE fragment adds 1/255
				env.background_color = Color(0, 0, 0)
				ground.visible = false
				for mode in ["raster", "passed"]:
					var sh := _count_shader(mode == "passed")
					var saved := []
					for mmi in g["mmis"]:
						var mesh: ArrayMesh = mmi.multimesh.mesh
						for si in mesh.get_surface_count():
							var base := mesh.surface_get_material(si) as BaseMaterial3D
							saved.append([mesh, si, base])
							var m := ShaderMaterial.new()
							m.shader = sh
							var is_card: bool = base != null and base.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED
							if is_card:
								m.set_shader_parameter("tex", base.albedo_texture)
								m.set_shader_parameter("cut", base.alpha_scissor_threshold)
								m.set_shader_parameter("has_tex", 1.0)
							mesh.surface_set_material(si, m)
					for k in 4:
						await process_frame
					await RenderingServer.frame_post_draw
					root.get_texture().get_image().save_png("%s_%s_%s.png" % [cfg["out"], nm, mode])
					for q in saved:
						q[0].surface_set_material(q[1], q[2])
				env.background_color = Color(0.55, 0.7, 0.9)
				ground.visible = true
			g["holder"].visible = false
	var f := FileAccess.open(String(cfg["out"]) + ".json", FileAccess.WRITE)
	f.store_string(JSON.stringify(res, " "))
	f.close()
	print("done")
	quit(0)
