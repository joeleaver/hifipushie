"""Hard-won rules as checks that fail loudly (codify checks, 2026-10-19; ledger docs/notes/codified.md).
One test per rule; each names the rule and where it is enforced."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

os.environ.setdefault("HIFIPUSHIE_HOME", tempfile.mkdtemp(prefix="hp_codified_"))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin" / "hooks"))


# -- 3. expressions are parameter mixes only ----------------------------------------------------------------------
def test_sculpted_expression_deltas_are_refused(monkeypatch):
    from hifipushie import faceshapes as fs
    monkeypatch.delenv(fs.ALLOW_SCULPT_ENV, raising=False)
    monkeypatch.setattr(fs, "SHAPE_SCULPT", "/x/sculpt.npz")
    with pytest.raises(ValueError, match="hand-sculpted"):  # from the environment
        with fs.character_fits({"base": {"head": {}}}, []):
            pass
    monkeypatch.setattr(fs, "SHAPE_SCULPT", "")
    with pytest.raises(ValueError, match="hand-sculpted"):  # from the spec
        with fs.character_fits({"base": {"head": {"face_fits": {"sculpt": "s.npz"}}}}, [], "/x"):
            pass
    monkeypatch.setattr(fs, "SHAPE_SCULPT", "/x/sculpt.npz")
    with pytest.raises(ValueError, match="hand-sculpted"):  # and at the point of use
        fs._sculpted({}, "body", 3, [])
    monkeypatch.setenv(fs.ALLOW_SCULPT_ENV, "1")  # the one explicit opt-out: logged
    log = []
    fs.refuse_sculpt("/x/sculpt.npz", log=log)
    assert log and log[0].startswith("WARNING")


def test_expression_presets_are_arkit_mixes():
    from hifipushie import faceshapes as fs
    w = fs.expression("smile_tess")
    assert w["mouthSmileLeft"] == w["mouthSmileRight"] == 0.8 and w["cheekSquintLeft"] == 1.0
    assert w["eyeSquintLeft"] == 0.5 and w["mouthDimpleLeft"] == 0.6 and w["mouthPressLeft"] == 0.2
    assert w["mouthUpperUpLeft"] == pytest.approx(0.108)
    with pytest.raises(ValueError):
        fs.expression({"mouthSmileLeft": 0.5, "lipSculptTess": 1.0})
    with pytest.raises(ValueError):
        fs.expression({"mouthSmileLeft": 1.4})


# -- 4. hair budget: card faces vs default, drawn (back faces in) vs the range max --------------------------------
def test_hair_budget_numbers_are_budgets_json():
    from hifipushie import budgets
    mx = {r: budgets.role(r)["parts"]["hair_cards"]["range"][1] for r in budgets.roles()}
    assert mx == {"hero": 50000, "main_npc": 20000, "secondary_npc": 8000, "crowd": 1500}


def test_hair_budget_refuses_drawn_over_max_and_counts_card_faces():
    from hifipushie import asset, budgets, hair
    asset.hair_budget.selftest()
    asset.budget_check.selftest()
    rb = budgets.role("crowd")
    rep = {"hair": {"triangles": 1600, "cards": True, "back_faces": True, "vertices": 900,
                    "layers": {"cap": [0, 100], "layer0": [100, 1500]}}}
    g = asset.budget_check(rb, rep, {})
    assert g["fail"] and g["hair"]["card_faces"] == 850 and g["hair"]["vertices"] == 900
    assert hair.BUDGET_UNIT == "card_faces"  # the cards are fitted to card faces, not drawn triangles
    src = (ROOT / "src/hifipushie/asset.py").read_text()
    assert 'if budget_gate["fail"]:' in src and "vertices=len(hpart[\"verts\"])" in src


# -- 6. hair previews: a single-sided card material needs the cards' own back faces --------------------------------
def test_single_sided_cards_without_back_faces_are_refused(tmp_path):
    from hifipushie import asset
    png = tmp_path / "flat.png"
    Image.new("RGBA", (4, 4), (128, 128, 255, 255)).save(png)
    V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.float32)
    part = {"verts": V, "corner_vert": np.array([0, 1, 2], np.int64), "uv": np.zeros((3, 2), np.float32),
            "normal": np.tile([0, 0, 1], (3, 1)).astype(np.float32),
            "tangent": np.tile([1, 0, 0], (3, 1)).astype(np.float32), "sign": np.ones(3, np.float32)}
    maps = [("0", {"basecolor": png, "orm": png, "normal": png, "specular": png})]

    def look(bf, ds):
        return {"hair": {"alpha_cutoff": 0.3, "double_sided": ds, "extras": {"hifipushie_hair": {"back_faces": bf}}}}
    asset.write_glb(tmp_path / "ok.glb", "h", {"hair": dict(part)}, maps, looks=look(True, False))
    asset.write_glb(tmp_path / "ok2.glb", "h", {"hair": dict(part)}, maps, looks=look(False, True))
    with pytest.raises(ValueError, match="half the cards"):
        asset.write_glb(tmp_path / "bad.glb", "h", {"hair": dict(part)}, maps, looks=look(False, False))


# -- 8. reviews: no captions / sheets / claims in; a review that didn't run is not 0 MAJORs ------------------------
def _render(path, caption=None):
    im = Image.new("RGB", (400, 300), (150, 150, 155))
    d = ImageDraw.Draw(im)
    d.ellipse((120, 60, 280, 260), fill=(200, 160, 130))
    if caption:
        d.text((8, 6), caption, fill=(0, 0, 0))
    im.save(path)
    return str(path)


def test_review_inputs_refuse_captions_sheets_and_claims(tmp_path):
    from hifipushie import reviewgate as rg
    clean = _render(tmp_path / "a.png")
    rg.refuse_inputs([clean], ["crease, right eye"], "a game character's head")
    with pytest.raises(rg.InputRefused, match="caption"):
        rg.refuse_inputs([_render(tmp_path / "b.png", "after r12: lids fixed")], ["lids"], "")
    Image.new("RGB", (3600, 900)).save(tmp_path / "sheet.png")
    with pytest.raises(rg.InputRefused, match="sheet"):
        rg.refuse_inputs([str(tmp_path / "sheet.png")], ["x"], "")
    for bad in ("lids now 2.5 mm", "brows fixed", "v7f result"):
        with pytest.raises(rg.InputRefused):
            rg.refuse_inputs([clean], ["lids"], bad)


def test_review_that_did_not_run_is_a_failure(tmp_path):
    from hifipushie import reviewgate as rg
    ok = tmp_path / "ok.md"
    ok.write_text("lids\n1. MAJOR: crease too dark\n2. MINOR: x\n## OTHER STAGES\n- MAJOR: hair\nVERDICT: FAIL\n")
    assert rg.result(ok) == {"ran": True, "verdict": "FAIL", "major": 1, "minor": 1} and rg.majors(ok) == 1
    for text in ("REVIEW FAILED (no VERDICT line; claude exit 1)\nusage limit", "the reviewer said nothing useful"):
        bad = tmp_path / "bad.md"
        bad.write_text(text)
        assert rg.result(bad)["ran"] is False and rg.result(bad)["major"] is None
        with pytest.raises(rg.ReviewNotRun):
            rg.majors(bad)
    review = Path("/mnt/data/hifipushie/bin/review")
    if review.exists():  # the live tool: exit 4 when the reviewer didn't run, 5 for refused input
        s = review.read_text()
        assert "sys.exit(4)" in s and "reviewgate" in s


# -- 9. heavy jobs declare their memory; human exports reserve >= 24 GB -------------------------------------------
def test_undeclared_heavy_job_is_refused():
    from hifipushie import resources
    with pytest.raises(ValueError, match="declare"):
        with resources.heavy("an undeclared job"):
            pass


def test_human_export_declares_24_gb():
    from hifipushie import asset, resources
    assert resources.EXPORT_HUMAN_GB >= 24
    assert asset.export_gb({"base": {"head": {}}}) >= 24 and asset.export_gb({"hair": {}}) >= 24
    assert asset.export_gb({"joints": {}}) < 24  # a prop keeps the measured estimate
    assert "gb=export_gb(" in (ROOT / "src/hifipushie/asset.py").read_text()


# -- 10. git guards --------------------------------------------------------------------------------------------------
def _git(d, *a, inp=None):
    return subprocess.run(["git", *a], cwd=d, input=inp, capture_output=True, text=True, check=True).stdout


def test_git_guard_blocks_private_workspace_big_and_branches(tmp_path, monkeypatch):
    """On a scratch repo (never this one): the pre-push guard refuses non-main refs, workspace/ paths, > 5 MB files and
    a private prefix (a made-up one here: real prefixes are never written in a tracked file); pre-commit refuses
    workspace/ and > 5 MB."""
    import guard
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "a.txt").write_text("hello\n")
    _git(d, "add", "a.txt")
    _git(d, "commit", "-qm", "base")
    base = _git(d, "rev-parse", "HEAD").strip()
    monkeypatch.chdir(d)
    monkeypatch.setenv("HIFIPUSHIE_PRIVATE_PREFIXES", "zq7,kk")

    def push(ref="refs/heads/main"):
        head = _git(d, "rev-parse", "HEAD").strip()
        return guard.pre_push([f"refs/heads/main {head} {ref} {base}"])
    (d / "b.txt").write_text("a clean change\nkkk and kk are not tags\n")
    _git(d, "add", "b.txt")
    _git(d, "commit", "-qm", "clean")
    assert push() == []
    assert any("only main" in f for f in push("refs/heads/feature"))
    (d / "c.txt").write_text("model zq7_a3 tuned\n")
    _git(d, "add", "c.txt")
    _git(d, "commit", "-qm", "notes")
    assert any("private model" in f for f in push())
    _git(d, "reset", "-q", "--hard", "HEAD~1")
    (d / "workspace").mkdir()
    (d / "workspace" / "x.json").write_text("{}")
    (d / "big.bin").write_bytes(os.urandom(5 * 1024 * 1024 + 10))
    _git(d, "add", "-f", "workspace/x.json", "big.bin")
    pc = guard.pre_commit()
    assert any("workspace/" in f for f in pc) and any("> 5 MB" in f for f in pc)
    _git(d, "commit", "-qm", "oops")
    pp = push()
    assert any("workspace/" in f for f in pp) and any("> 5 MB" in f for f in pp)
    monkeypatch.delenv("HIFIPUSHIE_PRIVATE_PREFIXES")
    monkeypatch.setattr(guard, "PREFIX_FILE", str(tmp_path / "none"))
    assert any("prefixes unknown" in f for f in push())


def test_no_private_prefix_in_tracked_files():
    """The prefixes live outside the repo; when they're known here, no tracked file may contain one (word start)."""
    import guard
    ps = guard.prefixes()
    if not ps:
        pytest.skip("private prefixes not configured on this machine")
    rx = guard.private_rx(ps)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    hits = [f for f in files if f.startswith(("src/", "bin/", "tests/")) and (ROOT / f).is_file()
            and (ROOT / f).suffix in (".py", ".sh", ".json", "") and rx.search((ROOT / f).read_text(errors="ignore"))]
    assert not hits, f"private-model names in tracked files: {hits}"


