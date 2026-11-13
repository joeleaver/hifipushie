# A sculpt from reference pictures: the feature map

A model can match its reference's outline and still be wrong everywhere inside it: a box for a head, no sockets,
no mouth. The outline is one feature. The feature map names all of them, as marks on the reference's own pictures,
so the sculpt is built from them and measured against each one. Make it BEFORE any shape is made.

## The calls

1. `read_reference(name, image, views, height)`: cuts a sheet into its views (one name per figure, left to right)
   and gives each a camera. Flat views to scale: `"front"`, `"back"`, `"side"` (the figure faces the picture's
   left: you see its LEFT side) and `"side_r"` (it faces the picture's right: its right side). Any other name is
   a picture in perspective; read it too, in a call of its own (its camera comes later, from fit_concept_camera,
   once there is a model). `height` is feet to top, in metres, of the first flat view.
   It returns, per view: the picture with its outline's NOTCHES labelled | its PATCHES, numbered | its FORM
   LINES, with pixel rulers. Check each
   cut-out is the whole figure: a part the colour of the background can be lost (pass `mask=`). Patches are
   bounded by form lines as well as by colour, so a plain-coloured subject has them too; if they are too many or
   too few to point at, read the view again at another `detail`.
   `read_reference(name, view=..., focus=[x0, y0, x1, y1])` looks closer; `detail="fine"` cuts smaller patches.
   Read EVERY picture before marking, and mark each feature in every picture that shows it.
2. `mark_features(name, features)`: you name what you see. It returns the map drawn on the picture, each
   feature's place and size, and what the map STILL OWES. `mark_features(name, view="front")` draws one view
   large, with rulers: check every mark there before building.
3. `build_masses(name, how)`: turns the map's masses into shapes, their numbers read off your marks. You say
   what each mass IS; you type no coordinate. It makes the model if there is none.
4. `build_forms(name, how)`: lays the map's forms on the built masses, their paths read off your marks. You say
   what each form IS and how far it stands out or sinks.
5. `feature_report(name, elements)`: says for every feature whether it is made, and how far it is from its mark.
   `elements` says which of the model's elements make a feature (build_masses writes that itself).

## What a feature is

Anything you would point at when describing the subject to someone who can't see it. Give each one a `kind`:

- `"mass"`: a solid of its own. It has thickness you could measure from another side.
- `"form"`: a shape on a mass's surface: a rim, a ridge, a hollow, a fold, a tuft, a crease, an edge where one
  surface steps over another.
- `"paint"`: colour only. If the surface would be smooth there with the colour gone, it is paint.

A form line in the picture is the edge of a form OR the edge of paint. The code can't tell; you can. Look at how
the light falls on each side of the line: a step in shape has a lit side and a shaded side, a change of colour
doesn't. When you can't tell, mark it as a form and say so in `inferred`.

A mass is ONE simple solid: something a ball, a drum, a flat flap, an upright trunk or a tube can make. A big
part of a subject is nearly always several of them melted together, and it is built as a box if you mark it as
one. A head is a skull and a muzzle or a jaw, and cheeks or a brow if they bulge; a body is a chest and a belly
or hips. Look at the part from the front AND the side: where it is narrower at one end in one of them (a snout
narrower than the skull behind it), where its outline steps or has a waist, it is two masses. Whatever hangs
free or stands out past the outline with a thickness of its own (locks of a beard or a fringe, a tuft on a
crown, teeth) is a mass too, or a row of masses: mark each lock, as one feature in several pieces.
Masses overlap freely: mark each one's whole extent, also where it lies in front of or inside its neighbour.

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

- `{"piece": "p12", "cuts": [["n3", "n7"], ...]}`: THE mark for a mass. Name a patch that lies on the thing (or
  a pixel `[x, y]`), and cut the figure wherever the thing meets a neighbour: the mark is the part of the figure
  joined to that patch once the cuts are made. A cut runs between two NOTCHES: the picture labels every place
  the outline pinches in (`n1`, `n2` ...: armpits, a crotch, the corners of a neck, the tips of gaps), and those
  are where parts divide. An arm is a patch on it and one cut from the armpit's notch. Where the other
  end has no notch (a smooth shoulder), say which way the cut goes instead: `["n17", "up"]` (or `"down"`,
  `"left"`, `"right"`) runs straight that way until it leaves the figure, and `["n17", "across"]` takes the
  shortest way through, which is how a limb is cut off at its root. A pixel `[x, y]` off the rulers works too.
  The mark's edge is then the picture's own outline to the pixel, which is what a shape is built from.
  Each cut parts off ONE neighbour, and a cut stops where it first leaves the figure: a mass with three
  neighbours takes three cuts. Where two notches don't seal a part off (it touches a third thing between them),
  add a cut from one notch `"up"` / `"down"`: it is safe however far it runs. Wrists and ankles have no notch:
  cut between two pixels just outside the figure on either side. `read_reference` lists every notch's pixels. A cut that parts nothing is refused by number: it missed the outline or stopped
  short of it. Look at the mark drawn large before you build from it.
- `{"patches": [12, 13]}`: the numbered patches. The quick way for a form or paint the patches follow.
- `{"box": [x0, y0, x1, y1]}`, `{"ellipse": [cx, cy, rx, ry]}`, `{"polygon": [[x, y], ...]}`: for what lies
  inside the outline and no cut can part off (a mass seen against another mass). A hand-drawn edge wobbles, and
  the shape built from it wobbles too: where an edge IS the figure's outline, overrun it and let the outline cut.
- `{"line": [[x, y], ...], "width": 3}`: a crease or a groove: something with no width of its own. It is
  measured by whether the model has form along it. A form that has height (a band, a rim, a cuff) is marked by its
  whole extent, never by a line along one edge.
  On a MASS a line says "it runs here, and this view doesn't show how thick it is": an arm hanging against the
  body, seen from the side, has no outline of its own there. Draw a line down its middle; its thickness comes
  from the view that shows its outline. A guessed polygon there is built as if it were the outline.
- Keys add up; `"minus": {...}` takes away. A box, ellipse, polygon or line key also takes a LIST of them, for one
  feature in several pieces (a scatter of bumps, a row of teeth): `{"ellipse": [[30, 40, 4, 4], [52, 44, 3, 3]]}`.
  Things made together and alike are one feature, not one each.
- A mark may overrun the figure's outline: only what is on the figure counts, so draw a mass's outer edge
  generously.
- `"mirror": true` on a front or back view also marks the `.L` / `.R` twin IN THAT VIEW, reflected about the
  view's centre line (the pixel column `read_reference` prints). Use it only where the picture really is the
  same on both sides; other views still need their own marks. In a BACK view the creature's left is at the
  picture's LEFT.
- Every call adds to the map. Naming a feature again changes only the fields and the views' marks that call
  gives; `"side": null` clears that view's mark; `remove=[...]` drops whole features.

Names ending `.L` are the creature's left. In a front view its left is at the picture's RIGHT.
Mark every feature in every view that shows it: one view gives no depth.
Draw round a mass as you see it. What sits `on` it and is a mass of its own (an eye on a head) is taken out of its
mark for you when the model is measured, so each mass is compared by what shows of the thing itself. Draw
a mass's WHOLE extent, also where it runs under another mass you have marked (a thigh inside shorts, a neck
behind a beard): it is built from its whole mark, and what the model hides there is not held against it.
Split masses where the subject is jointed, not where the outline happens to turn: a limb's segments, a hand apart
from its forearm.
A limb, horn or tail needs nothing added to sink its root into its neighbour: built as a tube it runs on under
the mass it was cut from by itself, and a box added there is built as part of its outline. Cut a mass at the
same height in every view: where its views end at different heights its shape is stretched between them.

