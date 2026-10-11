"""patch_v3.py: manual v2 -> v3 (the m3 / s3 drivers' corrections + mm: moves)."""
from pathlib import Path

p = Path("/home/joe/dev/hifipushie/.claude/worktrees/agent-ab7a5deaee4f6c3b5/src/hifipushie/gnm_driving_guide.md")
s = p.read_text()
R = [
    ("""drivers WITHOUT the manual passed 3 / 14, WITH it 7 / 14 (easy 5 / 8, medium 2 / 3, hard 0 / 3). Method, numbers and
dead ends: docs/notes/gnm_atlas.md "## gnmdrive".""",
     """drivers WITHOUT the manual passed 3 / 14, WITH it (v1) 7 / 14; on 14 more pairs 3 / 14 vs (v2) 6 / 14: 6 / 28 vs 13 /
28 pooled. Method, numbers and dead ends: docs/notes/gnm_atlas.md "## gnmdrive"."""),
    ("""zone's normal / against its surround), `nd:<gap>`, `gnm:<control>`.""",
     """zone's normal / against its surround), `mm:<measure>` (a measure you can SEE moved by that many mm, every other
measure held in mm: the precise finishing move), `nd:<gap>`, `gnm:<control>`."""),
    ("""- **Several free moves in one step compound**""",
     """- **Masses with macros and pc: moves, then MEASURE and finish with `mm:` moves.** The sheets say how many mm a
  pixel is: read the gap (pupils, the chin's tip, the forehead against the nasion, the philtrum) and type the mm:
  `{"mm:chin_forward": 2.5}`. Measures: pupils_apart, eyes_forward, eyes_height (over the nose base), brows_over_eyes,
  forehead_forward (vs the nasion), tip_forward, subnasale_forward, upper_lip_forward, lower_lip_forward, chin_forward,
  philtrum_length, chin_length, nose_length, cheekbone_width, jaw_width, chin_width, mouth_width, nose_width,
  skull_width, skull_top, skull_back, neck_width, under_chin. Cost |dc| 0.3-1.2 per mm, the rest of the face held.
- **Several free moves in one step compound**"""),
    ("""there. Under the chin, green above / behind red = the target is the fuller one.""",
     """there. Under the chin the line slopes, so judge it at right angles to the line: if the target's (red) line sits
  further from the jaw bone (lower and further out from the throat), the target is the fuller one (two drivers got
  this backwards: say which line is outside in words before you choose the sign)."""),
    ("""| Forehead stands forward of / behind the nasion (upright and full vs sloping) | `forehead_slope!` (- = forward, upright) | forehead -3.0 mm vs the nasion per +1 |""",
     """| Forehead stands forward of / behind the nasion (upright and full vs sloping) | `mm:forehead_forward` (mm) or `forehead_slope!` (- = forward, upright) | forehead -3.0 mm vs the nasion per +1 (by eye at the upper forehead less: a 9 mm gap took -2.5) |"""),
    ("""| free `jaw_width` +1, `cheek_fullness` +1, `under_chin` -0.6 (or `face_width` +1 if the skull is wider too) | jaw_width +1: jaw angles 8.8, neck 6.4, chin 3.9 mm | 1.5 each overshot 3-4 mm all round (compounding): ~1.0.""",
     """| free `jaw_width` +1, `cheek_fullness` +1, `under_chin` -0.6 (or `face_width` +1 if the skull is wider too); a fat face with jowls and a double chin: `gnm:head_000` -2 (a driver's biggest single win) | jaw_width +1: jaw angles 8.8, neck 6.4, chin 3.9 mm | ~1.0 each for a moderate gap (1.5 each overshot 3-4 mm), 1.5 each for a very large one (worked on m3_01)."""),
    ("""| Face wider just below the ears (masseter / parotid bulge) | `sculpt:parotid` (+, mm) | +2.5 mm per mm | jaw_width / face_width didn't reach it |""",
     """| Face wider just below the ears (masseter / parotid bulge) | `sculpt:parotid` (+, mm) | +2.5 mm per mm | jaw_width / face_width didn't reach it; -0.8 was invisible: 2 mm or more |"""),
    ("""| Chin stands forward / back in profile | `pc:chin_region1` (+: pogonion +3.6 mm, |dc| 1.0) or `chin_projection!` (+2.9 mm, lower lip +1.6) | |""",
     """| Chin stands forward / back in profile | `mm:chin_forward` (mm, vs the lower lip) or `pc:chin_region1` (+: pogonion +3.6 mm in the head, ~1.4 mm against the lips, |dc| 1.0) or `chin_projection!` (+2.9 mm, lower lip +1.6) | | pc:chin_region1 by eye: 0.6 barely moved, 1.8 gave ~2.5 mm: measure and use mm:chin_forward. |"""),
    ("""| Fuller lips (taller red in front) | `lip_fullness` free (pulls the nose tip back 1.9 mm: often welcome) or `lip_fullness!` | |""",
     """| Fuller lips (taller red in front) | `lip_fullness` free (pulls the nose tip back 1.9 mm: often welcome) or `lip_fullness!` | | free also drags lip_projection +0.68 (lips and chin ~1.5 mm forward): put the muzzle back with `pc:upper_lip_region0` (-). |"""),
    ("""| Longer upper lip: the mouth sits lower under the same nose | `philtrum!` (+) | 2.0 mm per sd, very clean |""",
     """| Longer upper lip: the mouth sits lower under the same nose | `mm:philtrum_length` (mm) or `philtrum!` (+) | 2.0 mm per sd, very clean | a "doubled lip seam" in the onion skin can be the lip's shape, not its height: philtrum! +1.5 didn't fix one |"""),
    ("""| Tip projects more, the bridge right | `nose_projection` free (+) | tip +3.6, nasion +2.1 mm |""",
     """| Tip projects more (less), the bridge right | `mm:tip_forward` (mm: the tip against the nose base, the bridge held) or `nose_projection` free (+) | tip +3.6, nasion +2.1 mm | free nose_projection (-) drops the bridge with the tip: mm:tip_forward is the clean one. |"""),
    ("""| The eyes AND brows sit lower (higher) over the same nose base | `nose_length!` (+: they rise; -: they drop) | eyes +1.9, nose base -1.5 mm per +1 |""",
     """| The eyes AND brows sit lower (higher) over the same nose base | `mm:eyes_height` (mm) or `nose_length!` (+: they rise; -: they drop) | eyes +1.9, nose base -1.5 mm per +1 | nose_length! drags face_length +0.6 per sd (the head longer): pair it with `face_length` (-). |"""),
    ("""| Pupils further apart (the onion skin shows irises doubled side by side) | `head_size` (+) | pupils +3.1 mm (and the face 6 mm wider) |""",
     """| Pupils further apart (the onion skin shows irises doubled side by side) | `mm:pupils_apart` (mm: the eyes alone, |dc| 0.61 per mm) | head_size moves them 3.1 mm per sd but the face 6 mm wider: too blunt when the outline already matches (two drivers) |"""),
    ("""| Eyes prominent, standing forward of the brow (more white in profile) | `eye_depth` FREE (-) | eyeballs +4.2 mm forward of the nasion (nasion -2.8, tip -3.5) |""",
     """| Eyes prominent, standing forward of the brow (more white in profile) | `mm:eyes_forward` (mm) or `eye_depth` FREE (-) | eyeballs +4.2 mm forward of the nasion (nasion -2.8, tip -3.5) |"""),
    ("""| Brows sit lower / higher over the eyes | `brow_height` free (2.7 mm), then `brow_height!` to finish (2.65 mm, clean) | |""",
     """| Brows sit lower / higher over the eyes | `brow_height` free (2.7 mm), then `brow_height!` or `mm:brows_over_eyes` to finish | brow_height! reads about HALF its 2.65 mm by eye (0.7 invisible, 1.5 for ~2 mm) | free at 2 drags lip_projection +0.85, the bridge -1.1 sd and pushes the forehead and nose ~2 mm forward;"""),
    ("""| The cheek's front plane stands forward / back in 3/4, the front width right | `relief:cheeks` (+ forward, mm; 1.3 mm per mm, very clean) or `sculpt:cheeks` (-2.5 worked on a too-full cheek) | |dc| 2.4 per mm |""",
     """| The cheek's front plane stands forward / back in 3/4, the front width right | `relief:cheeks` (+ forward, mm; 1.3 mm per mm) or `sculpt:cheeks` (-2.5 worked on a too-full cheek) | |dc| 2.4 per mm | relief:cheeks drags cheek_fullness ~0.9 sd per mm (the jowl widens; -1.5 thinned the lower cheek): not for a bone point. |
| The cheekbone / the apple under the eye stands proud in 3/4 (fullness HIGH on the cheek, not on the jowl) | `sculpt:malar` (mm) | | +4 matched an upper-cheek bulge, -1.5 a cheekbone proud in 3/4 (two drivers) |"""),
    ("""- "Bigger eyes": pupils apart (`head_size`) vs""", """- "Bigger eyes": pupils apart (`mm:pupils_apart`) vs"""),
    ("""- "Nose further out": the whole nose (`pc:nose_region0`) vs the radix (`sculpt:radix`) vs the tip (`nose_projection`).""",
     """- "Nose further out": the whole nose (`pc:nose_region0`) vs the radix (`sculpt:radix`) vs the tip (`mm:tip_forward`).
- "Cheek proud in 3/4": the plane (`relief:cheeks`) vs the bone / apple under the eye (`sculpt:malar`) vs the lower face
  (`cheek_fullness`).
- "Lips sit lower": the philtrum (`mm:philtrum_length`) vs the lip's shape (no move: record it)."""),
    ("""any driver: puffy lower-lid bags, dark hollow sockets, brow arch, a crisp lid crease, a narrow dorsum other than
through sculpt:bridge_walls.""",
     """any driver: puffy lower-lid bags, dark hollow sockets, brow arch / brow shape (straight vs angled), a crisp lid
crease, a narrow dorsum other than through sculpt:bridge_walls, a bulge at the nape in 3/4."""),
]
for a, b in R:
    assert a in s, a[:80]
    s = s.replace(a, b)
p.write_text(s)
print("ok", len(R))
