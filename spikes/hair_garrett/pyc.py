"""pyc.py <file.py | code>: run a snippet (a file, or code on the command line) with this environment (runl.sh pyc.py ...)."""
import sys

src = sys.argv[1]
code = open(src).read() if src.endswith(".py") else src
sys.argv = sys.argv[1:]
exec(compile(code, src if src.endswith(".py") else "<pyc>", "exec"), {"__name__": "__main__"})
