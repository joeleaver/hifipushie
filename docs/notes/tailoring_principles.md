# Tailored jacket: drafting principles (R1-R27)

Our knowledge, in our words, for drafting a men's tailored jacket (and later coats) for any body. Learned 2026-10-19
by reading FreeSewing's Jaeger design step by step (FreeSewing, MIT licence, Joost De Cock and contributors,
https://freesewing.org; Jaeger extends Bent, which extends Brian; the two-part sleeve is in @freesewing/library;
our pack is 4.10.2). Jaeger is a reference to learn from: nothing of it is copied or wrapped. Its source comments say
its collar "would benefit from a redesign", so where tailoring practice says more, the rule says so.
Code: `src/hifipushie/pattern_jacket.py` (rules(), the ops, the gate rows T); every value carries "source": R<n>.
Marks: [G] general principle; [J] Jaeger's own style / number (a fair default, not a law). Measures: girths,
lengths along the body; "neck" = the neck girth taken where the jacket collar sits (over the shirt).

## Body and ease
1. **Ease by zone** [G, numbers J]. Chest +8 %, waist +14 %, hips +12 % over the body (a jacket over a shirt). Why:
   the chest needs room to reach and breathe; the waist is where the shape is; the hips must clear sitting.
   The flat pattern then reads (CF to CF) about chest +6-8 %, waist +14 %, hips +12-15 %.
2. **Draft on a rectangle** [G]. Centre-back line, HPS level, chest line; the quarter chest (chest x (1 + ease) / 4)
   fixes the side. Why: every later point is a proportion of a body measure from this frame, so it grades.
3. **Back neck width = neck x 1.035 / 4.8 from the CB line** [G form, J numbers] (~ neck / 4.6), less the CB seam's
   shaping at the neck (0.5 % chest). Why: the collar sits on the base of the neck; a wider neck point stands off
   the neck and gapes (muslin 1: 103 vs 93).
4. **Back neck rise = 5 % of neck** (~20-25 mm) [G]. The CB neck sits only a little below the HPS. Why: the back neck
   is nearly straight; a deep back neck (muslin 1: 37) drops the collar off the neck at the back.
5. **Shoulder** [G]. The shoulder point at half the shoulder-to-shoulder (+ any ease), along the measured slope; the
   across-back at ~97 % of it. Front 1-2 deg steeper than the back in tailoring practice ([J] uses one slope).
6. **Armhole depth** [G]. The armhole level ~15 % of waist-to-armpit below the armpit (Jaeger: armholeDepth 5 % +
   half the biceps ease). Why: a jacket goes over a shirt and must let the arm move, but a deep armhole lifts the
   whole jacket when the arm rises.
7. **Front neck fitted to length** [G]. The front neck's depth is found by iteration so the whole neckline equals
   neck x (1 + collar ease 3.5 %). Why: the collar is drafted from that length.

## Shape
8. **Waist suppression, shared** [G, shares J]. Reduction = chest x (1 + ease) - waist x (1 + ease), half of it per
   side, taken out at: CB 16 %, side-back seam 32 %, side-front seam 32 %, front dart 20 %. The shaping fades out by
   the hip line. Why: many small take-ins keep each seam near the grain and put the shape where the body curves;
   one big take-in makes a hinge. A shaping that runs past the hip line pulls the hips in (our v2 first read -0.4 %).
9. **Side panel** [G]. A tailored jacket has no side seam: a side panel between a back seam dropped from the armhole
   hollow and a front seam at ~85 % of the front width; its armhole edge raised so the two panel seams match.
   Why: the panel follows the side of the ribcage, and both seams can be shaped.
10. **Front (fish-eye) dart** [G]. ~55 % of the way from CF to the side-front seam, from 2/3 of armhole -> waist above
    the waist to 2/3 of waist -> hips below (it ends in the hip pocket). Why: it shapes the front over the chest and
    in at the waist without breaking the lapel or the front edge (muslin 1 had none: "boxy fronts").
11. **Chest shaping** [J]. The upper front is turned ~1.5 deg about the side split (slash and spread). Why: room over
    the chest and a lapel that lies. Ours: not drafted (a canvas / press job on the drape).

## Front edge, lapel, buttons
12. **Overlap (button extension) = the button's diameter** [G]. The button centre sits on CF; the front edge is one
    diameter beyond it. Why: a smaller extension shows the under front and the buttonhole runs off the edge
    (muslin 1: 12 mm for a 20 mm button). [J] uses 1.5 % of chest (13-17 mm).
13. **Buttons** [G]. Top button at the break; a second ~30 % of break -> hem below it [J]. The break sits at or a
    little above the waist (concept-driven: Garrett's is the concept's).
