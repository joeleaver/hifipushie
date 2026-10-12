"""fork.py <src> <name>: blockin.fork (a block-in copied as its own root: the source's log is never written)."""
import sys
from hifipushie import blockin as bi
print(bi.fork(sys.argv[1], sys.argv[2], replace="--replace" in sys.argv))
