"""vyaw.py <model>...: each reference view's stated yaw, its camera's "yaw" key and face_ruler.view_yaw (the turn from
the fitted camera's rotation), and face_ruler.view_sanity's warning."""
import sys
from hifipushie import blockin as bi, face_ruler as fr
from hifipushie import blockin_models, face_ruler_camera, face_ruler_compare
for m in sys.argv[1:]:
    rj = blockin_models._refs(m)
    for v, cam, s in zip(rj["views"], rj["cameras"], face_ruler_compare.view_sanity(rj["views"], rj["cameras"])):
        print(f"{m:10s} {str(v['image']).split('/')[-1]:38s} stated {v.get('yaw')}  cam.yaw {cam.get('yaw', 0):+.1f}  r {[round(x, 3) for x in cam.get('r', [])]}  view_yaw {face_ruler_camera.view_yaw(cam):+.1f}  {s['warn'][:90]}")
