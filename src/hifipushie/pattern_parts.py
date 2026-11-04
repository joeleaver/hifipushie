"""The part inspector (fix run F2, t8 finding 3): what a FreeSewing design exports, as text an agent can declare edges from.

Why: a blind agent declaring `edges` ("pointA>pointB" along a part's seam path) had no way to see a part's point and
path names: it threw errors from inside its own design to print them (~9 calls), and couldn't tell that jaeger exports
no front / back (its front is reached through frontFacing.from). The guide pointed at repo files it can't open.

`inspect(design, measurements, options, draft)`: design = a pack design name (brian, bent, jaeger, carlton, simon,
  teagan...) or the agent's own design source; run in Node exactly like draft_own.node_draft (pattern_parts.mjs: no
  network, fs reads only, TIMEOUT) -> {"config": {measurements, optional, options, order, parts: {name: {from, after,
  hide, measurements, options}}}, "missing": [...], "parts": {name: {hidden, points, paths}}, "draft_error"?}.
`missing(source, measurements)`: the design's FULL measurement list (patternConfig: every part it drafts, through from /
  after) minus what step 3 took: draft_pattern refuses on it BEFORE drafting (a block drafted without one crashes deep
  inside FreeSewing: "Unable to draft part `simon.back` ... reading 'hide'").
`outline(path, points)`: a path's ops as point names in the order it runs (aliases at one spot joined by "=").
`run(...)` = the MCP tool body (server.pattern_parts): the text (numbers in text, C288) + an optional shape-only look of
  one part (its paths, the seam path's point names large).
Measurements for the draft: the record's step 3 when name + garment are given (else / for the rest DEFAULTS, said).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

RUNNER = Path(__file__).with_name("pattern_parts.mjs")
TIMEOUT = 60  # s
PACK_NAME = re.compile(r"[a-z][a-z0-9]*")
# an average adult man in FreeSewing's names (mm; shoulderSlope deg): only to SHOW a design's parts when no step 3 exists
DEFAULTS = {"biceps": 320.0, "chest": 1000.0, "highBust": 960.0, "hpsToBust": 260.0, "hpsToWaistBack": 470.0,
            "neck": 390.0, "shoulderToShoulder": 460.0, "shoulderSlope": 13.0, "waistToArmpit": 230.0, "waistToHips": 120.0,
            "shoulderToWrist": 640.0, "shoulderToElbow": 360.0, "wrist": 175.0, "hips": 960.0, "waist": 880.0,
            "seat": 1000.0, "waistToFloor": 1080.0, "waistToSeat": 220.0, "waistToKnee": 600.0, "waistToUpperLeg": 290.0,
            "crossSeam": 720.0, "crossSeamFront": 350.0, "knee": 400.0, "upperLeg": 600.0, "inseam": 800.0,
            "heel": 330.0, "ankle": 240.0, "head": 570.0, "hpsToWaistFront": 440.0, "bustSpan": 190.0,
            "underbust": 860.0, "bustFront": 520.0, "hpsToSeatBack": 690.0}


class InspectRefused(ValueError):
    """The design can't be inspected; the message says why."""


def source(design: str) -> str:
    """The module the runner imports: the agent's own source, or a re-export of a pack design."""
    from . import assets
    if isinstance(design, str) and PACK_NAME.fullmatch(design.strip()):
        n = design.strip()
        have = sorted(p.name for p in (assets.pack("freesewing") / "node_modules" / "@freesewing").iterdir())
        if n not in have:
            raise InspectRefused(f"no FreeSewing design {n!r} in the pack (designs: {', '.join(have)}); or pass your own "
                                 "design's source")
        return f"import {{ {n[0].upper() + n[1:]} as D }} from '@freesewing/{n}'\nexport default D\n"
    if not isinstance(design, str) or "Design" not in design:
        raise InspectRefused("design: a pack design name (brian, bent, jaeger, carlton, simon, teagan...) or your own "
                             "design's source (an ES module ending `export default new Design({...})`)")
    return design


def _scratch() -> Path:
    from . import store
    return store.HOME / "_cache" / "pattern_parts"


