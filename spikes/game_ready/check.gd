extends SceneTree
# A game-ready hifipushie character in a real engine (Godot 4, its own glTF importer at run time), shaded as a game
# would: the hair cards with spikes/godot_hair/hair_cards.gdshader, the skin with skin_blink.gdshader (basecolor x
# the blink-multiply map faded by eyeBlink), everything else with the importer's own materials. Shots: a bind pose,
# joint turns (Blender axes, as the rig tool), face shapes by ARKit name, and frames of a Mixamo-named animation
# from ANOTHER skeleton retargeted onto ours by bone name (world-space rest-relative rotations, each target bone
# first swung onto the source's rest direction: A-pose onto T-pose; hips translation scaled by hip height).
#
#   godot-quiet --path spikes/game_ready -s check.gd -- <x.glb> <x.json> <out prefix> <shots.json> [<anim.glb>]
#
# shots.json: [{"name", "turns": {"LeftArm": [[x, y, z], deg]}, "shapes": {"jawOpen": 1}, "anim": ["walk", 0.4],
#   "focus": "Head", "lift": 0.0, "dist": 1.2, "fov": 30, "views": ["front", "three_quarter", "side", "back"],
#   "w": 640, "h": 640}]   (anim: [clip, time in s] of the anim GLB; "sit": true = a seated pose by turns)

const P := "mixamorig_"
var hair_shader: Shader
var skin_shader: Shader
var skin_mats: Array = []

func _b2g(a) -> Vector3:
	return Vector3(a[0], a[2], -a[1]).normalized()

func _find(n: Node, cls: String, out: Array) -> void:
	if n.is_class(cls):
		out.append(n)
	for c in n.get_children():
		_find(c, cls, out)

func _tex(path: String) -> ImageTexture:
	var im := Image.load_from_file(path)
	if im == null:
		return null
	im.generate_mipmaps()
	return ImageTexture.create_from_image(im)

func _load_glb(path: String) -> Node:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(path, st) != OK:
		push_error("glTF import failed: " + path)
		return null
	return doc.generate_scene(st)

func _shader(path: String) -> Shader:
	var s := Shader.new()
	s.code = FileAccess.get_file_as_string(path)
	return s

func _materials(scene: Node, info: Dictionary, glb_dir: String) -> void:
	# part -> atlas -> maps, from the export's json; a mesh node is "<asset>_<part>"
	var meshes: Array = []
	_find(scene, "MeshInstance3D", meshes)
	var parts: Dictionary = info["parts"]
	for m in meshes:
		var pn := ""
		for p in parts:
			if String(m.name).ends_with("_" + String(p).replace("/", "_")) or String(m.name) == String(p):
				if String(p).length() > pn.length():
					pn = p
		if pn == "" and String(m.name).ends_with("_head"):  # the native head's own mesh (asset.head_body_meshes)
			for p in parts:
				if parts[p].has("meshes"):
					pn = p
		if pn == "":
			print("mesh ", m.name, ": no part")
			continue
		var r: Dictionary = parts[pn]
		var at: Dictionary = info["atlases"].get(r["atlas"], {})
		var maps: Dictionary = at.get("maps", {})
		if r.get("cards", false) or r.get("curves", false):
			var sm := ShaderMaterial.new()
			sm.shader = hair_shader
			sm.set_shader_parameter("albedo_tex", _tex(maps.get("basecolor", "")))
			sm.set_shader_parameter("normal_tex", _tex(maps.get("normal", "")))
			if maps.has("aux"):
				sm.set_shader_parameter("aux_tex", _tex(maps["aux"]))
			for k in m.mesh.get_surface_count():
				m.set_surface_override_material(k, sm)
			print("mesh ", m.name, ": hair cards shader")
		elif String(pn) == (String(info["skin"].get("part", "body")) if info.has("skin") else "body"):
			var sm := ShaderMaterial.new()
			sm.shader = skin_shader
			sm.set_shader_parameter("albedo_tex", _tex(maps["basecolor"]))
			sm.set_shader_parameter("orm_tex", _tex(maps["orm"]))
			sm.set_shader_parameter("normal_tex", _tex(maps["normal"]))
			if maps.has("blink"):
				sm.set_shader_parameter("blink_tex", _tex(maps["blink"]))
				sm.set_shader_parameter("has_blink", true)
			for k in m.mesh.get_surface_count():
				m.set_surface_override_material(k, sm)
			skin_mats.append(sm)
			print("mesh ", m.name, ": skin shader (blink map ", maps.has("blink"), ")")
		else:
			for k in m.mesh.get_surface_count():
				var mt = m.get_active_material(k)
				if mt is BaseMaterial3D and mt.albedo_texture != null:
					# run-time glTF loads have no mipmaps (sparkle at distance)
					var im: Image = mt.albedo_texture.get_image()
					if im != null and not im.has_mipmaps():
						im.generate_mipmaps()
						mt.albedo_texture = ImageTexture.create_from_image(im)

