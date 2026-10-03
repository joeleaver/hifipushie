#!/usr/bin/env bash
# Build the stack archive of a full sculpt image (for the thin box, Dockerfile.sculpt-thin):
#   docker/stage-sculpt-stack.sh IMAGE [OUT_DIR]   →  OUT_DIR/stack-<sha>.tar.zst  (sha = the image's HIFIPUSHIE_GIT_SHA)
# The archive holds blender/ python/ venv/ hifipushie-assets/ and VERSION. Putting it on the department's volume
# (/workspace/sculpt/) is the department's side: oxidegen's scripts/stage-sculpt-stack.sh.
set -euo pipefail
image="${1:?usage: $0 IMAGE [OUT_DIR]}"
out="$(realpath "${2:-.}")"
sha=$(docker image inspect "$image" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^HIFIPUSHIE_GIT_SHA=//p')
[[ -n "$sha" && "$sha" != *dirty* ]] || { echo "$image has no clean HIFIPUSHIE_GIT_SHA ('$sha')" >&2; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cid=$(docker create "$image")
for d in /opt/blender /opt/python /app/.venv /opt/hifipushie-assets; do
  name=$(basename "$d"); docker cp -q "$cid:$d" "$tmp/${name#.}"
done
docker rm -f "$cid" >/dev/null
echo "$sha" > "$tmp/VERSION"
tar -C "$tmp" -cf - VERSION blender python venv hifipushie-assets | zstd -T0 -3 -q -f -o "$out/stack-$sha.tar.zst"
ls -la "$out/stack-$sha.tar.zst"
