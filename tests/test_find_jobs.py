"""find_tool on plain-language jobs: the question a blind agent asks, and the tool it has to be handed.

Why: the trials name the step and the tool in their brief, so finding a tool was never tested. On 2026-11-10 a job
outside a workflow came back as another domain's workflow ("pose the character with an arm raised" and "judge the
result" -> the five garment steps; "compare my model to the reference picture" -> five hair tools, `compare` absent;
"make a chair" -> `check`): one stray word match picked the domain, and its steps pushed the matching tool out.

A job passes when one of its tools is in the first three. KNOWN_MISSES are the jobs the word match can't answer yet,
each with its reason: a miss that starts passing fails the test, so the list stays true.
uv run python tests/test_find_jobs.py     # the table, one line per job
"""
from hifipushie import server
from hifipushie import tools_find

TOP = 3

# (the job as an agent would ask it, the tools that answer it)
JOBS = [
    # the modelling core
    ("see my model from the back", {"look"}),
    ("a close-up of the face", {"look"}),
    ("move a joint and make a bone thicker", {"edit_model"}),
    ("undo my last change", {"revert", "history"}),
    ("how thick is the arm", {"measure"}),
    ("list my models", {"list_models"}),
    ("what parameters does the hand kit take", {"kit_reference"}),
    ("make a chair", {"put_model", "guide"}),
    ("add a sword prop", {"put_model", "guide"}),
    # plan, reference, concept
    ("compare my model to the reference picture", {"compare", "set_reference"}),
    ("draw a blockout plan first", {"set_plan"}),
    ("match the silhouette to the reference automatically", {"fit"}),
    ("render from the concept art's camera", {"fit_concept_camera", "look_matched"}),
    ("name the features in a character turnaround", {"read_reference", "mark_features"}),
    ("which features of the reference has my sculpt not made", {"feature_report"}),
    ("lay the brows and sockets of the reference on my block-in", {"build_forms"}),
    # export, rig, review
    ("export a GLB for a game engine", {"export_asset"}),
    ("pose the character with an arm raised", {"rig"}),
    ("rig the model for animation", {"rig"}),
    ("check the exported asset looks right", {"judge_asset"}),
    ("judge the result", {"review_view", "judge_asset"}),
    ("get an independent blind review of one view", {"review_view"}),
    # scene
    ("open the model in Blender", {"sync"}),
    ("what heavy jobs are running", {"heavy_status", "heavy_queue"}),
    # humans, skin, hair
    ("start a realistic human body", {"human"}),
    ("make a head from photos of a person", {"block_in_start"}),
    ("make the character smile", {"set_expression", "block_in_expression"}),
    ("add freckles and wrinkles", {"skin"}),
    ("give the character a beard", {"groom_hair", "hair_from_reference"}),
    ("tie the hair in a ponytail", {"tie_hair", "hair_from_reference"}),
    # clothes: a job that starts a garment gets the workflow's first step; a job inside it gets its own tool
    ("make a shirt", {"garment_plan"}),
    ("dress the character in a cloak", {"garment_plan"}),
    ("measure the waist of the body", {"body_tape", "measure_human"}),
    ("look at the garment beside the reference", {"look_chain"}),
    ("which step is the garment at", {"garment_record"}),
    # terrain, plants, clutter
    ("make a tree", {"grow_plant"}),
    ("build a mountain valley with a river", {"set_terrain"}),
    ("scatter rocks and logs on the ground", {"make_clutter"}),
]

# job -> why the word match misses it (kept true by test_known_misses_still_miss)
KNOWN_MISSES: dict[str, str] = {
    "which step is the garment at": "no word of the job names garment_record; the answer's first line (the workflow) "
                                    "does: \"garment_record shows every step\"",
}


