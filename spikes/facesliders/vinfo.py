import sys
import numpy as np
from hifipushie import faceslide
T = faceslide.template()
F = faceslide.fields()
nm = sys.argv[1]
for i in [int(x) for x in sys.argv[2].split(",")]:
    print(i, "X mm", (1000 * T["X"][i]).round(2), "n", T["n"][i].round(2), "ext", T["ext"][i], "field mm", (1000 * F[nm][1][i]).round(3))
