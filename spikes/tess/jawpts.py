"""jawpts.py <model>: Tess's jaw traced on the 3/4 and profile photos (likeness_points: jaw.L line down the ramus,
round the angle, along the lower border; ear_lobe.L), picked on contrast-enhanced 25 px grids (ref/jaw_both.png)."""
import sys
from hifipushie import server

name = sys.argv[1]
D = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
print(server.likeness_points(name, D + "tess_head_three_quarter_left.png",
                             points={"ear_lobe.L": [700, 758], "gonion.L": [662, 822]},
                             lines={"jaw.L": [[705, 765], [690, 795], [665, 822], [600, 852], [520, 880], [440, 900], [400, 905]]},
                             by="tess (grid trace)"))
print(server.likeness_points(name, D + "tess_head_profile_left.png",
                             points={"ear_lobe.L": [520, 757], "gonion.L": [555, 835]},
                             lines={"jaw.L": [[535, 765], [550, 800], [555, 835], [500, 860], [420, 885], [330, 910], [290, 918]]},
                             by="tess (grid trace)"))
