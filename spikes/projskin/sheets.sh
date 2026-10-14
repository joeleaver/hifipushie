#!/bin/bash
# sheets.sh: the gate sheets from the tiles (light: PIL only)
. /mnt/data/hifipushie/projskin/env.sh; cd $W
O=$S/out/shots; R=/home/joe/dev/hifipushie/workspace/human_renders
ROWS=view0,view1,view2,three_quarter_other,low_angle,high_angle,profile_other
uv run python spikes/projskin/sheet.py $R/ps_02_tess_projected.png 520 $ROWS "REFERENCE|$O/ps_tess_p|ref" "DE-LIT projection, photo light|$O/ps_tess_p|photo" "DE-LIT projection, NEW side light|$O/ps_tess_p|side" "RAW projection, new side light|$O/ps_tess_r|side" "PLAIN procedural skin, new side light|$O/tess_n1|side" "DE-LIT projection, top light|$O/ps_tess_p|top" ${1:+footer=$1}
uv run python spikes/projskin/sheet.py $R/ps_01_synthetic_delight.png 520 $ROWS "SYNTHETIC PHOTO (all the tool sees)|$O/ps_syn|ref" "TRUE head, new side light|$O/ps_syn|side" "DE-LIT projection, new side light|$O/ps_syn_p|side|vs=1" "RAW projection, new side light|$O/ps_syn_r|side|vs=1" "TRUE head, top light|$O/ps_syn|top" "DE-LIT projection, top light|$O/ps_syn_p|top|vs=4" footer=$S/out/ps01_footer.txt
