"""Garment step 7 as a tool (garment_details; T10): step 1's inventory -> details placed on the pattern -> carried onto the
latest build (and the hung garment when there is one) -> the record's step 7 (+ 7a: the built, DETAILED garment).

Validated against step 1: every detail with build full / simplified must be placed (a FAIL row names each one missing or
with another count than the inventory's); a detail not in the inventory, or one it omits, is refused by name. A spec
fault is refused by name with nothing written. The look is for SHAPE (C288): the build with its details beside the
reference + the flat pieces with the details drawn on them; the numbers (count, positions in pattern terms, sizes) are
in the text. Details never enter the sim: details.pkl keeps the anchors, and they are carried onto the hung mesh.
`presim_step7` is chain_presim's hook: step 7 is done only when every inventoried detail is placed (or there are none).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import garment_details as gd
from . import garment_record as gr

BUILT = ("full", "simplified")


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


def inventory(rec: dict) -> tuple:
    """(buildable details {name: entry}, omitted {name: entry}, step-0 cloths)."""
    s1 = rec["steps"]["1"]
    if s1.get("status") not in ("done", "passed"):
        raise gd.DetailRefused("step 1 (parts) isn't done: garment_plan step='parts' first")
    det = (s1.get("output") or {}).get("details") or {}
    cloths = ((rec["steps"]["0"].get("output") or {}).get("cloth") or {})
    return ({n: x for n, x in det.items() if x.get("build") in BUILT},
            {n: x for n, x in det.items() if x.get("build") not in BUILT}, cloths)


def declared_edges(rec: dict) -> dict:
    d = (rec["steps"]["4"].get("output") or {}).get("dir")
    p = Path(d) / "declarations.json" if d else None
    return (json.loads(p.read_text()).get("edges") or {}) if p and p.exists() else {}


def place_all(fl: gd.Flat, details: dict, inv: dict, omitted: dict, cloths: dict) -> tuple:
    """({name: placed}, refusals [str], gate rows). Refusals mean nothing is written."""
    placed, bad = {}, []
    for n, spec in details.items():
        if n in omitted:
            bad.append(f"{n}: the inventory omits it (build {omitted[n].get('build')!r}: {omitted[n].get('why', '')}); "
                       "change step 1 to build it")
            continue
        if n not in inv:
            bad.append(f"{n}: not in step 1's details ({', '.join(inv) or 'none'}): inventory it first (garment_plan step='parts')")
            continue
        cl = cloths.get(inv[n].get("cloth")) or {}
        try:
            placed[n] = gd.place(fl, n, spec, inv[n], cl)
        except gd.DetailRefused as e:
            bad.append(str(e))
            continue
        c = next((s.get("colour") for s in (spec if isinstance(spec, list) else [spec]) if isinstance(s, dict) and s.get("colour")),
                 None) or cl.get("colour")
        if not (isinstance(c, (list, tuple)) and len(c) >= 3):
            bad.append(f"{n}: colour [r, g, b] (no step-0 cloth colour to take it from)")
            continue
        placed[n]["colour"] = [int(v) for v in c[:3]]
        placed[n]["cloth"] = inv[n].get("cloth")
    rows = []
    for n, x in inv.items():
        want = x.get("count")
        if n not in placed:
            rows.append({"id": n, "status": "FAIL", "value": "not placed", "target": f"{want or 'all'} placed",
                         "why": "every inventoried detail with build full / simplified is placed", "back_to": "7"})
        else:
            got = placed[n]["count"]
            ok = want is None or got == want
            rows.append({"id": n, "status": "PASS" if ok else "FAIL", "value": f"{got} placed", "target": f"{want} (step 1)" if want else "any",
                         **({} if ok else {"why": f"{got} placed, the inventory counts {want}: fix the placement or step 1",
                                           "back_to": "7"})})
    return placed, bad, rows


def _meshes(placed: dict, X, M, N) -> dict:
    return {n: dict(zip(("V", "F"), gd.carry(p["instances"], X, M, N)), colour=p["colour"], cloth=p.get("cloth"))
            for n, p in placed.items()}


def flat_look(fl: gd.Flat, placed: dict, out: Path, px: int = 1400) -> Path:
    """The pieces that carry details, flat, side by side, with the details drawn on them (shape only)."""
    ps = sorted({p for x in placed.values() for p in x["pieces"]}, key=fl.names.index)
    boxes = []
    for p in ps:
        uv = fl.uv[np.unique(fl.F[fl.faces(p)])]
        boxes.append((uv.min(0), uv.max(0)))
    W = sum(b[1][0] - b[0][0] for b in boxes) + 0.05 * (len(ps) + 1)
    H = max(b[1][1] - b[0][1] for b in boxes) + 0.12
    s = px / max(W, H)
    im = Image.new("RGB", (int(W * s), int(H * s)), "white")
    dr = ImageDraw.Draw(im)
    x0 = 0.05
    for p, (lo, hi) in zip(ps, boxes):
        f = lambda q, lo=lo, x0=x0: [((u - lo[0] + x0) * s, (hi[1] - v + 0.07) * s) for u, v in np.atleast_2d(q)]
        for L in fl.loops(p):
            dr.line(f(fl.uv[L + L[:1]]), fill=(90, 90, 90), width=2)
        dr.text(f([[lo[0], hi[1] + 0.04]])[0], p, fill=(0, 0, 0))
        for n, x in placed.items():
            col = tuple(x["colour"])
            for it in x["instances"]:
                if it["piece"] != p:
                    continue
                if it["kind"] == "point":
                    (cx, cy), r = f(it["uv"])[0], max(2, it["size"] * s / 2)
                    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(0, 0, 0))
                else:
                    dr.line(f(it["C"]), fill=col, width=max(2, int(it["width"] * s)))
        x0 += hi[0] - lo[0] + 0.05
    im.save(out)
    return out


def render_look(r: dict, meshes: dict, out: str, size: int = 800) -> list:
    from . import chain_garment as cg, cloth, resources
    X = np.asarray(r["X"], float)
    parts = [{"name": "body", "V": r["bV"], "F": r["bT"], "color": "#c4bcb4"},
             {"name": "garment", "V": X, "F": cg.joined_faces(X, r["M"], r["bV"], r["bT"]), "color": "#a9c4e6"}]
    parts += [{"name": n, "V": m["V"], "F": m["F"], "color": _hex(m["colour"])} for n, m in meshes.items()]
    lo, hi = X.min(0), X.max(0)
    box = [[lo[0] - 0.05, lo[1] - 0.05, lo[2] - 0.03], [hi[0] + 0.05, hi[1] + 0.05, float(np.asarray(r["bV"])[:, 2].max()) + 0.02]]
    res = []
    with resources.heavy(f"look details {Path(out).name}", gb=3.0, gpu=True, log=lambda *_: None):
        for nm, dv in (("front", [0, -1, 0.05]), ("three", [-0.6, -0.8, 0.1])):
            res.append(str(cloth.render(parts, f"{out}_{nm}", views=[{"name": nm, "dir": dv}], resolution=size, box=box)[0]))
    return res


def beside(ref: str | None, paths: list, out: Path) -> Path:
    ims = [Image.open(p).convert("RGB") for p in paths]
    h = ims[0].size[1]
    if ref and Path(ref).exists():
        rr = Image.open(ref).convert("RGB")
        ims = [rr.resize((int(rr.size[0] * h / rr.size[1]), h))] + ims
    sh = Image.new("RGB", (sum(i.size[0] for i in ims) + 6 * (len(ims) - 1), h), "white")
    x = 0
    for i in ims:
        sh.paste(i.resize((int(i.size[0] * h / i.size[1]), h)), (x, 0))
        x += i.size[0] + 6
    sh.save(out)
    return out


def _ref(rec: dict) -> str | None:
    v = (rec["steps"]["0"].get("output") or {}).get("views") or []
    return v[0].get("image") if v else None


def text_lines(placed: dict, rows: list) -> list:
    L = []
    for n, x in placed.items():
        it = x["instances"][0]
        size = (f"{it['size'] * 1000:.0f} mm {it['shape']}, {it['thick'] * 1000:.1f} thick" if it["kind"] == "point"
                else f"{it['width'] * 1000:.1f} mm wide, {it['thick'] * 1000:.1f} thick")
        L.append(f"  {n}: {x['count']} on {', '.join(x['pieces'])}; {size}; colour {x['colour']}")
        L += [f"    {w}"[:400] for w in x["where"]]
    L += [f"  {r['status']} {r['id']}: {r['value']} (target {r['target']})" + (f" | {r['why']}" if r.get("why") else "")
          for r in rows if r["status"] != "PASS" or r["id"] not in placed]
    return L


def run(name: str, garment: str, details: dict, wear: str = "open", look: bool = True) -> tuple:
    """The tool body: (look paths, text)."""
    from . import chain_garment as cg, chain_presim as cp
    if not isinstance(details, dict) or not details:
        raise gd.DetailRefused("details: {name from step 1: spec | [specs]}: guide(topic=\"garment_details\")")
    rec = gr.load(name, garment)
    inv, omitted, cloths = inventory(rec)
    d = cg.job_dir(name, garment, wear)
    if not (d / "built.pkl").exists():
        raise gd.DetailRefused(f"no build of {garment} ({wear}) to place details on: chain_garment first")
    r = gd.load_result(d / "built.pkl")
    fl = gd.Flat(r["M"], declared_edges(rec))
    placed, bad, rows = place_all(fl, details, inv, omitted, cloths)
    if bad:
        return [], ("garment_details REFUSED (nothing written):\n  " + "\n  ".join(bad[:20]) +
                    "\nnext: fix those details (step 1's names; the pattern's points and edges) and call again")
    built = _meshes(placed, r["X"], r["M"], gd.vnormals(r["X"], r["M"], r["bV"], r["bT"]))
    hung, hnote = None, "no hung garment yet: the hang carries them (re-run this call after it)"
    if (d / "final.pkl").exists():
        h = gd.load_result(d / "final.pkl")
        if len(h["X"]) == len(r["X"]):
            hung, hnote = _meshes(placed, h["X"], h["M"], gd.vnormals(h["X"], h["M"], h["bV"], h["bT"])), "carried onto the hung garment"
        else:
            hnote = f"the hung mesh has {len(h['X'])} vertices, the build {len(r['X'])}: not carried (a tool fault; report it)"
    anchors = {n: {k: v for k, v in p.items()} for n, p in placed.items()}
    pickle.dump({"anchors": anchors, "built": built, "hung": hung}, open(d / "details.pkl", "wb"))
    verdict = "PASS" if all(x["status"] == "PASS" for x in rows) else "FAIL"
    looks = []
    if look:
        ld = gr.look_dir(name, garment)
        looks.append(str(flat_look(fl, placed, ld / "step7_flat.png")))
        shots = render_look(r, built, str(d / "details"))
        looks.insert(0, str(beside(_ref(rec), shots, ld / "step7_built.png")))
    out = {"job": str(d), "wear": wear, "build": (cg.status(d) or {}).get("build_id"), "built": str(d / "built.pkl"),
           "details_file": str(d / "details.pkl"), "hung": bool(hung),
           "details": {n: {"count": p["count"], "pieces": p["pieces"], "where": p["where"]} for n, p in placed.items()}}
    msg = gr._try(gr.write, name, garment, "7", "done" if verdict == "PASS" else "failed", output=out,
                  gate={"verdict": verdict, "rows": rows}, look=looks, back_to=None if verdict == "PASS" else "7",
                  by="garment_details")
    if verdict == "PASS" and not msg:
        msg = cp.write_7a(name, garment, out, cg.status(d) or {}, look=looks[:1] or None)
    lines = [f"{name}:{garment} garment_details (step 7) on the {wear} build: {verdict}; {sum(p['count'] for p in placed.values())} "
             f"details in {len(placed)} groups; {hnote}"] + text_lines(placed, rows)
    lines.append(f"  details mesh: {d / 'details.pkl'} (anchors + meshes per detail, separate from the cloth)")
    lines.append(f"  record: {msg}" if msg else "  record: step 7 written" + (" + 7a (the detailed build)" if verdict == "PASS" else ""))
    nxt = ("look at the build with its details beside the reference (shape only); then the pre-sim approval (7a)"
           if verdict == "PASS" else "place every FAIL row's detail (or fix step 1) and call again")
    return looks, "\n".join(lines) + f"\nnext: {nxt}"


def presim_step7(model: str, garment: str, out: dict) -> tuple:
    """chain_presim's hook after a structure pass: (record message, may 7a be written). Step 7 is done only when every
    inventoried detail is placed on THIS build, or the inventory has none."""
    rec = gr.load(model, garment)
    try:
        inv = inventory(rec)[0]
    except gd.DetailRefused:
        inv = {}
    if not inv:
        return gr._try(gr.write, model, garment, "7", "done", by="chain_garment",
                       output=dict(out, details={}, note="the inventory has no details to build")), True
    s7 = rec["steps"].get("7") or {}
    o7 = s7.get("output") or {}
    if s7.get("status") == "done" and o7.get("build") == out.get("build") and set(o7.get("details") or {}) >= set(inv):
        return gr._try(gr.write, model, garment, "7", "done", by="garment_details", output=o7, gate=s7.get("gate"),
                       look=s7.get("look")), True
    return gr._try(gr.write, model, garment, "7", "todo", by="chain_garment",
                   output=dict(out, details={}, note=f"{len(inv)} inventoried details to place ({', '.join(inv)}): "
                               f"call_tool(\"garment_details\", {{name, garment, details}})")), False
