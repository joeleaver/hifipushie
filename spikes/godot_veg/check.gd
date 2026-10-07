extends SceneTree
# Plant GLBs (hifipushie export_plant's per-LOD files) in a real engine: each loaded with Godot's own glTF importer and
# drawn alone, from the same cameras under the same suns, on a magenta ground-less background, one PNG each:
# <out prefix>_<file stem>_<view>_<sun>.png. spikes/godot_veg/measure.py compares their mean colours (does the impostor
# pop against the mesh LOD beside it?).
#
#   godot --path spikes/godot_veg -s check.gd -- <out prefix> <height m> <a.glb> <b.glb> ...
#
# As the consumer does: vertex colour used as albedo on foliage, slots whose material is `hidden` not drawn.

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var prefix: String = a[0]
	var H := float(a[1])
	var scenes: Array = []
	for i in range(2, a.size()):
		var doc := GLTFDocument.new()
		var st := GLTFState.new()
		var err := doc.append_from_file(a[i], st)
		if err != OK:
			push_error("glTF import failed: %s" % a[i])
			quit(1)
			return
		var sc := doc.generate_scene(st)
		root.add_child(sc)
		var meshes: Array = []
		_find(sc, "MeshInstance3D", meshes)
		for m in meshes:
			var mesh: Mesh = m.mesh
			for s in mesh.get_surface_count():
				var mat: Material = mesh.surface_get_material(s)
				if mat == null:
					continue
				var nm := String(mat.resource_name)
				var arr := mesh.surface_get_arrays(s)
				print(a[i].get_file(), " ", m.name, " surface ", s, " material ", nm, " tangents ", arr[Mesh.ARRAY_TANGENT] != null,
					" normal map ", (mat as BaseMaterial3D).normal_enabled, " transparency ", (mat as BaseMaterial3D).transparency,
					" cull ", (mat as BaseMaterial3D).cull_mode)
				if nm.begins_with("foliage"):
					(mat as BaseMaterial3D).vertex_color_use_as_albedo = true
				if nm.begins_with("impostor"):  # the export's recipe: its two quads must not shadow each other (a dark wedge)
					(mat as BaseMaterial3D).disable_receive_shadows = true
				if nm == "bark_forks":
					var hide := StandardMaterial3D.new()
					hide.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
					hide.albedo_color = Color(0, 0, 0, 0)
					m.set_surface_override_material(s, hide)
		sc.visible = false
		scenes.append([a[i].get_file().get_basename(), sc])

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
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = 1.7 * H
	cam.near = 0.1
	cam.far = 20.0 * H
	root.add_child(cam)
	cam.make_current()
	await process_frame
	# view azimuths (deg round the up axis; 0 = the camera on +Z, i.e. Blender's -y: the impostor's first picture)
	var views := {"front": 0.0, "diag": 45.0, "side": 90.0, "back20": 200.0}
	# suns: [azimuth the light comes FROM, elevation]
	var suns := {"left": [-60.0, 45.0], "front": [20.0, 35.0], "behind": [150.0, 40.0]}
	var at := Vector3(0, 0.5 * H, 0)
	for sn in suns:
		var sa := deg_to_rad(float(suns[sn][0]))
		var se := deg_to_rad(float(suns[sn][1]))
		var from := Vector3(sin(sa) * cos(se), sin(se), cos(sa) * cos(se))
		sun.look_at_from_position(at + from * 4.0 * H, at, Vector3.UP)
		for vn in views:
			var va := deg_to_rad(float(views[vn]))
			cam.look_at_from_position(at + Vector3(sin(va), 0.12, cos(va)).normalized() * 6.0 * H, at, Vector3.UP)
			for e in scenes:
				for o in scenes:
					o[1].visible = o == e
				for k in 3:
					await process_frame
				await RenderingServer.frame_post_draw
				var out := "%s_%s_%s_%s.png" % [prefix, e[0], vn, sn]
				root.get_texture().get_image().save_png(out)
	print("done")
	quit(0)
