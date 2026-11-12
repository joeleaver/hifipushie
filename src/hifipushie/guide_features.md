# A sculpt from reference pictures: the feature map

A model can match its reference's outline and still be wrong everywhere inside it: a box for a head, no sockets,
no mouth. The outline is one feature. The feature map names all of them, as marks on the reference's own pictures,
so the sculpt is built from them and measured against each one. Make it BEFORE any shape is made.

## The three calls

1. `read_reference(name, image, views, height)`: cuts a sheet into its views (one name per figure, left to right)
   and gives each a camera. Flat views to scale: `"front"`, `"back"`, `"side"` (the figure faces the picture's
   left: you see its LEFT side) and `"side_r"` (it faces the picture's right: its right side). Any other name is
   a picture in perspective; read it too, in a call of its own (its camera comes later, from fit_concept_camera,
   once there is a model). `height` is feet to top, in metres, of the first flat view.
   It returns, per view: the picture | its PATCHES, numbered | its FORM LINES, with pixel rulers. Check each
   cut-out is the whole figure: a part the colour of the background can be lost (pass `mask=`).
   `read_reference(name, view=..., focus=[x0, y0, x1, y1])` looks closer; `detail="fine"` cuts smaller patches.
   Read EVERY picture before marking, and mark each feature in every picture that shows it.
2. `mark_features(name, features)`: you name what you see. It returns the map drawn on the picture, each
   feature's place and size, and what the map STILL OWES.
3. `feature_report(name, elements)`: once there is a model, says for every feature whether it is made, and how
   far it is from its mark. `elements` says which of the model's elements make each feature.

## What a feature is

Anything you would point at when describing the subject to someone who can't see it. Give each one a `kind`:

- `"mass"`: a solid of its own. It has thickness you could measure from another side.
- `"form"`: a shape on a mass's surface: a rim, a ridge, a hollow, a fold, a tuft, a crease, an edge where one
  surface steps over another.
- `"paint"`: colour only. If the surface would be smooth there with the colour gone, it is paint.

A form line in the picture is the edge of a form OR the edge of paint. The code can't tell; you can. Look at how
the light falls on each side of the line: a step in shape has a lit side and a shaded side, a change of colour
doesn't. When you can't tell, mark it as a form and say so in `inferred`.

Work big to small: the masses first (every one, down to the small ones), then the forms on each, then the paint.
A subject's character usually lives in its forms, so be thorough there. Small is not the same as unimportant.

## The structure, in words

For each feature say what the pictures show and a measurement can't know:

- `on`: the feature it sits on or grows from.
- `join`: how it meets that feature: along its whole base, by a narrow end, hanging free beside it, sunk into it.
  Look at where the two outlines meet, in every view that shows it.
- `separate`: true for a thing that is its own rigid object (it could be lifted off, or it moves on its own).
- `authority`: the view to believe when two views disagree about it. Drawn and generated views often do.
- `inferred`: what no view shows (its far side, its inside, what is behind another feature) and your guess.
- `says`: anything else worth keeping: what it is made of, how soft its edge is, what it does.

## Marking

Marks are in each view's own pixels: read them off the rulers. Every mark is clipped to the figure.

- `{"patches": [12, 13]}`: the numbered patches. The quick way when the patches follow the feature.
- `{"box": [x0, y0, x1, y1]}`, `{"ellipse": [cx, cy, rx, ry]}`, `{"polygon": [[x, y], ...]}`: when they don't
  (a mass that takes in many patches: draw round it).
- `{"line": [[x, y], ...], "width": 3}`: a crease or a groove: something with no width of its own. It is
  measured by whether the model has form along it. A form that has height (a band, a rim, a cuff) is marked by its
  whole extent, never by a line along one edge.
- Keys add up; `"minus": {...}` takes away. A mark may overrun the figure's outline: only what is on the figure
  counts, so draw a mass's outer edge generously.
- `"mirror": true` on a front or back view also marks the `.L` / `.R` twin IN THAT VIEW, by reflection. Use it
  only where the picture really is the same on both sides; other views still need their own marks.
- A call replaces a feature's mark only in the views it names. `"side": null` clears that view's mark.

Names ending `.L` are the creature's left. In a front view its left is at the picture's RIGHT.
Mark every feature in every view that shows it: one view gives no depth.
Draw round a mass as you see it. What sits `on` it and is a mass of its own (an eye on a head) is taken out of its
mark for you when the model is measured, so each mass is compared by what shows of the thing itself.

Example (a made-up subject):

    mark_features("jug", {
      "body":   {"kind": "mass", "marks": {"front": {"polygon": [[40, 60], [200, 60], [215, 380], [25, 380]]},
                                           "side": {"box": [30, 60, 190, 380]}}},
      "handle": {"kind": "mass", "on": "body", "join": "by both ends, a gap between",
                 "marks": {"front": {"patches": [14, 15]}}, "inferred": "its thickness: no side view shows it"},
      "rim":    {"kind": "form", "on": "body", "marks": {"front": {"patches": [3]}, "side": {"patches": [2]}}},
      "stripe": {"kind": "paint", "on": "body", "marks": {"front": {"patches": [22, 23, 27]}}}})

## What the map owes

`mark_features` lists it every time. Clear every line, or answer it in the feature's own fields:

- UNMARKED: more than 2 % of a view's figure belongs to no feature. The pieces are hatched pink in the picture and
  their boxes are listed. Mark them, or widen the mass they are part of.
- DISAGREE: two flat views put a feature at different heights. Check your marks; if the pictures themselves
  disagree, set `authority`.
- SIDE: a `.L` marked on the creature's right, or the other way round.
- DEPTH: a mass seen in one view only. Mark it in a second view, or state your guess in `inferred`.
- ON: a form or paint with no mass named under it.

## Reading the report

`elements` names the model's own elements as `get_model` lists them: blobs, bones, strokes, kits (their generated
pieces come with them), `.R` for a `.L`'s mirrored twin, patterns like `"tuft*"`, or `"part:<part>"`. Every name
is checked before anything is measured. Give a feature no elements when nothing makes it. A form with no element
of its own because the mass's own shape makes it (a bulge that is part of the mass's outline) gets `["="]`: it is
then not measured, only judged by eye on its tile. Use `["="]` when you can SEE the form in the model, never to
pass one that isn't there.

`feature_report` rows, for masses and forms (paint is colour: a later stage): NOT MADE (no element makes it),
HIDDEN (made, but nothing of it shows from that view), OFF (with how far, how big, how much of the mark it
covers), right, IN ITS MASS (`["="]`). A form's elements count as part of the mass it is on. Fix NOT MADE first, biggest feature first; an
OFF feature is fixed at the element that makes it. The numbers place and size a feature; whether its SHAPE reads
right is judged by eye, on same-view tiles beside the picture (`feature_tiles(name, ..., label=<view>)` works
from every view read here) and by the blind review. A table with nothing wrong is where that look starts.
