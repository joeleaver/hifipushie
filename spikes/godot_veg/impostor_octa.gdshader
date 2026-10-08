// Hemi-octahedral impostor (hifipushie export_plant, contract 6+): the reference Godot 4 shader. Drop it on the
// impostor LOD's MeshInstance3D (the GLB's `impostor` quad) and set the uniforms from the GLB material's
// extras.hifipushie_impostor (or <name>_seasons.json "impostor"): frames, size, centre, crop / crops; albedo_atlas = the
// season's baseColorTexture, normal_atlas = its object-space normal map (`impostor_normal_texture` / the _normal.png).
// The quad's vertices are rebuilt here, so give the MeshInstance3D extra_cull_margin = size / 2 (its stored quad
// is a vertical square; seen from above the drawn one leaves that box). Don't receive shadows on it; casting is fine
// (in the shadow pass it turns to the light and draws the view from the sun's side).
// Conventions are in src/hifipushie/veg_impostor.py; that module's view() draws the same thing in numpy.
//
// Cost (2026-10-08, "impostor" agent; measured on the 890M in spikes/godot_veg/bench.gd): an impostor pixel is paid
// per texture fetch, and a far impostor is small on screen, so:
// - IMPORT BOTH ATLASES WITH MIPMAPS. Without them every fetch of a 2048 atlas at 5-10 texels per pixel misses the
//   cache. The normal atlas must stay RGBA (its alpha is the depth): never import it as a normal map (RGTC drops alpha).
// - the mip level is computed once from the fragment's footprint (`lod`), also for the parallax depth (it was level 0);
// - by the impostor's size on screen (`far_px` .. `near_px`, the frame's square in pixels) the blend sharpens toward the
//   nearest frame and the parallax step fades out; frames whose weight is under `min_weight` are skipped, so a small
//   impostor reads 1 frame (2 fetches) instead of 4 (12 fetches). Continuous: no pop at the hand-over;
// - coverage is summed from the albedo fetches first and the pixel discarded before any normal fetch.
// Every uniform keeps a default that draws as before for old exports (contract 6-9 files work unchanged).
shader_type spatial;
render_mode cull_back, shadows_disabled;

uniform sampler2D albedo_atlas : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D normal_atlas : filter_linear_mipmap, repeat_disable;
uniform float frames = 8.0;
uniform float size = 20.0;
uniform vec3 centre = vec3(0.0, 10.0, 0.0);
uniform float alpha_cut = 0.5;
uniform float roughness_value = 0.9;
uniform float blend_sharp = 2.0;
// [u0, u1, v0, v1] of a frame the quad covers (extras.hifipushie_impostor.crop, contract 8): every frame's drawn
// pixels lie inside it, so the quad is no bigger than the plant needs (the full square drew ~2x the pixels)
uniform vec4 crop = vec4(0.0, 1.0, 0.0, 1.0);
// per frame (index = column * frames + row) its own [u0, u1, v0, v1] (extras `crops`); the quad for a view is the union
// of the 4 frames it blends. has_crops 0 = use `crop` alone. Up to 16 x 16 frames.
uniform vec4 crops[256];
uniform float has_crops = 0.0;
// Size on screen of the bake square (`size` m) in pixels: at or over near_px the full blend + parallax; at or under
// far_px the nearest frame dominates (sharp_far) and no parallax. Set near_px = far_px = 0 for the full blend always.
uniform float near_px = 160.0;
uniform float far_px = 64.0;
uniform float sharp_far = 16.0;
uniform float min_weight = 0.02;
// added to the computed mip level (+1 = half the resolution); max_lod keeps frames from bleeding into each other
uniform float mip_bias = 0.0;
uniform float max_lod = 5.0;

varying vec3 obj_pos;
varying vec3 view_dir;

vec2 hemi_oct(vec3 d) {
	d.y = max(d.y, 0.0);
	d /= max(abs(d.x) + abs(d.y) + abs(d.z), 1e-6);
	return vec2(d.x + d.z, d.x - d.z);
}

vec3 oct_dir(vec2 g) {
	float px = 0.5 * (g.x + g.y);
	float pz = 0.5 * (g.x - g.y);
	return normalize(vec3(px, 1.0 - abs(px) - abs(pz), pz));
}

void frame_basis(vec3 d, out vec3 r, out vec3 u) {
	r = cross(vec3(0.0, 1.0, 0.0), d);
	float l = length(r);
	r = l > 1e-5 ? r / l : vec3(1.0, 0.0, 0.0);
	u = cross(d, r);
}