# Jobs worded afresh for the area re-review of 2026-11-12, never used to tune the first list: 33 of 49 found then, which
# is what an agent's own words meet. The make-a-thing rule, the plain-word KEYWORDS and "render = look" (find_route,
# C436) came from its misses; it is a regression list now, so the next measure needs new wording again.
FRESH = [
    # the modelling core
    ("turn the head to the left", {"edit_model", "rig"}),
    ("make the legs longer", {"edit_model", "fit"}),
    ("sculpt muscle definition on the arm", {"edit_model", "kit_reference", "guide"}),
    ("paint the creature green with darker spots", {"edit_model", "kit_reference", "guide"}),
    ("what does the model look like from above", {"look"}),
    ("check the mesh for problems", {"check"}),
    ("save an OBJ file", {"export"}),
    ("go back to an earlier version", {"revert", "history"}),
    ("show me the saved spec", {"get_model"}),
    ("make a dragon", {"put_model", "guide"}),
    ("make a stylised owl from this picture", {"put_model", "guide"}),
    ("build a wooden cart", {"put_model", "guide"}),
    ("use this concept image as a guide", {"set_reference", "fit_concept_camera", "set_plan"}),
    ("does the hand join the wrist cleanly", {"join_report"}),
    ("does the character match the art style", {"style_check"}),
    ("can a person fit through the doorway", {"clearance"}),
    ("crop the eyes from the concept and my render side by side", {"feature_tiles"}),
    ("put the hat on the character's head", {"edit_model", "put_model", "guide"}),
    # export, rig
    ("make lower-detail versions for distance", {"export_asset"}),
    ("how many triangles does the export have", {"judge_asset", "export_asset"}),
    ("bring my Blender edits back into the model", {"pull"}),
    ("add a skeleton", {"rig"}),
    ("bake the textures", {"export_asset"}),
    # humans, skin, hair
    ("make an old man", {"human"}),
    ("make her taller with broader shoulders", {"fit_human", "human"}),
    ("what are the body's measurements", {"measure_human", "body_tape"}),
    ("likeness of an actor from photos", {"block_in_start"}),
    ("fix the eyelids so they match the photo", {"lid_read", "block_in_step", "eye_ruler"}),
    ("what reference photos do I need", {"reference_brief", "check_references"}),
    ("raise one eyebrow", {"set_expression", "gnm_controls"}),
    ("skin tone and pores from the photo", {"skin_from_reference", "skin_project"}),
    ("close-up render of the skin", {"look_skin"}),
    ("short cropped hair", {"groom_hair", "hair_from_reference"}),
    ("copy the hairstyle from the photo", {"hair_from_reference"}),
    ("render the hair quickly", {"look_hair"}),
    ("export hair cards for the game", {"export_hair", "export_asset"}),
    # clothes
    ("sew a pair of trousers", {"garment_plan"}),
    ("draft the sewing pattern", {"draft_pattern"}),
    ("add buttons and a pocket", {"garment_details"}),
    ("set the fabric colour", {"garment_appearance"}),
    ("export the jacket for the game", {"export_garment"}),
    ("why was my pattern refused", {"pattern_check", "garment_record"}),
    # terrain, plants, clutter
    ("an island with cliffs and a beach", {"set_terrain"}),
    ("check the terrain's slopes", {"check_terrain"}),
    ("export the landscape as tiles", {"export_terrain"}),
    ("an oak tree in winter", {"grow_plant"}),
    ("prune the lower branches", {"edit_plant"}),
    ("a forest of pines", {"grow_stand"}),
    ("make the tree sway in the wind", {"wind_plant"}),
    ("a mossy boulder", {"make_clutter"}),
    ("grass and ferns on the forest floor", {"grow_plant", "grow_stand", "make_clutter"}),
    # the head route, measured 2026-11-14 (the likeness guide sent a block-in head to the old staged fit)
    ("make this head from the references", {"block_in_start"}),
    ("fit the nose and mouth of my block-in head to the photos", {"block_in_step", "face_ruler"}),
    ("move the nose of my block-in head", {"block_in_step", "face_ruler"}),
    ("start a block-in of a person from photos", {"block_in_start"}),
    # the dressed character's export, measured 2026-11-14 (export_garment led, with the pattern steps behind it)
    ("export the dressed character as one GLB", {"export_asset"}),
    ("export my character with its clothes for the game", {"export_asset"}),
    ("a game-ready file of the dressed character", {"export_asset"}),
    ("export the shirt as a game asset", {"export_garment"}),
]

FRESH_MISSES: dict[str, str] = {
    "turn the head to the left": "no tool poses a model while it is being modelled (edit_model moves joints one by one)",
    "close-up render of the skin": "look_skin is fourth: the skin route's steps lead and no word of the job is its verb",
    "set the fabric colour": "garment_appearance is the clothes route's seventh step; the route's first steps lead",
    "why was my pattern refused": "pattern_check is fifth: the clothes route's first steps lead",
}


