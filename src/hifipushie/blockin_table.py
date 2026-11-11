"""The target table: rows per measure, the feature table, passes, the table's text and delta. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import blockin
from . import blockin_models
from .blockin_expression import _per_view

# ---------------------------------------------------------------- the target table
def _spec_hash(name: str) -> str:
    from . import store
    sp = store.load(name)
    rj = blockin_models._refs(name)
    return hashlib.sha1(json.dumps([sp["base"], rj["cameras"]] + ([rj["expressions"]] if any(rj.get("expressions") or []) else []),
                               sort_keys=True).encode()).hexdigest()[:16]


def rows(name: str) -> list:
    """Every likeness checklist row (photo vs model through the model's fitted cameras): [{id, stage, view, unit,
    photo, model, tol}] with numbers on both sides; cached in the model's directory by its base + cameras."""
    from . import store
    from . import likeness_compare, likeness_render
    h = _spec_hash(name)
    p = store.HOME / name / "blockin_rows.json"
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("hash") == h:
            return d["rows"]
    out = []
    base, rj = store.load(name)["base"], blockin_models._refs(name)
    meshes = None
    if any(rj.get("expressions") or []):   # each picture against the head with ITS expression
        mv = _per_view(base, rj, range(len(rj["views"])), likeness_render.model_mesh)
        meshes = [mv[i] for i in range(len(rj["views"]))]
    for r in likeness_compare.compare(name, base, mesh=meshes)["rows"]:
        a, b = r.get("photo"), r.get("model")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not np.isfinite(a) or not np.isfinite(b):
            continue
        out.append({"id": r["id"], "stage": r.get("stage"), "view": r.get("view", r.get("vi")), "vi": str(r.get("vi")),
                    "unit": r.get("unit"), "photo": round(float(a), 3), "model": round(float(b), 3),
                    "tol": round(float(r.get("tol") or 0), 3)})
    p.write_text(json.dumps({"hash": h, "rows": out}, indent=1))
    return out


def _row(r: dict) -> dict:
    d = r["model"] - r["photo"]
    row = {k: r[k] for k in ("id", "view", "unit", "photo", "model", "tol")}
    row.update({"diff": round(d, 3), "ok": bool(r["tol"] and abs(d) <= r["tol"])})
    if r["id"] in blockin.FLAGGED:
        row["flag"] = blockin.FLAGGED[r["id"]]
    elif r["unit"] == "%" and r["model"] == 0.0 and r["photo"] != 0.0:
        # (radix / dorsum width, nasolabial fold, under-eye read exactly 0.00 on every clay: no reading there)
        row["flag"] = "the clay reader returned nothing (0.00 exactly): shown, not counted"
    return row


def table(name: str) -> dict:
    """{group: [{id, view, unit, photo, model, diff, tol, ok, flag?}]}: the five target groups (likeness items)."""
    R = rows(name)
    out = {}
    for g, ids in blockin.GROUPS.items():
        out[g] = [_row(r) for i in ids for r in sorted((r for r in R if r["id"] == i), key=lambda r: r["vi"])]
    return out


def feature_table(name: str, feature: str) -> dict:
    """The feature's own checklist rows (every likeness item of its stages), as one table group."""
    st, extra = blockin.FEATURES[feature]["stages"], blockin.FEATURES[feature].get("items", ())
    return {feature: [_row(r) for r in rows(name) if r["stage"] in st or r["id"] in extra]}


def passes(t: dict) -> dict:
    return {g: f"{sum(r['ok'] for r in rows if 'flag' not in r)}/{sum('flag' not in r for r in rows)}" for g, rows in t.items()}


def table_text(t: dict) -> str:
    s = []
    for g, rows in t.items():
        s.append(f"== {g} {passes(t)[g]}")
        for r in rows:
            mark = "flag" if "flag" in r else ("ok" if r["ok"] else "MISS")
            pct = f" ({100 * r['diff'] / r['photo']:+.0f}%)" if r["unit"] == "mm" and r["photo"] else ""
            s.append(f"  {r['id']:20s} {str(r['view']):13s} photo {r['photo']:8.2f}  model {r['model']:8.2f}  "
                     f"diff {r['diff']:+7.2f}{pct} tol {r['tol']:.2f} {r['unit'] or ''} {mark}")
    fl = {r["id"]: r["flag"] for rows in t.values() for r in rows if "flag" in r}
    if fl:
        s.append("flag = shown, not counted: " + "; ".join(f"{i}: {fl[i]}" for i in sorted(fl)))
    mm = [r["diff"] / r["photo"] for rows in t.values() for r in rows if r["unit"] == "mm" and r["photo"] > 20 and "flag" not in r]
    if len(mm) >= 5 and (np.median(mm) < -0.03 or np.median(mm) > 0.03) and np.mean(np.sign(mm) == np.sign(np.median(mm))) > 0.75:
        s.append(f"SIZE: the lengths over 20 mm are {100 * np.median(mm):+.0f}% (median) and mostly the same sign: a UNIFORM "
                 "scale, not shape. Check the camera (block_in_step cameras=[...]) and head_scale before identity steps.")
    return "\n".join(s)


def table_delta(t0: dict, t1: dict) -> list:
    out = []
    for g, rows in t1.items():
        old = {(r["id"], str(r["view"])): r for r in t0.get(g, [])}
        for r in rows:
            o = old.get((r["id"], str(r["view"])))
            if o is None:
                continue
            ch = "" if o["ok"] == r["ok"] else (" NOW OK" if r["ok"] else " WENT OUT")
            if ch and abs(r["diff"] - o["diff"]) < 0.15 * max(r["tol"], 1e-9):   # (a hair across the line: noise)
                ch += " (at the edge: the change is under 0.15 tol)"
            if ch or abs(r["diff"] - o["diff"]) > 0.5 * max(r["tol"], 1e-9):
                out.append(f"{r['id']} {r['view']}: {o['diff']:+.2f} -> {r['diff']:+.2f} (tol {r['tol']:.2f}){ch}"
                           + (" [flag]" if "flag" in r else ""))
    return out
