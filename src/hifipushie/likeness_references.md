# Likeness: references (handed, and what to ask for)

Read guide(topic="likeness") first.


Two modes: references you are handed (unpredictable: be robust and say what they can't support), and references
you can ask for or generate (get the best ones the checklist needs).

**Handed references.** Everything above is built to degrade honestly: each item says what it was measured from, with
a confidence, "inferred" from a weaker view, hand-placed points where the detector fails, and the coverage line.
`check_references(images, name=None)` judges a set before any fitting: views present (the detector's head pose),
lens (the fitted camera's focal when the model has one: under ~60 mm equivalent swells the nose), expression (smile,
open mouth, squint, raised or furrowed brows from the detector's blendshapes), the light's evenness, ears and
forehead covered (a colour heuristic: treat as a hint), and identity consistency between views (vertical proportions
that don't change with the head's turn should agree within 8%). It ends with the brief's shots to ask for.

**References we generate or ask for.** `reference_brief(kind="head" | "figure", subject)` is the shot list derived
from the checklist, with what makes each shot usable and prompt wording per shot (one shared identity block, so a
generator keeps the person):

- front, true left profile, three-quarter (45 deg); the front and three-quarter again under ONE side light (the
  planes: the shape items read shading); optional back and top; for a figure, full-body A-pose front and side;
- a long lens (85-135 mm equivalent) at eye height; neutral expression, mouth closed, eyes open to the horizon;
- soft even frontal light for the measuring shots; a plain background;
- hair off the ears and the hairline; the neck and jaw uncovered; nothing over the features;
- the same identity, light, scale and camera height in every view.

The brief's shape ({subject, common: {prompt, negative}, shots: [{id, view, light, purpose, must_show, prompt}],
text}) is shared with the clothing checklist's (`cloth_reference.reference_brief`), so one generator step can serve
both.
