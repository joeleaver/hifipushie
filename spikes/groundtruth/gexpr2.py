"""gexpr2.py <src model> <out model>: blockin.expression_step on a model of the expression test (each detector view's
expression fitted on the head as it stands: 20 lower-face components under their prior; the solve then reads that
view on the head WITH its expression). The fitted expression is printed."""
import sys
from hifipushie import blockin as bi
from hifipushie import blockin_steps

r = blockin_steps.expression_step(sys.argv[1], out=sys.argv[2])
print(blockin_steps.expression_text(r) if hasattr(bi, "expression_text") else r)
