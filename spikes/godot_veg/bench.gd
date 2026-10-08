extends SceneTree
# GPU cost of the hemi-octahedral impostor shader in a far forest, per variant (shader, textures, mesh), as the game
# draws it: MultiMeshes of one plant's impostor quad on a flat field, camera on a rim looking over, the consumer's rings
# (near band = ring 3, full blend; far band = ring 4+, from `thin_from` every other tree left out and the rest x1.2).
#
#   godot --path spikes/godot_veg --resolution 1280x720 -s bench.gd -- <config.json>
#
# config: {"dir": delivery folder, "stem": "vs_spruce_pixar", "out": prefix, "rounds": 5, "frames": 90, "warm": 40,
#   "eye": [x, y, z], "pitch": deg, "fov": deg, "near": [d0, d1], "far": [d1, d2], "spacing": m, "thin_from": m,
#   "variants": [{"name", "near": {mat}, "far": {mat}}]} with mat = {"shader": path, "params": {...}, "mips": bool,
#   "compress": bool, "mesh": "quad" | "oct", "oct": [8 x [u, v]]} or null (band not drawn).
# Writes <out>.json (gpu ms per round per variant, gpu busy before each round) and <out>_<variant>.png.

var cfg: Dictionary
var info: Dictionary
var slots: Dictionary
var dir: String
var tex_cache := {}
var bands := {}
var cam: Camera3D

func _tex(path: String, mips: bool, compress: bool, srgb: bool) -> ImageTexture:
	var key := "%s|%s|%s" % [path, mips, compress]
	if tex_cache.has(key):
		return tex_cache[key]
	var im := Image.load_from_file(path)
	if mips:
		im.generate_mipmaps()
	if compress:
		im.compress(Image.COMPRESS_S3TC, Image.COMPRESS_SOURCE_SRGB if srgb else Image.COMPRESS_SOURCE_GENERIC)
	var t := ImageTexture.create_from_image(im)
	tex_cache[key] = t
	return t

func _mesh(kind: String, poly: Array) -> ArrayMesh:
	var S := float(info["size"])
	var uv := PackedVector2Array()
	if kind == "oct":
		for p in poly:
			uv.append(Vector2(p[0], p[1]))
	else:
		uv = PackedVector2Array([Vector2(0, 0), Vector2(1, 0), Vector2(1, 1), Vector2(0, 1)])
	var v := PackedVector3Array()
	for q in uv:
		v.append(Vector3((q.x - 0.5) * S, (1.0 - q.y) * S, 0.0))
	var idx := PackedInt32Array()
	for k in range(1, uv.size() - 1):
		idx.append_array([0, k, k + 1])
	var a := []
	a.resize(Mesh.ARRAY_MAX)
	a[Mesh.ARRAY_VERTEX] = v
	a[Mesh.ARRAY_TEX_UV] = uv
	a[Mesh.ARRAY_INDEX] = idx
	var m := ArrayMesh.new()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, a)
	m.custom_aabb = AABB(Vector3(-S, -S, -S), Vector3(2 * S, 3 * S, 2 * S))
	return m

func _material(mat: Dictionary) -> Material:
	if String(mat["shader"]) == "std":
		var sm := StandardMaterial3D.new()
		sm.albedo_color = Color(1, 0, 0)
		sm.cull_mode = BaseMaterial3D.CULL_DISABLED
		return sm
	var sh := Shader.new()
	sh.code = FileAccess.get_file_as_string(String(mat["shader"]))
	var m := ShaderMaterial.new()
	m.shader = sh
	var imp: Dictionary = slots["impostor"]
	var mips: bool = mat.get("mips", true)
	var comp: bool = mat.get("compress", false)
	m.set_shader_parameter("albedo_atlas", _tex(dir + "/" + String(imp["baseColorTexture"]["file"]), mips, comp, true))
	m.set_shader_parameter("normal_atlas", _tex(dir + "/" + String(imp["impostorNormalTexture"]["file"]), mips, comp, false))
	m.set_shader_parameter("frames", float(info["frames"]))
	m.set_shader_parameter("size", float(info["size"]))
	var c: Array = info["centre"]
	m.set_shader_parameter("centre", Vector3(c[0], c[1], c[2]))
	var k: Array = info["crop"]
	m.set_shader_parameter("crop", Vector4(k[0], k[1], k[2], k[3]))
	var arr := PackedVector4Array()
	for q in info["crops"]:
		arr.append(Vector4(q[0], q[1], q[2], q[3]))
	m.set_shader_parameter("crops", arr)
	m.set_shader_parameter("has_crops", 1.0 if mat.get("crops", true) else 0.0)
	var p: Dictionary = mat.get("params", {})
	for key in p:
		m.set_shader_parameter(key, p[key])
	return m

func _positions(d0: float, d1: float, thin: bool) -> Array:
	var out := []
	var s: float = cfg["spacing"]
	var half := deg_to_rad(float(cfg.get("half_angle", 55.0)))
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var n := int(ceil(d1 / s))
	for i in range(-n, n + 1):
		for j in range(1, n + 1):
			var x := i * s + rng.randf_range(-0.4, 0.4) * s
			var z := -j * s + rng.randf_range(-0.4, 0.4) * s
			var yaw := rng.randf() * TAU
			var sc := rng.randf_range(0.85, 1.15)
			var keep := rng.randf() < 0.5
			var d := Vector2(x, z).length()
			if d < d0 or d >= d1 or abs(atan2(x, -z)) > half:
				continue
			if thin and d >= float(cfg["thin_from"]):
				if not keep:
					continue
				sc *= 1.2
			out.append(Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3.ONE * sc), Vector3(x, 0, z)))
	return out

