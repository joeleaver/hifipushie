import os

# numpy's bundled OpenBLAS spins up a thread per core, and on many-core machines small solves and matmuls
# (the fitter's normal equations) run 100x slower from contention. Must be set before numpy is imported.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
