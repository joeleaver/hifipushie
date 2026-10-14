// The skin of a hifipushie export as a game shades it: the baked base colour x the blink-multiply map faded by the
// eyeBlink morph weight (basecolor x lerp(1, map, 1 - eyeBlink): the lid crease line and the lid's share of the
// occlusion show on an open eye and fade as the lid closes), ORM (R occlusion, G roughness, B metallic), the normal map,
// and the tiling micro-detail normal of the export's skin recipe (optional).
shader_type spatial;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D blink_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D orm_tex : filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform bool has_blink = false;
uniform float eye_blink = 0.0;
uniform float specular = 0.5;
uniform float sss_strength = 0.25;

void fragment() {
	vec3 alb = texture(albedo_tex, UV).rgb;
	if (has_blink) {
		vec3 b = texture(blink_tex, UV).rgb;
		alb *= mix(vec3(1.0), b, 1.0 - clamp(eye_blink, 0.0, 1.0));
	}
	vec3 orm = texture(orm_tex, UV).rgb;
	ALBEDO = alb;
	AO = orm.r;
	AO_LIGHT_AFFECT = 0.6;
	ROUGHNESS = orm.g;
	METALLIC = orm.b;
	SPECULAR = specular;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	SSS_STRENGTH = sss_strength;
}