def inspect(design: str, measurements: dict | None = None, options: dict | None = None, draft: bool = True,
            d: Path | None = None) -> dict:
    from . import assets, draft_own as do, freesewing
    src = source(design)
    req = {"measurements": {k: float(v) for k, v in (measurements or {}).items()}, "options": dict(options or {}),
           "draft": bool(draft)}
    if isinstance(design, str) and PACK_NAME.fullmatch(design.strip()):
        req["pack"] = design.strip()  # (C362: which of its parts the package exports, to import)
    key = hashlib.sha1(json.dumps([src, req, RUNNER.read_text()], sort_keys=True).encode()).hexdigest()[:16]
    d = Path(d or _scratch() / key)
    cached = d / f"inspect_{key}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    d.mkdir(parents=True, exist_ok=True)
    pack = assets.pack("freesewing")
    (d / "design.mjs").write_text(src)
    (d / "inspect.mjs").write_bytes(RUNNER.read_bytes())
    if not (d / "node_modules").exists():
        (d / "node_modules").symlink_to(pack / "node_modules")
    perm = ["--permission", f"--allow-fs-read={d.resolve()}", f"--allow-fs-read={(pack / 'node_modules').resolve()}"]
    try:
        r = subprocess.run(do._sandbox([freesewing._node(), *perm, "inspect.mjs"]), input=json.dumps(req),
                           capture_output=True, text=True, cwd=d, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise InspectRefused(f"design.mjs: nothing after {TIMEOUT} s (a loop that never ends?)") from None
    if r.returncode != 0 or not r.stdout.strip():
        err = [x for x in r.stderr.strip().splitlines() if x.strip()]
        raise InspectRefused("design.mjs: Node failed: " + (next((x for x in err if "Error" in x), err[-1] if err else "?"))[:300])
    out = json.loads(r.stdout)
    if "error" in out:
        raise InspectRefused(do._at(src, out.get("line"), out["error"]))
    cached.write_text(json.dumps(out))
    return out


def missing(design: str, measurements: dict, d: Path | None = None) -> list:
    """The design's measurements (all it drafts) step 3 hasn't taken; [] when it has them all."""
    return list(inspect(design, measurements, None, draft=False, d=d).get("missing") or [])


def outline(path: dict, points: dict) -> list:
    """A path's ops as point names in order ('move' / 'line' / 'curve' ends; 'close' back to the start)."""
    at = {}
    for k, xy in points.items():
        if xy is not None:
            at.setdefault((round(xy[0], 1), round(xy[1], 1)), []).append(k)
    for v in at.values():  # (FreeSewing's own macro points last)
        v.sort(key=lambda k: k.startswith("__"))
    names = []
    for o in path.get("ops") or []:
        if o["type"] == "close":
            names.append("(close)")
        elif o.get("to") is None:
            names.append("(no value)")
        else:
            ks = at.get((round(o["to"][0], 1), round(o["to"][1], 1)))
            names.append("=".join([k for k in ks if not k.startswith("__")][:3] or ks[:1]) if ks else f"({o['to'][0]:.0f},{o['to'][1]:.0f})")
    return names


def _opt(k: str, o: dict) -> str:
    if "constant" in o:
        return f"{k} = {o['constant']}"
    for unit in ("pct", "deg", "mm", "count"):
        if o.get(unit) is not None:
            rng = f" [{o.get('min')}..{o.get('max')}]" if o.get("min") is not None else ""
            return f"{k} {unit} {o[unit]}{rng}"
    if o.get("bool") is not None:
        return f"{k} bool {o['bool']}"
    if o.get("list") is not None:
        return f"{k} list {o.get('dflt')} of {'/'.join(map(str, o['list']))}"
    return k


def text(name: str, res: dict, part: str = "", filled: list | None = None) -> str:
    c = res["config"]
    L = [f"design {name}: measurements it needs (every part it drafts): {', '.join(c['measurements']) or 'none'}"
         + (f"; optional: {', '.join(c['optional'])}" if c["optional"] else "")]
    if filled:
        L.append(f"  (drafted to show the parts with DEFAULT values for: {', '.join(filled)}: coordinates are only "
                 "indicative; give name + garment to draft with step 3)")
    if res.get("missing"):
        L.append(f"  not drafted: no value for {', '.join(res['missing'])}")
    if res.get("draft_error"):
        L.append(f"  the draft failed: {res['draft_error']}")
    for pn, ks in (res.get("nan") or {}).items():  # (C361, t s4-1: a crash on NaN points instead of their names)
        L.append(f"  part {pn}: points with NO value (NaN: a measurement or option it reads is missing or bad): "
                 f"{', '.join(ks[:12])}{' ...' if len(ks) > 12 else ''}")
    drafted = res.get("parts") or {}
    if not part:
        L.append("parts (draft order; HIDDEN = a base other parts are drafted from, not a piece you get; from = the part "
                 "it starts as a copy of, after = drafted after):")
        for pn in c["order"]:
            pc, dp = c["parts"].get(pn, {}), drafted.get(pn)
            head = (f"  {pn}{' HIDDEN' if pc.get('hide') else ''}: from {pc.get('from') or '-'}, after "
                    f"{', '.join(pc.get('after') or []) or '-'}")
            ex = res.get("exported")
            if ex is not None and pn not in ex:  # (C362, t s4-2: jaeger's front / back aren't exported)
                via = [f"{q}.from" for q, x in c["parts"].items() if q in ex and x.get("from") == pn] + \
                      [f"{q}.after" for q, x in c["parts"].items() if q in ex and pn in (x.get("after") or [])]
                head += (f"  [NOT EXPORTED: import an exported part and reach it as {' or '.join(via[:2])}]" if via else
                         "  [NOT EXPORTED by the package]")
            if dp:
                seam = dp["paths"].get("seam")
                head += f"; {len(dp['points'])} points, paths {', '.join(dp['paths']) or '-'}"
                if seam:
                    head += f"\n      seam runs: {' > '.join(outline(seam, dp['points']))}"
            L.append(head)
        L.append("options (default [min..max]; pct shown in %, but GIVE IT AS A FRACTION in draft_pattern's options: "
                 "4 % = 0.04): " + "; ".join(_opt(k, o) for k, o in c["options"].items()))
        L.append(f"next: pattern_parts(design, part=\"<part>\") for one part's points (x, y mm) and every path in order")
        return "\n".join(L)
    if part not in drafted:
        raise InspectRefused(f"part {part!r} not drafted (parts: {', '.join(drafted) or c['order']})")
    dp, pc = drafted[part], c["parts"].get(part, {})
    L.append(f"part {part}{' HIDDEN' if dp['hidden'] else ''}: from {pc.get('from') or '-'}, after "
             f"{', '.join(pc.get('after') or []) or '-'}; its own measurements {', '.join(pc.get('measurements') or []) or '-'};"
             f" options {', '.join(pc.get('options') or []) or '-'}")
    L.append("points (x right, y down, mm): " + "; ".join(f"{k} ({v[0]:.1f}, {v[1]:.1f})" for k, v in dp["points"].items()
                                                         if v is not None and not k.startswith("_")))
    for k, p in dp["paths"].items():
        L.append(f"path {k}{' (hidden)' if p['hidden'] else ''}: {' > '.join(outline(p, dp['points']))}")
    L.append("edges are declared along the seam path's order: \"a>b\" or \"a>via>b\" (draft_pattern declarations.edges)")
    return "\n".join(L)


def _bez(a, c1, c2, b, n=16):
    import numpy as np
    t = np.linspace(0, 1, n)[:, None]
    a, c1, c2, b = (np.asarray(v, float) for v in (a, c1, c2, b))
    return (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * b


def look(dp: dict, path: Path, size: int = 900) -> Path:
    """One part, shape only: its paths (seam thick), the seam path's point names large."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    polys = []
    for k, p in dp["paths"].items():
        pts, cur, start = [], None, None
        for o in p["ops"]:
            if o["type"] == "move":
                if len(pts) > 1:
                    polys.append((k, np.array(pts)))
                pts, cur, start = [o["to"]], o["to"], o["to"]
            elif o["type"] == "line" and o.get("to"):
                pts.append(o["to"]); cur = o["to"]
            elif o["type"] == "curve" and cur is not None:
                pts += list(_bez(cur, o["cp1"], o["cp2"], o["to"])[1:]); cur = o["to"]
            elif o["type"] == "close" and start is not None:
                pts.append(start)
        if len(pts) > 1:
            polys.append((k, np.array(pts)))
    if not polys:
        raise InspectRefused("the part has no paths to draw")
    allp = np.concatenate([q for _, q in polys])
    lo, hi = allp.min(0), allp.max(0)
    s = (size - 120) / max(float((hi - lo).max()), 1.0)
    T = lambda q: [(float((x - lo[0]) * s + 60), float((y - lo[1]) * s + 60)) for x, y in q]
    W, H = int((hi[0] - lo[0]) * s + 380), int((hi[1] - lo[1]) * s + 120)  # (room for the right-hand names)
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    for k, q in polys:
        dr.line(T(q), fill=(0, 0, 0) if k == "seam" else (150, 150, 150), width=4 if k == "seam" else 1)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for nm_ in outline(dp["paths"].get("seam", {"ops": []}), dp["points"]):
        k = nm_.split("=")[0]
        if k in dp["points"]:
            (x, y), = T([dp["points"][k]])
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(200, 30, 30))
            dr.text((x + 7, y - 26), nm_, fill=(200, 30, 30), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def run(design: str, name: str = "", garment: str = "", part: str = "", options: dict | None = None,
        look_part: bool = False) -> tuple[str | None, str]:
    """The MCP tool body: (look path or None, the text)."""
    meas, said = {}, "DEFAULTS"
    if name and garment:
        from . import draft_own_tool as dot, garment_record as gr
        meas, said = dot.measurements((gr.load(name, garment)["steps"]["3"].get("output") or {})), "step 3"
    cfg = inspect(design, meas, options, draft=False)
    need = cfg["config"]["measurements"]
    filled = [m for m in need if m not in meas and m in DEFAULTS]
    res = inspect(design, {**{m: DEFAULTS[m] for m in filled}, **meas}, options, draft=True)
    label = design.strip() if PACK_NAME.fullmatch(design.strip()) else "(your design)"
    txt = text(label, res, part, filled if filled else None)
    if said == "step 3" and filled:
        txt += f"\nstep 3 hasn't taken: {', '.join(filled)}: draft_pattern refuses until body_tape measures them by name"
    p = None
    if look_part and part:
        p = str(look(res["parts"][part], _scratch() / f"{label.strip('()').replace(' ', '_')}_{part}.png"))
        txt += f"\nlook: {p} (the part's paths, shape only; the seam path's points named; every value is in this text)"
    return p, txt
