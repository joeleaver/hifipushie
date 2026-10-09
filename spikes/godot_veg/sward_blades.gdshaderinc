// hifipushie sward (veg_sward): the per-blade LOD and the fade, as Godot 4 shader lines. Reference for the recipes in
// <name>_seasons.json `sward` (lod.recipe, fade_recipe). Include in a spatial shader that is opaque and culls back
// faces; call sward_vertex() first in vertex() (before the wind) and sward_fragment() after ALBEDO / ROUGHNESS are set.
// Channels: CUSTOM1.xy = across (TEXCOORD_4), CUSTOM1.zw = (blade rank, this mesh's width multiple) (TEXCOORD_5).
// Uniforms from the json: lod_dist = sward.lod.dist, lod_share = sward.lod.share, lod_band = sward.lod.band,
// fade_start / fade_end / fade_blend = sward.fade.start / end / blend_from, fade_ground = the terrain's grass colour there.

uniform vec4 lod_dist = vec4(2.5, 5.0, 12.0, 24.0);
uniform vec4 lod_share = vec4(1.0, 0.4, 0.2, 0.05);
uniform float lod_band = 0.25;
uniform float fade_start = 40.0;
uniform float fade_end = 60.0;
uniform float fade_blend = 12.0;
uniform vec3 fade_ground : source_color = vec3(0.27, 0.42, 0.15);
uniform float ground_roughness = 1.0;
uniform float winter_flatten = 0.0;  // sward.winter.flatten in winter and snow, else 0
uniform float winter_height = 1.0;   // sward.winter.height in winter and snow, else 1
uniform float snow_depth = 0.0;      // sward.snow.depth_m (or the engine's snow depth) in snow, else 0
varying float v_sward_look;

// the share of the blades drawn at distance d: log-interpolated through the rings, flat past the last
float sward_share(float d) {
	vec4 l = log(lod_share);
	if (d <= lod_dist.x) return lod_share.x;
	if (d < lod_dist.y) return exp(mix(l.x, l.y, (d - lod_dist.x) / (lod_dist.y - lod_dist.x)));
	if (d < lod_dist.z) return exp(mix(l.y, l.z, (d - lod_dist.y) / (lod_dist.z - lod_dist.y)));
	if (d < lod_dist.w) return exp(mix(l.z, l.w, (d - lod_dist.z) / (lod_dist.w - lod_dist.z)));
	return lod_share.w;
}

// density 0..1: the terrain's grass weight at the blade (sampled at its world xz), or the tile's four corner values
// (instance custom data, tile-local order -x-z, +x-z, -x+z, +x+z) mixed bilinearly by vertex.xz / tile_m + 0.5; 1 = full
void sward_vertex(inout vec3 vertex, vec4 custom1, mat4 model, vec3 camera, float density) {
	float d = distance(camera, (model * vec4(vertex, 1.0)).xyz);
	// a blade of rank r shrinks into the ground as the share passes r; the blades left widen (share x width stays 1)
	float S = sward_share(d);
	float lo = S - max(1e-4, lod_band * S * clamp((1.0 - S) * 8.0, 0.0, 1.0));
	// the density thins by the same per-blade threshold (the blades left do NOT widen for it) and shortens them
	float Sd = S * density;
	float lod = Sd - max(1e-4, lod_band * Sd * clamp((1.0 - Sd) * 8.0, 0.0, 1.0));
	float vis = 1.0 - smoothstep(lod, Sd, custom1.z);
	vertex.xz += custom1.xy * (vis / (S * custom1.w * (1.0 - 0.5 * (S - lo) / S)) - 1.0);
	vertex.y *= vis * mix(0.45, 1.0, smoothstep(0.0, 0.7, density));
	if (winter_flatten > 0.0) {  // winter straw: laid over one way (a direction that drifts slowly over the WORLD), shorter
		float h = vertex.y;
		vec3 w = (model * vec4(vertex, 1.0)).xyz;
		float a = 2.0 * sin(w.x * 0.21) + 2.0 * cos(w.z * 0.17);  // (any smooth world noise x 2 pi)
		vec3 dir = inverse(mat3(model)) * vec3(cos(a), 0.0, sin(a));
		vertex.xz += dir.xz * h * winter_height * winter_flatten;
		vertex.y = h * winter_height * (1.0 - winter_flatten);
	}
	vertex.y -= snow_depth;  // snow buries it: the tile sinks, the snow (the ground the engine draws) hides the rest
	// past the fade's start the blades sink; their look goes to the ground's over a longer run
	vertex.y *= 1.0 - smoothstep(fade_start, fade_end, d);
	v_sward_look = 1.0 - smoothstep(fade_blend, fade_end, d);
}

void sward_fragment(inout vec3 albedo, inout vec3 normal, inout float rough, mat4 view) {
	albedo = mix(fade_ground, albedo, v_sward_look);
	normal = normalize(mix((view * vec4(0.0, 1.0, 0.0, 0.0)).xyz, normal, v_sward_look));
	rough = mix(ground_roughness, rough, v_sward_look);
}

// vertex():   sward_vertex(VERTEX, CUSTOM1, MODEL_MATRIX, CAMERA_POSITION_WORLD, density);  ... then the wind
// fragment(): ALBEDO = ...; ROUGHNESS = ...; sward_fragment(ALBEDO, NORMAL, ROUGHNESS, VIEW_MATRIX);
