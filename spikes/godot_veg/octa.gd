extends SceneTree
# The hemi-octahedral impostor in Godot against the mesh LOD beside it, from above as well as the side: each file
# alone on magenta, orthographic cameras at elevations 0 / 20 / 45 deg and three azimuths, one sun. The impostor
# gets impostor_octa.gdshader with its uniforms and pictures from <stem>_seasons.json (as a game would).
# octa_measure.py compares the PNGs (coverage, luma, outline IoU impostor vs mesh).
#
#   godot --path spikes/godot_veg -s octa.gd -- <out prefix> <height m> <mesh LOD.glb> <impostor LOD.glb> <seasons.json> [season]

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _tex(path: String) -> ImageTexture:
	var im := Image.load_from_file(path)
	im.generate_mipmaps()
	return ImageTexture.create_from_image(im)

func _load(path: String) -> Node3D:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(path, st) != OK:
		push_error("glTF import failed: %s" % path)
		return null
	var sc := doc.generate_scene(st)
	root.add_child(sc)
	return sc

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var H := float(a[1])
	var season := a[5] if a.size() > 5 else ""
	var mesh_sc := _load(a[2])
	var imp_sc := _load(a[3])
	var sj: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(a[4]))
	var dir := a[4].get_base_dir()
	var slots: Dictionary = sj["slots"] if season == "" else sj["seasons"][season]
	var meshes: Array = []
	_find(mesh_sc, "MeshInstance3D", meshes)
	for m in meshes:  # as the consumer draws the mesh LODs: vertex colour on foliage, hidden slots not drawn
		for s in m.mesh.get_surface_count():
			var mat: Material = m.mesh.surface_get_material(s)
			if mat == null:
				continue
			var nm := String(mat.resource_name)
			if nm.begins_with("foliage"):
				(mat as BaseMaterial3D).vertex_color_use_as_albedo = true
			if season != "" and slots.has(nm) and not slots[nm].get("hidden", false) and nm.begins_with("foliage"):
				# the season's own material as the consumer applies it from the json: factor (linear) + its texture
				var sm: Dictionary = slots[nm]
				var mat2 := (mat as BaseMaterial3D).duplicate() as BaseMaterial3D
				var f: Array = sm.get("baseColorFactor", [1, 1, 1, 1])
				mat2.albedo_color = Color(f[0], f[1], f[2], f[3]).linear_to_srgb()
				if sm.has("baseColorTexture"):
					mat2.albedo_texture = _tex(dir + "/" + String(sm["baseColorTexture"]["file"]))
					mat2.texture_repeat = false
				m.set_surface_override_material(s, mat2)
			if slots.has(nm) and slots[nm].get("hidden", false):
				var hide := StandardMaterial3D.new()
				hide.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
				hide.albedo_color = Color(0, 0, 0, 0)
				m.set_surface_override_material(s, hide)
	var imeshes: Array = []
	_find(imp_sc, "MeshInstance3D", imeshes)
	if not sj.has("impostor") or sj["impostor"] == null:  # an older file: two crossed quads, drawn by their own material
		for m in imeshes:
			for s in m.mesh.get_surface_count():
				var mat0 := m.mesh.surface_get_material(s) as BaseMaterial3D
				mat0.disable_receive_shadows = true
				if slots.has(String(mat0.resource_name)) and slots[String(mat0.resource_name)].has("baseColorTexture"):
					var t0 := _tex(dir + "/" + String(slots[String(mat0.resource_name)]["baseColorTexture"]["file"]))
					mat0.albedo_texture = t0
	else:
		_octa(sj, slots, dir, imeshes)
	_shoot(prefix, H, mesh_sc, imp_sc)

func _octa(sj: Dictionary, slots: Dictionary, dir: String, imeshes: Array) -> void:
	var info: Dictionary = sj["impostor"]
	var imp_slot: Dictionary = slots["impostor"]
	var sh := ShaderMaterial.new()
	sh.shader = load("res://impostor_octa.gdshader")
	sh.set_shader_parameter("albedo_atlas", _tex(dir + "/" + String(imp_slot["baseColorTexture"]["file"])))
	sh.set_shader_parameter("normal_atlas", _tex(dir + "/" + String(imp_slot["impostorNormalTexture"]["file"])))
	sh.set_shader_parameter("frames", float(info["frames"]))
	sh.set_shader_parameter("size", float(info["size"]))
	var c: Array = info["centre"]
	sh.set_shader_parameter("centre", Vector3(c[0], c[1], c[2]))
	for m in imeshes:
		m.material_override = sh
		m.extra_cull_margin = 0.5 * float(info["size"])

func _shoot(prefix: String, H: float, mesh_sc: Node3D, imp_sc: Node3D) -> void:

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(1, 0, 1)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.75, 0.8, 0.9)
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.light_energy = 1.2
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 6.0 * H
	root.add_child(sun)
	var at := Vector3(0, 0.5 * H, 0)
	var from := Vector3(sin(deg_to_rad(-60.0)) * cos(deg_to_rad(45.0)), sin(deg_to_rad(45.0)), cos(deg_to_rad(-60.0)) * cos(deg_to_rad(45.0)))
	sun.look_at_from_position(at + from * 4.0 * H, at, Vector3.UP)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 1.7 * H
	cam.near = 0.1
	cam.far = 30.0 * H
	root.add_child(cam)
	cam.make_current()
	await process_frame
	var scenes := [["mesh", mesh_sc], ["impostor", imp_sc]]
	for el in [0.0, 20.0, 45.0]:
		for az in [0.0, 35.0, 110.0]:
			var e := deg_to_rad(el)
			var v := deg_to_rad(az)
			var dir3 := Vector3(sin(v) * cos(e), sin(e), cos(v) * cos(e))
			cam.look_at_from_position(at + dir3 * 6.0 * H, at, Vector3.UP if el < 80.0 else Vector3.FORWARD)
			for sc in scenes:
				for o in scenes:
					o[1].visible = o == sc
				for k in 3:
					await process_frame
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png("%s_%s_el%02d_az%03d.png" % [prefix, sc[0], int(el), int(az)])
	print("done")
	quit(0)
