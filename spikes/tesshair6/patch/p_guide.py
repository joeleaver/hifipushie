"""p_guide.py: (applied once) hair_guide.md for round six."""
from pathlib import Path

p = Path(__file__).resolve().parents[3] / "src/hifipushie/hair_guide.md"
s = p.read_text()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('''tie_hair(name, style={"tail": {"tousle": 0.9}})                                    # riff: a messier tail (ragged end, strays)
''', '''tie_hair(name, style={"tail": {"tousle": 0.9}})                                    # riff: a messier tail (ragged end, strays)
tie_hair(name, style={"front": {"looseness": 0.6, "drape": 0.6}})                  # riff: a held-back head with a LOOSE front
''')
rep('''`tousle`: 0 = brushed (an even end, nothing leaves the outline), 1 = tousled (locks end anywhere over the last third as pointed wisps that flick out, single hairs and thin wisps leave the outline all round); default 0.05 + 0.75 x wave |''',
    '''`tousle`: 0 = brushed (an even end, nothing leaves the outline), 1 = tousled, as SOFT irregular hair: some locks loosened out of the bundle, lock ends anywhere over the last half and open (no points, no flick), strands drawn fine at up to 2.7 x the count, single hairs and a few thin locks up to 18 cm leaving the outline with a curl; default 0.05 + 0.75 x wave. The hang, fullness and wave are the brushed tail's |''')
rep('''| `hairline` | 0..1 | how SOFT the hair's edge is.''', '''| `front` | 0..1, or {looseness 0..1, drape 0..1, locks: n a side} | the FRONT on its own: the hair in front of the ears sags and stands off the head as if the style were that much looser there, while the back stays as tight as `tightness` (`looseness`); it may hang further over the forehead's corners and temples (`drape`); `locks` = thick loosened locks (30-70 hairs) that fall from beside the part across the forehead's corner and are drawn back over the temple (default round(3 x looseness); none toward a tie above 30 deg). Front wisps get thicker, longer and more with it, so they read against skin from the front. Default none: a neat held-back arc |
| `hairline` | 0..1 | how SOFT the hair's edge is.''')
a0 = s.index("hairline at the temples should be soft (a hard saw edge reads as a wig). BARE SKIN ABOVE OR IN FRONT OF THE EAR")
a1 = s.index("What is still weak (2026-10-12): the head")
s = s[:a0] + '''hairline at the temples should be soft (a hard saw edge reads as a wig). The hairline finds the EAR on the head
itself (hair.ear: the bump on the scalp's rays, every base) and passes `groom.hairline.ear` m (default 6 mm) over its
top, with the sideburn `sideburns` m (default 14 mm) below that top in front of the ear: no per-model patch for a
"shaved" temple any more (until tesshair6 the ear was guessed from the brow, 1-3 cm too high; a negative `ear` from
those days is raised to 3 mm over the ear; `"ear_from": "brow"` keeps an old groom's line exactly). On an up-style
(high ponytail, top knot) the hair runs straight off the temple's line: its row of roots stands at uneven depths and
its strands start one by one over the band, so the edge is combed, not a row of teeth; it is still a visible combed
edge close up. Judge a tail against a picture by MEASURE and over seeds: `look_hair(name, views=["ref2"],
measure={"view": "ref2", "mask": hair_mask.png, "tie": [x, y]})` (below), with `groom_hair(name, groom={"seed": n},
replace=True)` for 3-4 seeds: one draw moves a tail's area about +-10 %. ''' + s[a1:]
rep('''`look_hair(name, views=None, size=480, clay=True, layout=False, reference=None, save=None, only=None, tier=None, debug=None, engine='eevee')`''',
    '''`look_hair(name, views=None, size=480, clay=True, layout=False, reference=None, save=None, only=None, tier=None, debug=None, engine='eevee', stage=None, measure=None)`''')
rep('''Needs the scene once: `sync` the model first.
''', '''views "ref0", "ref1", ...: the FITTED cameras of the model's reference pictures (human_refs.json: the block-in /
face solve's cameras), the whole picture squared: the hair as each picture shows it, always the hair of the spec as
it is NOW (a look never reads a mask or render back from an earlier one).
stage: another model with the same head whose scene is used (a riff's copy of a head needs no scene of its own:
`look_hair("riff", stage="the_head")`).
measure: {"view": "ref2", "mask": png, "tie": [x, y], "colour": true}: the current hair against that picture. mask =
a hair mask in the picture's own pixels (white = hair); the text then gives IoU, area, the outlines' distance (mm)
and, with tie = the tie's pixel in the picture, what hangs below it against hers (area %, length, width, reach in mm).
colour: CIE L* / chroma / hue of the dense hair's shadow / mid / highlight thirds, ours | the picture's, for the
engine rendered: the numbers to set look.eevee_gain / eevee_sat (EEVEE) or look.cycles_fit / cycles_width /
cycles_sat (Cycles) by. The look's own lights are used (look.light), not the picture's: compare bands, not single
pixels. (Sheets before th_30 labelled "Cycles" were path-traced with 2 transmission bounces, which renders dark hair
near black; look_hair(engine="cycles") uses 10.)
Needs the scene once: `sync` the model (or its stage) first.
''')
rep('''  Keys: hairline (front, temples, sideburns, nape, ear, front_points),''', '''  Keys: hairline (front, temples, sideburns = m below the FOUND ear's top, nape, ear = m over it, ear_from "mesh" | "brow", front_points),''')
p.write_text(s)
print("ok")
