"""Levels of detail for an exported character (asset.export(lods=[...])): every part's LOD0 low poly decimated to a
share of its triangles, ON THE SAME ATLAS (the LODs' GLBs reference LOD0's maps beside them), keeping what an engine
needs to swap them without a pop at the seams: skin weights, morph targets (face shapes), the native head / body split.

How: the part is cut into its glTF vertices' patches (one patch = triangles joined through vertices that share
position, uv, normal and tangent: a uv island inside one smoothing group, and the head / body meshes apart). Each patch
is decimated alone by quadric collapse (pyfqmr) with its BORDER held, so a uv seam, a hard edge and the head / body seam
ring keep their vertices exactly on both sides: no crack, no uv bleed across a chart. Every new vertex reads its
attributes at its closest point of its OWN patch of LOD0 (barycentric): uv, normal, tangent, the 4 bone weights (the
union of the corners' re-cut to 4), each face shape's move and normal turn, vertex colour. Border vertices sit on LOD0
vertices, so they read them exactly. Hair cards and the eyelash ribbons are cards (every vertex a border): they are not
decimated here (hair LODs are its card tiers).

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at lods.NAME: C422). lods_under: layers under covers: depth under a cover, orientation to covers, culling
what is covered, ringed islands, stray flaps, push_under_layers. lods_pieces: A part in pieces: split and decimate,
patch offsets and seating, patches, hull and small pieces, lifting made sheets, seam welds, fold guards, deviation,
welded pieces. lods_part: one part's LODs and all parts': the LOD shell, lod_part, card and ribbon LODs, lod_parts,
thin_strands.
"""
from __future__ import annotations
from . import moved

LOD_RATIOS = (0.5, 0.25, 0.12)  # share of LOD0's triangles per level (Joe's call: budgets per tier)
MIN_PATCH = 12  # triangles: smaller patches are kept as they are
HAIR_TIERS = ("main", "npc", "far")  # the hair's card tier at LOD1, 2, 3+ (hair.CARD_TIERS: one atlas for all)
MIN_PART = 1000  # triangles: smaller parts (eyes, teeth, props) are kept whole (the LOD3 eyes lost their cornea)
LOD_SMALL_FAR_RATIO = 0.15  # (r55) ... except at LODs whose ratio for the part is below this (LOD3), where they keep
LOD_SMALL_FAR = 0.5  # this share: ~4.9k triangles of small parts (shoes, tongue, laces, lanyard, clip, socks) were LOD3's
# floor, 40% of its 12,360; at LOD3's distance (several metres) a shoe or a clip at half its triangles reads the same
LOD_SMALL_KEEP = ("eyes",)  # ... but never these (the cornea)
CARDS_MIN = 0.2  # a hair LOD keeps at least this share of its card layer's triangles (the biggest cards)


POSE_SHAPE = "corr_"  # pose correctives (correctives.py) stay in every LOD: a LOD without face shapes still bends

LOD_SEAT_PATCHES = True  # (r58) outer pieces kept whole (patch pockets) are re-seated on the DECIMATED panel at their LOD0
# offset: kept whole over a coarser panel that no longer matched them, rc2h's LOD2 left hip pocket stood off as a twisted
# flap and the left chest pocket crumpled (the panel came through it). Each piece vertex goes to its closest point on the
# decimated rest of the outer shell + its LOD0 signed offset along that face's normal (within LOD_SEAT_REACH).
LOD_SEAT_REACH = 0.02  # m