Example (a made-up subject):

    mark_features("jug", {
      "body":   {"kind": "mass", "marks": {"front": {"polygon": [[40, 60], [200, 60], [215, 380], [25, 380]]},
                                           "side": {"box": [30, 60, 190, 380]}}},
      "handle": {"kind": "mass", "on": "body", "join": "by both ends, a gap between",
                 "marks": {"front": {"patches": [14, 15]}}, "inferred": "its thickness: no side view shows it"},
      "rim":    {"kind": "form", "on": "body", "marks": {"front": {"patches": [3]}, "side": {"patches": [2]}}},
      "stripe": {"kind": "paint", "on": "body", "marks": {"front": {"patches": [22, 23, 27]}}}})

## Building the masses

Build once the map owes nothing. For every mass say what it is, `"as"`:

- `"ball"`: one rounded lump. Its middle and its three half sizes come from the boxes of its marks. It fills its
  box, so it suits what is nearly round; a mass that is wider at one end (a pear, a wedge) is a trunk.
  A mark in several separate pieces (a row of hanging locks, a pair of knobs) is built as one lump per piece.
  `"socket": true` for a thing the picture shows SUNK below the surface round it: the mass it is `on` is
  hollowed round it. A number instead of true is the clearance round it, metres. Build the mass it sits in
  first. A thing that BULGES from the surface (a round eye in a rim) needs no socket: it stands proud. If it
  comes back HIDDEN, the mass under it is too full there, and that mass is what to fix (it is probably two).
- `"drum"`: a made, straight-sided thing: a cylinder along its long axis (`"along"` if it picks the wrong one),
  its rims rounded by `"edge"` metres.