14. **Roll line** [G]. From the break point to a point beyond the neck point, along the shoulder line extended by
    the collar stand's height (Jaeger 6 % of neck). Why: the lapel turns on the line where the collar stand meets
    the body; the two must be one line when worn.
15. **Gorge and notch** [G, angles J]. The gorge runs from the neck point to the notch; the collar ends at the notch,
    the lapel's top edge goes on beyond it. Notch depth, angle (Jaeger 45 deg) and gorge height are STYLE, read from
    the concept, not body rules. When the concept doesn't show it: the fall's end is drafted at half its CB height
    (pattern_jacket.FALL_FRONT 0.5), which gives a notch gap of 32-38 mm at 64-69 deg (cloth_checklist notch: 20-40 mm,
    60-90 deg). At 0.8, the gap was 53-61 mm (fit round 2).

## Collar
16. **A tailored collar is two pieces: stand + fall** [G]. Measured at CB from the ROLL LINE: the stand (neck seam to
    roll line) is neck / 16, held to 25-30 mm; the fall (roll line to its edge) is the stand + 10 mm, so it covers the
    stand and the seam by about 1 cm (Mueller & Sohn lapel-collar drafts: stand 2.5-3 cm; Theatre Design & Technology
    1981: the fall a little deeper than the stand; cloth_checklist collar_stand 25-30 / collar_fall stand + 6..15).
    The fall has its own FOLD (roll) line, 4 mm above its seam on the stand (FALL_FOLD), and it turns down about that
    line. So the stand PIECE is 4 mm less than the stand read from the roll line (Garrett: piece 24.3, read 28.3; round
    1's "stand ~25 at CB" was the piece). Why: the stand holds the collar up the neck; the fall turns down over it; a
    separate stand (or a well-shaped one-piece undercollar) lets each part take its own shape.
    CHANGED fit round 2 (2026-10-19). Before, it was Jaeger's 18 % of neck split 30 / 70, which gave stand 28.5 / fall
    56 for Garrett. That fall is 27 mm deeper than the stand, so the checklist collar_fall FAILED. The split also grew
    with the neck (a 522 neck: stand 36), while practice keeps the stand at 2.5-3 cm for every man. The form showed it:
    with no fold line, the fall stood up like a hood.
17. **The stand's neck edge is drafted near-straight** [G]. Its length = back neck + front neck to the notch; it runs
    straight across the back and rises only gently toward the front (sagitta / chord ~0.02-0.04); its top edge is
    then a little shorter, so it leans in to the neck. Why: a collar whose neck edge follows the neckline (sagitta
    ~0.2-0.3, a crescent) is a FLAT collar: it lies on the shoulders and cannot stand (muslin 1, 535 mm wide).
18. **The fall is sprung** [G, spread J; fixed fit rounds 2-3]. Its outer edge is as long as the line it LIES on: the
    neckline offset into the body pieces by the edge's drop below the neck seam (fall - stand from the roll line at
    CB, tapering u^2 to the fall's end) + pi x its stand-off there (fall stack / 2 + cloth / 2). The spread is solved
    from that (Garrett 17 deg: outer 265 vs neck seam 246 per half), its height + the turn depth (pi/2 x the fall's
    stack + the under-stack it wraps). The stand + shirt collar are under the ROLL LINE, never under the outer edge
    (round 2 counted them there: spread 43 deg). Check: tailoring books spread ~1-1.5 cm per half over the neck seam
    (Aldrich, Metric Pattern Cutting for Menswear; Cabrera & Flaherty) + our stand's lean-in. Replaces Jaeger's
    fixed 13 deg / 5 %. The undercollar is a turn smaller at its outer edge (pi/2 x the fall stack, ~3 mm; books
    trim 3 mm), on the bias. PRACTICE DIFFERS from our cut: books cut the UNDERcollar in two (stand + fall, bias) and
    the TOP collar in one (straight grain, a turn bigger); our stand + fall are the undercollar's pieces and the fall
    stands in for the top collar on the form (open: the one-piece top collar is not drafted).

## Sleeve
19. **Two-piece sleeve** [G]. Box: eased biceps / 2 wide, shoulder-to-wrist long; cap height 45 % of the eased biceps
    (biceps ease 20 %); the under sleeve set in from the box edges (back factor / 4, front / 9) so both seams sit under
    the arm; bent ~10 deg at the elbow; wrist = wrist x 1.4, the top sleeve wider than the under. The cap is fitted
    to the armhole by iteration: cap = armhole x (1 + cap ease). Cap ease 1-2 % ([J] 1 %, reads 1.85 %); ours 3 %
    (wool, set with a pad and head). Why: a cap a little longer than the armhole gives the rounded head; two pieces
    give the forward pitch of a relaxed arm.
20. **Sleeve vent** [J]. ~35 % of the lower arm long, a sixth of the wrist wide.

## Hem, pockets, vents, length
21. **Hip (flap) pockets** [G, numbers J]. ~0.68 of the front's hip width, ~1/3 of waist -> hips below the waist
    (22 % of waist-to-hips), centred ~3/4 out from CF (they cross the dart's end); flap ~1/3 of the width deep. A
    construction choice of the design ("pockets": "flap"). Ours stay inside the front piece (a tooling limit:
    op_pocket cannot cross a seam).
22. **Chest welt** [G, numbers J]. At the armhole-pitch level, ~37 % of the front width, welt ~17.5 % of that tall,
    tilted ~2.5 deg up to the side; left front only in practice.
23. **Inner pockets** [J]. A welt on the facing at the dart's top level (not drafted by us).
24. **Back vent** [G, numbers J]. A centre vent ~35 % of waist -> hips above the hip line, its underlay neck / 10 wide.
25. **Length** [G]. Hip length + a style bonus (Jaeger 19 %); the CF hem dropped ~2 % and cut away from the lower
    button at ~2.5 deg, rounded. Ours: the concept's length (length_bonus 0.15).
26. **Collar neck edge eased on** [G]. Walk the seam: neck edge = neckline, or ~1 cm shorter eased on (Mueller &
    Sohn) so the collar hugs; Jaeger and we sew 1:1 (option `ease`).
27. **Lapel facing turn allowance** [G, fit round 3]. Above the break the lapel turns back with the facing outermost:
    the facing is let out pi/2 x the lapel stack (cloth + canvas + facing, ~3 mm) at its lapel edge, nothing at the
    break, full at the lapel point and the gorge, and eased on (Cabrera & Flaherty, Classic Tailoring Techniques:
    facing 3-6 mm wider at the lapel, eased across the roll line) so the seam rolls under. op_lapel_turn; a cut-piece
    record (the facing is fused to the front: the form / sim surface does not change).
28. **The stand runs off at the front** [G, fit round 18; OPT-IN]. The collar's roll line is the lapel's roll line run
    on (R14), so it meets the gorge where the lapel's roll line crosses it (pattern_draft._roll_meets_neck; Garrett /
    the test bodies: ~32 mm past the neck point, ~100 mm before the collar's end, at ~34 deg). The stand's height
    falls to near nothing there (STAND_RUN_OFF end 3 mm, profile as op_collar: stand x (1 - (s / s_x)^p)) and the
    collar's end past it is all fall, lying flat in the lapel's plane; the outer edge's length is unchanged. Source:
    general tailoring practice for a notched collar (the undercollar's crease line runs off into the gorge line at the
    roll line; Aldrich, Metric Pattern Cutting for Menswear and Cabrera & Flaherty describe the draft; page not checked
    here: no copy at hand). Gate row collar_stand_end (<= 3 + 3 mm). OPT-IN because the fall's own crease (its fold
    4 mm above the seam, turned 172 deg) still runs to the end: on the form it folds the flat end back over the lapel
    (gorge_lie worse: tip 12 / 14 mm). NEXT: the fall's fold must run off at s_x with the stand.
29. **The lapel edge has a belly** [G, garrett jacket fit round 32]. The lapel edge from the break to the lapel point
    is drawn with a slight convex curve, not a straight line: rolled over a curved chest a straight edge reads hollow
    (round 31 worn: 7 / 14 / 22 mm inside the break -> point line at 150 / 200 / 250 mm below the HPS, where the concept's
    edge is straight). op_lapel `belly` (m) at `belly_at` (fraction from the break); Garrett: 10 mm at 0.4. Sources:
    tailoring drafts draw the lapel edge "with a slight curve" from the break to the point (the lapel's belly / crown);
    the amount is style, read from the reference's worn edge.

## What the gate checks (pattern_jacket.tailor_rows, cloth_check.pattern_gate for a jacket)
back_neck_width R3 (+-6 mm), back_neck_rise R4 (+-6 mm), waist_suppression R8 (11-20 % of chest), hips_clearance
R1 / R8 (>= hips + 4 %), front_dart R10 (present), front_overlap R12 (button +-4 mm), collar_neck_edge_straight R17
(sagitta <= 0.08 across the whole edge), collar_stand_cb R16 (+-1.2 % neck), collar_fall_cb R16 / R18 (+-2 % neck), the fall's fold line (flat_pattern: no fold line
-> FAIL), the checklist's flat collar_stand / collar_fall / notch rows read on a two-piece collar (cloth_check
collar_draft_two_piece, notch_flat),
pockets R21 (present when the design asks). Known answers: tests/test_tailoring.py.
