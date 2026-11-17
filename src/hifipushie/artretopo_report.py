"""Artist retopo: the run's report (the blind-run kit's required output, docs/blind/artist_retopo.md).

report/ holds: final.glb, rigged.glb, rom_sheet.jpg, close_rom.jpg (+ close_mouth.jpg), final_cmp.jpg, wire_sheet.jpg,
rom.json, press.json, bake.json, cage_check.json, input_check.json, joints.json, props.json (if any), every
cage_v<N>.py, decisions.md (the artist's own log) and report.md (numbers + the file list)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .artretopo_run import folder

FILES = ("final.glb", "rigged.glb", "rom_sheet.jpg", "close_rom.jpg", "close_mouth.jpg", "final_cmp.jpg", "wire_sheet.jpg",
         "rom.json", "rom_final.txt", "press.json", "bake.json", "cage_check.json", "input_check.json", "joints.json",
         "props.json", "cage.py")
NEED = ("final.glb", "rigged.glb", "rom_sheet.jpg", "close_rom.jpg", "final_cmp.jpg", "rom.json")


def write(name: str, decisions: str, out_dir: str | None = None) -> str:
    d = folder(name); out = Path(out_dir) if out_dir else d / "report"
    miss = [f for f in NEED if not (d / f).exists()]
    if miss:
        raise ValueError(f"not finished: {miss} missing (press, bake and rig first)")
    if len(decisions.strip()) < 200:
        raise ValueError("decisions: write the log (what you read off the sculpt, every loop decision and why, what "
                         "you changed after each look, what is still wrong): a few paragraphs at least")
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in FILES + tuple(p.name for p in sorted(d.glob("cage_v*.py"))):
        if (d / f).exists():
            shutil.copy(d / f, out / f); copied.append(f)
    (out / "decisions.md").write_text(decisions.strip() + "\n")
    J = lambda f: json.loads((d / f).read_text()) if (d / f).exists() else {}
    rom, press, bake, cage = J("rom.json"), J("press.json"), J("bake.json"), J("cage_check.json")
    L = [f"# {d.name}: artist retopo report", "",
         f"- cage: {cage.get('quads')} quads, {cage.get('vertices')} verts, version {cage.get('version')} "
         f"({len(list(d.glob('cage_v*.py')))} versions), pinned {cage.get('pinned')}, seam edges {cage.get('seam_edges')}",
         f"- low: {press.get('low_faces')} quads, folds {press.get('folded')}, LOD1 {press.get('lod1_faces')} quads",
         f"- bake: invented verts {bake.get('invented_verts')}, thin verts {bake.get('thin_verts')}, props {bake.get('props')}",
         f"- rig: {rom.get('rig', {}).get('bones')} bones, helpers {rom.get('rig', {}).get('helpers')}, jaw verts "
         f"{rom.get('rig', {}).get('jaw_verts')}, props on {rom.get('rig', {}).get('props')}", "",
         "| pose | folds | squashed < 0.5 | stretched > 1.8 | min | max |", "|---|---|---|---|---|---|"]
    for k, v in rom.get("poses", {}).items():
        L.append(f"| {k} | {v['folds']} | {v['squashed']} | {v['stretched']} | {v['min_ratio']} | {v['max_ratio']} |")
    L += ["", "Files: " + ", ".join(copied + ["decisions.md"])]
    (out / "report.md").write_text("\n".join(L) + "\n")
    return f"report written to {out}:\n" + "\n".join(L)
