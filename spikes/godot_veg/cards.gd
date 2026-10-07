extends SceneTree
# Alpha-card foliage (a style's leaf clouds, realistic cards) at its LOD distances in a real engine: does it thin out,
# vanish or shimmer? Each GLB is drawn alone at the distance where the plant fills <share> of the view's height
# (perspective, fov 40), twice: the camera moved half a pixel sideways between the two. measure_cards.py compares the
# plant's covered area across files (coverage kept?) and the pixels that flip between the two frames (shimmer).
#
#   godot --path spikes/godot_veg -s cards.gd -- <out prefix> <height m> <mode> <a.glb>:<share> <b.glb>:<share> ...
#
# mode: scissor (what the importer gives for glTF MASK), a2c (alpha to coverage, needs MSAA), hash (alpha hash).
# Prints each foliage surface's channels (is TEXCOORD_3 there as CUSTOM0?).

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var H := float(a[1])
	var mode: String = a[2]
	var scenes: Array = []
	for i in range(3, a.size()):
		var parts := a[i].rsplit(":", true, 1)
		var doc := GLTFDocument.new()
		var st := GLTFState.new()
		if doc.append_from_file(parts[0], st) != OK:
			push_error("glTF import failed: %s" % parts[0])
			quit(1)
			return
		var sc := doc.generate_scene(st)
		root.add_child(sc)
		var meshes: Array = []
		_find(sc, "MeshInstance3D", meshes)
		for m in meshes:
			var mesh: Mesh = m.mesh
			for s in mesh.get_surface_count():
				var mat: BaseMaterial3D = mesh.surface_get_material(s)
				if mat == null:
					continue
				var nm := String(mat.resource_name)
				var arr := mesh.surface_get_arrays(s)
				var c0 = arr[Mesh.ARRAY_CUSTOM0]
				var fmt: int = mesh.surface_get_format(s)
				print(parts[0].get_file(), " ", m.name, " surface ", s, " material ", nm, " transparency ", mat.transparency, " cull ", mat.cull_mode,
					" uv2 ", arr[Mesh.ARRAY_TEX_UV2] != null, " custom0 ", (c0.size() if c0 != null else 0), " verts ", arr[Mesh.ARRAY_VERTEX].size(),
					" custom0 format ", (fmt >> Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT) & Mesh.ARRAY_FORMAT_CUSTOM_MASK,
					" scissor ", mat.alpha_scissor_threshold)
				if c0 != null and c0.size() >= 8:
					print("  custom0 first vertex ", c0[0], " ", c0[1], " ", c0[2], " ", c0[3])
				if nm.begins_with("foliage"):
					mat.vertex_color_use_as_albedo = true
					if mat.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
						if mode == "a2c":
							mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
							mat.alpha_antialiasing_edge = 0.3
						elif mode == "hash":
							mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_HASH
		sc.visible = false
		scenes.append(["%s_%d" % [parts[0].get_file().get_basename(), int(round(float(parts[1]) * 100.0))], sc, float(parts[1])])

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
	sun.directional_shadow_max_distance = 30.0 * H
	root.add_child(sun)
	var cam := Camera3D.new()
	cam.fov = 40.0
	cam.near = 0.1
	cam.far = 100.0 * H
	root.add_child(cam)
	cam.make_current()
	await process_frame
	var at := Vector3(0, 0.5 * H, 0)
	sun.look_at_from_position(at + Vector3(-0.6, 0.7, 0.5).normalized() * 4.0 * H, at, Vector3.UP)
	var px := float(root.size.y)
	for e in scenes:
		for o in scenes:
			o[1].visible = o == e
		var d: float = H / (float(e[2]) * 2.0 * tan(deg_to_rad(20.0)))
		var pixel := 2.0 * d * tan(deg_to_rad(20.0)) / px
		for f in 2:
			cam.look_at_from_position(at + Vector3(0.3, 0.1, 1.0).normalized() * d + Vector3(1, 0, -0.3).normalized() * 0.5 * pixel * f, at + Vector3(1, 0, -0.3).normalized() * 0.5 * pixel * f, Vector3.UP)
			for k in 3:
				await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png("%s_%s_%s_%d.png" % [prefix, e[0], mode, f])
		print("drawn ", e[0], " at ", d, " m, a pixel = ", pixel, " m")
	print("done")
	quit(0)