- `"flap"`: a thin thing seen broad from one side (an ear, a fin, a leaf, a flat tail): one thick sheet along the
  long axis of its broadest mark, its width read across, its thickness from its other view (or `"thick"`,
  metres). It lies in the plane of the view that shows it broadest: a flap marked broad from the back is thin
  from the side. A flap that sticks out sideways leans the way its other view shows it. `"cup"`: metres its
  edges lift, for a hollow side. A ball or a tube would make it a fat lump.
- `"trunk"`: one upright mass through cross-sections: at each height its width from the front and back marks
  together, its depth and its lean from the side mark. For a mass that stands up and sits on the centre line. Its
  two ends are domes. It follows its mark: where the mark's edge is a straight cut, so is the trunk's side.
- `"tube"`: a limb, a horn, a tail: something long, whichever way it runs and however it bends. It follows its
  mark's own MIDDLE LINE, and its thickness is read ACROSS that line, so a slanted limb is as thick as it is
  drawn. Built as a chain of bones through `"joints"` stations (4 by default, so 3 bones; more for a curve). Its
  second view gives where it is at each height, also when it is foreshortened there (a horn seen from the front
  shows its splay): mark it there by its own outline. The end that was
  cut from another mass runs on under that mass; a free end stops where its mark stops. The answer says how long
  and how thick it read each tube, and which ends it took as cut: check those against the picture.

`"round"`: 2 is round in section (an ellipse), 4 is a soft box; 2.0 to 2.6 look much alike, so move it in whole
steps (a ball's or trunk's own judgement call: look at the outline's corners). It changes the section only: a
mass's outline from the front and side stays what its marks are.
`"sections"`: how many heights a trunk is read at (7; more for a wavy outline).
`"part"`: any name: the mass becomes its own piece (its own mesh and colour later) and never melts into the
rest; give it to a thing that is separate. `"blend"`: metres, how softly a mass melts into what it touches: 0.003
for a thing that sits ON another with a crisp line round it, 0.02 (what you get if you say nothing) for an
ordinary join, 0.04 for one that grows OUT of the other with no line at all. The `join` you wrote says which.

Where the flat views disagree about a mass's height (drawn views often do), set its `authority`: the other
views' marks are fitted to that one before it is built, and the report measures those views against the fitted
mark. A trunk reads its outline smoothed over a tenth of its height; a real step in the outline wants its own mass.

Both views are needed for a shape: what a missing view would give is listed as ASSUMED, and for a ball with no
side mark you must give `"y"` (where it sits front to back). `.L` is built and mirrored to `.R`: the `.R`'s
own marks are then only measured against, so where the picture is not the same on both sides the `.R` reads OFF.
That is the picture's doing; say so and move on.

    build_masses("jug", {"body": {"as": "trunk", "round": 2.2}, "handle": {"as": "tube", "joints": 5, "y": 0.0},
                         "knob": {"as": "ball"}})

A small mass that sits ON a bigger one must stand proud of it to be seen. If it comes back HIDDEN, the mass
under it is too full there: make a mass that is narrower in front than behind out of two, or pull its corners
in (`"round"` nearer 2). A `"socket"` is for a thing that really is sunk; cut round a thing that should bulge,
it leaves a small ball in a wide hole.

It answers with the feature report for the masses and a picture. A mass that is OFF is fixed in its MARK (redraw
it, in the view that is wrong) or in what you said it is, then built again: building a feature again replaces
what was built before. Don't move on to forms until every mass is right from every view.

## Laying the forms

Once every mass is right, lay the forms: this is where the subject starts to look like itself. For every form
say what it is, `"as"`:

- `"raise"`: it stands out of the mass: a brow, a pad, a bulge, a lock, a cuff. Clay is laid along the mark's own
  middle line, as wide at each place as the mark is there; a round mark is one dab. A `line` mark is a ridge
  along the line (`"width"`: metres, half across).
- `"sink"`: it is pressed in: a hollow, a nostril; a `line` mark is a groove or a crease.
- `"rim"`: a raised ring. Mark the ring itself (an ellipse `minus` a smaller one) and it runs along the ring's
  middle; on a filled mark it runs just inside the edge (`"width"`: half its breadth).
- `"band"`: a ring ALL THE WAY ROUND a limb, a horn or a tail (a mass you built as a tube): a cuff, a growth
  ring, a collar. Mark it in one view as a strip across the limb: it is laid round the limb there, as broad
  along the limb as the strip. Several strips are several bands. A negative `"depth"` presses it in.

`"depth"`: metres, how far out or in. ONE VIEW CAN'T SHOW IT: left out, it is guessed from the form's breadth and
listed as ASSUMED. Look at the form from the side, in the picture and in the clay, and set it. A thick, puffy
form wants more than the guess; a shallow one less. `"profile"`: `"soft"` melts in, `"round"` is a dome with an
edge, `"flat"` a plateau, `"sharp"` a cusp (a crease). `"view"`: the flat view it is laid from: the one that
looks most squarely at it (by default the one where its mark is largest). A form on a mass's side is laid from
the side view; laid from the front it would smear along the mass's edge. A thing that goes ROUND a mass that
is not a tube (ribs round a drum) shows a face to every view: mark it in each and give `"view": "all"` (or a
list), and it is laid from each. A form at a mass's very edge, seen edge-on from every view (a fringe hanging under a jaw),
can't be laid well: clay pushed out there points along the edge. Locks that hang free are masses.

    build_forms("jug", {"rim": {"as": "raise", "depth": 0.004}, "spout_groove": {"as": "sink", "width": 0.003},
                        "badge": {"as": "rim", "depth": 0.002, "view": "front"}})

A mark in separate pieces (a row of rings, a pair of bumps) is laid as one stroke per piece; pieces that
overlap are one piece. A form `on` another form lies on that form's mass. A stroke whose path crosses a gap in
the mass (a socket, a notch) or runs off it can't be laid: it is LEFT OUT and said, and the rest of the call
goes on: redraw that mark clear of the gap. A `.L` form is laid and mirrored: name the `.L` only. A form is laid
on the mass it is `on`, and lands on that mass's own part: an eyeball or a held thing of another `part` in front of
it is not in the way. Where a mark overruns the mass (the picture is fuller there than the model), those places
are left out and said: fix the mass if it matters. A thing that sticks out past the outline and has a thickness
of its own (a tuft standing on a crown, a tooth) is a MASS, not a form: mark and build it as one.

It answers with the forms' rows of the report and a picture. Then LOOK: a close clay look of each region beside
the picture (`look` with `"focus": [x, y, z]` and `"zoom"`), from the front, the side and three-quarter. A form
that measures right and reads wrong is wrong: change its depth, breadth or profile, or its mark, and lay it again.

## What the map owes

`mark_features` lists it every time. Clear every line, or answer it in the feature's own fields:

- UNMARKED: more than 2 % of a view's figure belongs to no feature. The pieces are hatched pink in the picture and
  their boxes are listed. Mark them, or widen the mass they are part of.
- DISAGREE: two flat views put a feature at different heights. Check your marks; if the pictures themselves
  disagree, set `authority`.
- SIDE: a `.L` marked on the creature's right, or the other way round.
- DEPTH: a mass marked in one picture only. Mark it in any second picture that shows it (a perspective one
  counts), or state your guess in `inferred`.
- ON: a form or paint with no mass named under it.

## Reading the report

`elements` names the model's own elements as `get_model` lists them: blobs, bones, strokes, kits (their generated
pieces come with them), `.R` for a `.L`'s mirrored twin, patterns like `"tuft*"`, or `"part:<part>"`. Every name
is checked before anything is measured. Give a feature no elements when nothing makes it. A form with no element
of its own because the mass's own shape makes it (a bulge that is part of the mass's outline) gets `["="]`: it is
then not measured, only judged by eye on its tile. Use `["="]` when you can SEE the form in the model, never to
pass one that isn't there.

