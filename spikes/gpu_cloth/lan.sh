#!/usr/bin/env bash
# A ZOZO job on one of the department's own machines (oxidegen bundle jobs `run --local`: free, the files never leave the
# LAN), run with the job folder as its last argument; leaves out.npz in it. Exit 0 when it did; exit 9 when the route is
# not available (no token, no client, the machine not online): the caller then runs the job here.
# Settings (environment or the machine's local config, localconf.py; never written in the repo):
#   LAN_HOST        pin the job to this machine (its oxidegen name); unset = any department machine with a GPU
#   LAN_RAM_GB      one job's peak memory there (default 4; killed past 1.25x)
#   OXIDEGEN_BUNDLE_CLIENT  the client (default ~/dev/oxidegen/scripts/bundle/bundle_client.py: --local needs its version)
#   OXIDEGEN_TOKEN, else $OXIDEGEN_TOKEN_FILE (default ~/.config/oxidegen/hifipushie-cloth-token). Never printed.
# The runner is this checkout's cloth_zozo.py, unedited (its hash is part of every sim's cache key).
set -euo pipefail
job="${@: -1}"
job="$(cd "$job" && pwd)"
here="$(cd "$(dirname "$0")" && pwd)"
client="${OXIDEGEN_BUNDLE_CLIENT:-$HOME/dev/oxidegen/scripts/bundle/bundle_client.py}"
if [ ! -r "$client" ]; then echo "lan.sh: no bundle client ($client): not run" >&2; exit 9; fi
if [ -z "${OXIDEGEN_TOKEN:-}" ]; then
  tf="${OXIDEGEN_TOKEN_FILE:-$HOME/.config/oxidegen/hifipushie-cloth-token}"
  if [ ! -r "$tf" ]; then echo "lan.sh: no OXIDEGEN_TOKEN and no token file: not run" >&2; exit 9; fi
  OXIDEGEN_TOKEN="$(tr -d '[:space:]' < "$tf")"
  export OXIDEGEN_TOKEN
fi
if [ -n "${LAN_HOST:-}" ]; then
  up="$(cd / && timeout 60 python3 "$client" machines 2>/dev/null | python3 -c 'import json,sys; h=sys.argv[1]; print(any(m.get("name")==h and m.get("state")=="online" for m in json.load(sys.stdin).get("machines",[])))' "$LAN_HOST" || echo False)"
  if [ "$up" != "True" ]; then echo "lan.sh: the configured machine is not online: not run" >&2; exit 9; fi
  pin=(--host "$LAN_HOST")
else
  pin=()
fi
name="$(basename "$(dirname "$job")")_$(basename "$job")_$(date +%H%M%S)"
stage="$(mktemp -d "${TMPDIR:-/tmp}/lan_XXXXXX")"
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/$name"
cp "$job/job.json" "$job/in.npz" "$stage/$name/"
(cd "$stage" && python3 "$client" run --bundle "${BUNDLE:-zozo}" --runner "$here/../../src/hifipushie/cloth_zozo.py" \
  --batch "$name" --pull "$stage/res" --timeout-minutes "${BUNDLE_TIMEOUT_MIN:-120}" --local --gpu \
  --ram-gb "${LAN_RAM_GB:-4}" "${pin[@]}" "$stage/$name")
if [ ! -f "$stage/res/$name/out.npz" ]; then echo "lan.sh: $name returned no out.npz" >&2; exit 1; fi
cp "$stage/res/$name/out.npz" "$job/out.npz"
