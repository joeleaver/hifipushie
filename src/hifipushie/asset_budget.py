"""Running Blender for the export, and its budgets: the lash cap, export_gb, budget_check, hair_budget, margins. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import asset
from . import render, validated

def _blender(job: dict, timeout: float = 600):
    with tempfile.TemporaryDirectory(prefix="hifipushie-asset-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps(job))
        from . import resources  # killed with the job if its tool call is cancelled
        r = resources.run([render.BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                           "--python", str(asset.SCRIPT), "--", str(p)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")


def lash_cap(rb: dict, report: dict) -> int | None:
    """Triangles the lashes may take under the role's eyes_mouth_lashes budget: the budget less what the eyes, teeth,
    tongue and brows already take (report). None without that budget."""
    b = (rb.get("parts") or {}).get("eyes_mouth_lashes")
    if not b:
        return None
    return max(0, int(b["default"]) - sum(int(report[pn].get("triangles", 0)) for pn in asset.EML_PARTS if pn in report))


def _selftest_hair_budget():
    """Known answers: 26040 drawn with back faces = 13020 card faces + the cap; over the range max is a FAIL."""
    rep = {"hair": {"triangles": 26040, "cards": True, "back_faces": True, "vertices": 16115,
                    "layers": {"cap": [0, 1040], "layer0": [1040, 25000]}}}
    h = hair_budget(asset._ROLE_T, rep)
    assert h == {"drawn": 26040, "card_faces": 13540, "vertices": 16115, "default": 25000, "max": 50000}, h
    one = {"hair": {**rep["hair"], "back_faces": False}}
    assert hair_budget(asset._ROLE_T, one)["card_faces"] == 26040
    assert hair_budget(asset._ROLE_T, {"body": {"triangles": 5}}) is None


def _selftest_budget_check():
    rep = {"hair": {"triangles": 52000, "cards": True, "back_faces": True, "vertices": 30000,
                    "layers": {"cap": [0, 2000], "layer0": [2000, 50000]}}, "hat": {"triangles": 900}}
    g = budget_check(asset._ROLE_T, rep, {})
    assert g["parts"]["hair_cards"] == [27000, 25000] and g["fail"] and g["parts"]["accessories"] == [900, None], g
    assert g["total"] == [27900, 100000]
    ok = budget_check(asset._ROLE_T, {"hair": {**rep["hair"], "triangles": 40000}}, {})
    assert not ok["fail"] and any(ln.startswith("budget: hair_cards drawn 40000") for ln in ok["lines"]), ok


def export_gb(spec: dict, name: str | None = None) -> float:
    """The memory an export declares to resources.heavy: the measured estimate for export_asset, and for a human
    character (a spec with base, skin or hair) at least resources.EXPORT_HUMAN_GB (24 GB: v7e was OOM-killed at less)."""
    from . import resources
    gb = resources.estimate("export_asset", name)
    if any(k in spec for k in ("base", "skin", "hair")):
        gb = max(gb, resources.EXPORT_HUMAN_GB)
    return float(gb)


@validated.known_answer(_selftest_budget_check)
def budget_check(rb: dict, report: dict, spec: dict) -> dict:
    """LOD0 triangles by budget part (budgets.json's parts: head, body, clothing, hair_cards, eyes_mouth_lashes,
    accessories) against the role's defaults: {"parts": {part: [count, budget]}, "total": [count, budget], "lines"}."""
    skin_pn = (spec.get("skin") or {}).get("part", "body")
    have: dict = {}
    for pn, r in report.items():
        n = int(r.get("triangles", 0))
        if pn == skin_pn and r.get("meshes"):
            have["head"] = have.get("head", 0) + int(r["meshes"].get("head", {}).get("triangles", 0))
            have["body"] = have.get("body", 0) + int(r["meshes"].get("body", {}).get("triangles", 0))
            continue
        k = ("body" if pn == skin_pn else "clothing" if r.get("cloth") else "hair_cards" if (r.get("curves") or r.get("cards"))
             else "eyes_mouth_lashes" if (r.get("lashes") or pn in asset.EML_PARTS) else "accessories")
        have[k] = have.get(k, 0) + n
    bp = rb["parts"]
    hair = hair_budget(rb, report)
    if hair:  # the role default counts card FACES (one side): engine-proof back faces reuse the same vertices
        have["hair_cards"] = hair["card_faces"]
    parts = {k: [have.get(k, 0), int(bp[k]["default"]) if k in bp else None] for k in sorted(set(have) | set(bp))}
    tot = [sum(have.values()), int(rb["lod0_triangles"]["default"])]
    lines, fail = [], []
    for k, (n, b) in parts.items():
        over = b is not None and n > b
        lines.append(("WARNING budget: " if over else "budget: ") + f"{k} {n} of {b}" + (" (OVER)" if over else ""))
    if hair:
        ln = (f"hair_cards drawn {hair['drawn']} triangles (back faces included) of the role's range max {hair['max']}; "
              f"card faces {hair['card_faces']} of {hair['default']}; vertices {hair['vertices']}")
        if hair["max"] is not None and hair["drawn"] > hair["max"]:
            fail.append(ln)
            lines.append("FAIL budget: " + ln)
        else:
            lines.append("budget: " + ln)
    lines.append(("WARNING budget: " if tot[0] > tot[1] else "budget: ") + f"total {tot[0]} of {tot[1]} (LOD0)")
    return {"parts": parts, "total": tot, "lines": lines, "hair": hair, "fail": fail}


