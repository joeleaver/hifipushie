# Hair: tied-back hair as a style (`tie_hair`)

Read guide(topic="hair") first: describe the hairstyle in words before touching a knob.

The way to ask for swept-back tied hair. One call, a handful of words; the same call on any head gives the same
hairstyle, and a riff changes one word:

```
tie_hair(name, style={"tie": "low", "side": "left", "tightness": 0.3, "neatness": 0.2,
                      "tail": {"length": 0.24, "wave": 0.8, "fullness": 0.8}})     # a loose low side ponytail
tie_hair(name, style={"tie": "high", "side": "centre", "tightness": 0.9, "part": "none"})   # riff: high and tight
tie_hair(name, style={"tail": "bun", "tie": "top"})                                # riff: a top knot
tie_hair(name, style={"tie": "low", "side": "left", "tightness": 0.85, "neatness": 0.95, "wisps": 0.7,
                      "tail": {"length": 0.24, "wave": 0.6, "fullness": 0.75}})    # sleek head, front wisps, a poofed tail
tie_hair(name, style={"hairline": 0.0})                                            # riff: a gelled, hard-edged hairline
tie_hair(name, style={"tail": {"tousle": 0.9}})                                    # riff: a messier tail (ragged end, strays)
tie_hair(name, style={"front": {"looseness": 0.6, "drape": 0.6}})                  # riff: a held-back head with a LOOSE front
tie_hair(name, style={"volume": 0.6})                                              # riff: BODY: the hair stands up from the part and arcs over
tie_hair(name, look={"sun": 0.8, "highlights": 0.4})                               # riff: sun-lightened lengths, lighter ribbons
tie_hair(other, carry_from=name)                                                   # the same hair on another head
look_hair(name, views=["around"])                                                  # six sides with the bust
```

What the words mean (all optional; `tie_hair(name)` alone is an ordinary low ponytail with a centre part):

| word | values | what it does |
|---|---|---|
| `tie` | nape, low, mid, high, top (or deg) | the tie's height on the back of the head |
| `side` | centre, left, right (or deg) | off to the person's own left / right (a side ponytail) |
| `tightness` | 0..1 | 1 = scraped back flat; 0 = loose: the hair sags between root and tie, stands off the head, hangs over the temples |
| `lift` | 0..1 | a few mm of lift at the roots and over the top (default 1 - tightness); the default of `volume` |
| `volume` | 0..1, or {amount 0..1, crown, sides, nape (x the amount there), root 0..1, arc 0..1, layers 0..1, hold 0..1} | the hair's BODY over the head. 0 = a cap lying on the skull (every strand runs straight to the tie along the scalp); 1 = big loose hair. With volume the hair STANDS UP out of its root, and out of the parting on both banks (`root`: 0 = eases off the scalp over ~4 cm, 1 = stands straight up and bends over within a cm), carries a dome (3.4 cm at the crown, 3 cm above the temples, 1.4 cm at the nape at amount 1; widest high, close where it passes over the ear), in LAYERS (`layers`: 0 = one shell, 1 = locks at every height: a thick mass, under-layers darker by look.depth), and its way first FALLS sideways and down from the root before the tie takes it back (`arc`: convex arcs from the part to the temple; default = amount), keeping its height until just before the tie (`hold`, default 1 - tightness; the tie then stands further off the head). Also `locks` 0..1 (the mass as LOCKS, not one combed shell: each lock's height swells and sinks along it, it wanders and crosses its neighbours, a few are lifted off the mass, widths and clump sizes differ; default by the amount) and `cross` 0..1 (a share of a part's bank locks lean over the line: no clean valley between two lobes). Default: `lift`, but NONE for an up-style (tie high / top: hair pulled up does not fall from its roots; asked for there it is a smooth pouf without fall, layers or locks) and none for half up. Measured on one photographed head: its outline stands 17-19 mm off the skull over the top, 17-24 mm at the sides, 30+ mm above the tie; that is amount 0.5 (crown 0.75, sides 0.6, hold 1) |
| `part` | centre, left, right, none | none = combed straight back; a part is combed away from on both banks, in front only |
| `ears` | tucked, covered | the hair passes over the ears' tops, or hangs over them |
| `tail` | {kind: tail / bun / plait / none, length m, fullness 0..1, wave 0..1, tousle 0..1, to: back / shoulder} | what leaves the tie; a tail HANGS (gravity, the neck and shoulders hold it). `fullness` is its VOLUME: 0 = a sleek thin tail (1.8 cm radius), 1 = bushy (6 cm, more locks, airier, frizzier); it opens out of the band as a fan, full by ~9 cm. `wave`: 0 = straight, 1 = loose waves that run through the bundle (neighbouring locks nearly in step: sheets, not ropes). `tousle`: 0 = brushed (an even end, nothing leaves the outline), 1 = tousled, as SOFT irregular hair: some locks loosened out of the bundle, lock ends anywhere over the last half and open (no points, no flick), strands drawn fine at up to 2.7 x the count, single hairs and a few thin locks up to 18 cm leaving the outline with a curl; default 0.05 + 0.75 x wave. The hang, fullness and wave are the brushed tail's |
| `wisps` | 0..1, or {amount 0..1, where: [part, front, temple, sideburn, nape], length [m, m], softness 0..1, loose: n, curls: n} (`curls`: fine separate CURLED locks a side, 5-12 hairs each, that leave the hair at the forehead's corners, the temples and in front of the ears and hang close to the face, each with its own length and helix; default round(9 x amount). Under hair with `volume` the flat clumps are cut back: lying on the skin they show as a grey veil) | the short soft hair that never reached the tie: small clumps of fine hairs along the hairline that fall along the skin (the front's out toward the temples; the temples' are a short fringe in front of the ear, about half drawn back toward the tie). softness 0 = small defined locks, 1 = wide and frizzy. `loose`: THICK loose locks a side (18-45 hairs, 9-19 cm) out of the forehead's corner and the temple, swept back over the temple toward the ear and drooping; default round(2.5 x amount). Default amount from neatness (none on a neat head); independent of it when given: a sleek head WITH wisps is `neatness` 0.95 + `wisps` 0.7 |
| `front` | 0..1, or {looseness 0..1, drape 0..1, locks: n a side} | the FRONT on its own: the hair in front of the ears sags and stands off the head as if the style were that much looser there, while the back stays as tight as `tightness` (`looseness`); it may hang further over the forehead's corners and temples (`drape`); `locks` = thick loosened locks (30-70 hairs) that fall from beside the part across the forehead's corner and are drawn back over the temple (default round(3 x looseness); none toward a tie above 30 deg). Front wisps get thicker, longer and more with it, so they read against skin from the front. Default none: a neat held-back arc |
| `hairline` | 0..1 | how SOFT the hair's edge is. 0 = a clean hard line (gelled; a wig's edge); 1 = the hair thins out over the last centimetre before the line, fine baby hairs (1-4 cm) stand along it from the part to the sideburn, the part wanders a few mm. Default 0.8 - 0.3 x neatness: every real hairline is soft, so this is on for every style (a neat head has baby hairs too) |
| `escaped` | n a side, or {count, where: [part, temple, ear, nape], length [m, m]} | single stray HAIRS (each a thin line: use `wisps` for anything soft); default none |
| `neatness` | 0..1 | 0 = slept in (strays, halo, uneven lengths), 1 = every hair in place |
| `half` | true + `length` m | half up: only the top is tied, the rest hangs loose |
| `detail` | {"tie": {...}, "strands": {...}} | the escape hatch: hair_tied's own keys over what the style makes |

How it is built (hair_flow.py), so you can predict it: roots all over the scalp (not rows from the hairline), each
traced along the head toward the tie: toward the tie + away from the parting + down the head by looseness, never
across bare skin. Hair rooted further from the tie lies over hair rooted nearer. The tail is a bundle of locks that
each leave the tie in a cone and fall; the bundle's radius is then SET along it (the bulge out of the band, full to
near the end), every lock waves on its own phase and plane, turns on its way and ends at its own length, and its
strands end over its last third (thin tapering locks were strings, all strands to the end planks). A wisp is ONE
lock of 6-28 fine hairs (their own part-transparent strand object): its line starts in the hair at the hairline and
is traced along the SKIN (gravity in the surface's tangent plane + a slow curl; it may not lift off while the skin
is under it), its hairs fan a little and end one by one. Escaped pieces are a few single hairs from one root, each
falling on its own.

