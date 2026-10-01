"""Stage the asset packs the hosted image ships (docker/assets/<pack>/...): exactly the files of assets.json, copied
from a local packs directory when it has them intact, else fetched from their sources by checksum.

    uv run python docker/stage_assets.py [SRC]      (SRC default: $HIFIPUSHIE_ASSETS, else ./workspace/_templates)

Shipped: gnm (Apache-2.0) and makehuman (CC0 core assets), each with its SOURCE.txt (and gnm's LICENSE). The
optional hbm pack (only for re-exporting the template) is left out. The Dockerfile verifies the checksums again.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

from hifipushie import assets

PACKS = ("gnm", "makehuman")
DEST = Path(__file__).resolve().parent / "assets"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HIFIPUSHIE_ASSETS") or "workspace/_templates")
    m = assets.manifest()
    shutil.rmtree(DEST, ignore_errors=True)
    missing = []
    for pack in PACKS:
        for f in m[pack]["files"]:
            s, d = src / pack / f["path"], DEST / pack / f["path"]
            if s.is_file() and _sha(s) == f["sha256"]:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(s, d)
            else:
                missing.append(pack)
        (DEST / pack).mkdir(parents=True, exist_ok=True)
        (DEST / pack / "SOURCE.txt").write_text(f"{m[pack]['source']}\nLicence: {m[pack]['licence']}\n"
                                                f"Checksums: hifipushie src/hifipushie/assets.json.\n")
    if missing:  # fetch what the local copy lacks (only those files: fetch skips intact ones)
        os.environ["HIFIPUSHIE_ASSETS"] = str(DEST)
        assets.fetch(sorted(set(missing)))
    os.environ["HIFIPUSHIE_ASSETS"] = str(DEST)
    bad = {k: v for k, v in assets.verify(list(PACKS)).items() if v}
    if bad:
        print(f"staging failed: {bad}", file=sys.stderr)
        return 1
    size = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"staged {', '.join(PACKS)} from {src} into {DEST} ({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
