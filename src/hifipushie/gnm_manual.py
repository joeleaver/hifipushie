"""The GNM driving manual as data: what you see (an artist's phrase) -> the control(s) that fix it.

The manual is gnm_driving_guide.md (guide topic "gnm_driving"; built and tested by the gnmdrive driving test,
docs/notes/gnm_atlas.md "## gnmdrive"). Its tables are parsed here (one source of truth): every row is an entry
{section, see, use, size, watch, moves}; `suggest(text)` ranks the entries for a phrase ("the mouth stands forward in
profile", "pupils further apart", "double chin") by word overlap (IDF-weighted, crude stems, a few synonyms), plus the
"look alike" notes that mention its words. gnm_controls(phrase=...) and block_in_step's reply (for its `seen` text)
use it."""
from __future__ import annotations

import math
import re
from pathlib import Path

GUIDE = Path(__file__).with_name("gnm_driving_guide.md")
_C: dict = {}
STOP = set("a an the and or of to in on at by for with from as is are be it its this that than then not no vs your you "
           "same only all one two per more less very".split())
SYN = {"lip": "lip", "lips": "lip", "vermilion": "lip", "red": "lip", "mouth": "mouth", "muzzle": "muzzle",
       "snout": "muzzle", "protrusive": "muzzle", "profile": "profile", "angle": "angle", "pupil": "pupil",
       "pupils": "pupil", "iris": "pupil", "irises": "pupil", "eyeball": "ball", "eyeballs": "ball", "balls": "ball",
       "ball": "ball", "double": "submental", "submental": "submental", "jowl": "jowl", "jowls": "jowl",
       "fluffy": "heavy", "fat": "heavy", "heavier": "heavy", "heavy": "heavy", "chunky": "full", "fuller": "full",
       "full": "full", "plump": "full", "lean": "lean", "gaunt": "lean", "thin": "thin", "thinner": "thin",
       "wider": "wide", "wide": "wide", "broad": "wide", "broader": "wide", "narrower": "narrow", "narrow": "narrow",
       "pinched": "narrow", "longer": "long", "long": "long", "taller": "tall", "tall": "tall", "shorter": "short",
       "short": "short", "bigger": "big", "big": "big", "larger": "big", "smaller": "small", "small": "small",
       "forward": "forward", "ahead": "forward", "out": "forward", "proud": "forward", "projects": "forward",
       "projecting": "forward", "protruding": "forward", "back": "back", "behind": "back", "receding": "back",
       "deep": "deep", "deeper": "deep", "deepset": "deep", "sunken": "deep", "prominent": "prominent",
       "bulging": "prominent", "bulge": "prominent", "skull": "skull", "cranium": "skull", "vault": "skull",
       "crown": "skull", "dome": "skull", "head": "head", "halo": "halo", "rim": "halo", "outline": "halo",
       "forehead": "forehead", "brow": "brow", "brows": "brow", "eyebrow": "brow", "eyebrows": "brow",
       "ridge": "ridge", "glabella": "glabella", "nose": "nose", "nasal": "nose", "bridge": "bridge", "dorsum": "bridge",
       "radix": "radix", "nasion": "radix", "tip": "tip", "lobule": "tip", "wing": "ala", "wings": "ala", "alae": "ala",
       "ala": "ala", "nostril": "nostril", "nostrils": "nostril", "upturned": "upturn", "turned": "upturn",
       "drooping": "droop", "hooked": "droop", "chin": "chin", "jaw": "jaw", "jawline": "jaw", "mandible": "jaw",
       "gonial": "jaw", "neck": "neck", "throat": "neck", "cheek": "cheek", "cheeks": "cheek", "cheekbone": "cheekbone",
       "cheekbones": "cheekbone", "malar": "cheekbone", "zygomatic": "cheekbone", "ear": "ear", "ears": "ear",
       "eye": "eye", "eyes": "eye", "lid": "lid", "lids": "lid", "eyelid": "lid", "hooded": "hooded",
       "crease": "crease", "fold": "crease", "philtrum": "philtrum", "upper": "upper", "lower": "lower",
       "spacing": "apart", "apart": "apart", "set": "apart", "close": "apart", "masseter": "masseter",
       "parotid": "masseter", "bags": "bags", "puffy": "bags", "hollow": "hollow", "hollows": "hollow"}


