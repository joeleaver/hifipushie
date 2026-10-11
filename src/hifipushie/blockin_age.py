"""The AGE step of the block-in: soft-tissue age cues driven to the population's change between two ages, the GNM way.

Data: `agestats.json` (blockin3, 2026-10-10): the cues of `agecues` measured on Wikimedia Commons portraits of people
whose Wikidata entries carry a birth date (age at the photo = the photo's year - the birth year; frontal, eyes open,
mouth closed; a few hundred people 18-90), a curve per cue: b0 + b1 a + b2 a^2 + sex + smile + resolution + greyscale,
a = (age - 50) / 10. Only statistics ship (the pictures stay on /mnt/data; licences / attribution in the notes).

The step reads the cues on the model's clay (its front camera, the clay key light, MediaPipe on the render), takes the
population's CHANGE from `age_from` to `age_to` (deltas, not absolute levels: clay and photographs differ in skin and
light, and the person keeps their own lips, lids and folds), and solves the amounts of GNM levers that make that
change: `relief:` / `sculpt:` zone moves (gnm_controls: least-cost identity change, macros held) and held macros,
weighted by each cue's population residual sd, with a cost on |dc|. What GNM can't reach is reported with numbers;
the designed `shape:` ops are only offered for those (never applied silently).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

STATS = Path(__file__).with_name("agestats.json")
# Aged MASSES (Joe's plan, 2026-10-10): driven through GNM here. Aged LINES (nasolabial / marionette / under-eye
# valleys, fine lines, skin texture): the skin's age layers (normal / displacement relief), calibrated to the same
# curves: LINE_CUES are reported as targets, not solved here (a clay valley has a reader floor, see LEVERS).
MASS_CUES = ("lip_upper", "lip_lower", "philtrum", "nose_w", "jaw_ratio", "lower_ratio")
LINE_CUES = ("nl_len", "marionette", "nl_depth", "trough", "cheek_rms", "wr_forehead")
# the lids' age change goes to the EYE STEP (blockin_eyes: identity + eye-region expression for the margins and the
# fold line's height), not to identity levers here: its targets are reported (eye opening, fold line height)
EYE_CUES = ("open", "lid_tps")
CUES = MASS_CUES
# GNM levers (block-in move names) and their trial size (mm for sculpt / relief, sd for macros). 2 mm, not 1: the
# shading readers have a FLOOR on smooth clay (no valley at all -> 0): relief:marionette read 0.000 at +-1 mm on
# Garrett's clay and 0.013 / 0.019 / 0.022 at -2 / -4 / -8 mm (and GNM's -8 mm visibly carves the sulcus round the
# mouth): the reader, not GNM. Central differences across the floor understate the slope; the step re-reads after.
LINE_LEVERS = {"relief:nasolabial": -2.0, "relief:marionette": -2.0, "relief:tear_trough": -2.0}
LEVERS = {
    "lip_fullness!": 0.5, "sculpt:upper_vermilion": -1.0, "sculpt:lower_vermilion": -1.0, "philtrum!": 0.5,
    "nose_width!": 0.5, "sculpt:jowls": 2.0, "jaw_width!": 0.5,
}


def stats() -> dict:
    return json.loads(STATS.read_text())


def population_change(age_from: float, age_to: float, sex: str = "male", cues=CUES, min_z: float = 2.5) -> dict:
    """{cue: (delta, resid_sd, z)}: the curves' change between the two ages (cues whose age term is significant)."""
    S = stats()["cues"]
    out = {}
    for k in cues:
        s = S.get(k)
        if not s or abs(s.get("z_age", 0)) < min_z:
            continue
        b = s["b"]
        f = lambda A: b[1] * (A - 50) / 10 + b[2] * ((A - 50) / 10) ** 2  # noqa: E731
        out[k] = (float(f(age_to) - f(age_from)), float(s["resid_sd"]), float(s["z_age"]))
    return out


def _front(base: dict, cam: dict):
    from . import agecues, humanfit, likeness
    st = humanfit.state(base)
    mesh = likeness.model_mesh_from_state(st)
    P0 = humanfit.project(cam, st["L"])
    c = P0[:68].mean(0)
    s = 1.6 * float(np.ptp(P0[:68, 1]))
    box = (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2)
    im, _ = likeness.render(mesh, cam, box, px=900, brows=False)
    d = likeness.detect_info([im])[0]
    if d is None:
        raise RuntimeError("blockin_age: the detector found no face on the clay")
    ipd = float(np.linalg.norm(np.asarray(st["L"][68]) - np.asarray(st["L"][69]))) * 1000
    return agecues.cues(im, d["P"], ipd_mm=ipd), im


def landmark_cues(base: dict) -> dict:
    """The mass cues on the model's OWN 3D landmarks (68 + eye centres; mm on the face's front plane, x across / z
    up): exact and linear, where MediaPipe on the clay drifts 1-1.5 mm with unrelated shading (jw's note; the first
    synthetic plan on the clay detector got every lip / nose sign wrong). Definitions follow the photo readers'
    (vermilion heights at the midline, subnasale -> upper lip top, ...): their DELTAS compare, not their levels."""
    from . import humanfit
    L = np.asarray(humanfit.state(base)["L"], float) * 1000.0
    z = lambda i: L[i, 2]  # noqa: E731
    wx = lambda a, b: abs(L[a, 0] - L[b, 0])  # noqa: E731
    cheek = wx(1, 15)
    return {"lip_upper": z(51) - z(62), "lip_lower": z(66) - z(57), "philtrum": z(33) - z(51), "nose_w": wx(31, 35),
            "jaw_ratio": wx(4, 12) / cheek, "lower_ratio": wx(5, 11) / cheek,
            "open": float(np.mean([z(37) - z(41), z(38) - z(40), z(43) - z(47), z(44) - z(46)]))}


