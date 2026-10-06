"""one.py <age> <sex> [outfit]: one clothed clay human through put_model + look (whole + face)."""
import sys, time
from hifipushie import server, humans, store
from hifipushie.spec import expand_mirror

S = "/tmp/claude-1000/-home-joe-dev-hifipushie/1d5c679b-4c56-495b-8635-72e86a3b3567/scratchpad/humans3/"
age, sex = float(sys.argv[1]), float(sys.argv[2])
kind = sys.argv[3] if len(sys.argv) > 3 else None
name = f"hum3_t_{age:g}_{sex:g}".replace(".", "p")
t = time.time()
sp = humans.spec(age, sex, outfit_kind=kind, skin=False)
print(server.put_model(name, sp)[:600])
print(humans.describe(sp))
J = expand_mirror(store.load(name))["joints"]
H = J["head"]["pos"][2] / 0.93
print("put", round(time.time() - t, 1))
t = time.time()
server.look(name, views=["front", "side", "back"], size=640, resolution=320, paint=False, save=S + name + ".png")
print("look", round(time.time() - t, 1))
t = time.time()
nz = J["lm_nose_tip"]["pos"]
server.look(name, views=["front", "three_quarter", "side"], size=512, focus=[0, nz[1] + 0.03, nz[2]], zoom=float(sys.argv[4]) if len(sys.argv) > 4 else 3.4, resolution=280, paint=False, save=S + name + "_face.png")
print("face", round(time.time() - t, 1), S + name + ".png")
