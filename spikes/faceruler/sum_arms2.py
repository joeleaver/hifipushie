import json
import sys

import numpy as np

G = '/mnt/data/hifipushie/faceruler/out/'
try:
    rows = json.load(open(G + 'validate_v2.json'))
    names = list(rows[0]['truth'])
    print(len(rows), 'pairs (v2, camera refinement): rms error, mean over measures:',
          {v: round(float(np.mean([np.sqrt(np.mean([(r[v][m][0] - r['truth'][m]) ** 2 for r in rows])) for m in names])), 2) for v in ('exact', 'hair', 'cam', 'outline')})
    print('cam per measure rms:', {m: round(float(np.sqrt(np.mean([(r['cam'][m][0] - r['truth'][m]) ** 2 for r in rows]))), 2) for m in names})
except Exception as e:
    print(e)
for s in sys.argv[1:]:
    try:
        d = json.load(open(G + f'arms2_{s}.json'))
    except Exception as e:
        print(e)
        continue
    arms = [a for a in ('fitcam:all', 'fitcam:top8', 'fitcam:sig', 'cam:all', 'cam:top8', 'hair:sig') if a in next(iter(d.values()))]
    print(s, len(d), 'cases;', {a: f"{sum(d[k][a]['pass'] for k in d)}/{len(d)}" for a in arms})
    for k in d:
        m = d[k]['mesh']
        print(' ', k, '+'.join(d[k]['regions']), ''.join('*' if d[k][a]['pass'] else '-' for a in arms),
              'ruler rms err %.2f' % np.sqrt(np.mean([(d[k]['fitcam'][n] - m[n]) ** 2 for n in m])),
              'cam fitted off', np.round(np.abs(np.array(d[k]['dev'])).mean(0), 1).tolist())
    dev = np.array([d[k]['dev'] for k in d]).reshape(-1, 4)
    print('  fitted camera deviations rms (mm, mm, %, deg):', np.round(np.sqrt((dev ** 2).mean(0)), 2).tolist())
    names = list(next(iter(d.values()))['mesh'])
    print('  fitcam error per measure (rms mm):', {n: round(float(np.sqrt(np.mean([(d[k]['fitcam'][n] - d[k]['mesh'][n]) ** 2 for k in d]))), 2) for n in names})