def clay_cues(base: dict, cam: dict) -> dict:
    """The cues as the step reads them: geometry on the model's landmarks (landmark_cues), lid fold and lines on its
    clay through the front camera (agecues on the render)."""
    c = dict(_front(base, cam)[0])
    c.update(landmark_cues(base))
    return c


def _with(spec: dict, moves: dict) -> dict:
    from . import blockin as bi
    sp = copy.deepcopy(spec)
    c = bi.identity(sp)
    for k, v in moves.items():
        c = c + float(v) * bi.direction(k)
    bi.set_identity(sp, c)
    return sp


def jacobian(spec: dict, cam: dict, levers: dict = None, cues=CUES) -> tuple:
    """(J [cue x lever] per unit lever, c0 cues, cost per unit |dc|): central differences on the clay read."""
    from . import blockin as bi
    levers = levers or LEVERS
    LM = {"lip_upper", "lip_lower", "philtrum", "nose_w", "jaw_ratio", "lower_ratio", "open"}
    read = (lambda b: landmark_cues(b)) if set(cues) <= LM else (lambda b: clay_cues(b, cam))  # noqa: E731
    c0 = read(spec["base"])
    J = np.zeros((len(cues), len(levers)))
    cost = np.zeros(len(levers))
    for j, (k, h) in enumerate(levers.items()):
        cp = read(_with(spec, {k: h})["base"])
        cm = read(_with(spec, {k: -h})["base"])
        for i, q in enumerate(cues):
            a, b = cp.get(q, np.nan), cm.get(q, np.nan)
            J[i, j] = (a - b) / (2 * h) if np.isfinite(a) and np.isfinite(b) else 0.0
        cost[j] = float(np.linalg.norm(bi.direction(k)))
    return J, c0, cost


def solve(J, cost, cues, change: dict, lam: float = 0.05, levers: dict = None) -> dict:
    """Amounts a (lever units) minimising sum_k ((J a - delta_k) / sd_k)^2 + lam |cost * a|^2 over the cues with a
    population change; returns {"moves", "pred" {cue: (target delta, predicted)}}."""
    levers = levers or LEVERS
    rows = [i for i, q in enumerate(cues) if q in change]
    A = np.array([J[i] / change[cues[i]][1] for i in rows])
    y = np.array([change[cues[i]][0] / change[cues[i]][1] for i in rows])
    R = np.sqrt(lam) * np.diag(cost)
    a = np.linalg.lstsq(np.r_[A, R], np.r_[y, np.zeros(len(cost))], rcond=None)[0]
    names = list(levers)
    return {"moves": {names[j]: round(float(a[j]), 3) for j in range(len(names)) if abs(a[j]) > 1e-3},
            "pred": {cues[i]: (round(change[cues[i]][0], 4), round(float(J[i] @ a), 4)) for i in rows}}


def plan(spec: dict, cam: dict, age_from: float, age_to: float, sex: str = "male", lam: float = 0.05,
         levers: dict | None = None) -> dict:
    """The age step without saving: the population's mass change between the ages, the levers' Jacobian on this
    head's clay, the solved moves, and the line targets for the skin. {"moves", "pred", "lines", "J", "c0", "cost"}."""
    levers = levers or LEVERS
    change = population_change(age_from, age_to, sex, cues=MASS_CUES)
    J, c0, cost = jacobian(spec, cam, levers, MASS_CUES)
    sol = solve(J, cost, MASS_CUES, change, lam=lam, levers=levers)
    lines = population_change(age_from, age_to, sex, cues=LINE_CUES)
    eyes = population_change(age_from, age_to, sex, cues=EYE_CUES)
    return {**sol, "lines": {k: round(v[0], 4) for k, v in lines.items()},
            "eyes": {k: round(v[0], 4) for k, v in eyes.items()}, "J": J.tolist(), "c0": c0,
            "cost": [round(float(x), 2) for x in cost], "change": {k: round(v[0], 4) for k, v in change.items()}}


def check(spec: dict, cam: dict, res: dict) -> dict:
    """Re-read the clay after the solved moves: {cue: (target delta, predicted, measured)} (the Jacobian is linear;
    the detector on clay is not)."""
    c1 = landmark_cues(_with(spec, res["moves"])["base"])
    return {k: (t, p, round(float(c1[k] - res["c0"][k]), 4)) for k, (t, p) in res["pred"].items()}


def step(name: str, age_from: float, age_to: float, out: str | None = None, sex: str | None = None,
         lam: float = 0.05) -> dict:
    """A block-in step: the solved GNM moves applied with blockin.step (logged; seen names the ages), plus the plan
    and the re-read. The skin's line targets are in the report (not applied)."""
    from . import blockin as bi, store
    sp = store.load(name)
    cam = bi._refs(name)["cameras"][0]
    sex = sex or ("male" if float(sp["base"].get("body", {}).get("sex", 1.0)) >= 0.5 else "female")
    res = plan(sp, cam, age_from, age_to, sex, lam=lam)
    rep = bi.step(name, res["moves"], out=out, seen=f"age {age_from:g} -> {age_to:g}: population mass change "
                  + ", ".join(f"{k} {v:+.3g}" for k, v in res["change"].items()),
                  why="blockin_age: GNM levers solved on the clay's age cues (Wikimedia age curves)")
    return {"plan": res, "check": check(sp, cam, res), "step": rep}
