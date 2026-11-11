"""What the fit may set: bounds, groups, sigmas, and getting / setting a parameter by its path. Part of the skin read (skin_read.py has the overview)."""
from __future__ import annotations

def _get(sk: dict, path: str):
    from . import skin as skinmod
    a, _, b = path.partition(".")
    if a == "tone":
        return skinmod.tone_params(sk.get("tone"))[b]
    if a == "zones":
        return float((sk.get("zones") or {}).get(b, skinmod.ZONE_LAYERS[b]))
    if path == "features.flush":
        v = (sk.get("features") or {}).get("flush")
        return float(v if isinstance(v, (int, float)) else (v or {}).get("amount", 1.0 if v else 0.0)) if v else 0.0
    if path == "hair.lashes":
        v = (sk.get("hair") or {}).get("lashes", 0.7)
        return float(v if isinstance(v, (int, float)) else (v or {}).get("amount", 1.0)) if v else 0.0
    if a == "lips":
        lp = sk.get("lips") or {}
        return float((lp.get("lower") or {}).get(b[6:], 1.0)) if b.startswith("lower.") else float(lp.get(b, 1.0))
    raise KeyError(path)


def _set(sk: dict, path: str, x: float) -> None:
    from . import skin as skinmod
    a, _, b = path.partition(".")
    x = round(float(x), 4)
    if a == "tone":
        t = skinmod.tone_params(sk.get("tone"))
        t[b] = x
        sk["tone"] = {k: round(float(v), 4) for k, v in t.items()}
    elif a == "zones":
        sk.setdefault("zones", {})[b] = x
    elif path == "features.flush":
        f = sk.setdefault("features", {})
        if isinstance(f.get("flush"), dict):
            f["flush"] = {**f["flush"], "amount": x}
        else:
            f["flush"] = x
        if x <= 0.005:
            f.pop("flush", None)
    elif path == "hair.lashes":
        h = sk.setdefault("hair", {})
        h["lashes"] = {**h["lashes"], "amount": x} if isinstance(h.get("lashes"), dict) else x
    elif a == "lips":
        lp = sk.setdefault("lips", {})
        if b.startswith("lower."):
            lp.setdefault("lower", {})[b[6:]] = x
        else:
            lp[b] = x


def _stubble_opts(sk: dict):
    v = (sk.get("hair") or {}).get("stubble")
    if not v:
        return None
    return {"amount": float(v)} if isinstance(v, (int, float)) else dict(v)


def _path_set(sk: dict, path: str) -> bool:
    a, _, b = path.partition(".")
    d = sk.get(a) or {}
    if a == "tone":
        return True
    if b.startswith("lower."):
        return b[6:] in (d.get("lower") or {})
    return b in d


def _unset(sk1: dict, sk0: dict, path: str) -> None:
    """A parameter the fit left where it was and the description never named: take it out again."""
    a, _, b = path.partition(".")
    d = sk1.get(a)
    if not isinstance(d, dict):
        return
    if b.startswith("lower."):
        (d.get("lower") or {}).pop(b[6:], None)
        if "lower" in d and not d["lower"]:
            d.pop("lower")
    else:
        d.pop(b, None)
    if not d and a not in sk0:
        sk1.pop(a, None)
