#!/usr/bin/env bash
# zozo.sh <backend rocm|cuda|cpu> <job folder> [cloth_zozo args]: src/hifipushie/cloth_zozo.py (the zozo backend's runner) with an unpacked ZOZO release
# ($PPF_ROOT, the folder holding ppf-contact-solver and python/), memory-capped (systemd scope, $ZOZO_MEM, default 6G),
# under hifipushie's machine-wide heavy slot (resources.heavy) when $HIFIPUSHIE_HEAVY_PY names a python with hifipushie.
set -euo pipefail
be=$1; shift
here="$(cd "$(dirname "$0")" && pwd)"
R="${PPF_ROOT:?set PPF_ROOT to the unpacked ppf-contact-solver release}"
export CARGO_TARGET_DIR="$R/target/$be" PYTHONPATH="$R" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME
cmd=(systemd-run --user --scope -q -p "MemoryMax=${ZOZO_MEM:-6G}" -p MemorySwapMax=0 "$R/python/bin/python3.12" "$here/../../src/hifipushie/cloth_zozo.py" "$@")
if [ -n "${HIFIPUSHIE_HEAVY_PY:-}" ]; then
  exec "$HIFIPUSHIE_HEAVY_PY" -c "import subprocess, sys
from hifipushie import resources
with resources.heavy('zozo cloth', log=print):
    sys.exit(subprocess.call(sys.argv[1:]))" "${cmd[@]}"
fi
exec "${cmd[@]}"