def ranked(query: str, limit: int = 5) -> list[str]:
    return [line.split(". ", 1)[1].split(" [")[0] for line in server.find_tool(query, limit).splitlines()
            if line[:1].isdigit() and ". " in line]


def _hit(job: str, want: set) -> bool:
    return bool(want & set(ranked(job, TOP)))


def test_plain_jobs_find_their_tool():
    missed = [(j, ranked(j, TOP)) for j, want in JOBS if j not in KNOWN_MISSES and not _hit(j, want)]
    assert not missed, missed


def test_freshly_worded_jobs_find_their_tool():
    missed = [(j, ranked(j, TOP)) for j, want in FRESH if j not in FRESH_MISSES and not _hit(j, want)]
    assert not missed, missed
    fixed = [j for j in FRESH_MISSES if _hit(j, dict(FRESH)[j])]
    assert not fixed, f"now found, take them out of FRESH_MISSES: {fixed}"


def test_making_a_thing_no_domain_names_is_the_modellers_job():
    """ "make a stylised owl from this picture" came back as three hair tools (the word "picture"): a making job whose
    subject no domain names leads with put_model and the playbook; a domain's own subject still wins."""
    for job in ("make a stylised owl from this picture", "build a wooden cart", "sculpt a dragon", "make a chair"):
        assert ranked(job)[:2] == ["put_model", "guide"], (job, ranked(job))
        assert server.find_tool(job).startswith("no domain makes this by name"), job
    assert ranked("make a tree")[0] == "grow_plant" and ranked("make a shirt")[0] == "garment_plan"
    assert ranked("make an old man")[0] == "human" and ranked("make a head from photos of a person")[0] == "block_in_start"
    assert "put_model" not in ranked("make the character smile")[:1]  # ("make the ..." changes a thing, it makes none)


def test_known_misses_still_miss():
    jobs = dict(JOBS)
    assert set(KNOWN_MISSES) <= set(jobs), set(KNOWN_MISSES) - set(jobs)
    fixed = [j for j in KNOWN_MISSES if _hit(j, jobs[j])]
    assert not fixed, f"now found, take them out of KNOWN_MISSES: {fixed}"


def test_a_job_outside_a_workflow_is_not_handed_one():
    """A stray word match never turns the answer into another domain's steps."""
    flows = [s_["steps"] for s_ in server.TOOL_GROUPS.values() if s_.get("workflow")]
    for job in ("pose the character with an arm raised", "judge the result", "make a chair", "add a sword prop",
                "compare my model to the reference picture", "how thick is the arm"):
        text, r = server.find_tool(job), ranked(job)
        assert text[:2] in ("1.", "no"), (job, text[:80])  # (no workflow line on top)
        assert all(r != steps[:len(r)] for steps in flows), (job, r)
    assert server.find_tool("make a chair").startswith("no domain makes this by name") and ranked("make a chair")[0] == "put_model"
    assert server.find_tool("a chair").startswith("no tool is named for this job") and ranked("a chair")[0] == "guide"
    assert 'guide(topic="props")' in server.find_tool("add a sword prop")


def test_a_tool_for_the_job_comes_before_one_that_mentions_it():
    """export_garment's notes say "arm", "raised" and "posed" (its bend check); rig is the tool that poses."""
    r = ranked("pose the character with an arm raised")
    assert r[0] == "rig" and r.index("rig") < r.index("export_garment"), r


def test_one_stem_for_a_word_and_its_plural():
    for a, b in (("tree", "trees"), ("silhouette", "silhouettes"), ("pose", "posing"), ("freckle", "freckles")):
        assert tools_find._stem(a) == tools_find._stem(b), (a, b)


def test_a_job_that_starts_a_workflow_still_gets_it_in_order():
    for job in ("make a shirt", "dress the character in a cloak", "sew a jacket for him"):
        text, r = server.find_tool(job, 8), ranked(job, 8)
        assert text.startswith("Clothes: garment_plan"), (job, text[:80])
        assert r.index("garment_plan") < r.index("draft_pattern") < r.index("chain_garment"), (job, r)


if __name__ == "__main__":
    ok = 0
    for job, want in JOBS:
        r = ranked(job)
        hit = bool(want & set(r[:TOP]))
        ok += hit
        print(f"{'ok  ' if hit else 'MISS'} {job!r:52} -> {r}")
    print(f"{ok} / {len(JOBS)} in the first {TOP}")
