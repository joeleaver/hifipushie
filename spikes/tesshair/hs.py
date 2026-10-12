"""hs.py <model> [views]: spikes/tess/hscore.py (IoU / hairline band / scalp / forehead arch / colour bands against
the tess agent's traces in $T) under the machine-wide heavy slot; summary lines only."""
import io, runpy, sys, contextlib, os
from hifipushie import resources

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
buf = io.StringIO()
with resources.heavy(f"tesshair hscore {sys.argv[1]}", gb=6):
    sys.argv = [f"{W}/tess/hscore.py"] + sys.argv[1:]
    with contextlib.redirect_stdout(buf):
        runpy.run_path(sys.argv[0], run_name="__main__")
for ln in buf.getvalue().splitlines():
    if ln.startswith("view") or any(k in ln for k in ("hairline band", "scalp showing", "forehead arch", "colour shadow", "coverage")):
        print(ln)