The hair's EDGE (`hairline`, gather.edge): between the hairline and where the inner roots begin (1.2 cm in) lies a BAND
of fine blue-noise roots. Their locks are narrow, and the nearer the line a lock roots the fewer strands it carries and
the finer they are drawn (part transparent in EEVEE, which never draws a strand under a pixel wide), with soft sides
(`rim`): a density ramp, not a row of full locks starting on a line (that row was the hard dark arc, and where the hair
runs ALONG the line, beside the part and at the temples, its lock starts and sides were stair steps and a V notch).
Inner locks rooted within ~3 cm of the hairline are narrower with soft sides and staggered starts. At the temples and
sideburns the band IS the hair (a strip 1-2.5 cm wide in front of the ear): it is full by 5 mm there and carries more
strands; left unrooted the temple reads as shaved skin. Only the sideburn's lowest fringe, which could
never reach a tie, grows no lock: baby hairs and wisps are that hair. With `hairline` 0 it is the old single row and
the sideburn grows no lock at all.

Judge it from every side (`views=["around"]`), not the front: tied hair is wrong from behind first. What to read:
on top the strands must run front-to-back (lateral bands = a cap); the tail must end hanging, not pointing; the
hairline at the temples should be soft (a hard saw edge reads as a wig). The hairline finds the EAR on the head
itself (hair.ear: the bump on the scalp's rays, every base) and passes `groom.hairline.ear` m (default 6 mm) over its
top, with the sideburn `sideburns` m (default 14 mm) below that top in front of the ear: no per-model patch for a
"shaved" temple any more (a negative `ear` from older grooms is raised to 3 mm over the ear; `"ear_from": "brow"` keeps an old groom's line
exactly). On an up-style
(high ponytail, top knot) the hair runs straight off the temple's line: its row of roots stands at uneven depths and
its strands start one by one over the band, so the edge is combed, not a row of teeth; it is still a visible combed
edge close up. Judge a tail against a picture by MEASURE and over seeds: `look_hair(name, views=["ref2"],
measure={"view": "ref2", "mask": hair_mask.png, "tie": [x, y]})` (below), with `groom_hair(name, groom={"seed": n},
replace=True)` for 3-4 seeds: one draw moves a tail's area about +-10 %. What is still weak: the head
hair reads smoother than loose real hair in EEVEE; a tousled tail is stringier than real brushed-out hair (strands
drawn a pixel wide with dark air between them) and its strays are few; single escaped hairs draw as thin lines (ask
for wisps); the strip in front of the ear is thinner than real hair there.

The older by-hand tie (`groom.tie` with gather rows, `curtain`, `frame`, below under groom_hair) stays for models
made with it; do not start new tied hair there: its curtain lays the front ACROSS the head.