# -- 11. doc size gates ----------------------------------------------------------------------------------------------
def test_claude_md_under_8_kb():
    assert (ROOT / "CLAUDE.md").stat().st_size < 8 * 1024


def test_state_pages_at_most_60_lines():
    long = {p.name: n for p in (ROOT / "docs/state").glob("*.md") if (n := len(p.read_text().splitlines())) > 60}
    assert not long, f"STATE pages over 60 lines: {long}"


# -- 12. gate measures carry known-answer self-tests ----------------------------------------------------------------
def test_gate_measures_are_validated():
    from hifipushie import validated
    assert validated.missing() == []
    res = validated.run()
    assert all(v == "ok" for v in res.values()), res


# -- 13. incremental build == cold build; BUILD_VERSION bumped with the meshing --------------------------------------
SPEC = {"joints": {"hip": {"pos": [0, 0, 0.5], "r": 0.12}, "head": {"pos": [0, 0, 0.9], "r": 0.1},
                   "hand.L": {"pos": [0.3, 0, 0.6], "r": 0.05}},
        "bones": {"spine": {"a": "hip", "b": "head", "r_a": 0.12, "r_b": 0.08},
                  "arm.L": {"a": "hip", "b": "hand.L", "r_a": 0.05, "r_b": 0.04}}}
