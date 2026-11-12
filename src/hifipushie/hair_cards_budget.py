"""Levers and the budget: lever matches, bend rows, segments, triangles, fit_budget, join. Part of hair cards (hair_cards.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_cards

class LeverMatchedNothing(RuntimeError):
    pass


def lever_matched(name: str, matched: int, population: int) -> int:
    """Record and print how many cards an ON lever selected; raise when it selected none of a non-empty population."""
    hair_cards.LEVER_MATCHES.setdefault(name, []).append((int(matched), int(population)))
    print(f"lever {name}: matched {int(matched)} of {int(population)} cards", flush=True)
    if hair_cards.STRICT_LEVERS and population > 0 and matched == 0:
        raise LeverMatchedNothing(f"lever {name} is on but matched 0 of {population} cards (its filter selects nothing: "
                                  f"check the class / kind keys the cards carry at this point)")
    return int(matched)


def bend_selected(c: dict) -> bool:
    return hair_cards.BEND_ROWS > 0 and (not hair_cards.BEND_CLS or c.get("cls") in hair_cards.BEND_CLS)


def _turning(c: dict, path_only: bool = False) -> float:
    """deg: the summed turning of a card's path tangent and its across axis X (the larger; path_only: the path's)."""
    out = 0.0
    for V_ in (np.diff(np.asarray(c["P"], float), axis=0),) + (() if path_only else (np.asarray(c["X"], float),)):
        if len(V_) < 2:
            continue
        V_ = V_ / np.maximum(np.linalg.norm(V_, axis=1, keepdims=True), 1e-12)
        out = max(out, float(np.degrees(np.arccos(np.clip((V_[1:] * V_[:-1]).sum(1), -1, 1))).sum()))
    return out


def _segments(c: dict, per: float) -> int:
    n = int(np.clip(np.ceil(float(c["s"][-1] - c["s"][0]) / max(per, 1e-4)), 2, 200))
    if bend_selected(c):
        nb = int(np.ceil(_turning(c, path_only=hair_cards.BEND_PATH) / hair_cards.BEND_ROWS))
        n = int(np.clip(max(n, nb if hair_cards.BEND_MAX <= 0 else min(nb, n + hair_cards.BEND_MAX)), 2, 200))
    return n


def triangles(cards: list, S: dict, segment: float | None = None) -> int:
    seg = float(segment or S["segment"])
    lam = max(float(S["wavelength"]), 0.01)
    per = seg if float(S["wave"]) <= 0 else min(seg, lam / 6)
    return int(sum(2 * _segments(c, per) for c in cards))


def fit_budget(cards: list, S: dict, budget: int) -> tuple[list, float, dict]:
    """Cards and a segment length for a triangle budget: segments lengthen first (to 3 cm, or the tier's own
    segment), then cards go one by one, the least needed first (`prio`: fly-aways and the top layers' outer cards
    before the coverage layer's centre cards, so every lock keeps its middle card longest). Returns (cards,
    segment, what was dropped)."""
    info = {"asked": int(budget)}
    seg = float(S["segment"])
    seg_max = seg * 1.5  # (stretching every card to 3 cm segments first made a hero's cards straight planks)
    keep = list(cards)
    for _ in range(40):
        n = triangles(keep, S, seg)
        if n <= budget or seg >= seg_max:
            break
        seg = min(seg_max, seg * max(1.08, min(n / budget, 2.0)))
    if triangles(keep, S, seg) > budget:
        order = sorted(range(len(keep)), key=lambda i: keep[i].get("prio", keep[i]["layer"]))
        fl_ = {**hair_cards.FIT_FLOOR, **(S.get("fit_floor") or {})}
        if any(v > 0 for v in fl_.values()):  # (round 40) a class's floor share goes first, in its own prio order: under
            # a far tier's budget the tail's cards (prio: outer layers first) all fell behind the head's (r39: LOD1-3
            # kept a fragment of Tess's tail at 3/4)
            first = []
            for cl_, sh_ in fl_.items():
                own_ = [i for i in order if keep[i].get("cls") == cl_]
                first += own_[:int(np.ceil(float(sh_) * len(own_)))]
            fs_ = set(first)
            order = sorted(first, key=lambda i: keep[i].get("prio", keep[i]["layer"])) + [i for i in order if i not in fs_]
            info["floor"] = {cl_: int(sum(1 for i in first if keep[i].get("cls") == cl_)) for cl_ in fl_}
        cost = np.cumsum([triangles([keep[i]], S, seg) for i in order])
        m = max(1, int(np.searchsorted(cost, budget, side="right")))
        kept = sorted(order[:m])
        info["dropped_cards"] = len(keep) - m
        keep = [keep[i] for i in kept]
    info["triangles"], info["segment"] = triangles(keep, S, seg), round(seg, 4)
    return keep, seg, info


def join(*meshes) -> dict:
    """Card meshes joined into one."""
    ms = [m for m in meshes if m is not None and len(m["verts"])]
    if not ms:  # nothing to join (a far tier of a short cut: no hair off the head, no baby hairs): an empty mesh
        return next(m for m in meshes if m is not None)
    out, off, nc = {}, 0, 0
    tris = []
    for m in ms:
        tris.append(m["tris"] + off)
        off += len(m["verts"])
    for k in ("verts", "uv", "normal", "tangent", "col", "along", "layer"):
        out[k] = np.concatenate([m[k] for m in ms])
    cards = []
    for m in ms:
        cards.append(m["card"] + nc)
        nc += int(m["card"].max()) + 1 if len(m["card"]) else 0
    out["card"] = np.concatenate(cards)
    out["tris"] = np.concatenate(tris)
    return out
