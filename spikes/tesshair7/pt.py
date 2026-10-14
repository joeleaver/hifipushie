"""pt.py <test file> ...: each test file in its OWN process (pytest -q), exit codes and skips reported; for hv.py
(the light slots were starved: tests ride in this agent's heavy slot)."""
import os
import subprocess
import sys

W = os.environ.get("W", ".")
bad = 0
for t in sys.argv[1:]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", f"{W}/tests/{t}.py"], capture_output=True, text=True, cwd=W)
    tail = [l for l in r.stdout.strip().split("\n") if l.strip()][-int(os.environ.get("PT_TAIL", 14)):]
    print(f"== {t}: exit {r.returncode}")
    print("\n".join(tail))
    bad += r.returncode != 0
sys.exit(1 if bad else 0)
