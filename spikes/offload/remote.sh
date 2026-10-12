#!/bin/bash
# remote.sh <runner.py> <outputs a,b> <ram_gb> <cpus> [gpu|nogpu] <job dir>...: run job folders on Joe's other machines
# through oxidegen compute jobs (docs: /home/joe/dev/oxidegen/docs/compute-jobs.md; free; NICO-TOP first). Blocks until
# the outputs are back in ./results/<batch>/<job>/. The environment is THIS repo at HEAD (git archive: COMMIT first;
# uncommitted changes do not travel) + `uv sync` + the asset packs in $PACKS, built once per machine per commit (a new
# commit rebuilds it: ~4 min with gnm makehuman faceid hbm, so batch your jobs per commit).
# Job folders are uploads (128 MiB cap): pack a model with spikes/tour/pack_model.py (model folders are ~100 KB + its
# reference pictures; stage caches are rebuilt on the machine, ~1 min). Jobs are sandboxed: no access to this
# machine's paths; a job sees only its folder, the environment ({dir} = $HP_DIR) and Blender ($OXIDEGEN_BLENDER).
set -e
R=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
runner=$1; outs=$2; ram=$3; cpus=$4; gpu=$5; shift 5
A=${XDG_RUNTIME_DIR:-/tmp}/hp_repo_$(git -C "$R" rev-parse --short HEAD).tar.gz
[ -f "$A" ] || git -C "$R" archive --format=tar.gz --prefix=repo/ -o "$A" HEAD
ln -sf "$A" repo.tar.gz
B='{"archive": "repo.tar.gz", "dir": "repo", "setup": ["sh", "-c", "uv sync --frozen && HIFIPUSHIE_ASSETS=$PWD/_assets .venv/bin/hifipushie-assets fetch '"${PACKS:-gnm makehuman faceid hbm}"'"], "shared": true, "command": ["{dir}/.venv/bin/python", "{runner}", "jobs/{job}"], "env": {"PYTHONPATH": "{dir}/src:{dir}/spikes/garrett3:{dir}/spikes/tour", "HP_DIR": "{dir}"}, "progress_prefix": "step:"}'
G=""; [ "$gpu" = gpu ] && G=--gpu
OXIDEGEN_TOKEN=$(cat ~/.config/oxidegen/hifipushie-cloth-token) exec python3 /home/joe/dev/oxidegen/scripts/bundle/bundle_client.py run \
  --local --ram-gb "$ram" --cpus "$cpus" $G --bundle "$B" --runner "$runner" --outputs "$outs" \
  --batch "${BATCH:-hp-$(date +%H%M%S)}" --timeout-minutes "${TIMEOUT:-40}" "$@"
