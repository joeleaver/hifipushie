#!/usr/bin/env bash
# Build (and with --push, push) the hosted sculpt runner image: ghcr.io/joeleaver/oxidegen-sculpt:<git short sha>.
#   docker/build-sculpt.sh [--push] [ASSETS_SRC]
set -euo pipefail
cd "$(dirname "$0")/.."
push=0
if [[ "${1:-}" == "--push" ]]; then push=1; shift; fi
sha=$(git rev-parse --short HEAD)
if [[ -n "$(git status --porcelain -- src pyproject.toml uv.lock Dockerfile.sculpt)" ]]; then sha="$sha-dirty"; fi
image="${IMAGE:-ghcr.io/joeleaver/oxidegen-sculpt}:$sha"
uv run python docker/stage_assets.py "$@"
docker build -f Dockerfile.sculpt --build-arg GIT_SHA="$sha" -t "$image" .
docker image inspect "$image" --format 'built {{index .RepoTags 0}}: {{.Size}} bytes'
if (( push )); then
  docker push "$image"
  docker image inspect "$image" --format '{{index .RepoDigests 0}}'
fi
