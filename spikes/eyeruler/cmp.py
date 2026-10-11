"""cmp.py <refs model> [<model>]: eye_ruler.compare's table."""
import sys

from hifipushie import eye_ruler as er

print(er.compare(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)["text"])
