#!/usr/bin/env bash
# Round 2 on the GPU box (bundle: run_newton.py, run_zozo.py, requirements.txt, jobs/<name>/sim):
#   bash pod_round2.sh newton   the Newton matrix, two runs at a time (Python launches leave the GPU half idle)
#   bash pod_round2.sh zozo     ZOZO's CUDA backend on the same jobs ($PPF_ROOT: the unpacked release)
cd "$(dirname "$0")"
PY=${PY:-/root/gpucloth/venv/bin/python}
mkdir -p results
r() {  # r <job> <variant> [args]
  name=$1; v=$2; shift 2; out=results/${name}_$v; mkdir -p "$out"
  echo "== $name $v $(date +%T)"
  $PY run_newton.py "jobs/$name/sim" --out "$out/out.npz" --set full_surface=true "$@" > "$out/run.log" 2>&1
  grep -E 'stage |total|high water|Error|NaN' "$out/run.log" | tail -7
}
z() {  # z <job> <variant> [args]
  name=$1; v=$2; shift 2; out=results/${name}_$v; mkdir -p "$out"
  echo "== zozo $name $v $(date +%T)"
  CARGO_TARGET_DIR="$PPF_ROOT/target/cuda" PYTHONPATH="$PPF_ROOT" PYTHONNOUSERSITE=1 \
    "$PPF_ROOT/python/bin/python3.12" run_zozo.py "jobs/$name/sim" --out "$out/out.npz" "$@" > "$out/run.log" 2>&1
  grep -E '^cloth:|FATAL|failed|Error' "$out/run.log" | tail -5
}
case "${1:-newton}" in
  newton)
    ( r shirt_h10 n10
      r shirt_h10 n10sl3 --set strain_limit=0.03
      r shirt_h10 n10sl5 --set strain_limit=0.05
      r shirt_h10 it20sl3 --iterations 20 --set strain_limit=0.03
      r shirt_h10 ib10sl3 --set strain_limit=0.03 --set physical.interfacing_bend=10 ) > newton_a.log 2>&1
    ( r coat_h10 n10
      r coat_h10 n10sl3 --set strain_limit=0.03
      r coat_h10 s30sl3 --substeps 30 --set strain_limit=0.03
      r coat_h10 s40sl3 --substeps 40 --set strain_limit=0.03 ) > newton_b.log 2>&1
    true
    cat newton_a.log newton_b.log
    echo NEWTON_DONE ;;
  zozo)
    z shirt_h10 zozo --set body_offset=0.001 --set contact_gap=0.0003 --set interfacing=false
    z coat_h10 zozo --set body_offset=0.001 --set contact_gap=0.0003 --set interfacing=false
    echo ZOZO_DONE ;;
esac
