#!/usr/bin/env bash
# The thin sculpt box's start (Dockerfile.sculpt-thin): unpack a stack archive from the network volume onto the
# container disk, then run the runner. The archive is the one for the department's wanted version
# (stack-<sha>.tar.zst in HIFIPUSHIE_STACK_DIR, matched by sha prefix: then no in-place update runs), else
# HIFIPUSHIE_STACK (an older one: the runner then updates in place, as the full image does).
set -euo pipefail
dir="${HIFIPUSHIE_STACK_DIR:-/workspace/sculpt}"
want="${OXIDEGEN_WANTED_VERSION:-}"
archive=""
if [[ -n "$want" ]]; then
  for f in "$dir"/stack-*.tar.zst; do
    [[ -f "$f" ]] || continue
    sha="${f##*/stack-}"; sha="${sha%.tar.zst}"
    if (( ${#sha} >= 7 )) && [[ "${want,,}" == "${sha,,}"* ]]; then archive="$f"; break; fi
  done
fi
archive="${archive:-${HIFIPUSHIE_STACK:-}}"
if [[ -z "$archive" || ! -f "$archive" ]]; then
  echo "sculpt-stack-boot: no stack archive (wanted ${want:-none}, HIFIPUSHIE_STACK=${HIFIPUSHIE_STACK:-unset}, in $dir)" >&2
  exit 3
fi
start=$(date +%s.%N)
zstd -dc "$archive" | tar --no-same-owner -xf - -C /opt/stack
# The stack's own sha (it decides whether the runner updates in place): its VERSION file, else the archive's name.
if [[ -f /opt/stack/VERSION ]]; then ver=$(< /opt/stack/VERSION); else ver="${archive##*/stack-}"; ver="${ver%.tar.zst}"; fi
export HIFIPUSHIE_GIT_SHA="$ver"
echo "sculpt-stack-boot: unpacked $(basename "$archive") (hifipushie $ver) in $(awk "BEGIN{printf \"%.1f\", $(date +%s.%N)-$start}") s" >&2
exec hifipushie-artist
