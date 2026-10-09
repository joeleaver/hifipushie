extends SceneTree
# Hair card GLBs in Godot 4 through GIVEN cameras (gdcams.json: eye / target / up / fov, or an off-axis "frustum"
# [size, offset x, offset y] per unit of near distance = a crop of a fitted photo camera), with either Godot's
# StandardMaterial as the importer leaves it (+ mipmaps, flow-map anisotropy, a2c: what look.gd did) or
# hair_cards.gdshader (two shifted strand highlights, wrapped diffuse, the aux texture's root / clump shade).
#   godot-quiet --path spikes/godot_hair -s look2.gd -- <out prefix> <body.glb|-> <hair.glb> <cams.json> <std|kk> [params.json]
# params.json: {"uniform": value} for the shader (and "shadow": false, "ambient": 0.35, "key": 1.0, "fill": 0.4).
# Writes <prefix>_<camera name>.png, prints "done".

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)


func _load(path: String) -> Node:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	st.base_path = path.get_base_dir()
	if doc.append_from_file(path, st) != OK:
		push_error("cannot load " + path)
	return doc.generate_scene(st)


func _tex(path: String, normal: bool) -> ImageTexture:
	var im := Image.load_from_file(path)
	im.generate_mipmaps(normal)
	return ImageTexture.create_from_image(im)


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var mode: String = a[4]
	var P: Dictionary = {}
	if a.size() > 5 and FileAccess.file_exists(a[5]):
		P = JSON.parse_string(FileAccess.get_file_as_string(a[5]))
	var cams: Array = JSON.parse_string(FileAccess.get_file_as_string(a[3]))
	if a[1] != "-":
		var body := _load(a[1])
		root.add_child(body)
		var bm: Array = []
		_find(body, "MeshInstance3D", bm)
		for m in bm:
			if String(m.name).to_lower().contains("hair"):
				m.visible = false
	var dir: String = a[2].get_base_dir()
	var hm: Array = []
	if a[2] != "-":  # "-" = the body alone (the bald reference for coverage)
		var hair := _load(a[2])
		root.add_child(hair)
		_find(hair, "MeshInstance3D", hm)
	var sh: Shader = load("res://hair_cards.gdshader")
	for m in hm:
		if not P.get("shadow", true):
			m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var mesh: Mesh = m.mesh
		for s in mesh.get_surface_count():
			var mat: BaseMaterial3D = mesh.surface_get_material(s)
			if mat == null:
				continue
			if mode == "kk":
				var sm := ShaderMaterial.new()
				sm.shader = sh
				sm.set_shader_parameter("albedo_tex", _tex(dir.path_join("hair_basecolor.png"), false))
				sm.set_shader_parameter("normal_tex", _tex(dir.path_join("hair_normal.png"), true))
				sm.set_shader_parameter("aux_tex", _tex(dir.path_join("hair_aux.png"), false))
				for k in P.keys():
					if k in ["shadow", "ambient", "key", "fill", "rim"]:
						continue
					var v = P[k]
					if v is Array:
						v = Color(v[0], v[1], v[2]) if v.size() == 3 else v
					sm.set_shader_parameter(k, v)
				mesh.surface_set_material(s, sm)
				print("surface ", s, " -> hair_cards.gdshader")
				continue
			mat.vertex_color_use_as_albedo = true
			for tn in ["albedo_texture", "normal_texture", "roughness_texture", "ao_texture"]:
				var tx: Texture2D = mat.get(tn)
				if tx == null:
					continue
				var im: Image = tx.get_image()
				if not im.has_mipmaps():
					if im.is_compressed():
						im.decompress()
					im.generate_mipmaps(tn == "normal_texture")
					mat.set(tn, ImageTexture.create_from_image(im))
			mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			var fp := dir.path_join("hair_flow.png")
			if FileAccess.file_exists(fp):
				mat.anisotropy_enabled = true
				mat.anisotropy = 0.35
				mat.anisotropy_flowmap = _tex(fp, false)
			mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
			mat.alpha_antialiasing_edge = 0.3
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.56, 0.6, 0.65)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.77, 0.81, 0.86)
	env.ambient_light_energy = float(P.get("ambient", 0.35))
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var C := Vector3(0.0, 1.6959, 0.0579)
	var key := DirectionalLight3D.new()
	key.light_energy = float(P.get("key", 1.0))
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 4.0
	root.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.light_energy = float(P.get("fill", 0.3))
	root.add_child(fill)
	var rim := DirectionalLight3D.new()
	rim.light_energy = float(P.get("rim", 0.5))
	root.add_child(rim)
	var cam := Camera3D.new()
	cam.near = 0.05
	cam.far = 50.0
	root.add_child(cam)
	cam.make_current()
	await process_frame
	key.look_at_from_position(C + Vector3(-0.45, 0.55, 0.75) * 3.0, C, Vector3.UP)
	fill.look_at_from_position(C + Vector3(0.7, 0.2, 0.6) * 3.0, C, Vector3.UP)
	rim.look_at_from_position(C + Vector3(0.35, 0.5, -0.8) * 3.0, C, Vector3.UP)
	for c in cams:
		var e := Vector3(c["eye"][0], c["eye"][1], c["eye"][2])
		var t := Vector3(c["target"][0], c["target"][1], c["target"][2])
		var u := Vector3(c["up"][0], c["up"][1], c["up"][2])
		cam.look_at_from_position(e, t, u)
		if c.has("frustum") and c["frustum"] != null:
			cam.projection = Camera3D.PROJECTION_FRUSTUM
			cam.near = 0.5
			cam.size = float(c["frustum"][0]) * cam.near
			cam.frustum_offset = Vector2(float(c["frustum"][1]), float(c["frustum"][2])) * cam.near
		else:
			cam.projection = Camera3D.PROJECTION_PERSPECTIVE
			cam.near = 0.05
			cam.fov = float(c["fov"])
		for k in 4:
			await process_frame
		await RenderingServer.frame_post_draw
		var im := root.get_texture().get_image()
		var w := im.get_width()
		var h := im.get_height()
		var s := mini(w, h)
		im = im.get_region(Rect2i((w - s) / 2, (h - s) / 2, s, s))
		im.save_png("%s_%s.png" % [prefix, c["name"]])
	print("done")
	quit(0)
