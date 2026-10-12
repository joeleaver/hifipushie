"""cmp.py <out.png> <model> [model ..] [views=0,2]: reference | models, the fitted-camera tiles (s_<model>_v<n>.png in out/ or
tesshair2/out)."""
import os, sys
from PIL import Image
R = '/home/joe/dev/s0urc3/docs/img/tess_ref_full/'
REF = {0: 'tess_head_front.png', 1: 'tess_head_three_quarter_left.png', 2: 'tess_head_profile_left.png'}
D = ['/mnt/data/hifipushie/tesshair3/out/', '/mnt/data/hifipushie/tesshair2/out/', '/mnt/data/hifipushie/tesshair/out/']
args = [a for a in sys.argv[2:] if '=' not in a]
kw = dict(a.split('=') for a in sys.argv[2:] if '=' in a)
vs = [int(v) for v in kw.get('views', '0,2').split(',')]
N = int(kw.get('n', 620))


def sq(im):
    w, h = im.size
    m = max(w, h)
    c = Image.new('RGB', (m, m), (205, 205, 205))
    c.paste(im, ((m - w) // 2, (m - h) // 2))
    return c.resize((N, N))


S = Image.new('RGB', (N * (1 + len(args)), N * len(vs)), 'white')
for i, v in enumerate(vs):
    S.paste(sq(Image.open(R + REF[v]).convert('RGB')), (0, N * i))
    for j, m in enumerate(args):
        f = next((d + f's_{m}_v{v}.png' for d in D if os.path.exists(d + f's_{m}_v{v}.png')), None)
        if f:
            S.paste(sq(Image.open(f).convert('RGB')), (N * (j + 1), N * i))
S.save(sys.argv[1])
