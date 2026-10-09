extends SceneTree
# Card hair as a real engine draws it: a character's GLB (its own hair hidden) + a hair tier's GLB, Godot's own
# importer, front / three-quarter / side at bust distance, with alpha scissor (what glTF MASK imports as), alpha to
# coverage (MSAA 4x in project.godot) or alpha hash.
#
#   godot-quiet --path spikes/godot_hair -s look.gd -- <out prefix> <body.glb | -> <hair.glb> <scissor|a2c|hash> <cx> <cy> <cz> [dist] [anisotropy] [nomip|mip] [tag]
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
	var aniso := float(a[8]) if a.size() > 8 else 0.6  # 0 = no anisotropy / flow map
	var nomip := a.size() > 9 and a[9] == "nomip"  # textures as a run-time glTF load leaves them
	var tag: String = a[10] if a.size() > 10 else mode
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
		if a.size() > 11 and a[11] == "noshadow":  # (cards a millimetre over the cap shadow it in hard flakes)
			m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var mesh: Mesh = m.mesh
		for s in mesh.get_surface_count():
			var mat: BaseMaterial3D = mesh.surface_get_material(s)
			if mat == null:
				continue
			print(a[2].get_file(), " ", m.name, " surface ", s, " transparency ", mat.transparency, " scissor ", mat.alpha_scissor_threshold,
				" cull ", mat.cull_mode, " vertex colour as albedo ", mat.vertex_color_use_as_albedo, " verts ", mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX].size())
			mat.vertex_color_use_as_albedo = true  # (COLOR_0 = the cards' root-to-tip ramp: the importer leaves it off)
			# mipmaps: images a GLTFDocument loads at run time come without (the editor's import makes them): a
			# strand texture then sparkles at any distance. Make them, and filter with them.
			var mips := 0
			for tn in ["albedo_texture", "normal_texture", "roughness_texture", "ao_texture"]:
				var tx: Texture2D = mat.get(tn)
				if tx == null:
					continue
				var im: Image = tx.get_image()
				if nomip:
					if im.has_mipmaps():
						im.clear_mipmaps()
						mat.set(tn, ImageTexture.create_from_image(im))
					continue
				if not im.has_mipmaps():
					if im.is_compressed():
						im.decompress()
					im.generate_mipmaps(tn == "normal_texture")
					mat.set(tn, ImageTexture.create_from_image(im))
					mips += 1
			mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR if nomip else BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
			print("  mipmaps made for ", mips, " textures")
			# the flow map (KHR_materials_anisotropy's texture: Godot's importer does not read the extension)
			var flow_path: String = a[2].get_base_dir().path_join("hair_flow.png")
			if aniso > 0.0 and FileAccess.file_exists(flow_path):
				var fi := Image.load_from_file(flow_path)
				fi.generate_mipmaps()
				mat.anisotropy_enabled = true
				mat.anisotropy = aniso
				mat.anisotropy_flowmap = ImageTexture.create_from_image(fi)
				print("  anisotropy ", aniso, " with flow map")
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
	env.ambient_light_energy = 0.35
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var key := DirectionalLight3D.new()
	key.light_energy = 1.0
	key.shadow_enabled = true
	key.directional_shadow_max_distance = 4.0
	root.add_child(key)
	var rim := DirectionalLight3D.new()
	rim.light_energy = 0.5
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
		root.get_texture().get_image().save_png("%s_%s_%s.png" % [prefix, tag, v[0]])
	print("done")
	quit(0)
