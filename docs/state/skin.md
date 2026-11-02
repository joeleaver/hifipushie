# STATE: skin -- route run 2026-11-01 (branch skin-route; readiness audit /mnt/data/hifipushie/readiness/skin.md)

## This run: the route a blind agent sees (tools, not scripts)
- find_tool("skin" | "pores" | "stubble" | "make-up" | "paint skin texture") -> new `skin` domain, its workflow line first:
  approved head -> forms -> skin(age, tone) -> skin_from_reference -> brow_read(match=True) -> hand finish ->
  look_skin(beside=<region>) -> review_view, one region per call. texture_from_reference is not offered for skin words.
- look_skin(beside=face|forehead|brows|eye|cheek|nose|mouth|jaw[.L/.R], view=i): the model through picture i's fitted
  camera, under its fitted light at its exposure, beside the same crop of the picture. Both crops go to
  workspace/_looks/skin_beside/, and the reply ends with the review_view call that takes them. Refuses views / flat / layer
  and lights other than photo. engine="cycles" is gone.
- skin_from_reference: the atlas for photographs is the default (a fresh one is reused, a stale one is remade and the reply
  says so). The per-picture read needs painting=True. Refused: read_only + project, painting + project, project=False
  without an atlas, and the atlas route without skin.tone. The reply lists what this route does not read (irises, folds,
  pores, roughness).
- skin(): names the patch keys with NO EFFECT under a stack, by diffing what shows (checked on gp_h6c: zones.midface_red,
  variation and lips.blood are dead, tone is body only, lips.over_stack works). The diff has a 25 s budget.
  stack_edit = skin_layers.edit. Fold relief is given in mm against 1 mm, and the reply warns when the head is not approved.
- Every skin tool's reply ends with next:. The export refuses skin.projection.opacity > 0, and texture_from_reference
  refuses on skin.stack.
- Code: src/hifipushie/skin_route.py (new), skin_look.beside, small hooks in server.py / next_steps.after_look(how=) /
  asset._export. Tests: tests/test_skin_route.py (18). codified C265-C269.

## Not verified (machine load 80-100 all run)
- NO real look_skin(beside) image yet. tp_k19's first 1 mm head stage did not finish meshing in 2 x 25-40 min under
  capped (CPUWeight 20). So the crop framing, light and exposure are unjudged.
- The existing skin test files (marks, project, skin, read) each passed their first tests, then timed out at 600 s per
  file under load. The code they test (skin.py, skin_layers, skin_read) is unchanged here. A rerun was started:
  /mnt/data/hifipushie/skin_route_test_skin*.log.
- Seen on real data: gp_h6c (head/garrett approved) reports its skin.projection as STALE against its own head key. Either
  the head key drifted or the atlas is really stale. Not checked.

## Carried from r24 (still open, unchanged)
- Best by blind A/B (not Joe-approved): Tess tp_k19_a16, Garrett gp_h6c_a11. Brows too dark, lips off and salmon, Tess
  ala blob (nose form), Garrett cheek streaks. Their code is on land-older (79cbce57), not on main.
- Blocker 2 (winning settings as defaults: brows.strands ~.6, lips.over_stack) needs renders and an A/B. Blocker 4 (a
  per-person skin_check table) is not started.

NEXT: on an idle machine, render look_skin("tp_k19", beside="eye") once and judge the pair yourself (framing, exposure,
then crop size). Then run one blind agent through the skin route from find_tool("skin") with nothing but the MCP.
