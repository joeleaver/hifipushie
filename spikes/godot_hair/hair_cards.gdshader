// Hair cards as shipped real-time hair shades them (Kajiya-Kay / Scheuermann's two shifted highlights along the strand,
// a wrapped diffuse, the root-to-tip and in-clump shade from the atlas's aux texture), for our export's GLBs
// (extras.hifipushie_hair.recipe): base colour x COLOR_0, alpha-to-coverage, TANGENT's bitangent (the atlas's v) runs
// root to tip, aux R = root gradient (1 at the root), G = a value per strand, B = depth in the clump (0 = deep).
// Godot's StandardMaterial reads none of the aux texture and has one GGX anisotropic lobe: a uniform fine hatch.
shader_type spatial;
render_mode cull_disabled, depth_draw_opaque;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D aux_tex : filter_linear_mipmap_anisotropic, repeat_disable;
uniform float alpha_cut = 0.33;
uniform float a2c_edge = 0.3;
uniform float normal_strength = 0.35;
uniform float root_shade = 0.35;   // darker toward the root (the hair's own shadow where it leaves the scalp)
uniform float inner_shade = 0.35;  // darker deep in the clump (aux B)
uniform float value_vary = 0.12;   // a value per strand (aux G)
uniform float wrap = 0.45;         // wrapped diffuse: light scatters round a strand
uniform float shadow_soft = 0.55;  // share of the shadow map kept (hair lets light through)
uniform vec3 spec1_color : source_color = vec3(0.9, 0.88, 0.85);
uniform float spec1_power = 90.0;
uniform float spec1_strength = 0.35;
uniform float spec1_shift = 0.06;
uniform float spec2_power = 22.0;
uniform float spec2_strength = 0.45;
uniform float spec2_shift = -0.10;
uniform float shift_jitter = 0.3;  // per strand (aux G): breaks the highlight band into strands

varying vec3 v_strand;
varying float v_shift;
varying vec3 v_alb;
varying float v_dep;

void fragment() {
	// two-sided cards share ONE normal (bent toward the hair volume): Godot flips NORMAL on back faces, which lit
	// every card seen from behind (silhouettes, over the ears, the hairline) as if from inside: a black fringe
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
		TANGENT = -TANGENT;
		BINORMAL = -BINORMAL;
	}
	vec4 a = texture(albedo_tex, UV);
	vec4 x = texture(aux_tex, UV);
	vec3 alb = a.rgb * COLOR.rgb;
	alb *= 1.0 - root_shade * x.r;
	alb *= mix(1.0 - inner_shade, 1.0, x.b);
	alb *= 1.0 + value_vary * (x.g - 0.5) * 2.0;
	ALBEDO = alb;
	ALPHA = a.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_cut;
	ALPHA_ANTIALIASING_EDGE = a2c_edge;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	NORMAL_MAP_DEPTH = normal_strength;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
	v_strand = normalize(BINORMAL);
	v_shift = (x.g - 0.5) * shift_jitter;
	v_dep = x.b;
	v_alb = alb;
}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	float diff = clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0);
	float sh = mix(1.0, ATTENUATION, shadow_soft);
	DIFFUSE_LIGHT += diff * sh * LIGHT_COLOR / PI;
	vec3 H = normalize(LIGHT + VIEW);
	vec3 t1 = normalize(v_strand + NORMAL * (spec1_shift + v_shift));
	vec3 t2 = normalize(v_strand + NORMAL * (spec2_shift + v_shift));
	float c1 = dot(t1, H);
	float c2 = dot(t2, H);
	float s1 = pow(sqrt(max(0.0, 1.0 - c1 * c1)), spec1_power);
	float s2 = pow(sqrt(max(0.0, 1.0 - c2 * c2)), spec2_power);
	float vis = clamp(ndl + 0.25, 0.0, 1.0) * sh * mix(0.35, 1.0, v_dep);
	SPECULAR_LIGHT += (s1 * spec1_strength * spec1_color + s2 * spec2_strength * v_alb) * vis * LIGHT_COLOR / PI;
}