func _band(name: String, xf: Array) -> MultiMeshInstance3D:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = _mesh("quad", [])
	mm.instance_count = xf.size()
	for i in xf.size():
		mm.set_instance_transform(i, xf[i])
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.extra_cull_margin = 0.5 * float(info["size"])
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mmi.name = name
	root.add_child(mmi)
	return mmi

func _busy() -> int:
	var out := []
	OS.execute("sh", ["-c", "cat /sys/class/drm/card*/device/gpu_busy_percent | head -1"], out)
	return int(String(out[0]).strip_edges()) if out.size() > 0 else -1

func _initialize() -> void:
	cfg = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
	dir = cfg["dir"]
	var sj: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(dir + "/" + String(cfg["stem"]) + "_seasons.json"))
	info = sj["impostor"]
	slots = sj["slots"]
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.55, 0.7, 0.9)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.75, 0.8, 0.9)
	env.ambient_light_energy = 0.5
	var we := WorldEnvironment.new()
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-45, -30, 0)
	sun.shadow_enabled = false
	root.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(4000, 4000)
	ground.mesh = pm
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.3, 0.4, 0.2)
	ground.material_override = gm
	root.add_child(ground)
	cam = Camera3D.new()
	cam.fov = float(cfg.get("fov", 75.0))
	cam.far = 4000.0
	root.add_child(cam)
	var e: Array = cfg["eye"]
	cam.position = Vector3(e[0], e[1], e[2])
	cam.rotation_degrees = Vector3(float(cfg["pitch"]), 0, 0)
	cam.make_current()
	var nb: Array = cfg["near"]
	var fb: Array = cfg["far"]
	if cfg.has("cluster"):  # a small wood round `target` (the path test), nothing in the far band
		var xs := []
		var rng := RandomNumberGenerator.new()
		rng.seed = 3
		var tg: Array = cfg["target"]
		for k in int(cfg["cluster"]):
			var a := rng.randf() * TAU
			var rr := sqrt(rng.randf()) * float(cfg.get("cluster_r", 40.0))
			xs.append(Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * rng.randf_range(0.85, 1.15)), Vector3(tg[0] + cos(a) * rr, 0, tg[2] + sin(a) * rr)))
		bands["near"] = _band("near", xs)
	else:
		bands["near"] = _band("near", _positions(nb[0], nb[1], false))
	bands["far"] = _band("far", _positions(fb[0], fb[1], true))
	print("trees near %d far %d" % [bands["near"].multimesh.instance_count, bands["far"].multimesh.instance_count])
	_run()

# the camera along an arc toward / round `target` (r from r0 to r1 m, azimuth az0 -> az1 deg, height h), every step a
# PNG <out>_<variant>_NNN.png: path.py measures frame-to-frame change (a pop is a spike)
func _path(variants: Array, mats: Array) -> void:
	var pth: Dictionary = cfg["path"]
	var tg: Array = cfg["target"]
	for vi in variants.size():
		var v: Dictionary = variants[vi]
		for b in ["near", "far"]:
			var mmi: MultiMeshInstance3D = bands[b]
			mmi.visible = mats[vi][b] != null
			if mats[vi][b] != null:
				mmi.material_override = mats[vi][b]
				mmi.multimesh.mesh = _mesh(v[b].get("mesh", "quad"), v[b].get("oct", []))
		var n := int(pth["steps"])
		for k in n:
			var t := float(k) / float(n - 1)
			var r := lerpf(float(pth["r0"]), float(pth["r1"]), t)
			var az := deg_to_rad(lerpf(float(pth["az0"]), float(pth["az1"]), t))
			var at := Vector3(tg[0], tg[1], tg[2])
			cam.look_at_from_position(at + Vector3(sin(az) * r, float(pth["h"]), cos(az) * r), at, Vector3.UP)
			for w in 3:
				await process_frame
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png("%s_%s_%03d.png" % [cfg["out"], v["name"], k])
	print("done")
	quit(0)

func _run() -> void:
	var vp := root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(vp, true)
	var variants: Array = cfg["variants"]
	var mats := []
	for v in variants:
		var pair := {}
		for b in ["near", "far"]:
			pair[b] = _material(v[b]) if v.get(b) != null else null
		mats.append(pair)
	var res := {}
	if cfg.has("path"):
		await _path(variants, mats)
		return
	for v in variants:
		res[v["name"]] = {"gpu": [], "busy": []}
	for r in int(cfg["rounds"]):
		for vi in variants.size():
			var v: Dictionary = variants[vi]
			for b in ["near", "far"]:
				var mmi: MultiMeshInstance3D = bands[b]
				var m = mats[vi][b]
				mmi.visible = m != null
				if m != null:
					mmi.material_override = m
					var mm: Dictionary = v[b]
					mmi.multimesh.mesh = _mesh(mm.get("mesh", "quad"), mm.get("oct", []))
			for k in int(cfg["warm"]):
				await process_frame
			var busy := _busy()
			var acc := []
			for k in int(cfg["frames"]):
				await process_frame
				acc.append(RenderingServer.viewport_get_measured_render_time_gpu(vp))
			acc.sort()
			res[v["name"]]["gpu"].append(acc[acc.size() / 2])
			res[v["name"]]["busy"].append(busy)
			if r == 0:
				await RenderingServer.frame_post_draw
				root.get_texture().get_image().save_png("%s_%s.png" % [cfg["out"], v["name"]])
			print("round %d %-24s gpu median %.2f ms (busy %d%%)" % [r, v["name"], acc[acc.size() / 2], busy])
	var f := FileAccess.open(String(cfg["out"]) + ".json", FileAccess.WRITE)
	f.store_string(JSON.stringify(res, " "))
	f.close()
	print("done")
	quit(0)