void vertex() {
	mat4 inv_model = inverse(MODEL_MATRIX);
	vec3 d;
	if (PROJECTION_MATRIX[3][3] > 0.5) {  // orthographic (a directional light's shadow pass): the camera's back axis
		d = (inv_model * vec4(INV_VIEW_MATRIX[2].xyz, 0.0)).xyz;
	} else {
		d = (inv_model * vec4(INV_VIEW_MATRIX[3].xyz, 1.0)).xyz - centre;
	}
	d.y = max(d.y, 0.0);
	d = length(d) > 1e-6 ? normalize(d) : vec3(0.0, 0.0, 1.0);
	vec3 r, u;
	frame_basis(d, r, u);
	vec4 c = crop;
	if (has_crops > 0.5) {
		vec2 g = (hemi_oct(d) * 0.5 + 0.5) * (frames - 1.0);
		vec2 i0 = clamp(floor(g), vec2(0.0), vec2(frames - 2.0));
		c = vec4(1.0, 0.0, 1.0, 0.0);
		for (int k = 0; k < 4; k++) {
			vec2 ij = i0 + vec2(float(k % 2), float(k / 2));
			vec4 f = crops[int(ij.x * frames + ij.y)];
			if (f.y > f.x) {
				c = vec4(min(c.x, f.x), max(c.y, f.y), min(c.z, f.z), max(c.w, f.w));
			}
		}
		if (c.y <= c.x) {
			c = crop;
		}
	}
	vec3 p = centre + (mix(c.x, c.y, UV.x) - 0.5) * size * r + (0.5 - mix(c.z, c.w, UV.y)) * size * u;
	VERTEX = p;
	NORMAL = d;
	TANGENT = r;
	BINORMAL = u;
	obj_pos = p;
	view_dir = d;
}

void fragment() {
	vec3 vd = normalize(view_dir);
	vec2 g = (hemi_oct(vd) * 0.5 + 0.5) * (frames - 1.0);
	vec2 i0 = clamp(floor(g), vec2(0.0), vec2(frames - 2.0));
	vec2 f = clamp(g - i0, vec2(0.0), vec2(1.0));
	// one mip level for every fetch, from the footprint of the pixel on the bake square (texels of a frame per pixel)
	float frame_tex = float(textureSize(albedo_atlas, 0).x) / frames;
	float foot = max(length(dFdx(obj_pos)), length(dFdy(obj_pos))) / size * frame_tex;
	float lod = clamp(log2(max(foot, 1e-6)) + mip_bias, 0.0, max_lod);
	// 0 near .. 1 far: the bake square's size on screen in pixels is frame_tex / foot
	float px = frame_tex / max(foot, 1e-6);
	float t = near_px > far_px ? clamp((near_px - px) / (near_px - far_px), 0.0, 1.0) : 0.0;
	float sharp = mix(blend_sharp, sharp_far, t * t);
	float par = 1.0 - t;
	vec2 fs = vec2(pow(f.x, sharp), pow(f.y, sharp));
	vec2 gs = vec2(pow(1.0 - f.x, sharp), pow(1.0 - f.y, sharp));
	vec2 den = fs + gs;
	vec4 acc = vec4(0.0);
	float wsum = 0.0;
	vec2 uvs[4];
	float wa[4];
	for (int k = 0; k < 4; k++) {
		wa[k] = 0.0;
		uvs[k] = vec2(0.0);
		vec2 o = vec2(float(k % 2), float(k / 2));
		// bilinear weights sharpened (blend_sharp > 1: the nearest view dominates, less ghosting and fewer sky holes filled)
		float w = mix(gs.x, fs.x, o.x) * mix(gs.y, fs.y, o.y) / (den.x * den.y);
		if (w < min_weight) {
			continue;
		}
		vec2 ij = i0 + o;
		vec3 r, u;
		frame_basis(oct_dir(ij / (frames - 1.0) * 2.0 - 1.0), r, u);
		vec3 q = obj_pos - centre;
		vec2 fuv = vec2(dot(q, r) / size + 0.5, 0.5 - dot(q, u) / size);
		if (par > 0.01) {
			// one parallax step: where the view ray through this point meets the plant as this frame saw it
			float dep = (textureLod(normal_atlas, (ij + clamp(fuv, 0.0, 1.0)) / frames, lod).a - 0.5) * size * par;
			q -= vd * dep;
			fuv = vec2(dot(q, r) / size + 0.5, 0.5 - dot(q, u) / size);
		}
		wsum += w;
		if (fuv.x < 0.0 || fuv.x > 1.0 || fuv.y < 0.0 || fuv.y > 1.0) {
			continue;
		}
		vec2 auv = (ij + fuv) / frames;
		vec4 c = textureLod(albedo_atlas, auv, lod);
		acc.rgb += w * c.a * c.rgb;
		acc.a += w * c.a;
		wa[k] = w * c.a;
		uvs[k] = auv;
	}
	float alpha = acc.a / max(wsum, 1e-4);
	if (alpha < alpha_cut) {
		discard;  // before any normal fetch
	}
	vec3 nacc = vec3(0.0);
	for (int k = 0; k < 4; k++) {
		if (wa[k] > 0.0) {
			nacc += wa[k] * (textureLod(normal_atlas, uvs[k], lod).rgb * 2.0 - 1.0);
		}
	}
	ALBEDO = acc.rgb / max(acc.a, 1e-4);
	ALPHA = alpha;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	ROUGHNESS = roughness_value;
	vec3 n = length(nacc) > 1e-5 ? normalize(nacc) : vd;
	NORMAL = normalize((VIEW_MATRIX * (MODEL_MATRIX * vec4(n, 0.0))).xyz);
}
