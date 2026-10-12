#!/bin/bash
# tests.sh [files]: the tests this thread must leave passing, one light slot, log in the scratch out/tests.log
W=/home/joe/dev/hifipushie/.claude/worktrees/agent-ae615b730ec496d10
cd $W
export HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates
CAP=10G /mnt/data/hifipushie/bin/slot uv run python -m pytest -q ${@:-tests/test_chinread.py tests/test_solvereads.py tests/test_refread.py tests/test_face_ruler.py tests/test_blockin.py tests/test_toolsets.py} > /mnt/data/hifipushie/chinread/out/tests.log 2>&1
tail -5 /mnt/data/hifipushie/chinread/out/tests.log
