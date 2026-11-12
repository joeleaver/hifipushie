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


def ranked(query: str, limit: int = 5) -> list[str]:
    return [line.split(". ", 1)[1].split(" [")[0] for line in server.find_tool(query, limit).splitlines()
            if line[:1].isdigit() and ". " in line]


def _hit(job: str, want: set) -> bool:
    return bool(want & set(ranked(job, TOP)))


def test_plain_jobs_find_their_tool():
    missed = [(j, ranked(j, TOP)) for j, want in JOBS if j not in KNOWN_MISSES and not _hit(j, want)]
    assert not missed, missed


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
    assert server.find_tool("make a chair").startswith("no tool is named for this job") and ranked("make a chair")[0] == "guide"
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
