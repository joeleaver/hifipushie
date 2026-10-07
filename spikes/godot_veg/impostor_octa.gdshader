// Hemi-octahedral impostor (hifipushie export_plant, contract 6): the reference Godot 4 shader. Drop it on the
// impostor LOD's MeshInstance3D (the GLB's `impostor` quad) and set the uniforms from the GLB material's
// extras.hifipushie_impostor (or <name>_seasons.json "impostor"): frames, size, centre; albedo_atlas = the season's
// baseColorTexture, normal_atlas = its object-space normal map (`impostor_normal_texture` / the _normal.png file).
// The quad's vertices are rebuilt here, so give the MeshInstance3D extra_cull_margin = size / 2 (its stored quad
// is a vertical square; seen from above the drawn one leaves that box). Don't receive shadows on it; casting is fine
// (in the shadow pass it turns to the light and draws the view from the sun's side).
// Conventions are in src/hifipushie/veg_impostor.py; that module's view() draws the same thing in numpy.
shader_type spatial;
render_mode cull_back, shadows_disabled;

uniform sampler2D albedo_atlas : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D normal_atlas : filter_linear_mipmap, repeat_disable;
uniform float frames = 8.0;
uniform float size = 20.0;
uniform vec3 centre = vec3(0.0, 10.0, 0.0);
uniform float alpha_cut = 0.5;
uniform float roughness_value = 0.9;

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
	vec3 p = centre + (UV.x - 0.5) * size * r + (0.5 - UV.y) * size * u;
	VERTEX = p;
	NORMAL = d;
	TANGENT = r;
	BINORMAL = u;
	obj_pos = p;
	view_dir = d;
}

void fragment() {
	vec2 g = (hemi_oct(normalize(view_dir)) * 0.5 + 0.5) * (frames - 1.0);
	vec2 i0 = clamp(floor(g), vec2(0.0), vec2(frames - 2.0));
	vec2 f = clamp(g - i0, vec2(0.0), vec2(1.0));
	vec4 acc = vec4(0.0);
	vec3 nacc = vec3(0.0);
	for (int k = 0; k < 4; k++) {
		vec2 o = vec2(float(k % 2), float(k / 2));
		float w = mix(1.0 - f.x, f.x, o.x) * mix(1.0 - f.y, f.y, o.y);
		if (w <= 0.0) {
			continue;
		}
		vec2 ij = i0 + o;
		vec3 r, u;
		frame_basis(oct_dir(ij / (frames - 1.0) * 2.0 - 1.0), r, u);
		vec2 fuv = vec2(dot(obj_pos - centre, r) / size + 0.5, 0.5 - dot(obj_pos - centre, u) / size);
		// one parallax step: where the view ray through this point meets the plant as this frame saw it
		float dep = (textureLod(normal_atlas, (ij + clamp(fuv, 0.0, 1.0)) / frames, 0.0).a - 0.5) * size;
		vec3 q = obj_pos - normalize(view_dir) * dep;
		fuv = vec2(dot(q - centre, r) / size + 0.5, 0.5 - dot(q - centre, u) / size);
		if (fuv.x < 0.0 || fuv.x > 1.0 || fuv.y < 0.0 || fuv.y > 1.0) {
			continue;
		}
		vec2 auv = (ij + fuv) / frames;
		vec4 c = texture(albedo_atlas, auv);
		acc.rgb += w * c.a * c.rgb;
		acc.a += w * c.a;
		nacc += w * c.a * (texture(normal_atlas, auv).rgb * 2.0 - 1.0);
	}
	ALBEDO = acc.rgb / max(acc.a, 1e-4);
	ALPHA = acc.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	ROUGHNESS = roughness_value;
	vec3 n = length(nacc) > 1e-5 ? normalize(nacc) : normalize(view_dir);
	NORMAL = normalize((VIEW_MATRIX * (MODEL_MATRIX * vec4(n, 0.0))).xyz);
}
