"""Blind A/B with controls: the trios, the key, the review's score. Part of the judge (judge.py has the overview)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from . import judge
from .judge_crops import _flat, photo_crops

# ------------------------------------------------------------------ blind A/B
def ab(old_run, new_run, out, ref_run=None, head=None, only=None, context="", dry=False) -> dict:
    """Blind trios of the same crops: reference | X | Y (bin/review-ab randomises X / Y and keeps the key), the
    reference = ref_run's crop (e.g. the approved build) or, for the photo-lit face features, the photo crop. Two
    CONTROL items carry the reference itself as a candidate (once as old, once as new): the key-applied review must
    call the reference copy closer in both, else the review is refused (labels swapped, or the reviewer didn't look).
    dry: write the trios + prompt for a subagent instead of running review-ab."""
    from PIL import Image
    old_run, new_run, out = Path(old_run), Path(new_run), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    co, cn = (json.loads((r / "crops.json").read_text()) for r in (old_run, new_run))
    cr = json.loads((Path(ref_run) / "crops.json").read_text()) if ref_run else {}
    pho = photo_crops(head, out) if head else {}
    items = []
    for k in sorted(set(co) & set(cn)):
        if "file" not in co[k] or "file" not in cn[k] or (only and not any(o in k for o in only)):
            continue
        if co[k]["state"] != cn[k]["state"]:
            raise RuntimeError(f"judge ab: {k}: old and new were rendered under different states; refusing")
        ref = None
        if k in cr and "file" in cr[k]:
            if cr[k]["state"] != cn[k]["state"]:
                raise RuntimeError(f"judge ab: {k}: the reference run's render state differs; refusing")
            ref = cr[k]["file"]
        elif "-photo-" in k and f"{co[k].get('view')}__{co[k].get('feature')}" in pho:
            ref = pho[f"{co[k]['view']}__{co[k]['feature']}"]["file"]
        if ref is None:
            continue
        flat = []
        for p in (ref, co[k]["file"], cn[k]["file"]):  # flattened on one grey, the reference's size
            im = _flat(Image.open(p))
            q = out / "in" / f"{k}__{len(flat)}.png"
            q.parent.mkdir(exist_ok=True)
            im.save(q)
            flat.append(str(q))
        items.append((k, flat))
    if not items:
        raise RuntimeError("judge ab: no crop has a reference (give ref_run or head)")
    ctl = items[len(items) // 2]
    args = [f"{k}={a}:{b}:{c}" for k, (a, b, c) in items]
    # (named like crops, so the reviewer can't tell which items are controls)
    args += [f"{ctl[0]}{judge.CTL_OLD}={ctl[1][0]}:{ctl[1][0]}:{ctl[1][2]}", f"{ctl[0]}{judge.CTL_NEW}={ctl[1][0]}:{ctl[1][1]}:{ctl[1][0]}"]
    meta = {"old": str(old_run), "new": str(new_run), "ref": str(ref_run) if ref_run else f"photo:{head}",
            "items": [k for k, _ in items], "control_crop": ctl[0]}
    (out / "ab.json").write_text(json.dumps(meta, indent=1))
    if dry or not os.path.exists(judge.REVIEW_AB):
        return {**meta, "dry": True, "args": args, "prompt": _trios(out / "review", args, context)}
    cmd = [sys.executable, judge.REVIEW_AB, str(out / "review"), *args, "--context", context or "game character crops"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode == 4 or "KEY APPLIED" not in r.stdout:
        return {**meta, "dry": True, "args": args, "error": "review-ab did not run: " + r.stdout[-300:],
                "prompt": _trios(out / "review", args, context)}
    return {**meta, **score_review(out / "review")}


def _trios(rdir: Path, args: list, context: str = "") -> str:
    """review-ab's trios without its reviewer (no `claude -p`): trio_<n>.png, key.json and prompt.md for a fresh
    blind subagent, which writes its answer to review.md; then `judge score <dir>` applies the key."""
    import random
    from PIL import Image, ImageDraw
    rdir = Path(rdir)
    rdir.mkdir(parents=True, exist_ok=True)
    key, listing = {}, []
    args = random.sample(args, len(args))  # (the controls not always last)
    for n, a in enumerate(args):
        name, _, trio = a.partition("=")
        ref, old, new = trio.split(":")
        order = [("old", old), ("new", new)]
        random.shuffle(order)
        key[name] = {"X": order[0][0], "Y": order[1][0]}
        ims = [Image.open(q).convert("RGB") for q in (ref, order[0][1], order[1][1])]
        h = max(i.height for i in ims)
        ims = [i.resize((max(1, i.width * h // i.height), h)) for i in ims]
        im = Image.new("RGB", (sum(i.width for i in ims) + 24, h + 22), (30, 30, 30))
        d, x = ImageDraw.Draw(im), 0
        for lab, i in zip(("REFERENCE", "X", "Y"), ims):
            im.paste(i, (x, 22))
            d.text((x + 4, 4), lab, fill=(255, 255, 255))
            x += i.width + 12
        q = rdir / f"trio_{n}.png"
        im.save(q)
        listing.append(f"- {name}: {q}")
    (rdir / "key.json").write_text(json.dumps(key, indent=1))
    prompt = (f"You are a senior art director at a game studio comparing two candidate results against a reference. You "
              f"have no stake in either. {('What is shown: ' + context) if context else ''}\nEach image is one region: "
              "REFERENCE on the left, then candidates X and Y, same framing. Read every image with the Read tool.\n"
              + "\n".join(listing) + "\n\nFor each region: list each candidate's faults against the REFERENCE, worst "
              "first, concretely, marking each MAJOR or MINOR; describe in one line what X and what Y look like; then say "
              "which is closer to the reference. Don't praise, don't guess at causes. End with exactly one line per region "
              "\"REGION <name>: X|Y|SAME\", then \"OVERALL: X|Y|SAME\". Write your whole answer to " + str(rdir / "review.md"))
    (rdir / "prompt.md").write_text(prompt)
    return prompt


def apply_key(rdir: Path) -> dict:
    """A subagent's review.md (REGION lines) with key.json applied -> KEY APPLIED lines appended; then scored."""
    import re
    rdir = Path(rdir)
    txt = (rdir / "review.md").read_text().split("\nKEY APPLIED:")[0]
    key = json.loads((rdir / "key.json").read_text())
    lines = []
    for name, k in key.items():
        m = re.search(r"REGION\s+" + re.escape(name) + r"\s*:\s*(X|Y|SAME)", txt)
        v = m.group(1) if m else "?"
        lines.append(f"{name}: {k.get(v, 'same' if v == 'SAME' else '?').upper()}")
    (rdir / "review.md").write_text(txt + "\nKEY APPLIED:\n" + "\n".join(lines) + "\n")
    return score_review(rdir)


def score_review(rdir: Path) -> dict:
    """The key-applied review (review.md's KEY APPLIED lines), with the controls checked."""
    txt = (Path(rdir) / "review.md").read_text()
    res = {}
    for ln in txt.split("KEY APPLIED:")[-1].splitlines():
        if ":" in ln and not ln.startswith("VERDICT"):
            k, v = ln.split(":", 1)
            res[k.strip()] = v.strip().lower()
    meta = json.loads((Path(rdir).parent / "ab.json").read_text()) if (Path(rdir).parent / "ab.json").exists() else {}
    c = meta.get("control_crop")
    co = res.get(f"{c}{judge.CTL_OLD}") if c else next((v for k, v in res.items() if k.endswith(judge.CTL_OLD)), None)
    cn = res.get(f"{c}{judge.CTL_NEW}") if c else next((v for k, v in res.items() if k.endswith(judge.CTL_NEW)), None)
    ctl_ok = co == "old" and cn == "new"
    ctl_keys = {f"{c}{judge.CTL_OLD}", f"{c}{judge.CTL_NEW}"} if c else {k for k in res if k.endswith((judge.CTL_OLD, judge.CTL_NEW))}
    votes = {"old": 0, "new": 0, "same": 0}
    for k, v in res.items():
        if k not in ctl_keys and v in votes:
            votes[v] += 1
    verdict = ("NEW" if votes["new"] > votes["old"] else "OLD" if votes["old"] > votes["new"] else "TIE")
    return {"controls_ok": ctl_ok, "regions": res, "votes": votes,
            "verdict": verdict if ctl_ok else f"REFUSED (controls: {co} / {cn}; the reference copy must win both: "
                                              "labels swapped, or the reviewer didn't look)"}
