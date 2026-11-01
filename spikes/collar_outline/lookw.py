import sys as _s; _s.path.insert(0, "/mnt/data/hifipushie/folds_ab/D")
from joined import joined
import sys, pickle, numpy as np
from PIL import Image, ImageDraw
from hifipushie import cloth, resources
D="/mnt/data/hifipushie/folds_ab/D/"; tags=sys.argv[1:]
box=[[-0.34,-0.24,0.78],[0.34,0.16,1.66]]; views=(("front",[0,-1,0.05]),("side",[-1,0,0.03]),("back",[0,1,0.05]))
rows=[]
with resources.heavy("lookw",gb=3.0,gpu=True):
    for t in tags:
        d=pickle.load(open(f"{D}{t}.pkl","rb")); X=np.asarray(d["A"],float); M=d["mesh"]; F=np.asarray(M["F"])
        parts=[{"name":"body","V":d["bodyV"],"F":d["bodyF"],"color":"#c4bcb4"},{"name":"shirt","V":X,"F":joined(X,M,np.asarray(d["bodyV"],float),np.asarray(d["bodyF"])),"color":"#c9ccd2","thickness":0.0004,"offset":0.0}]
        rows.append((t,[Image.open(cloth.render(parts,f"{D}{t}_w_{n}",views=[{"name":n,"dir":v}],resolution=560,box=box)[0]).convert("RGB") for n,v in views]))
H=520; sc=lambda im: im.resize((int(im.size[0]*H/im.size[1]),H))
W=max(sum(sc(i).size[0] for i in r[1]) for r in rows); sh=Image.new("RGB",(W,(H+22)*len(rows)),"white"); dr=ImageDraw.Draw(sh)
for k,(t,ims) in enumerate(rows):
    x=0; dr.text((4,(H+22)*k+5),t,fill="black")
    for i in ims: i=sc(i); sh.paste(i,(x,(H+22)*k+22)); x+=i.size[0]
fn=f"{D}whole_{'_'.join(tags)}.png"; sh.save(fn); print(fn)