GOLDEN = ROOT / "tests/data/build_golden.json"


def _mesh(name):
    from hifipushie import store
    z = np.load(store.build(name, resolution=64)["mesh"])
    return {k: z[k] for k in z.files}


def _stats(m):
    V = m["verts"] if "verts" in m else m[next(iter(m))]
    return [int(len(V)), round(float(np.asarray(V, float).sum()), 4)]


def test_incremental_build_equals_cold_build():
    from hifipushie import store
    store.save("cod_inc", SPEC, "a")
    _mesh("cod_inc")
    s2 = json.loads(json.dumps(SPEC))
    s2["joints"]["hand.L"]["pos"] = [0.32, 0.02, 0.62]
    store.save("cod_inc", s2, "move the hand")
    inc = _mesh("cod_inc")
    store._LIVE.clear()
    import shutil
    shutil.rmtree(store._dir("cod_inc") / "build")
    cold = _mesh("cod_inc")
    assert set(inc) == set(cold)
    for k in inc:
        assert np.array_equal(inc[k], cold[k]), k


def test_build_version_bumped_when_meshing_output_changes():
    """A fixed spec's mesh stats are recorded per BUILD_VERSION: if the mesh changes and BUILD_VERSION didn't, bump it
    (store.BUILD_VERSION) and record the new stats here (HIFIPUSHIE_REGOLD=1)."""
    from hifipushie import store
    store.save("cod_gold", SPEC, "golden")
    st = _stats(_mesh("cod_gold"))
    gold = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    v = str(store.BUILD_VERSION)
    if os.environ.get("HIFIPUSHIE_REGOLD") == "1" or v not in gold:
        gold[v] = st
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(gold, indent=1) + "\n")
    assert gold[v][0] == st[0] and abs(gold[v][1] - st[1]) < 1e-3, \
        f"meshing output changed ({gold[v]} -> {st}) with BUILD_VERSION {v}: bump store.BUILD_VERSION"


