#!/bin/bash
# run.sh <script.py> [args]: a scratch script with the humans track's environment
export HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace
cd "$(dirname "$0")/.."
exec uv run python "$@" 2>&1
