# Reading garments from reference art

How professionals read a garment off a picture, and how hifipushie turns that reading into a design sheet and later
judges a simulated garment against it. Tools: `garment_from_reference` (read: the form, the camera, the sheet, the
target table), `check_garment_reference` (check: ranked misses and focus panels), `garment_reference` (the knowledge
base the choices come from). The checklist itself is data: `cloth_checklist.json`.

The face has an equivalent list (the likeness checklist, FISWG-based). The clothing list is harder for four reasons:
it depends on the garment KIND; it covers construction AND drape AND wear state AND material; many items are CHOICES
(a notched or a peaked lapel, one button done up or two) rather than numbers; and garments are layered, so one
garment's item is read through another's (a shirt cuff "shows" only relative to a jacket sleeve).

## How the professions read a garment

**Technical designers (tech packs, specs).** A garment is a flat sketch plus a points-of-measure (POM) table: each
POM has a code, a written "how to measure" and a tolerance (+-). The reference points are fixed: HPS (high point
shoulder, where shoulder seam meets neckline), CB neck, shoulder point, 1 inch (25 mm) below armhole, waist, hem.
Typical tops: body length HPS to hem (front and back), across chest 1" below armhole, across shoulder, waist,
bottom sweep, sleeve length (CB neck or shoulder point to hem), bicep, cuff/sleeve opening, neck width, collar
point length, collar stand height, placket length/width, button count and spacing. Jackets add lapel width, gorge
height (where collar meets lapel), notch, button stance (top button's height), break point (where the lapel begins
to roll), vent length. Bottoms: waist, front rise, back rise, seat/hip, thigh 1" below crotch, knee (a set distance
below crotch), leg opening, inseam, outseam. Tolerances are small (+-3 to +-13 mm by POM) because the spec drives
production; a reference picture can't support that: our tolerances are what a picture can support (see below).
Sources: tech-pack POM guides (e.g. TUL Liberec's garment-measurement course; dc-onesource spec sheets, which define
HPS, body length "HPS to finished hem at back", chest "1 inch below armhole", sleeve "CB neck to shoulder point to
hem").

**Tailors (tailored jackets, trousers).** They read PROPORTION and FIT TELLS rather than every number: the jacket's
length covers the seat; the shoulder line ends at the shoulder bone (pads or soft); the waist suppression; lapel
width in proportion to the chest (about 3.25-4 in / 85-100 mm on a classic lapel) and the gorge's height; the button
stance (the waist button near the natural waist / the index fingertip with the arm hanging); the sleeve shows about
1/2 in (10-15 mm) of shirt cuff; the shirt collar shows above the jacket collar at the back of the neck; the lapel
lies on the chest (no gap); no tent at the hem, the fronts hang straight or close; trousers: the break (none, half,
full: the hem's rest on the shoe), the leg opening against the shoe, the crease runs straight to the hem, the rise
sits at the waist, a belt or side adjusters. Sources: Parisian Gentleman, "Mysteries of the tailored jacket";
Westwood Hart lapel proportions; Articles of Style fit guides; The London Lounge (button stance and gorge line);
Proper Cloth "What is a pant break".

**Costume designers.** A costume breakdown (per character, per scene) lists each garment by layer from the skin out,
its silhouette, the period/kind, the fabric (fibre, weight, weave, surface: matte, sheen, nap), colour and pattern
scale, the WEAR STATE (open/closed, sleeves rolled, collar up, tucked, belted, worn in or new, ageing and
breakdown), fit (how it sits on THIS body) and the details that carry character. Silhouette first, because that is
what reads from across a stage; detail last.

**3D garment artists (Marvelous Designer, CLO).** The production order is: silhouette and proportions on the avatar
(lengths and widths blocked from the reference), fit / ease, construction (pieces, seams, internal lines, fold
lines, buttons and buttonholes), layers and arrangement, fabric properties (weight, stretch, bend: drape decides fold
size and spacing), then the fold character (where the big folds sit, compression at the elbow and knee, gravity
folds, tension folds from a button), then detail (topstitching, trims) in normal maps. A garment that matches every
detail but has the wrong silhouette or length still reads wrong. (Marvelous Designer field guide 2024, as cited in
garment_kb.json; ArtStation / The Rookies digital costume breakdowns.)

What every one of these has in common, and what our checklist copies:
1. **Big to small.** Silhouette and lengths, then fit, then construction details, then wear state, then fabric and
   folds. An earlier item is held while a later one is fitted (the face list's rule too).
2. **Fixed reference points.** Every number is measured from body landmarks (HPS, shoulder point, waist, crotch,
   knee, wrist, floor), so it survives a different body. We express a picture's measure ANCHORED: a fraction along a
   pair of body landmarks (the jacket hem at t = 0.31 from crotch to knee), carried onto our body.
3. **Choices are named.** A notched lapel, a two-button single-breasted front with the top button done up, a box
   placket: these come from a closed vocabulary (garment_kb.json `details`), not free text.
4. **Every item says which view shows it.** Lengths and widths from the front; the tent, the jacket's balance and
   the trouser break from the side; the collar show at the back; buttons and plackets close up.

## The checklist (cloth_checklist.json)

Each item:
- `id`, `stage` (1 silhouette and lengths, 2 fit, 3 construction, 4 wear state and layering, 5 fabric and folds),
  `kinds` (the garment kinds it applies to; `*` = every garment), `what` (a sentence that says what to look for),
- `view` (which picture shows it) and `region` (the body landmarks the focus crop is drawn round),
- `type`: `length` / `width` (a number read from 2 points), `choice` (from a garment_kb `detail`), `count`, `bool`,
  `colour`, `level` (a word on a scale: e.g. drape soft..crisp);
- `anchor` for numbers ([landmark a, landmark b]: the reading is the fraction along a -> b) or `per` (a width as a
  share of a body width);
- `measure`: what our side reads on a simulated garment (cloth_reference.MEASURES), or `"missing: ..."` (then the
  check says it can't judge it, and the report lists it as a tool to build);
- `tolerance`: in the item's units (mm for anchored lengths after carrying onto our body; a share for widths; exact
  for choices and counts);
- `sets`: the design-sheet key or pattern op that changes it (what to edit when the check fails).

Tolerances are what a picture supports: a painted concept is not a spec. 15-25 mm on lengths, 8-12% on widths, exact
on choices and counts. Anything finer (a 3 mm lapel difference) is not visible at full-figure scale; read it from a
close crop or leave it at the KB's default.

## Reading a reference (garment_from_reference)

1. Give the images (a full-figure front is the backbone; a side or 3/4 adds depth items: tent, break, balance) and
   the body landmarks you can see in each (`points`: head_top, chin, shoulder.L/R, elbow, wrist, hip, crotch, knee,
   ankle, floor: pixels, u right v down). An orthographic camera is fitted to the model's own joints (scale, roll,
   shift; least squares): a concept sheet in A-pose is near orthographic. For a painting in perspective at 3/4, give
   a `yaw` hint and use it only for choices, not numbers (the check says so).
2. Ask for the FORM (`answers` left out): one row per item for the garments' kinds, with the crop for each item (the
   region round the landmarks drawn on the reference) and the points to mark for numbers.
3. Fill the form item by item, big to small: a value, a confidence (high, medium, low) and `"not visible"` where the
   picture doesn't show it (a back vent in a front view). Don't guess what isn't visible: an unseen item keeps the
   KB default and is not judged.
4. The tool returns the design-sheet patch (choices -> `details`, lengths -> block options / ops where a rule maps
   them, wear state -> `closures` / `tie`, fabric -> `fabric`, colour -> `color`) and the target table (anchored
   numbers with tolerances, stored in `<model>/cloth_refs.json`). It does not apply the patch: review it, then
   `design_garment`.

## Checking a simulation (check_garment_reference)

Reads the cached sims only (never starts one). For each item: our value, the reference's, the miss in tolerances.
Ranked misses: stage first (a wrong length matters more than a wrong placket), then the miss's size. Focus panels:
the reference crop | our garment drawn through the SAME fitted camera, the item's region outlined. Items whose
`measure` is missing are listed apart ("can't judge: no measure"), and so are items the reference marked not
visible.

Read the panels before believing a number: a measure can be wrong (a hem read on a flared front corner, a cuff show
read on a sleeve that rode up on one arm). The report says which misses are the MEASURE's fault when it can tell
(the item's reference confidence is low, or the two arms disagree by more than the tolerance).

## What usually goes wrong (from Garrett's suit, 2026-10)

Every hand correction made on the suit is an item, so a check would have found it:
- buttons: two done up instead of one (`jacket.buttons_done`), the jacket worn open vs closed (`jacket.front_state`);
- no visible shirt placket (`shirt.placket`, choice + `relief` visibility);
- jacket collar and shirt collar placed wrong (`jacket.collar_show`, `jacket.collar_hug`, `shirt.collar_state`);
- no belt (`trousers.belt`);
- trousers too wide (`trousers.knee_width`, `trousers.leg_opening`);
- short sleeves (`jacket.sleeve_end`, `jacket.cuff_show`);
- a tented jacket hem (`jacket.front_hang`).

## Getting good references (garment_reference_brief)

The best reading comes from pictures made for it. `garment_reference_brief(garments, subject, outfit, name)` writes
the shot list from the checklist (`cloth_reference.reference_brief`; the same format as the face's likeness brief:
`{"subject", "common": {"prompt", "negative"}, "shots": [{"id", "view": {"yaw", "pitch", "framing"}, "light",
"purpose": [item ids], "must_show", "prompt"}]}`):
- a turnaround: front, side (the tent, the trouser break), back (collar show, vent, back hem), 3/4 (lapels lying on
  the chest), all full length, the figure in an A-pose with the arms about 20 degrees out (sleeves and the jacket's
  sides clear), palms forward, feet hip-width, a long lens (~100 mm) from chest height (near orthographic: numbers
  can be read), a plain light grey backdrop, even light;
- the wear state said plainly in every prompt (which buttons are done up, tucked or not, belt, collar open, no tie),
  taken from the model's reading when there is one (never from the model's current, possibly wrong, state);
- detail close-ups: collar and lapel, front closure and placket (with the belt and fly), cuff (the shirt cuff past
  the sleeve), pockets, hem and break, back vent;
- one raking-light pass (a low hard side light) for the cloth's weave, weight and folds;
- the SAME person in the SAME clothes in every image (said in the common prompt; the negative prompt bans hands in
  pockets, wind, dramatic light, cropping, wide angles, outfit changes).

`garment_reference_brief(..., views=[...])` (`cloth_reference.check_references`) validates a set you already have:
per checklist item, which picture supports it, or why none does (wrong direction, a perspective or seated painting
can't give numbers, a close item too small in a full-length shot, folds without raking light, colour under warm or
dramatic light) and which brief shot would supply it. Garrett's two concepts (an A-pose front + a seated 3/4 oil
painting) support 57 of 73 items; the back, side and raking shots are what's missing (back length, vent, collar show,
the tent, collar hug, the trouser break, drape and folds).

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `cloth` toolset: enable_toolset("cloth") turns it on.

