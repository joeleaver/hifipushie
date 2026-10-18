"""budgets: the profile loads, every number names known sources, parts fit the role's total, LODs shrink.
Run: uv run python tests/test_budgets.py"""
from hifipushie import budgets


def _walk(d, path=()):
    if isinstance(d, dict):
        if "src" in d:
            yield path, d
        for k, v in d.items():
            yield from _walk(v, path + (k,))


def test_sources_resolve():
    P = budgets.load()
    for path, e in _walk({k: v for k, v in P.items() if k != "sources"}):
        for s in e["src"]:
            assert s in P["sources"], (path, s)
        if "basis" in e:
            assert e["basis"] in ("sourced", "derived", "thin"), path
    for s, rec in P["sources"].items():
        assert rec["url"].startswith("https://") and rec["kind"] in ("primary", "secondary", "anecdote"), s


def test_roles_and_parts():
    assert budgets.roles() == ["hero", "main_npc", "secondary_npc", "crowd"]
    prev = None
    for n in budgets.roles():
        r = budgets.role(n)
        lo, hi = r["lod0_triangles"]["range"]
        tot = r["lod0_triangles"]["default"]
        assert lo <= tot <= hi, n
        assert sum(p["default"] for p in r["parts"].values()) <= tot, n
        for p, v in r["parts"].items():
            assert v["range"][0] <= v["default"] <= v["range"][1], (n, p)
        if prev:
            assert tot < prev, n
        prev = tot


def test_triangles_and_lods():
    assert budgets.triangles("hero") == 103000  # (r40: eyes_mouth_lashes derived from its components)
    assert budgets.triangles("hero", "head", lod=1) == 12500
    assert budgets.triangles("hero", "body", lod=1) == 3750
    assert budgets.triangles("hero", "hair_cards", overrides={"hair_cards": 40000}) == 40000
    L = budgets.lod_triangles("main_npc", "hair_cards")
    assert all(a > b for a, b in zip(L, L[1:]))
    try:
        budgets.role("villain")
        raise AssertionError("unknown role accepted")
    except KeyError:
        pass
    assert "hero" in budgets.table()
    assert budgets.sources(budgets.role("hero")["lod0_triangles"])[0]["id"] == "hunt_budgets"


if __name__ == "__main__":
    for f in (test_sources_resolve, test_roles_and_parts, test_triangles_and_lods):
        f()
    print("ok")
