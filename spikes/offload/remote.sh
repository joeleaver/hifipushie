#!/bin/bash
# remote.sh <runner.py> <outputs a,b> <ram_gb> <cpus> [gpu|nogpu] <job dir>...: run job folders on Joe's other machines
# through oxidegen compute jobs (docs: /home/joe/dev/oxidegen/docs/compute-jobs.md; free; NICO-TOP first). Blocks until
# the outputs are back in ./results/<batch>/<job>/. The environment is THIS repo at HEAD (git archive: COMMIT first;
# uncommitted changes do not travel) + `uv sync` + the asset packs in $PACKS, built once per machine per commit (a new
# commit rebuilds only the code + uv sync: the packs are kept in the machine's cache, oxidegen v139). Files travel
# over the LAN from this computer, so the client must keep running until the outputs are back.
# Job folders are uploads (128 MiB cap): pack a model with spikes/tour/pack_model.py (model folders are ~100 KB + its
# reference pictures; stage caches are rebuilt on the machine, ~1 min). Jobs are sandboxed: no access to this
# machine's paths; a job sees only its folder, the environment ({dir} = $HP_DIR) and Blender ($OXIDEGEN_BLENDER).
set -e
R=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
runner=$1; outs=$2; ram=$3; cpus=$4; gpu=$5; shift 5
# NICO-TOP's slot cap is ~14 GB: a bigger request never starts and blocks the queue for every job behind it
# (hp-lashes2, 20 GB, 2026-10-15). Split the job instead.
[ "${ram%.*}" -le 12 ] || { echo "remote.sh: ram_gb $ram > 12 never starts on NICO-TOP and blocks the queue; split the job" >&2; exit 2; }
A=${XDG_RUNTIME_DIR:-/tmp}/hp_repo_$(git -C "$R" rev-parse --short HEAD).tar.gz
[ -f "$A" ] || git -C "$R" archive --format=tar.gz --prefix=repo/ -o "$A" HEAD
ln -sf "$A" repo.tar.gz
PACKS=${PACKS:-gnm makehuman faceid hbm}
K=hp_assets_$(cat "$R/src/hifipushie/assets.json" <(echo "$PACKS") | sha256sum | cut -c1-12)
# (asset packs live in the machine's per-user cache, keyed by assets.json + the pack list: a new commit costs only uv sync)
SETUP='uv sync --frozen && A=$OXIDEGEN_CACHE/'"$K"' && { [ -f $A/.done ] || { HIFIPUSHIE_ASSETS=$A .venv/bin/hifipushie-assets fetch '"$PACKS"' && touch $A/.done; }; } && ln -sfn $A _assets'
B='{"archive": "repo.tar.gz", "dir": "repo", "setup": ["sh", "-c", "'"$SETUP"'"], "shared": true, "command": ["{dir}/.venv/bin/python", "{runner}", "jobs/{job}"], "env": {"PYTHONPATH": "{dir}/src:{dir}/spikes/garrett3:{dir}/spikes/tour", "HP_DIR": "{dir}"}, "progress_prefix": "step:"}'
G=""; [ "$gpu" = gpu ] && G=--gpu
OXIDEGEN_TOKEN=$(cat ~/.config/oxidegen/hifipushie-cloth-token) exec python3 /home/joe/dev/oxidegen/scripts/bundle/bundle_client.py run \
  --local --ram-gb "$ram" --cpus "$cpus" $G --bundle "$B" --runner "$runner" --outputs "$outs" \
  --batch "${BATCH:-hp-$(date +%H%M%S)}" --timeout-minutes "${TIMEOUT:-40}" "$@"
