"""syncE.py <th_E name> ...: server.sync on a th_E copy (its scene.blend: look_hair needs one), cloth dropped from the
copy first (a hairline sheet does not need a simulated suit), then scene.blend copied to <name>b."""
import json
import shutil
import sys
import time

from hifipushie import server, store

for n in sys.argv[1:]:
    assert n.startswith("th_E"), n
    f = store.HOME / n / "spec.json"
    sp = json.loads(f.read_text())
    if sp.pop("cloth", None) is not None:
        f.write_text(json.dumps(sp, indent=1))
        print(n, "cloth dropped")
    t = time.time()
    try:
        if not (store.HOME / n / "scene.blend").exists():
            print(n, str(server.sync(n))[:300].replace("\n", " | "))
        (store.HOME / (n + "b")).mkdir(exist_ok=True)
        shutil.copy(store.HOME / n / "scene.blend", store.HOME / (n + "b") / "scene.blend")
        print(n, f"sync {time.time() - t:.0f} s")
    except Exception as e:
        print(n, "FAILED", type(e).__name__, str(e)[:600])