@validated.known_answer(_selftest_hair_budget)
def hair_budget(rb: dict, report: dict) -> dict | None:
    """(hair-budget rule, coordinator 2026-10-19; codified) LOD0 hair cards against the role: card FACES (one side)
    against budgets.json's hair_cards default; DRAWN triangles (the index count, engine-proof back faces included)
    against the role's range MAX (hero 50k, main_npc 20k, secondary_npc 8k, crowd 1.5k), a hard limit; vertices
    reported. Counting back faces against the default halved Tess's cards and lowered her crown (round 39). None
    without card hair in the report."""
    rows = [r for r in report.values() if r.get("cards")]
    if not rows:
        return None
    drawn = sum(int(r.get("triangles", 0)) for r in rows)
    back = sum(sum(int(v[1]) for k, v in (r.get("layers") or {}).items() if k != "cap") // 2
               for r in rows if r.get("back_faces"))
    b = (rb.get("parts") or {}).get("hair_cards") or {}
    rng = b.get("range") or [None, None]
    return {"drawn": drawn, "card_faces": drawn - back, "vertices": sum(int(r.get("vertices", 0)) for r in rows),
            "default": int(b["default"]) if "default" in b else None, "max": int(rng[1]) if rng[1] is not None else None}


def game(glb: Path, timeout: float = 900, **job) -> str:
    """The game-like EEVEE render of an exported GLB (blender_game.py): job keys frames / poses / size / hide
    (asset_export.preview) or shots / anim / out (the engine-stage checks). Returns Blender's log."""
    with tempfile.TemporaryDirectory(prefix="hifipushie-game-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps({"glb": str(glb), **{k: v for k, v in job.items() if v is not None}}))
        from . import resources
        r = resources.run([render.BLENDER, "-b", *render._threads(), "--factory-startup", "--python-exit-code", "1",
                           "--python", str(asset.GAME_SCRIPT), "--", str(p)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"blender failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
        return r.stdout


def margin_px(texture: int) -> int:
    """Gap between UV islands in texels: enough for bilinear filtering and the first mips (dilation fills it)."""
    return max(2, texture // 512)


def min_part(triangles: int) -> int:
    """No part gets fewer triangles than this (or all it has): eyes, teeth, pots stay round."""
    return max(300, triangles // 100)
