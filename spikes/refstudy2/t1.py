"""t1.py <tests/test_x.py> <test name> ...: run named tests of a test module one by one."""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("t", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
for n in sys.argv[2:]:
    getattr(m, n)()
    print("ok", n)
