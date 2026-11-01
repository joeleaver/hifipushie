import sys, pickle, numpy as np
from scipy.spatial import cKDTree
D='/mnt/data/hifipushie/folds_ab/D/'; H='/mnt/data/hifipushie/folds_ab/H/'; job=sys.argv[1]; out_tag=sys.argv[2]
p=pickle.load(open(H+job+'_prep.pkl','rb')); o=pickle.load(open(H+job+'/out.pkl','rb')); z=np.load(H+job+'/in.npz')
M=p['M']; keep=p['keep']; X=p['Xall'].copy(); V=np.asarray(o['V'],float); hold=p['hold']; start=z['X']
X0=X.copy(); X[keep]=V
pc=np.asarray(M['piece']); nm=list(M['names']); F=np.asarray(M['F']); uv=M['uv']
sew=np.asarray(M['sew']).reshape(-1,2); idx=-np.ones(len(X),int); idx[keep]=np.arange(keep.sum())
# weld: each sewn pair at its mean; a pair with a held side takes the held side
for a,b in sew:
    if keep[a] and keep[b]:
        ha,hb=hold[idx[a]],hold[idx[b]]
        if ha and not hb: X[b]=X[a]
        elif hb and not ha: X[a]=X[b]
        elif not ha: m=(X[a]+X[b])/2; X[a]=m; X[b]=m
fr=~hold; dm=np.linalg.norm(V-start,axis=1)[fr]
print('free cloth moved mm: p50',round(np.median(dm)*1e3,1),'p95',round(np.percentile(dm,95)*1e3,1),'max',round(dm.max()*1e3,1)); print('held moved max mm',round(np.linalg.norm(V-start,axis=1)[hold].max()*1e3,3))
print('free cloth mean z drop mm',round((start[fr,2]-V[fr,2]).mean()*1e3,1))
P=[nm.index(n) for n in ('back','yoke','front.L','front.R')];inP=np.isin(pc,P);Fp=F[np.all(inP[F],axis=1)];ed=np.unique(np.sort(np.r_[Fp[:,[0,1]],Fp[:,[1,2]],Fp[:,[2,0]]],axis=1),axis=0)
L=np.linalg.norm(uv[ed[:,0]]-uv[ed[:,1]],axis=1);l=np.linalg.norm(X[ed[:,1]]-X[ed[:,0]],axis=1)/L-1;l0=np.linalg.norm(X0[ed[:,1]]-X0[ed[:,0]],axis=1)/L-1
print('link stretch p50',round(np.median(l)*100,1),'p99',round(np.percentile(l,99)*100,1),'max',round(l.max()*100,1),'| before hang p99',round(np.percentile(l0,99)*100,1),'max',round(l0.max()*100,1))
_b=pickle.load(open(D+sys.argv[3]+'U.pkl','rb')) if len(sys.argv)>3 else None; bV=np.asarray(_b['bodyV'],float);bF=np.asarray(_b['bodyF']);N=np.zeros_like(bV);fn=np.cross(bV[bF[:,1]]-bV[bF[:,0]],bV[bF[:,2]]-bV[bF[:,0]])
for k in range(3): np.add.at(N,bF[:,k],fn)
N/=np.linalg.norm(N,axis=1)[:,None];iv=np.where(keep)[0][fr];_,j=cKDTree(bV).query(X[iv]);sd=np.einsum('ij,ij->i',X[iv]-bV[j],N[j]);print('free cloth inside the full body:',(sd<0).sum(),'of',len(iv),'deepest',round(sd.min()*1e3,1),'mm')
sg=np.linalg.norm(X[sew[:,0]]-X[sew[:,1]],axis=1);print('seam gap max (torso)',round(sg[keep[sew].all(1)].max()*1e3,1))
Fa=F[np.all(np.isin(pc[F],[nm.index(k) for k in ('back','yoke','front.L','front.R','sleeve.L','sleeve.R')]),axis=1)];ea=np.unique(np.sort(np.r_[Fa[:,[0,1]],Fa[:,[1,2]],Fa[:,[2,0]]],axis=1),axis=0);La=np.linalg.norm(uv[ea[:,0]]-uv[ea[:,1]],axis=1);l=np.linalg.norm(X[ea[:,1]]-X[ea[:,0]],axis=1)/La-1;print('after weld: link p99',round(np.percentile(l,99)*100,1),'max',round(l.max()*100,1));print('worst at',[(round(float(l[k])*100),nm[pc[ea[k,0]]],np.round(X[ea[k,0]]*1e3).tolist()) for k in np.argsort(-l)[:4]])
pickle.dump({'A':X,'mesh':M,'bodyV':bV,'bodyF':bF,'at':p['at']},open(D+out_tag+'.pkl','wb'));print('saved',out_tag)
