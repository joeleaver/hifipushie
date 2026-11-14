"""Tiling rock detail: the rock's grain below ~0.5 m as a small seamless material, laid along the bedding.

Detail by scale (agreed 2026-10-01): geometry carries >= ~1 m (landform, cliffs, beds, blocks); each tile's unique maps
carry the macro (colour, staining, AO, layer weights, the normal of the >= 0.5 m structure) at a few texels/m; what
is finer (grain, small facets, hairline fractures, laminae, crustose lichen) is the same everywhere on one kind of
rock, so it is authored once per rock type as a tileable swatch, and the engine draws it sharp at any distance.

`swatch(rock)`: a SIZE x SIZE m patch of rock face at RES texels/m (s along the strike, t up the beds): polygonal
fracture facets at three sizes (`periodic_cells`: Voronoi planes on a torus, sizes varying place to place), FFT spectra
(periodic by construction), cracks on facet nets' zero lines, clustered pits, veins, per-facet tones. Every term is
periodic in both directions, so the swatch tiles exactly (never cropped and cross-faded); `tileability` measures the
wrap seam like the tile border checks. Its settings (TUNE) are tuned toward CC0 photoscans by `swatch_stats` (slope and
albedo per octave, edges, fractures; 2026-10-01: the scans had 3x our slope and 5-10x our albedo variation in every
octave). `scan_swatch(set)` takes a scan (asset pack rock_scans) as the swatch instead (export cfg detail_source).

`DetailProjection`: where the swatch lies. Strike-binned planar projection: BINS vertical planes round the compass
(u = p . d_k, to the right as one faces the rock) plus the top plane, v = the bed coordinate (z + the beds' offset:
terrain_rock.bed_offset + the wander, the same coordinate the solid rock's beds use), so the swatch's grain and laminae
run along the beds and are never stretched by more than 1 / cos(22.5 deg) = 1.08. Which planes apply follows the
rock's normal averaged over RADIUS (a pure function of position: tiles agree at their borders, LODs agree). Exported
per cliff-tile vertex as `_DETAIL` (strike x, y, side share, bed coordinate) for shaders that blend the two nearest planes
and the top (seamless, like triplanar), and as a UV set (each triangle on its nearest plane: stock engine detail maps
on a UV channel; seams where the plane changes). A single global UV can't follow the strike: round every peak the
faces close into a ring, and a function's gradient can't circulate (a least-squares strike coordinate came out at
0.37 m per metre on the alps wall: the swatch stretched 2.7x).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_swatch.NAME: C422). terrain_swatch_periodic: periodic pieces a swatch is made of: facets, spectral
noise, cells, pits, veins, all wrapping at the tile's edge. terrain_swatch_make: making a swatch: `swatch`, a scanned
swatch, its stats, the detail swatch, tileability. terrain_swatch_detail: A swatch as detail on the ground: the detail
image, the repetition's profile and fade, `write`, the bed-aligned projection. terrain_swatch_lines: the structure's
lines (a macro map): joint openness, drawn beds and joints, `structure_lines`.
"""
from __future__ import annotations

import numpy as np
from . import moved

SIZE = 4.0        # m: the swatch's side
RES = 256         # texels per metre (1024 x 1024)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# The procedural swatch's settings, tuned toward measured CC0 rock scans (swatch_stats; examples/scan_compare.py):
# cells = facet sizes (m) and their tilt (rms slope), step and cup (m); fractures = facet nets whose zero lines crack,
# their coverage (`on` thresholds), half-width and depth (m); albedo: per-octave tone noise, per-facet tones (each
# softened over `cell_soft` x its size), proud places lighter, weathering patches, grime round and under fractures.
# 2026-10-01 (rock5): albedo rms per octave 0.05-0.07 -> 0.13 at 0.25-1 m falling to 0.06-0.09 below 6 cm
# (rock_face_03: 0.10-0.12 flat; flat at that level read as speckled dirty granite on pebble's dark rock at 15 m, so
# the energy sits in the larger octaves), luminance std 0.195 -> 0.28 (0.32), percentiles 1/5/50/95/99 of the
# multiplier 0.49/0.60/0.96/1.54/1.84 (the scan's 0.50/0.60/0.96/1.54/1.85: a long pale tail, `skew`), correlation with
# high-passed height 0.12 -> 0.25 (0.23); hard per-facet tones that strong read as terrazzo, so they are softened
TUNE = {
    "cells": [{"size": 0.32, "stretch": 1.3, "vary": 1.6, "slope": 0.10, "step": 0.006, "cup": 0.005, "soft": 0.12},
              {"size": 0.09, "stretch": 1.1, "vary": 1.2, "slope": 0.12, "step": 0.002, "cup": 0.0015, "soft": 0.12},
              {"size": 0.03, "stretch": 1.0, "vary": 1.0, "slope": 0.14, "step": 0.0006, "cup": 0.0004, "soft": 0.2}],
    "rough": 0.0025, "rough_beta": 0.9,
    "fractures": [{"net": 0.7, "on": [0.0, 0.3], "width": 0.006, "depth": 0.025},
                  {"net": 0.3, "on": [0.1, 0.35], "width": 0.004, "depth": 0.012}],
    "scars": 0.035,
    "speck": 0.55, "speck_beta": 0.3, "cell_tone": [0.17, 0.2, 0.13], "cell_soft": 0.15, "proud": 0.07,
    "rough_var": 0.15, "patch": 0.22, "halo_m": 0.03, "streak_m": 0.15, "grime": 0.35, "skew": 1.0,
}

