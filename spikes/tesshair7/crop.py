import sys
from PIL import Image
R='/home/joe/dev/s0urc3/docs/img/tess_ref_full/'
m=sys.argv[1]; o=sys.argv[2] if len(sys.argv)>2 else 'th_T66'
def sq(f):
    im=Image.open(f).convert('RGB'); w,h=im.size; s=max(w,h); x=Image.new('RGB',(s,s),(200,200,200)); x.paste(im,((s-w)//2,(s-h)//2)); return x
def tile(mm,v):
    import os
    for d in ('/mnt/data/hifipushie/tesshair7/out/','/mnt/data/hifipushie/tesshair6/out/'):
        if os.path.exists(d+'s_'+mm+'_'+v+'.png'): return Image.open(d+'s_'+mm+'_'+v+'.png').convert('RGB')
S=520
rows=[('v0','tess_head_front.png',(0.22,0.03,0.72,0.53)),('v1','tess_head_three_quarter_left.png',(0.3,0.03,0.8,0.53)),('v2','tess_head_profile_left.png',(0.36,0.03,0.86,0.53))]
out=Image.new('RGB',(3*S,len(rows)*S))
for r,(v,rf,box) in enumerate(rows):
    for k,im in enumerate([sq(R+rf),tile(m,v),tile(o,v)]):
        if im is None: continue
        s=im.size[0]; out.paste(im.crop((int(box[0]*s),int(box[1]*s),int(box[2]*s),int(box[3]*s))).resize((S,S)),(k*S,r*S))
out.save('/mnt/data/hifipushie/tesshair7/out/c_'+m+'.jpg',quality=88)
