"""Export budgets by role and target (`budgets.json`): what a character, prop, tree or terrain may cost on a
mainstream gaming PC, each number with its sources and whether it was read, derived or is a thin guess.
Research and derivation: docs/notes/budgets.md. Budgets follow from role and target: state them, never invent them.

    budgets.role("hero")                       # the role's whole entry
    budgets.triangles("main_npc")              # LOD0 total
    budgets.triangles("hero", "hair_cards", lod=2)
    budgets.lod_triangles("hero", "head")      # [LOD0, LOD1, ...]
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name("budgets.json")
ABOVE_NECK = {"head", "hair_cards", "eyes_mouth_lashes"}
BELOW_NECK = {"body", "clothing"}


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(PATH.read_text())


def load() -> dict:
    """The whole profile (a copy: edit freely)."""
    return copy.deepcopy(_load())


def roles() -> list[str]:
    return list(_load()["characters"]["roles"])


def role(name: str) -> dict:
    r = _load()["characters"]["roles"]
    if name not in r:
        raise KeyError(f"unknown role {name!r}: one of {', '.join(r)}")
    return copy.deepcopy(r[name])


def lod_ratios(part: str | None = None) -> list[float]:
    """Share of LOD0's triangles at each LOD: above the neck holds detail longer than below it (MetaHuman)."""
    L = _load()["characters"]["lod_ratios"]
    if part == "hair_cards":
        return list(_load()["characters"]["hair_cards"]["lod_ratios"])
    if part in ABOVE_NECK:
        return list(L["head_and_hair"])
    if part in BELOW_NECK:
        return list(L["below_neck"])
    return list(L["default"])


def triangles(role_name: str, part: str | None = None, lod: int = 0, overrides: dict | None = None) -> int:
    """Triangle budget for a role (whole character when `part` is None) at a LOD. `overrides` = {part or "total": n}
    replaces the LOD0 default (the caller's stated budget)."""
    r = role(role_name)
    key = part or "total"
    if overrides and key in overrides:
        n0 = int(overrides[key])
    elif part is None:
        n0 = r["lod0_triangles"]["default"]
    else:
        if part not in r["parts"]:
            raise KeyError(f"unknown part {part!r} for {role_name}: one of {', '.join(r['parts'])}")
        n0 = r["parts"][part]["default"]
    rs = lod_ratios(part)
    if not 0 <= lod < len(rs):
        raise IndexError(f"lod {lod} outside 0..{len(rs) - 1}")
    return int(round(n0 * rs[lod]))


def lod_triangles(role_name: str, part: str | None = None, overrides: dict | None = None) -> list[int]:
    return [triangles(role_name, part, k, overrides) for k in range(len(lod_ratios(part)))]


def sources(entry: dict) -> list[dict]:
    """The source records an entry's `src` ids name."""
    S = _load()["sources"]
    return [dict(S[s], id=s) for s in entry.get("src", [])]


def table() -> str:
    """The character profile as a text table (role | LOD0 | parts | textures)."""
    rows = []
    for n in roles():
        r = role(n)
        parts = ", ".join(f"{p} {v['default'] / 1000:g}k" if v["default"] >= 1000 else f"{p} {v['default']}"
                          for p, v in r["parts"].items())
        tex = ", ".join(f"{k} {v}" for k, v in r["textures"]["sets"].items())
        rows.append(f"{n}: {r['lod0_triangles']['default']} tris ({r['lod0_triangles']['range'][0]}-"
                    f"{r['lod0_triangles']['range'][1]}), {r['on_screen']} on screen; {parts}; maps {tex}")
    return "\n".join(rows)