SCAN_PX = 1024  # a scan's swatch is resampled to this many pixels across

VARIATION_M = 24.0          # m: the anti-tiling mask's period on the detail UV
VARIATION_SCALE = 1.618     # the second sampling's size: the swatch at SIZE x this
VARIATION_OFFSET = [0.37, 0.71]  # its offset (in swatches)
TILE_LIMIT = 1.5  # a wrap seam jumping more than this x its neighbours' steps shows as a line every swatch


REF_VIEW = (1920, 60.0)     # px, deg: the camera the manifest quotes fade distances for


REPEAT = {"periodicity": 0.3, "contrast": 0.02, "px": 768, "span": 2.0}

RECIPE = (
    "The tile maps are macro only (a few texels/m: colour, AO, roughness, layer weights, the normal of the >= 0.5 m "
    "structure); the rock below ~0.5 m is a tiling swatch per rock type, drawn on top in the shader. glTF viewers that "
    "ignore it show the macro maps alone (the reference material): correct, softer up close. Per pixel, on cliff tiles, "
    "where the rock layers weigh w = sum of the `layers`' weights (_WEIGHTS / the weights map):\n"
    "1. Projection (seamless, custom shader): s = normalize(_DETAIL.xy) (the strike, u runs to the right as one faces "
    "the rock), v = _DETAIL.w (the bed coordinate, m). theta = atan2(s.y, s.x) / (2 pi / bins); k0 = floor(theta), f = "
    "theta - k0; for k in (k0, k0 + 1): d_k = (cos, sin)(k 2 pi / bins), uv_k = (dot(worldpos.xy, d_k), v), tangent "
    "T_k = (d_k, 0), bitangent B = +z (both projected onto the surface and normalised). Blend the two by f^4 / (f^4 + "
    "(1 - f)^4). Top plane: uv = worldpos.xy, T = +x, B = +y. Blend sides vs top by _DETAIL.z (the side share). "
    "Simpler (stock detail maps): TEXCOORD_<texcoord> holds each triangle's nearest plane (metres; seams where the "
    "plane changes); its tangents are MikkTSpace on that UV set, or the analytic T/B above.\n"
    "2. Anti-tiling: sample the swatch at uv / size_m and at uv / (size_m x variation_scale) + variation_offset; mix by "
    "the variation texture (R) sampled at uv / variation_m.\n"
    "3. Albedo: macro base colour x (1 + w (2 x albedo_detail - 1)) (the albedo texture is linear, 0.5 = unchanged). "
    "Roughness: ORM.g x (1 + w (2 x rough_detail - 1)).\n"
    "4. Normal: the detail normal (tangent space on the plane's T/B, glTF convention) in world space, combined with "
    "the macro normal by RNM about the vertex normal Nv: t = Nm + Nv; u = 2 (Nd.Nv) Nv - Nd; n = normalize(t (t.u) / "
    "(t.Nv) - u); then mix(Nm, n, w).\n"
    "5. Lines (the lines map, TEXCOORD_0, linear filtering, never sRGB): per set (R/B bed planes, G/A joints) s = (c - "
    "0.5) x 2 x line_d metres, a = strength; half-width = (1.2 + 3.3 n) cm x (0.5 + 0.5 a) with n 0..1 wandering "
    "along the line over ~1.5 m, its edge wandering +-40% of it over ~10 cm (never to zero: a width that reached 0 "
    "under a fixed jitter drew dashes); crack = a (1 - smoothstep(0, 0.02, |s| - edge)); shadow = a (1 - "
    "smoothstep(0.015, 0.06, |s|)); albedo x (1 - (0.45 crack + 0.3 shadow) w); a groove: height -(crack + 0.5 shadow) "
    "x 4 cm (bump or derivatives of s). The signed distances interpolate linearly across a line, so it stays crisp at "
    "any distance. The lines never fade.\n"
    "6. Distance fade (fade): mipmaps (trilinear/anisotropic) handle the detail's aliasing; the fade only hides its "
    "repetition, measured from the swatch (repetition: contrast and periodicity of the mipped, anti-tiled detail per "
    "footprint). With p = the pixel's footprint in metres (length(fwidth(worldpos)), or view distance x the pixel's "
    "angle), w_detail = w x (1 - smoothstep(ln footprint_m[0], ln footprint_m[1], ln p)) for the albedo and normal "
    "terms (distance_m quotes the same for a 1920 px, 60 deg view); footprint_m null = no fade needed.")


# ---------------------------------------------------------------- the structure's lines (a macro map)
LINE_D = 0.5  # m: the lines map's signed distances run -LINE_D..LINE_D (8 bits: 4 mm a step)


JOINT_OPEN = {"across": 2.2, "along": 7.0, "up": 6.0, "lo": 0.72, "hi": 0.88, "thick": (1.4, 2.4)}

LINE_GATE_TX = (1.5, 2.5)  # texels: a line's strength fades out between these distances from it


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_swatch_periodic", "terrain_swatch_make", "terrain_swatch_detail", "terrain_swatch_lines")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
