#!/bin/bash
# remote_train.sh <outputs a,b> <ram_gb> <cpus> <job dir>...: spikes/offload/remote.sh for a TRAINING job
# (job_train.py): the same environment (this repo at HEAD + uv sync + asset packs) PLUS a torch (CUDA) venv built
# ONCE per machine in the machine's cache by the bundle's setup step (jobs are sandboxed: they can read the cache but
# not write it, and uv's own cache is closed to them: a venv made inside a job failed with "Permission denied").
# {dir}/_torch -> the venv. No pretrained weights, no datasets: torch, numpy, pillow only.
set -e
R=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
outs=$1; ram=$2; cpus=$3; shift 3
A=${XDG_RUNTIME_DIR:-/tmp}/hp_repo_$(git -C "$R" rev-parse --short HEAD).tar.gz
[ -f "$A" ] || git -C "$R" archive --format=tar.gz --prefix=repo/ -o "$A" HEAD
ln -sf "$A" repo.tar.gz
PACKS=${PACKS:-gnm makehuman faceid hbm}
K=hp_assets_$(cat "$R/src/hifipushie/assets.json" <(echo "$PACKS") | sha256sum | cut -c1-12)
T=dl_torch_v2      # v1 took PyPI's newest torch (CUDA 13 libraries): no CUDA on NICO-TOP's driver; v2 = the cu124 build only
SETUP='uv sync --frozen && A=$OXIDEGEN_CACHE/'"$K"' && { [ -f $A/.done ] || { HIFIPUSHIE_ASSETS=$A .venv/bin/hifipushie-assets fetch '"$PACKS"' && touch $A/.done; }; } && ln -sfn $A _assets && V=$OXIDEGEN_CACHE/'"$T"' && { [ -f $V/.done ] || { rm -rf $V && uv venv --python 3.12 $V && uv pip install --python $V/bin/python numpy pillow && uv pip install --python $V/bin/python --index-url https://download.pytorch.org/whl/cu124 torch && touch $V/.done; }; } && ln -sfn $V _torch'
B='{"archive": "repo.tar.gz", "dir": "repo", "setup": ["sh", "-c", "'"$SETUP"'"], "shared": true, "command": ["{dir}/.venv/bin/python", "{runner}", "jobs/{job}"], "env": {"PYTHONPATH": "{dir}/src", "HP_DIR": "{dir}"}, "progress_prefix": "step:"}'
OXIDEGEN_TOKEN=$(cat ~/.config/oxidegen/hifipushie-cloth-token) exec python3 /home/joe/dev/oxidegen/scripts/bundle/bundle_client.py run \
  --local --ram-gb "$ram" --cpus "$cpus" --gpu --bundle "$B" --runner "$R/spikes/denselm/job_train.py" --outputs "$outs" \
  --batch "${BATCH:-dl-train-$(date +%H%M%S)}" --timeout-minutes "${TIMEOUT:-120}" "$@"
