extends SceneTree
# Groundcover in a real engine: each GLB drawn ALONE where a player meets a clump (eye 1.7 m up, looking at it from a
# few distances and directions), on magenta, with Godot's own importer (alpha scissor for MASK, TANGENT read, vertex
# colour on for foliage / heads as the plant shader does). ground_measure.py compares each GLB's pixels with the
# first one's (the full plant's LOD 0) at the same view: covered area, IoU of the silhouettes, mean colour.
#
#   godot --path spikes/godot_veg -s ground.gd -- <out prefix> <distances m,..> <azimuths deg,..> <label>=<a.glb> ...

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var dists: Array = Array(a[1].split(",")).map(func(x): return float(x))
	var azs: Array = Array(a[2].split(",")).map(func(x): return float(x))
	get_root().size = Vector2i(1920, 1080)  # the game's view: what a pixel covers decides the mip level and so what an alpha test keeps
	var scenes: Array = []
	var top := 0.0
	for i in range(3, a.size()):
		var parts := a[i].split("=", true, 1)
		var doc := GLTFDocument.new()
		var st := GLTFState.new()
		if doc.append_from_file(parts[1], st) != OK:
			push_error("glTF import failed: %s" % parts[1])
			quit(1)
			return
		var sc := doc.generate_scene(st)
		root.add_child(sc)
		var meshes: Array = []
		_find(sc, "MeshInstance3D", meshes)
		var tris := 0
		for m in meshes:
			var mesh: Mesh = m.mesh
			top = maxf(top, mesh.get_aabb().end.y)
			for s in mesh.get_surface_count():
				tris += mesh.surface_get_array_index_len(s) / 3
				var mat: BaseMaterial3D = mesh.surface_get_material(s)
				if mat == null:
					continue
				var nm := String(mat.resource_name)
				if nm.begins_with("foliage") or nm.begins_with("heads"):
					mat.vertex_color_use_as_albedo = true
				for prop in ["albedo_texture", "normal_texture"]:  # (mipmapped, as a game imports a texture drawn in 3D)
					var t: Texture2D = mat.get(prop)
					if t != null:
						var img := t.get_image()
						if img.is_compressed():
							img.decompress()
						if OS.get_environment("NOMIPS") == "1":
							img.clear_mipmaps()
						elif not img.has_mipmaps():
							img.generate_mipmaps()
						mat.set(prop, ImageTexture.create_from_image(img))
		print(parts[0], " triangles ", tris)
		sc.visible = false
		scenes.append([parts[0], sc])
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
	root.add_child(sun)
	sun.look_at_from_position(Vector3(-0.6, 0.8, 0.5).normalized() * 10.0, Vector3.ZERO, Vector3.UP)
	var cam := Camera3D.new()
	cam.fov = 75.0  # (Godot's default, the game's)
	cam.near = 0.05
	cam.far = 200.0
	root.add_child(cam)
	cam.make_current()
	await process_frame
	var at := Vector3(0, 0.45 * top, 0)
	for d in dists:
		for az in azs:
			var r := deg_to_rad(az)
			var eye := Vector3(sin(r) * d, 1.7, cos(r) * d)
			cam.look_at_from_position(eye, at, Vector3.UP)
			for e in scenes:
				for o in scenes:
					o[1].visible = o == e
				for k in 3:
					await process_frame
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png("%s_%s_d%d_a%d.png" % [prefix, e[0], int(round(d * 10)), int(az)])
			print("view d ", d, " az ", az, " fov ", cam.fov)
	print("done")
	quit(0)