### `garment_from_reference`

`garment_from_reference(name, garments, views, answers=None, save=True)`

Read reference art of an outfit into design sheets and a target table, item by item, with the garment
checklist (guide(topic="cloth_reference"); cloth_checklist.json): silhouette and lengths first, then fit,
construction details, wear state and layering, fabric and folds. garments: {garment name: kind} (garment_kb kinds:
jacket, shirt, suit_trousers...). views: [{"image": path, "kind": "front" | "side" | "back" | "three" | "other",
"points": {body landmark: [u, v]}, "crops": {item id: [u0, v0, u1, v1]}}] (u right, v down; landmarks head_top,
chin, neck_base, shoulder.L/R, elbow.L/R, wrist.L/R, knee.L/R, ankle.L/R, floor; 3+ on a near-orthographic front
view fit its camera to the model's body). Without `answers`: the FORM to fill (one row per item, what to look for,
the view, the choices or the points to mark). With answers ({garment: {item id: {"value" | "points": {name:
[u, v]}, "view": i, "confidence": "high" | "medium" | "low", "note"} | "not visible"}}): the design-sheet patch per
garment (choices -> details, wear -> closures / tie / over, fabric, colour) and the target table (lengths anchored
on body landmarks, widths in metres), stored in <model>/cloth_refs.json. The patch is NOT applied: review it, then
design_garment / edit the garment. check_garment_reference judges a sim against it.