LOD_MADE_SHEETS = True  # (2026-10-19) a shell's "made" triangles (cloth.EXPORT_MADE_SHEETS: made-piece fronts, then their
# backs and rims) are decimated as sheets at the made floor and their backs rebuilt from them, like the garment's inner
# shell: decimated as closed slabs the fronts and backs crossed (Garrett's open shirt collar: flat facets, back faces out)
LOD_MADE_FLOOR = 0.35  # (r54) a two-sided garment's made pieces (pockets, collar, lapels, buttons: the triangles after its
# shells) keep at least this share at every LOD: at the coat's LOD2 share (0.11) its 1,176 made-piece triangles went to
# 134, the pockets became fans of a few long triangles and the decimated outer shell came through them (grey fans on the
# LOD1-3 fronts, r54/zoom4.png). ~1.2k triangles at LOD0, so the floor costs ~350 at LOD3.
LOD_MADE_FLOOR_X = 2.0  # (r55) ... but at most this x the LOD's ratio: the flat 0.35 put LOD3 164 over its 12,360 (lapels at
# 2 x the shell's resolution still read at LOD3's distance)
LOD_KEEP_PIECE = 200  # triangles: (r55) a made piece that is its own small connected piece (a button: 174) is decimated
# apart from the collar / lapels: decimated with them at the made floor, rc2d's buttons became grey cones. Kept whole ...
LOD_KEEP_PIECE_RATIO = 0.1  # ... at LODs whose ratio is at least this (LOD1, LOD2), and below it (LOD3) at
LOD_KEEP_OUTER_PIECES = True  # (r56) ... and so is a small piece of the OUTER shell (a patch pocket: 106 triangles, 62
# of their vertices on its border). Welded with the coat it was decimated with its border held: at LOD2 a fan of ~60
# long triangles from one vertex, the pale streaks the coordinator saw after LOD_REWIND. Its inner shell is rebuilt with
# the outer's. (LOD_FOLD_GUARD below did not help: the fan never bends, it is the border held around no interior.)
LOD_KEEP_PIECE_FAR = 0.15  # this share (a button is a few pixels at LOD3's switch distance)


LOD_PATCH_GAP = 0.006  # m: (r56) ... only a small outer piece lying ON the rest of the outer shell (its vertices' median
# distance to the rest's surface under this: a patch pocket ~2.6 mm) is kept whole: rc2f's sweater, its outer shell cut
# into many small pieces by the garment cull, stayed at 3,836 triangles from LOD1 to LOD2 (LOD2 2.4k over budget).

LOD_KEEP_PIECE_HULL = True  # (r61) at the far LOD (ratio below LOD_KEEP_PIECE_RATIO) a small made piece (a button) is
# replaced by its convex hull before it is decimated: fqmr took rc2l's 174-triangle buttons (a dome with four thread
# holes) to ~26 crumpled triangles at LOD3; the hull (on the piece's own vertices: uv, weights, shapes carried) is a clean
# lens that decimates to a clean lens
LOD_KEEP_PIECE_HULL_FLAT = 0.08  # ... not a piece flatter than this (thinnest / widest spread)

LOD_MADE_GAP = 0.001  # m: (r54) ... and every made-piece vertex whose garment's decimated outer shell lies less than this
LOD_MADE_REACH = 0.008  # m: ... inside it (within this along its normal, either way) is lifted out to this over it


LOD_LIFT_RIGID = True  # (r56) see _lift_made

