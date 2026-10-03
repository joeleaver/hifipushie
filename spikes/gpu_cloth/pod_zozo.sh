#!/usr/bin/env bash
# ZOZO round on a CUDA box, one job at a time (bundle: cloth_zozo.py, jobs/<name>/sim; $PPF_ROOT = the unpacked
# ppf-contact-solver release, which carries its own python and CUDA runtime):
#   bash pod_zozo.sh check        the GPU, and each job's scene built + 2 frames (start checks, ms/frame)
#   bash pod_zozo.sh run [names]  each job in full into results/<name>/ (out.npz + run.log), progress lines echoed
set -uo pipefail
cd "$(dirname "$0")"
: "${PPF_ROOT:?set PPF_ROOT to the unpacked release}"
export CARGO_TARGET_DIR="$PPF_ROOT/target/cuda" PYTHONPATH="$PPF_ROOT" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME
PY="$PPF_ROOT/python/bin/python3.12"
jobs_=${2:-$(ls jobs)}
case "${1:-run}" in
  check)
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
    for n in $jobs_; do
      echo "== check $n $(date +%T)"
      $PY cloth_zozo.py "jobs/$n/sim" --frames 2 --out /tmp/check_$n.npz 2>&1 | grep -E "^cloth: zozo|violation|Error" | cut -c1-300
    done ;;
  run)
    mkdir -p results
    for n in $jobs_; do
      out=results/$n; mkdir -p "$out"
      echo "== run $n $(date +%T)"
      $PY cloth_zozo.py "jobs/$n/sim" --out "$out/out.npz" --snap 24 > "$out/run.log" 2>&1
      grep -E "^cloth: zozo|Error|FATAL" "$out/run.log" | cut -c1-300
      nvidia-smi --query-gpu=memory.used --format=csv,noheader
    done
    echo ZOZO_DONE ;;
esac