### `check_garment_reference`

`check_garment_reference(name, garments=None, save=None, top=9)`

Judge the model's simulated garments against its reference reading (<model>/cloth_refs.json, written by
garment_from_reference): every checklist item measured on the CACHED sims (never simulates), the misses ranked
(misses in tolerances x stage weight x confidence: a wrong length outranks a wrong placket), items the picture
didn't show judged against the tailoring rule where there is one (collar show, cuff show, tent), what can't be
judged and why; and a focus sheet: per ranked miss the reference crop | our garments drawn through the SAME fitted
camera, the reading's points in red, ours in blue. Read the panels before believing a number.

### `garment_reference_brief`

`garment_reference_brief(garments, subject='a man', outfit='', name=None, views=None)`

A shot list for getting the best reference images of a garment or outfit (from an image generator or a
shoot), derived from the garment checklist: a turnaround (front, side, back, 3/4) in an A-pose with the arms a
little away from the body, the wear state said plainly (which buttons are done up, tucked, belt, collar), detail
close-ups (collar and lapel, closure and placket, cuff, pockets, hem and break, back vent), even light plus a
raking pass for fabric and folds, a plain background, the same figure and garments in every image; each shot's
full prompt. garments: {name: kind}. name: a model whose reading (cloth_refs.json) or, without one, whose garments
give the wear state. views: a set of pictures to VALIDATE instead ([{"yaw", "framing": "full" | "bust" |
"close:<region>", "light": "even" | "raking" | "warm" | "dramatic", "perspective": "ortho-ish" | "perspective",
"posed": "a-pose" | "other", "size": [w, h]}]): which checklist items they can and can't support, and why.