`feature_report` first gives the whole outline's overlap with each picture: one row among many. Then, for masses
and forms (paint is colour: a later stage): NOT MADE (no element makes it), HIDDEN (made, but nothing or little
of it shows from that view past the masses in front: judge it in its other views), OFF (with how far, how big, how
much of the mark it covers), right, IN ITS MASS (`["="]`),
CAN'T MEASURE (with the reason). A form's elements count as part of the mass it is on. A feature is measured by
what shows of the thing itself: clothing over a limb is the clothing's, not the limb's.

A row's words compare the MODEL'S footprint with YOUR MARK: "the model's is 12 mm to the picture's left and 5 mm
below the mark" means move the mark that way if the model is right, or the model the other way if the mark is.
The report's picture is drawn in the view's own pixels, with rulers: a mark can be read straight off it. Tiny
things (a few pixels) are judged by place only. A perspective picture is measured once it has a camera: when the
model exists, `fit_concept_camera(name, <that view's saved picture>, label=<the view's name>)`.

A picture can't say how tall a model was built, where its ground is, or where its origin lies along its length.
So the report first lays each flat view on the model (one scale for the sheet, each view's ground row, a side
view's centre line) and says what moved in a MOVED line: "the model is 1.04 x the height the sheet was read at"
is a finding about the model. Features are then placed relative to the whole figure, as an eye compares them. Fix NOT MADE first, biggest feature first; an
OFF feature is fixed at the element that makes it. The numbers place and size a feature; whether its SHAPE reads
right is judged by eye, on same-view tiles beside the picture (`feature_tiles(name, ..., label=<view>)` works
from every view read here) and by the blind review. A table with nothing wrong is where that look starts:
"right" says a mass covers its mark, not that it looks like the thing. Look at the clay beside the picture
every round and say what you see.
