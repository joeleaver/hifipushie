extends SceneTree
# A rigged hifipushie GLB in a real engine: loaded with Godot's own glTF importer, posed on its Skeleton3D, the twist
# joints driven by the export's recipe (<name>.json rig.twist; swing-twist of the driver, share x roll about the
# twist joint's own +Y), face shapes set by name, one PNG per pose.
#
#   godot --path spikes/godot_rig -s check.gd -- <x.glb> <x.json> <out prefix> <poses.json>
#
# poses.json: [{"name", "turns": {"LeftArm": [[x, y, z], deg] | ["roll", deg]}, "shapes": {"jawOpen": 1},
#               "focus": "Neck", "dist": 1.2, "views": ["front", "three_quarter", "side", "back"], "twist": true}]
# Axes in turns are Blender's (Z up, the character faces -Y), as in the rig tool; glTF = (x, z, -y).

const P := "mixamorig_"  # Godot's importer turns the colon into an underscore

func _b2g(a) -> Vector3:
	return Vector3(a[0], a[2], -a[1]).normalized()

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	var err := doc.append_from_file(a[0], st)
	if err != OK:
		push_error("glTF import failed: %d" % err)
		quit(1)
		return
	var scene := doc.generate_scene(st)
	root.add_child(scene)
	var info: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(a[1]))
	var poses: Array = JSON.parse_string(FileAccess.get_file_as_string(a[3]))
	var sks: Array = []
	_find(scene, "Skeleton3D", sks)
	var sk: Skeleton3D = sks[0]
	var meshes: Array = []
	_find(scene, "MeshInstance3D", meshes)
	print("godot ", Engine.get_version_info()["string"], ": ", sk.get_bone_count(), " bones, ", meshes.size(), " meshes")
	var missing := 0
	for nm in info["rig"]["bones"]:
		if sk.find_bone(String(nm).replace(":", "_")) < 0:
			missing += 1
	print("export bones not found in the imported skeleton: ", missing, " of ", info["rig"]["bones"].size())

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.42, 0.44, 0.48)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.75, 0.78, 0.85)
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38, 32, 0)
	sun.light_energy = 1.25
	sun.shadow_enabled = true
	root.add_child(sun)
	var cam := Camera3D.new()
	cam.fov = 30
	cam.near = 0.02
	root.add_child(cam)
	cam.make_current()
	await process_frame

	for pz in poses:
		sk.reset_bone_poses()
		for m in meshes:
			var mesh: Mesh = m.mesh
			for k in mesh.get_blend_shape_count():
				m.set_blend_shape_value(k, 0.0)
		var turns: Dictionary = pz.get("turns", {})
		for bn in turns:
			var i := sk.find_bone(P + bn)
			if i < 0:
				push_error("no bone " + bn)
				continue
			var t = turns[bn]
			var ax: Vector3
			if t[0] is String:  # "roll": about the segment this joint ends (Hand, Foot) or its own (others)
				var par := sk.get_bone_parent(i)
				var seg := i
				if bn.ends_with("Hand") or bn.ends_with("Foot"):
					ax = (sk.get_bone_global_rest(i).origin - sk.get_bone_global_rest(par).origin).normalized()
				else:
					for c in sk.get_bone_children(seg):
						if not sk.get_bone_name(c).contains("Twist"):
							ax = (sk.get_bone_global_rest(c).origin - sk.get_bone_global_rest(i).origin).normalized()
							break
			else:
				ax = _b2g(t[0])
			# base joints rest unrotated: an axis in model space is the axis in the joint's parent frame
			sk.set_bone_pose_rotation(i, sk.get_bone_rest(i).basis.get_rotation_quaternion() * Quaternion(ax, deg_to_rad(t[1])))
		var driven := 0
		if pz.get("twist", true):
			for tw in info["rig"]["twist"]:
				var ti := sk.find_bone(String(tw["bone"]).replace(":", "_"))
				var di := sk.find_bone(String(tw["driver"]).replace(":", "_"))
				if ti < 0 or di < 0:
					continue
				var axis := _b2g(tw["axis"])
				var q := sk.get_bone_rest(di).basis.get_rotation_quaternion().inverse() * sk.get_bone_pose_rotation(di)
				var roll := 2.0 * atan2(Vector3(q.x, q.y, q.z).dot(axis), q.w)
				if roll > PI:
					roll -= TAU
				if roll < -PI:
					roll += TAU
				sk.set_bone_pose_rotation(ti, sk.get_bone_rest(ti).basis.get_rotation_quaternion() * Quaternion(Vector3.UP, float(tw["share"]) * roll))
				if absf(roll) > 1e-4:
					driven += 1
		var shapes: Dictionary = pz.get("shapes", {})
		var set_n := 0
		for m in meshes:
			for s in shapes:
				var k: int = m.find_blend_shape_by_name(s)
				if k >= 0:
					m.set_blend_shape_value(k, float(shapes[s]))
					set_n += 1
		var fi := sk.find_bone(P + String(pz.get("focus", "Spine2")))
		var at: Vector3 = (sk.global_transform * sk.get_bone_global_pose(fi)).origin + Vector3(0, float(pz.get("lift", 0.0)), 0)
		var dist := float(pz.get("dist", 1.5))
		for v in pz.get("views", ["front"]):
			var dir := Vector3(0, 0, 1)  # the character faces +Z in glTF
			if v == "three_quarter":
				dir = Vector3(0.6, 0.15, 0.8).normalized()
			elif v == "side":
				dir = Vector3(1, 0, 0)
			elif v == "back":
				dir = Vector3(0, 0, -1)
			elif v == "back_quarter":
				dir = Vector3(-0.6, 0.2, -0.8).normalized()
			cam.look_at_from_position(at + dir * dist, at, Vector3.UP)
			for k in 4:
				await process_frame
			await RenderingServer.frame_post_draw
			var out := "%s_%s_%s.png" % [a[2], pz["name"], v]
			root.get_texture().get_image().save_png(out)
			print("wrote ", out, " (twist joints driven: ", driven, ", shape slots set: ", set_n, ")")
	quit(0)
