extends SceneTree
# Card hair as a real engine draws it: a character's GLB (its own hair hidden) + a hair tier's GLB, Godot's own
# importer, front / three-quarter / side at bust distance, with alpha scissor (what glTF MASK imports as), alpha to
# coverage (MSAA 4x in project.godot) or alpha hash.
#
#   godot-quiet --path spikes/godot_hair -s look.gd -- <out prefix> <body.glb | -> <hair.glb> <scissor|a2c|hash> <cx> <cy> <cz> [dist]
#
# cx cy cz: the head's centre in glTF axes (Blender x, z, -y). Prints each hair surface's material facts.

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _load(path: String) -> Node:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(path, st) != OK:
		push_error("glTF import failed: %s" % path)
		return null
	return doc.generate_scene(st)

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var mode: String = a[3]
	var C := Vector3(float(a[4]), float(a[5]), float(a[6]))
	var dist := float(a[7]) if a.size() > 7 else 0.62
	if a[1] != "-":
		var body := _load(a[1])
		root.add_child(body)
		var bm: Array = []
		_find(body, "MeshInstance3D", bm)
		for m in bm:
			if String(m.name).to_lower().contains("hair"):
				m.visible = false
	var hair := _load(a[2])
	root.add_child(hair)
	var hm: Array = []
	_find(hair, "MeshInstance3D", hm)
	for m in hm:
		var mesh: Mesh = m.mesh
		for s in mesh.get_surface_count():
			var mat: BaseMaterial3D = mesh.surface_get_material(s)
			if mat == null:
				continue
			print(a[2].get_file(), " ", m.name, " surface ", s, " transparency ", mat.transparency, " scissor ", mat.alpha_scissor_threshold,
				" cull ", mat.cull_mode, " vertex colour as albedo ", mat.vertex_color_use_as_albedo, " verts ", mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX].size())
			if mode == "a2c":
				mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
				mat.alpha_antialiasing_edge = 0.3
			elif mode == "hash":
				mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_HASH
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.56, 0.6, 0.65)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.77, 0.81, 0.86)
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var key := DirectionalLight3D.new()
	key.light_energy = 1.6
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 4.0
	root.add_child(key)
	var rim := DirectionalLight3D.new()
	rim.light_energy = 1.2
	root.add_child(rim)
	var cam := Camera3D.new()
	cam.fov = 30.0
	cam.near = 0.05
	cam.far = 50.0
	root.add_child(cam)
	cam.make_current()
	await process_frame
	key.look_at_from_position(C + Vector3(-0.45, 0.55, 0.75) * 3.0, C, Vector3.UP)
	rim.look_at_from_position(C + Vector3(0.35, 0.5, -0.8) * 3.0, C, Vector3.UP)
	for v in [["front", 0.0, 5.0], ["three_quarter", 40.0, 12.0], ["side", 90.0, 5.0]]:
		var az := deg_to_rad(v[1])
		var el := deg_to_rad(v[2])
		cam.look_at_from_position(C + Vector3(sin(az) * cos(el), sin(el), cos(az) * cos(el)) * dist, C, Vector3.UP)
		for k in 4:
			await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("%s_%s_%s.png" % [prefix, mode, v[0]])
	print("done")
	quit(0)
