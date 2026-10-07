"""styles.py <tmp dir>: one person (an adult, dressed) through each human style sheet on the one mesh, whole figure and
face, with the sliders used: workspace/human_renders/om_30_styles_round0.png. Round 0 = the sheets' hand-set values."""
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

from hifipushie import humanfit, humans, server, store, stylesheet
from hifipushie.spec import expand_mirror

OUT = Path("/home/joe/dev/hifipushie/workspace/human_renders")
STYLES = [None, "human_feature", "human_cartoon", "human_anime", "human_lowpoly"]


def main():
    tmp = Path(sys.argv[1])
    tmp.mkdir(parents=True, exist_ok=True)
    cells = []
    for st in STYLES:
        name = "om_style_" + (st or "realistic")
        f1, f2 = tmp / f"{name}_body.png", tmp / f"{name}_face.png"
        t = time.time()
        try:
            print(server.human(name, age=28, sex=0.0, seed=8, skin=False, source="human", style=st).splitlines()[0][:160], flush=True)
            sp = store.load(name)
            J = expand_mirror(sp)["joints"]
            s_ = humanfit.state(sp["base"])
            m = s_["measures"]
            it = humanfit.integrity(sp["base"], s_)
            nz = J["lm_nose_tip"]["pos"]
            hh = m["head_height"] / 100
            server.look(name, views=["front", "side"], size=520, resolution=300, save=str(f1))
            server.look(name, views=["front", "three_quarter"], size=420, focus=[0, nz[1] + 0.03, nz[2] + 0.04 * hh],
                        zoom=m["stature"] / 100 / (1.5 * hh), resolution=300, save=str(f2))
            sl = json.dumps(((sp["base"].get("style") or {})), sort_keys=True) if st else "{}"
            cells.append((st or "realistic (no style)", Image.open(f1), Image.open(f2),
                          f"{m['stature']:.0f} cm, {m['heads']:.1f} heads; eye_width/face_width {m['eye_width'] / m['face_width']:.3f}; "
                          + humanfit.verdict(it).split("\n")[0], sl))
        except Exception as e:  # noqa: BLE001
            print(f"{st}: FAILED {e!r}"[:600], flush=True)
        print(f"  {st}: {time.time() - t:.0f} s", flush=True)
    if not cells:
        return
    w = max(c[1].width + c[2].width for c in cells)
    h = max(max(c[1].height, c[2].height) for c in cells) + 64
    out = Image.new("RGB", (w, h * len(cells)), (30, 32, 36))
    d = ImageDraw.Draw(out)
    for i, (label, body, face, line, sl) in enumerate(cells):
        y = i * h
        d.text((6, y + 4), f"{label}: {line}", fill=(255, 255, 160))
        for k in range(0, len(sl), 230):
            d.text((6, y + 18 + 12 * (k // 230)), sl[k:k + 230], fill=(200, 200, 200))
        out.paste(body, (0, y + 60))
        out.paste(face, (body.width, y + 60))
    out.save(OUT / "om_30_styles_round0.png")
    print(OUT / "om_30_styles_round0.png")
    del stylesheet


if __name__ == "__main__":
    main()
