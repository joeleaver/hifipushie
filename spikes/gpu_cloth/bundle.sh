#!/usr/bin/env bash
# A cloth job on oxidegen's GPU fleet (bundle jobs, docs in oxidegen's docs/bundle-jobs.md), run with the job folder
# as its last argument: HIFIPUSHIE_GPU=bundle (cloth_job.run_zozo picks this script) or HIFIPUSHIE_ZOZO_REMOTE=<this>.
# The folder goes up as ONE job of its own batch with this checkout's cloth_zozo.py as the runner (unedited: its hash
# is part of every sim's cache key), the call waits for it and leaves out.npz in the folder. Exit 0 when it did.
# Auth: OXIDEGEN_TOKEN, else read from $OXIDEGEN_TOKEN_FILE (default /mnt/data/hifipushie/gpubox/oxidegen_token,
# chmod 600). The token is never printed. spikes/gpu_cloth/remote.sh (a rented box over ssh) is the legacy fallback.
set -euo pipefail
job="${@: -1}"
job="$(cd "$job" && pwd)"
here="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${OXIDEGEN_TOKEN:-}" ]; then
  tf="${OXIDEGEN_TOKEN_FILE:-/mnt/data/hifipushie/gpubox/oxidegen_token}"
  if [ ! -r "$tf" ]; then echo "bundle.sh: no OXIDEGEN_TOKEN and no token file ($tf): not run" >&2; exit 9; fi
  OXIDEGEN_TOKEN="$(tr -d '[:space:]' < "$tf")"
  export OXIDEGEN_TOKEN
fi
name="$(basename "$(dirname "$job")")_$(basename "$job")"  # job_<key>_<mode>: unique per stage
stage="$(mktemp -d "${TMPDIR:-/tmp}/bundle_XXXXXX")"
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/$name"
cp "$job/job.json" "$job/in.npz" "$stage/$name/"
python3 "$here/bundle_client.py" run --bundle "${BUNDLE:-zozo}" --runner "$here/../../src/hifipushie/cloth_zozo.py" \
  --batch "$name" --pull "$stage/res" --timeout-minutes "${BUNDLE_TIMEOUT_MIN:-120}" "$stage/$name"
if [ ! -f "$stage/res/$name/out.npz" ]; then echo "bundle.sh: $name returned no out.npz" >&2; exit 1; fi
cp "$stage/res/$name/out.npz" "$job/out.npz"