# -- 1 / 2. approved head geometry; skin folds may not reshape it (code on the export branches, merging to main) ----
def test_export_gates_on_the_approved_head_and_fold_form():
    from hifipushie import asset
    if not hasattr(asset, "approved_head") or not hasattr(asset, "FOLD_FORM_MAX_MM"):
        pytest.skip("asset.approved_head / FOLD_FORM_MAX_MM not on this branch yet (export branches; coordinator merges)")
    assert asset.FOLD_FORM_MAX_MM <= 1.0
    src = (ROOT / "src/hifipushie/asset.py").read_text()
    assert "is not the approved head" in src and "skin.folds change the head's form" in src
    with tempfile.TemporaryDirectory() as d:
        Path(d, "approved.json").write_text(json.dumps({"approved": {}}))
        with pytest.raises(ValueError):
            asset.approved_head({"base": {"head_approved": "head/nobody", "head": {}}}, [], Path(d, "approved.json"))


def test_mixed_view_transforms_are_refused():
    """Rule 5: a colour comparison or a game-light render that mixes view transforms (AgX vs Khronos PBR Neutral vs
    Standard) refuses loudly; face_light_check must be told both renders' views."""
    from hifipushie import asset
    img = np.full((64, 64, 3), 128.0)
    with pytest.raises(asset.MixedViewTransform):
        asset.face_light_check(img, img, views=("AgX", "Khronos PBR Neutral"))
    with pytest.raises(asset.MixedViewTransform):
        asset.same_view({"lights": []}, asset.GAME_LIGHT)   # a look naming no view renders AgX
    with pytest.raises(ValueError):
        asset.face_light_check(img, img)                    # views undeclared
    assert asset.same_view(asset.GAME_LIGHT, "Khronos PBR Neutral") == "Khronos PBR Neutral"
    with pytest.raises(asset.MixedViewTransform):
        asset.game_light_view({**asset.GAME_LIGHT, "view": "AgX"}, "look")
    with pytest.raises(asset.MixedViewTransform):
        asset.game_light_view({**asset.GAME_LIGHT, "view": "Standard"}, "look")
    asset.game_light_view(asset.GAME_LIGHT)                 # the game rig under its own view
    asset.game_light_view({"lights": [{"dir": [0, 0, 1], "energy": 1.0}], "view": "AgX"})  # another rig: free


def test_review_refuses_a_contact_sheet_grid():
    """(Joe 2026-10-19) a reviewer sees ONE view per turn: a grid of views with flat gutters is refused, a single view
    on a flat background is not."""
    import numpy as np
    from PIL import Image
    from hifipushie import reviewgate
    rng = np.random.default_rng(0)
    view = lambda: (rng.random((200, 200)) * 200 + 30).astype(np.uint8)
    one = np.full((300, 300), 90, np.uint8)
    one[50:250, 50:250] = view()
    assert reviewgate.grid_gutters(Image.fromarray(one)) is None
    sheet = np.full((420, 420), 90, np.uint8)
    for y in (0, 220):
        for x in (0, 220):
            sheet[y:y + 200, x:x + 200] = view()
    sheet[200:220, :] = 20
    sheet[:, 200:220] = 20
    assert reviewgate.grid_gutters(Image.fromarray(sheet))