func _rot(b: Basis) -> Quaternion:
	return b.orthonormalized().get_rotation_quaternion()

func _dir(sk: Skeleton3D, i: int, W: Transform3D) -> Vector3:
	# a bone's rest direction in world space: to its first non-twist, non-end child, else from its parent
	var o := (W * sk.get_bone_global_rest(i)).origin
	for c in sk.get_bone_children(i):
		var cn := sk.get_bone_name(c)
		if cn.contains("Twist"):
			continue
		var d := (W * sk.get_bone_global_rest(c)).origin - o
		if d.length() > 1e-5:
			return d.normalized()
	var p := sk.get_bone_parent(i)
	if p >= 0:
		var d := o - (W * sk.get_bone_global_rest(p)).origin
		if d.length() > 1e-5:
			return d.normalized()
	return Vector3.UP

func _arc(a: Vector3, b: Vector3) -> Quaternion:
	var c := a.cross(b)
	var d := a.dot(b)
	if c.length() < 1e-6:
		return Quaternion() if d > 0 else Quaternion(Vector3.FORWARD if absf(a.x) > 0.9 else Vector3.RIGHT, PI)
	return Quaternion(c.normalized(), acos(clampf(d, -1.0, 1.0)))

func _retarget(sk: Skeleton3D, src: Skeleton3D) -> int:
	var Wt := sk.global_transform
	var Ws := src.global_transform
	var Rt := _rot(Wt.basis)
	var hip_t := (Wt * sk.get_bone_global_rest(sk.find_bone(P + "Hips"))).origin.y
	var hip_s := (Ws * src.get_bone_global_rest(src.find_bone("mixamorig_Hips"))).origin.y
	var g := {}  # bone -> its global pose rotation (skeleton space) as set
	var n := 0
	for i in sk.get_bone_count():  # parents come first in Godot's bone order
		var nm := sk.get_bone_name(i)
		var par := sk.get_bone_parent(i)
		var gpar: Quaternion = g[par] if par >= 0 else Quaternion()
		var j := src.find_bone(nm)
		if j < 0 or nm.contains("Twist"):
			g[i] = gpar * sk.get_bone_rest(i).basis.get_rotation_quaternion()
			sk.set_bone_pose_rotation(i, sk.get_bone_rest(i).basis.get_rotation_quaternion())
			continue
		var s_rest := _rot(Ws.basis * src.get_bone_global_rest(j).basis)
		var s_pose := _rot(Ws.basis * src.get_bone_global_pose(j).basis)
		var delta := s_pose * s_rest.inverse()
		var swing := _arc(_dir(sk, i, Wt), _dir(src, j, Ws))
		var t_rest := _rot(Wt.basis * sk.get_bone_global_rest(i).basis)
		var t_world := delta * swing * t_rest
		var gi := Rt.inverse() * t_world
		g[i] = gi
		sk.set_bone_pose_rotation(i, gpar.inverse() * gi)
		n += 1
		if nm == P + "Hips":
			var d := (Ws * src.get_bone_global_pose(j)).origin - (Ws * src.get_bone_global_rest(j)).origin
			d *= hip_t / maxf(hip_s, 1e-3)
			sk.set_bone_pose_position(i, sk.get_bone_rest(i).origin + Rt.inverse() * d)
	return n

func _drive_twist(sk: Skeleton3D, info: Dictionary) -> int:
	var driven := 0
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
	return driven