def _stem(w: str) -> str:
    w = w.lower().strip("`'\".,;:()!?*")
    if w in SYN:
        return SYN[w]
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            w2 = w[: -len(suf)]
            return SYN.get(w2, w2)
    return w


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.split(r"[^A-Za-z0-9_'-]+", text) if w and w.lower() not in STOP and len(w) > 1]


def entries() -> list[dict]:
    """Every table row of the manual: {section, see, use, size, watch, moves}."""
    if "e" in _C:
        return _C["e"]
    out, sec = [], ""
    for line in GUIDE.read_text().split("\n"):
        if line.startswith("## "):
            sec = line[3:].strip()
            continue
        if not line.startswith("|") or line.startswith("|---") or "You see" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        see, use, size, watch = cells[0], cells[1], cells[2], " | ".join(cells[3:])
        out.append({"section": sec, "see": see, "use": use, "size": size, "watch": watch,
                    "moves": re.findall(r"`([^`]+)`", use)})
    _C["e"] = out
    return out


def alike() -> list[str]:
    """The "look alike" notes (one bullet each)."""
    if "a" not in _C:
        txt = GUIDE.read_text()
        part = txt.split("## Phrases that look alike", 1)[-1].split("\n## ", 1)[0]
        bul, cur = [], ""
        for line in part.split("\n")[1:]:
            if line.startswith("- "):
                if cur:
                    bul.append(cur)
                cur = line[2:].strip()
            elif line.startswith("  ") and cur:
                cur += " " + line.strip()
        if cur:
            bul.append(cur)
        _C["a"] = bul
    return _C["a"]


def suggest(text: str, top: int = 3) -> dict:
    """The manual's entries for a phrase, best first: {"entries": [...], "alike": [...]}."""
    es = entries()
    docs = [set(_words(e["see"] + " " + e["section"])) for e in es]
    n = len(docs)
    df = {}
    for d in docs:
        for w in d:
            df[w] = df.get(w, 0) + 1
    q = set(_words(text))
    scores = []
    idf = lambda ws: sum(math.log(1 + n / df[w]) for w in ws)  # noqa: E731
    for i, d in enumerate(docs):
        if not q & d:
            continue
        see = es[i]["see"]
        head = set(_words(re.split(r"[:(]| / | vs ", see, maxsplit=1)[0]))   # the phrase's head (before ':', '(', ' / ')
        rest = set(_words(see)) - head
        sec = set(_words(es[i]["section"])) - head - rest
        s = 1.5 * idf(q & head) + idf(q & rest) + 0.3 * idf(q & sec)
        s /= 1 + 0.02 * len(head | rest)   # (the more specific row wins a tie)
        scores.append((s, i))
    scores.sort(key=lambda t: -t[0])
    al = []
    for b in alike():
        bw = set(_words(b.split(":")[0]))
        if q & bw:
            al.append((len(q & set(_words(b))), b))
    al.sort(key=lambda t: -t[0])
    return {"entries": [dict(es[i], score=round(s, 2)) for s, i in scores[:top]], "alike": [b for _, b in al[:2]]}


def text(res: dict) -> str:
    if not res["entries"]:
        return "manual: no entry matches (guide topic gnm_driving has the tables)"
    out = []
    for e in res["entries"]:
        out.append(f"- [{e['section']}] {e['see']} -> {e['use']} ({e['size']}). Watch: {e['watch']}")
    for b in res["alike"]:
        out.append(f"  looks alike: {b}")
    return "\n".join(out)