LOD_REWIND = True  # (r55) see lod_part: folded-over decimated triangles wound to face their normals
LOD_WELD = True  # (r51) a part whose per-patch decimation misses its share (patch borders are kept: uv seams, smoothing
# groups) is decimated welded instead, per mesh, and each new triangle takes the uv island of the LOD0 triangle nearest it
LOD_WELD_OVER = 1.25  # ... when the per-patch result has more than this x the share's triangles. Tess's r50 body (a template
# wrap cut into many uv islands) stopped at 3,238 and the coat / jeans at ~3.5k / 3.0k from LOD1 to LOD3: the islands'
# borders were the floor, so LOD2 / LOD3 went over budgets.py's shares.
LOD_BORDER_OVER = 1.25  # (r52) a welded mesh still over this x its share is redecimated with border collapses allowed:
# pattern-piece cloth is mostly border (sim seams are not coincident vertices; rc2's LOD3 coat 3,492 triangles had 2,074
# border edges), so the coat / jeans / sweater stayed at 3.5k / 3.0k / 2.4k from LOD2 to LOD3 even welded.
LOD_BORDER_SHARED = False  # (r59, OFF after rc2j: changed nothing at LOD2 (the fly slit stayed, counts identical), +1.3k at LOD3 (jeans 346 -> 1012), neckline unchanged) the LOD_BORDER_OVER redecimation (border collapses) is skipped for a group of a part whose
# border touches another group of it (within LOD_SEAM_WELD): rc2i's LOD2 jeans opened a slit at the fly (body skin and the
# coat's inside seen through it: no jeans along the pick ray), its panel's border collapsed away from the made piece's
LOD_SEAM_WELD = 0.002  # m: (r53) in a welded decimation, BORDER vertices closer than this are joined first. The border
# collapses alone (LOD_BORDER_OVER) met the shares but opened the sim's seams (0.1-0.5 mm apart, not shared vertices):
# rc2b's LOD2 / 3 coat showed grey slits at its seams and pockets. Joined, a seam is an inner edge (decimated across like
# cloth) and only the true openings (hems, front edges, cuffs) stay borders.
LOD_SEAM_WELD_NO_CHAIN = True  # (r60) see _weld_seams

LOD_FOLD_GUARD = ()  # (r56, off: see LOD_KEEP_OUTER_PIECES; (2.0, 4.0) to try) a welded decimation that folds triangles over (rc2e's LOD2 coat pockets: 64 of 151;
# LOD_REWIND only turned them to face out, the pale fan streaks stayed) is redone with the LOD0 triangles around the
# folds cut out as their own piece (borders held, so the two pieces still share their cut) at these x the ratio in turn,
# kept whole when both still fold; the rest is decimated to what is left of the target.
LOD_FOLD_GROW = 2.0  # ... the cut-out: LOD0 triangles within this x a folded triangle's longest edge of its centroid

LOD_DEV_MAX = 0.015  # m: (r60) a welded group's decimation whose farthest LOD0 vertex lies more than this off the result is
# redone with LOD_DEV_GROW x the target (up to LOD_DEV_TRIES times): fqmr reaches a small target by raising its error
# threshold until it collapses across a deep fold (rc2j's LOD2 jeans: the crotch bridged front to back, 41 mm off LOD0, the
# body seen through a slit at the fly; the outer shell at 0.11 = 369 triangles)
LOD_DEV_GROW = 1.3
LOD_DEV_MIN_TRIS = 1000  # (r61, = MIN_PART) groups with fewer LOD0 triangles than this are not redone (small parts: shoes, soles); at their small_far ratio (0.5) the bound is 3.3 mm, so the guard grew rc2l's LOD2 shoes 371 -> 629, soles 143 -> 243 (rc2i's were fine)
LOD_DEV_REF = 0.11  # ... LOD_DEV_MAX holds at this ratio and scales with (LOD_DEV_REF / ratio) ** LOD_DEV_POW (farther LODs, coarser)
LOD_DEV_POW = 1.0
LOD_DEV_TRIES = 2  # (4: LOD3 coat 976 -> 2304, over the LOD3 budget; 2: ~ +0.8k at LOD3, +1.0k at LOD2)

RIBBON_WIDEN = 3.0  # a ribbon LOD widens its kept ribbons by 1 / ratio, at most this (coverage at a distance)