func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var here := (get_script() as Script).resource_path.get_base_dir()
	hair_shader = _shader(ProjectSettings.globalize_path("res://").path_join("../godot_hair/hair_cards.gdshader"))
	skin_shader = _shader(ProjectSettings.globalize_path("res://").path_join("skin_blink.gdshader"))
	var scene := _load_glb(a[0])
	if scene == null:
		quit(1)
		return
	root.add_child(scene)
	var info: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(a[1]))
	var shots: Array = JSON.parse_string(FileAccess.get_file_as_string(a[3]))
	_materials(scene, info, a[0].get_base_dir())
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
	var src: Skeleton3D = null
	var player: AnimationPlayer = null
	if a.size() > 4:
		var an := _load_glb(a[4])
		an.visible = false if an is Node3D else true
		root.add_child(an)
		var ss: Array = []
		_find(an, "Skeleton3D", ss)
		src = ss[0]
		var pl: Array = []
		_find(an, "AnimationPlayer", pl)
		player = pl[0]
		print("animation source: ", src.get_bone_count(), " bones, clips ", player.get_animation_list())

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.42, 0.44, 0.48)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.75, 0.78, 0.85)
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38, 32, 0)
	sun.light_energy = 1.3
	sun.shadow_enabled = true
	root.add_child(sun)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-15, -140, 0)
	fill.light_energy = 0.35
	root.add_child(fill)
	var cam := Camera3D.new()
	cam.near = 0.02
	root.add_child(cam)
	cam.make_current()
	await process_frame

	for pz in shots:
		sk.reset_bone_poses()
		for m in meshes:
			for k in m.mesh.get_blend_shape_count():
				m.set_blend_shape_value(k, 0.0)
		var nret := 0
		if pz.has("anim") and player != null:
			player.play(pz["anim"][0])
			player.seek(float(pz["anim"][1]), true)
			player.pause()
			nret = _retarget(sk, src)
		var turns: Dictionary = pz.get("turns", {})
		for bn in turns:
			var i := sk.find_bone(P + bn)
			if i < 0:
				push_error("no bone " + bn)
				continue
			var t = turns[bn]
			sk.set_bone_pose_rotation(i, sk.get_bone_pose_rotation(i) * Quaternion(_b2g(t[0]), deg_to_rad(t[1])))
		if pz.has("hips_drop"):
			var hi := sk.find_bone(P + "Hips")
			sk.set_bone_pose_position(hi, sk.get_bone_pose_position(hi) + Vector3(0, -float(pz["hips_drop"]), float(pz.get("hips_back", 0.0))))
		var driven := _drive_twist(sk, info)
		var shapes: Dictionary = pz.get("shapes", {})
		var set_n := 0
		for m in meshes:
			for s in shapes:
				var k: int = m.find_blend_shape_by_name(s)
				if k >= 0:
					m.set_blend_shape_value(k, float(shapes[s]))
					set_n += 1
		var blink := 0.0
		for s in ["eyeBlinkLeft", "eyeBlinkRight", "eyeBlink"]:
			blink = maxf(blink, float(shapes.get(s, 0.0)))
		for sm in skin_mats:
			sm.set_shader_parameter("eye_blink", blink)
			if sm.get_shader_parameter("blink_tex") != null:
				sm.set_shader_parameter("has_blink", bool(pz.get("blink_map", true)))
		for m in meshes:  # parts left out of this shot (mesh node "<asset>_<part>")
			var vis := true
			for k_ in pz.get("hide", []):
				if String(m.name).ends_with("_" + String(k_)):
					vis = false
			m.visible = vis
		var fi := sk.find_bone(P + String(pz.get("focus", "Spine2")))
		await process_frame
		var at: Vector3 = (sk.global_transform * sk.get_bone_global_pose(fi)).origin + Vector3(0, float(pz.get("lift", 0.0)), 0)
		var dist := float(pz.get("dist", 1.5))
		cam.fov = float(pz.get("fov", 30.0))
		root.size = Vector2i(int(pz.get("w", 720)), int(pz.get("h", 720)))
		for v in pz.get("views", ["front"]):
			var dir := Vector3(0, 0, 1)  # the character faces +Z in glTF
			if v == "three_quarter":
				dir = Vector3(0.6, 0.12, 0.8).normalized()
			elif v == "side":
				dir = Vector3(1, 0.05, 0)
			elif v == "left":
				dir = Vector3(-1, 0.05, 0)
			elif v == "back":
				dir = Vector3(0, 0.1, -1).normalized()
			elif v == "back_quarter":
				dir = Vector3(-0.6, 0.2, -0.8).normalized()
			cam.look_at_from_position(at + dir.normalized() * dist, at, Vector3.UP)
			for k in 4:
				await process_frame
			await RenderingServer.frame_post_draw
			var out := "%s_%s_%s.png" % [a[2], pz["name"], v]
			root.get_texture().get_image().save_png(out)
			print("wrote ", out, " (retargeted ", nret, ", twist driven ", driven, ", shapes set ", set_n, ")")
	print("done")
	quit(0)
