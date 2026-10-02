#!/usr/bin/env bash
# On the GPU box, from the bundle folder (run_newton.py, requirements.txt, jobs/<name>/sim/{job.json,in.npz}):
#   bash pod_run.sh setup         pip install the runner's deps, print the GPU
#   bash pod_run.sh smoke         one job, 10 frames, vertex and full-surface contact (CUDA path, SDF build)
#   bash pod_run.sh all [args]    every job in jobs/, each variant into results/<job>_<variant>/ (out.npz + log)
set -uo pipefail
cd "$(dirname "$0")"
py=${PY:-python3}
case "${1:-all}" in
  setup)
    $py -m pip install -q -r requirements.txt && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
    $py -c "import warp as wp; wp.init(); print(wp.get_cuda_devices())" ;;
  smoke)
    j=$(ls -d jobs/*/sim | head -1)
    for fs in false true; do
      $py run_newton.py "$j" --out /tmp/smoke_$fs.npz --set full_surface=$fs \
        --set 'stages=[{"name":"sew","frames":10,"gravity":0,"sew":true,"sew_force":6,"self_collision":true,"fixed":[],"body":true},{"name":"settle","frames":10,"gravity":1,"sew":true,"sew_force":null,"self_collision":true,"fixed":[],"body":true}]' 2>&1 | grep -E "cloth:|Error|error" | grep -v progress
    done ;;
  all)
    shift || true
    mkdir -p results
    for j in jobs/*/; do
      name=$(basename "$j")
      for v in ${VARIANTS:-vtx full}; do
        fs=false; [ "$v" = full ] && fs=true
        out=results/${name}_$v; mkdir -p "$out"
        echo "== $name $v $(date +%T)"
        $py run_newton.py "$j/sim" --out "$out/out.npz" --set full_surface=$fs "$@" > "$out/run.log" 2>&1
        grep -E "stage |welded|total|SDF|Error" "$out/run.log" | tail -12
        nvidia-smi --query-gpu=memory.used --format=csv,noheader
      done
    done ;;
esac
