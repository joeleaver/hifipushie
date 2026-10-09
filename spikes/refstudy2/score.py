"""score.py: several blind readers' six-view reads of one head against Joe's read of Garrett, descriptor by descriptor.
For each descriptor: the share of (reader, view) pairs that picked it, over the views that can show it (confidence
weighted: clear 1, likely 0.6, hint 0.3). WANT = Joe's words first ("chunky, handsome, square jaw, cleft chin, cute
nose"), then what the reference reader saw that doesn't contradict them; AVOID = their opposites and what the MAP head
was read as (soft, young). score = sum(WANT shares x weight) - sum(AVOID shares x weight).
  run.sh score.py <model> <tag> [<model> <tag> ...]     (tag = the prefix: readers are <tag>_r1, _r2, ...)"""
import sys

from hifipushie import likeness_read as lr

WANT = {"build_chunky": 2, "jaw_square": 2, "chin_cleft": 2, "nose_snub": 2,            # Joe's
        "chin_strong": 1, "chin_broad": 1, "brow_heavy": 1, "eyes_deep": 1, "eyes_hooded": 1, "face_square": 1, "overall_rugged": 1}
AVOID = {"jaw_soft": 2, "chin_weak": 2, "brow_flat": 1, "overall_boyish": 1, "build_lean": 1, "nose_aquiline": 1,
         "chin_pointed": 1, "jaw_narrow": 1, "face_round": 0.5, "cheeks_full": 0.5, "nose_bulbous": 0.5, "build_heavy": 0.5}


def shares(name, tags):
    by = {d["id"]: d for d in lr.descriptors()}
    reads = lr.load(name)["reads"]
    out = {}
    for k, d in by.items():
        s = n = 0.0
        for t in tags:
            for v, rd in reads[t]["views"].items():
                if not lr.judgeable(d, v):
                    continue
                n += 1
                e = rd["descriptors"].get(k)
                if e:
                    s += lr.CONF.get(e.get("confidence", "likely"), 0.6)
        out[k] = (s / n if n else 0.0)
    return out


def total(sh):
    return sum(sh.get(k, 0) * w for k, w in WANT.items()) - sum(sh.get(k, 0) * w for k, w in AVOID.items())


def tags_of(name, tag):
    reads = lr.load(name)["reads"]
    return sorted(t for t in reads if t.startswith(tag + "_r"))


def text(name, tags, head=True):
    sh = shares(name, tags)
    f = lambda ks: "  ".join(f"{k.split('_', 1)[1]} {sh.get(k, 0):.2f}" for k in ks)  # noqa: E731
    lines = [f"SCORE {name} [{len(tags)} readers]: {total(sh):+.2f}", "   want:  " + f(WANT), "   avoid: " + f(AVOID)]
    reads = lr.load(name)["reads"]
    for t in tags:
        for v, rd in reads[t]["views"].items():
            if v in ("front", "profile_right") and rd.get("summary"):
                lines.append(f"     {t} {v}: {rd['summary'][:150]}")
    return "\n".join(lines)


if __name__ == "__main__":
    a = sys.argv[1:]
    rows = []
    for name, tag in zip(a[0::2], a[1::2]):
        tg = tags_of(name, tag)
        print(text(name, tg))
        rows.append((name, shares(name, tg)))
    ks = list(WANT) + list(AVOID)
    print("\n" + " " * 22 + " ".join(f"{k.split('_', 1)[1][:7]:>7s}" for k in ks) + "   score")
    for name, sh in rows:
        print(f"{name[-22:]:22s}" + " ".join(f"{sh.get(k, 0):7.2f}" for k in ks) + f"   {total(sh):+.2f}")
