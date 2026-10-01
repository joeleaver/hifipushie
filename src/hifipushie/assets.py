"""Third-party assets the pipeline reads (not in the repo): one directory, fetched by checksum.

The directory is $HIFIPUSHIE_ASSETS, else <HIFIPUSHIE_HOME>/_templates (where they always lived). Each pack
(`assets.json`: gnm, makehuman, hbm) is a subdirectory holding its files, a SOURCE.txt (URL, commit, licence)
written by `fetch`. Code asks `pack(name)` / `path(name, rel)`, which say how to fetch a pack that's missing.

  uv run hifipushie-assets verify            which packs are present and intact
  uv run hifipushie-assets fetch [packs...]  download what's missing or corrupt (default: every required pack)

Downloads go to a ".part" file inside the pack's directory (never /tmp) and replace the file only when its
sha256 matches. A zip download ("member") extracts that one file.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

MANIFEST = Path(__file__).with_name("assets.json")


def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def root() -> Path:
    env = os.environ.get("HIFIPUSHIE_ASSETS")
    if env:
        return Path(env).expanduser()
    from . import store
    return store.HOME / "_templates"


def pack(name: str) -> Path:
    """A pack's directory, checked present (every file of the manifest exists; sizes/checksums are `verify`'s job,
    so this stays cheap enough to call on every use)."""
    m = manifest()
    if name not in m:
        raise ValueError(f"no asset pack {name!r} (have {', '.join(m)})")
    d = root() / name
    missing = [f["path"] for f in m[name]["files"] if not (d / f["path"]).exists()]
    if missing:
        raise FileNotFoundError(
            f"asset pack {name!r} ({m[name]['needed_by']}) is missing from {d} ({len(missing)} files, e.g. "
            f"{missing[0]}): run `uv run hifipushie-assets fetch {name}` (source: {m[name]['source']}; "
            f"licence: {m[name]['licence']}), or set HIFIPUSHIE_ASSETS to where they are")
    return d


def path(name: str, rel: str) -> Path:
    return pack(name) / rel


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(names: list[str] | None = None) -> dict[str, list[str]]:
    """{pack: problems} (empty list = intact) for the given packs (default all)."""
    m = manifest()
    out = {}
    for name in names or list(m):
        d = root() / name
        probs = []
        for f in m[name]["files"]:
            p = d / f["path"]
            if not p.exists():
                probs.append(f"missing {f['path']}")
            elif _sha256(p) != f["sha256"]:
                probs.append(f"checksum mismatch {f['path']}")
        out[name] = probs
    return out


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "hifipushie-assets"})  # (Poly Haven refuses no UA: 403)
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)


def fetch(names: list[str] | None = None, log=print) -> None:
    """Download every missing or corrupt file of the given packs (default: all packs not marked optional)."""
    m = manifest()
    names = names or [n for n, p in m.items() if not p.get("optional")]
    for name in names:
        if name not in m:
            raise ValueError(f"no asset pack {name!r} (have {', '.join(m)})")
        d = root() / name
        d.mkdir(parents=True, exist_ok=True)
        for f in m[name]["files"]:
            dest = d / f["path"]
            if dest.exists() and _sha256(dest) == f["sha256"]:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_name(dest.name + ".part")
            log(f"{name}: {f['path']} <- {f['url']}")
            try:
                _download(f["url"], part)
                if f.get("member"):  # one file out of a zip
                    with zipfile.ZipFile(part) as z:
                        names_in = z.namelist()
                        member = f["member"] if f["member"] in names_in else next(
                            (n for n in names_in if n.endswith("/" + Path(f["member"]).name)), None)
                        if member is None:
                            raise ValueError(f"{f['url']} has no {f['member']}")
                        raw = dest.with_name(dest.name + ".unzip")
                        with z.open(member) as src, open(raw, "wb") as out:
                            shutil.copyfileobj(src, out, 1 << 20)
                    part.unlink()
                    part = raw
                got = _sha256(part)
                if got != f["sha256"]:
                    raise ValueError(f"{f['path']}: sha256 {got} != {f['sha256']} (the source changed?)")
                part.replace(dest)
            finally:
                for p in (part, dest.with_name(dest.name + ".part")):
                    if p.exists() and p != dest:
                        p.unlink()
        (d / "SOURCE.txt").write_text(f"{m[name]['source']}\nLicence: {m[name]['licence']}\n"
                                      f"Fetched by hifipushie-assets (checksums in src/hifipushie/assets.json).\n")
        log(f"{name}: ok ({d})")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd, names = (argv[0] if argv else "verify"), argv[1:]
    print(f"assets directory: {root()}")
    if cmd == "fetch":
        fetch(names or None)
        return 0
    if cmd == "verify":
        bad = 0
        m = manifest()
        for name, probs in verify(names or None).items():
            opt = " (optional)" if m[name].get("optional") else ""
            print(f"{name}{opt}: " + ("ok" if not probs else f"{len(probs)} problems: " + "; ".join(probs[:3])))
            bad += bool(probs) and not m[name].get("optional")
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
