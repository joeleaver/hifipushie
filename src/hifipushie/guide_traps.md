# Traps: symptom -> real cause -> what to check first

Each of these has cost a whole round of work more than once. Check the list before you trust a result or a diagnosis.

## Looking and judging (every domain)

- **"It reads right at a glance."** You made it, so you see what you meant. Cause: the author judges what the picture
  was made to prove. Check first: the reference BESIDE the result, cropped to one feature, then `review_view` on
  that pair (a blind reviewer who sees no captions). Numbers come after the look.
- **Every measure passes and it still looks wrong.** Cause: the measure sits beside the fault, not on it (a
  silhouette band, the wrong crop). Check first: crop the region the eye complains about and confirm the measure's
  box is on it; add the missing item before changing the model.
- **A whole-model sheet shows nothing wrong.** Cause: the feature is 40 pixels wide there. Check first: one feature
  per tile, reference | result through the SAME camera, at least 400 px: `feature_tiles` after `look_matched`, or
  `look` with a camera on the feature.
- **Two pictures disagree about a colour or a shape.** Cause: different cameras, lights or view transforms. Check
  first: both through one camera and one light (`look_matched`; `set_reference` + `compare` for outlines). Never
  compare a clay view with an exported one.
- **The review found 2 faults last round and 5 this round.** Cause: two separate reviews are two sittings; their
  counts are noise. Check first: fix the worst MAJOR and look again at THAT region; never steer by the count.

## Editing

- **An edit changed nothing.** Cause: a misspelt key, a key in the wrong section, or a later element covering it
  (a higher `layer`, a subtract). Check first: the answer's own lines. A joint, a bone and a blob REFUSE an unknown
  key; `set_terrain` and `groom_hair` print a WARNING for a key that was not read. Then try two far-apart values.
- **Each fix uncovers the next fault.** Cause: the fault belongs to an earlier stage (the plan, the blockout, the
  pattern) and is being patched downstream. Check first: which stage decides this; go back to it (`history`,
  `revert`).
- **The tool said PASS.** Cause: a tool's own checks say the piece is well-formed (no crossings, it compiles, it is
  inside the budget), not that it is the thing in the reference. Clean is not right. Check first: the reference.

## Stages

- **A later stage looks wrong and the earlier one "was fine".** Cause: it consumed a piece nobody approved, or the
  newest file rather than the approved one. Check first: what the stage took (`garment_record` for a garment; the
  answer's first line of `export_asset` names what it left out).
- **"It runs end to end."** That is plumbing, not a result. The result is the picture beside its reference.

## By domain (their own lists)

Clothes: guide(topic="cloth_faults"). Looking at a model: guide(topic="looking"). Export: judge the exported GLB as
a game draws it, never the clay view (guide(topic="game_export")). The steps every stage takes: guide(topic="gates").
