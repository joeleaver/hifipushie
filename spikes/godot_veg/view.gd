extends SceneTree
# One plant file as Godot draws it (its importer, alpha scissor, mipmaps), under a sun and a plain sky, from cameras
# you give: for judging a delivery beside a reference photo at the same framing.
#
#   godot-quiet --path spikes/godot_veg --resolution 900x900 -s view.gd -- <config.json>
# config: {"glb": path, "out": prefix, "sun": [pitch deg, yaw deg], "ground": [r, g, b], "shadows": true,
#          "views": [{"name", "eye": [x, y, z], "look": [x, y, z], "fov": deg}]}   (Godot axes: +Y up, metres)

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _initialize() -> void:
	var cfg: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(String(cfg["glb"]), st) != OK:
		push_error("glTF import failed")
		quit(1)
		return
	var sc := doc.generate_scene(st)
	root.add_child(sc)
	var ms: Array = []
	_find(sc, "MeshInstance3D", ms)
	for m in ms:
		var mesh: ArrayMesh = m.mesh
		for s in mesh.get_surface_count():
			var mat := mesh.surface_get_material(s) as BaseMaterial3D
			if mat == null:
				continue
			if mat.albedo_texture != null:
				var im := mat.albedo_texture.get_image()
				if im != null and not im.has_mipmaps():
					im.generate_mipmaps()
					mat.albedo_texture = ImageTexture.create_from_image(im)
			if String(mat.resource_name).begins_with("foliage"):
				mat.vertex_color_use_as_albedo = true
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.62, 0.74, 0.9)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.7, 0.78, 0.9)
	env.ambient_light_energy = 0.55
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	var sr: Array = cfg.get("sun", [-48, -35])
	sun.rotation_degrees = Vector3(sr[0], sr[1], 0)
	sun.shadow_enabled = bool(cfg.get("shadows", true))
	sun.directional_shadow_max_distance = 150.0
	root.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(3000, 3000)
	ground.mesh = pm
	var gm := StandardMaterial3D.new()
	var gc: Array = cfg.get("ground", [0.3, 0.36, 0.18])
	gm.albedo_color = Color(gc[0], gc[1], gc[2])
	ground.material_override = gm
	root.add_child(ground)
	var cam := Camera3D.new()
	cam.far = 3000.0
	root.add_child(cam)
	cam.make_current()
	for v in cfg["views"]:
		var e: Array = v["eye"]
		var l: Array = v["look"]
		cam.fov = float(v.get("fov", 40.0))
		cam.look_at_from_position(Vector3(e[0], e[1], e[2]), Vector3(l[0], l[1], l[2]), Vector3.UP)
		for k in 6:
			await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s_%s.png" % [cfg["out"], v["name"]])
	print("done")
	quit(0)
