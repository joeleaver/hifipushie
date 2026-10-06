"""face.py <age> <sex> <tag> '<head overrides json>' [zoom] [at: mouth|nose|neck|face]: clay face close-up of a variant."""
import sys, json, time
from hifipushie import server, humans, store
from hifipushie.spec import expand_mirror

S = "/tmp/claude-1000/-home-joe-dev-hifipushie/1d5c679b-4c56-495b-8635-72e86a3b3567/scratchpad/humans3/"
age, sex, tag = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
over = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
zoom = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0
at = sys.argv[6] if len(sys.argv) > 6 else "face"
name = f"hum3_f_{tag}"
sp = humans.spec(age, sex, skin=False, head=over.pop("head", None), **over)
server.put_model(name, sp)
J = expand_mirror(store.load(name))["joints"]
nz = J["lm_nose_tip"]["pos"]
f = {"face": [0, nz[1] + 0.03, nz[2]], "mouth": J["lm_lip_upper"]["pos"], "nose": nz, "neck": [0, nz[1] + 0.04, J["lm_chin"]["pos"][2] - 0.03]}[at]
t = time.time()
server.look(name, views=["front", "three_quarter", "side"], size=512, focus=f, zoom=zoom, resolution=300, paint=False, save=S + name + ".png")
print(S + name + ".png", round(time.time() - t, 1))