LOD_UNDER_GAP = 0.002  # m: (r53) an under garment's vertex is put at least this far under its cover at every LOD
LOD_UNDER_FACES = True  # (r57) push_under_layers also tests points inside faces (a long face pokes between vertices)
LOD_UNDER_FACE_GRID = 4  # (r58) ... a barycentric grid with this many steps per edge (corners left out) + the centroid (1 = the centroid alone):
# rc2h LOD2 showed a hexagonal sweater patch through the coat at her right armhole (flat-ID render + a ray pick: sweater
# 5 mm in front of the coat) where every vertex AND centroid was under it: the coat bends between them
LOD_UNDER_ORIENT = True  # (r67) under_depth: outward normals agree with the nearest cover's facing
LOD_UNDER_FACE_ALIGN = 0.5  # (r67) a poking face moves only corners whose normal is within 60 deg of its own
LOD_UNDER_FACE_DEEP = 0.008  # m: (r58) a face point more than this outside its cover is not a poke but a face that runs
# out from under the cover's edge (a sweater cuff past the coat sleeve: -20 mm at the grid points), left alone
LOD_UNDER_FACE_DEEP_FAR = 0.015  # m: (r61) ... at the far LOD (ratio below LOD_SMALL_FAR_RATIO: LOD3), where a coarse cover
# folds farther: rc2l's LOD3 sweater face stood 12 mm in front of the coat at her right armhole (an orange wedge), its
# vertices under (0.03 pushed a cuff out instead)
LOD_UNDER_LOD0_NORMAL = True  # (r59) see push_under_layers: a last pass along the LOD0 normals (parts with masks)
LOD_UNDER_WORN_MAX = 0.01  # m: (r61) see push_under_layers; 0 = off
LOD_UNDER_REACH = 0.02  # m: ... when its cover lies within this along the vertex's normal (either way)

LOD_UNDER_MAX_MOVE = 0.010  # m: (Garrett s8) no push-under moves a garment vertex further (0 = no cap)
# LOD_UNDER_ORIENT (above) also gates orient_to_covers: (Garrett s7) the under part's "outward" normals agree with the nearest cover's outward

LOD_UNDER_CULL_FROM = 2  # (r60) from this LOD on, a part worn under garments (not the skin: socks) drops the faces whose
# LOD0 points were all under a garment more than LOD_UNDER_CULL_RIM from the nearest LOD0 point that was not: the LOD0 cull
# keeps a 40 mm rim under every opening (close up, a hem rides up), and rc2j's LOD2 showed that rim (the socks' tops) as a
# shard through the decimated jeans' calf, which pushing in along either normal did not cure (socks poking 42 -> 8)
LOD_UNDER_CULL_RIM = 0.015  # m
LOD_UNDER_CULL_GARMENTS_FROM = 1  # (Garrett s10) from this LOD on, an under GARMENT (the shirt) drops its faces that were
# deep under its covers at LOD0 the same way (cull_covered, the same rim): v7's LOD1 back showed a long white shirt shard down
# the right forearm sleeve where the decimated sleeve dips more than LOD_UNDER_MAX_MOVE under the LOD0 shirt (shirt poking
# 86 -> 36, 192 capped); a bigger push sent the shirt out through the other side (v6b), so the hidden faces go instead

LOD_UNDER_ISLAND = 24  # (r65) faces: a patch of faces deeper than LOD_UNDER_FACE_DEEP outside the cover is still a poke
# when it is a small island (at most this many faces) and every face around it is under the cover (rc2p LOD0: a 10-face
# sweater flap 8-22 mm through the coat's upper back, kept as "a face that runs outside" at every export); 0 = off

LOD_UNDER_STRAY = 0.03  # m (r66): an under-layer vertex with NO cover along its own normal (within the reach) but outside
# its cover's nearest surface (signed by the cover's outward normal) by up to this, in a small island ringed by vertices
# under the cover, is a flap through it: moved in along the cover's normal to the gap under it. rc2p/q's coat speck: a
# sweater flap 17-23 mm out of the coat's back whose vertex normals point sideways (0.78, -0.55, 0.28): along them no
# cover in reach, so neither the vertex nor the face test ever saw it (game_ready.md r66). 0 = off.

LASH_LODS = (0.5, 0.25, 0.1)  # share of the lashes' triangles kept at LOD1, 2, 3 (whole lashes, longest first): they
# were 4.9k at every LOD, more than the hero's whole eyes / mouth / lashes budget at LOD0 (budgets.json)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("lods_under", "lods_pieces", "lods_part")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
