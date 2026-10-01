#!/bin/sh
# Build the asset-packs tarball local runners download (the department serves it; `setup` checks its sha256):
#   scripts/build-packs.sh [SRC]  ->  dist/hifipushie-packs-<git short sha>.tar.gz (+ its sha256 on stdout)
# Only the licensed packs, exactly the files of src/hifipushie/assets.json: gnm (Apache-2.0) and makehuman (CC0),
# each with SOURCE.txt (and gnm's LICENSE); copied from SRC ($HIFIPUSHIE_ASSETS or ./workspace/_templates) when
# intact, else fetched by checksum. Reproducible: sorted, fixed mtimes/owners.
set -eu
cd "$(dirname "$0")/.."
sha=$(git rev-parse --short HEAD)
uv run python docker/stage_assets.py "$@" >&2
mkdir -p dist
out="dist/hifipushie-packs-$sha.tar.gz"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C docker/assets -cf - gnm makehuman \
  | gzip -n -9 > "$out"
sha256sum "$out"
