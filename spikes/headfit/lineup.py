"""lineup.py: whole humans by age, head to toe, clay, at true relative height + measured proportions vs references.
MakeHuman body (its own height for the age) + GNM head following it."""
import json, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import server, store, makehuman
from hifipushie.spec import expand_mirror

S = "/tmp/claude-1000/-home-joe-dev-hifipushie/1d5c679b-4c56-495b-8635-72e86a3b3567/scratchpad/skin2/"
OUT = "/home/joe/dev/hifipushie/workspace/skin_renders/"
PEOPLE = [("baby 1", 1, 0.5), ("toddler 3", 3, 0.5), ("child 7", 7, 0.5), ("pre-teen 11", 11, 0.5), ("teen 16 f", 16, 0.0),
          ("woman 30", 30, 0.0), ("man 30", 30, 1.0), ("woman 75", 75, 0.0), ("man 75", 75, 1.0)]
# references: stature cm (WHO / CDC medians), heads in the height (Loomis / Richer proportion charts), crotch height / stature
REF = {1: (75, 4.0, 0.36), 3: (95, 5.0, 0.42), 7: (122, 6.0, 0.46), 11: (144, 6.75, 0.48), 16: (162, 7.25, 0.48), 30: (170, 7.5, 0.48), 75: (166, 7.5, 0.47)}
only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
rows, cells, faces = [], [], []
for label, age, sex in PEOPLE:
    name = "skin2_lu_" + label.replace(" ", "_").replace("-", "")
    body = {"source": "makehuman", "age": age, "sex": sex, "weight": 0.5, "muscle": 0.5}
    spec = {"symmetry": True, "blend": 0.035, "joints": {}, "bones": {}, "blobs": {}, "parts": {"eyes": {"color": "#e8e0d6"}},
            "base": {"body": body, "eyes": "eyes", "head": {"source": "gnm", "follow_body": True, "seed": 5, "spread": 0.4, "mouth_gap": 0.0,
                                                             "expression": {"left_eye_region_000": 0.6, "right_eye_region_000": 0.6}}}}
    try:
        if not only or label in only or True:
            server.put_model(name, spec)
        mh = makehuman.body({k: v for k, v in body.items() if k != "source"})
        P = np.asarray(mh["P"], float)
        mh_top, mh_chin = float(P[:, 2].max() - P[:, 2].min()), float(mh["chin_z"] - P[:, 2].min())
        J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(store.load(name))["joints"].items() if "pos" in v}
        b = store.build(name, 160)
        V = np.load([v for v in b.values() if str(v).endswith(".npz")][0])["verts"]
        z0, top = float(V[:, 2].min()), float(V[:, 2].max())
        H = top - z0
        chin = float(J["lm_chin"][2])
        eye = float(J["eye.L"][2]) if "eye.L" in J else float(J["lm_eye_inner.L"][2])
        head = top - chin
        io = 2 * abs(float(J["eye.L"][0])) if "eye.L" in J else 0
        hip = float(J["hip.L"][2]) - z0
        neck = chin - float(J["neck"][2])
        sh = 2 * abs(float(J["shoulder.L"][0]))
        r = REF[age]
        rows.append(f"{label:12s} stature {H * 100:5.1f} cm (ref {r[0]}) | heads in height {H / head:4.2f} (ref {r[1]}; MakeHuman's own head {mh_top / (mh_top - mh_chin):4.2f}) | "
                    f"hip joint / stature {hip / H:4.2f} (crotch ref {r[2]}) | eye line {100 * (top - eye) / head:3.0f}% down the head | "
                    f"chin above neck joint {neck * 100:4.1f} cm | shoulders {sh / head:4.2f} heads | interocular {io * 1000:4.1f} mm")
        f = S + f"lu_{name}.png"
        server.look(name, views=["front", "side"], size=700, focus=[0, 0, 0.95], zoom=1.0, resolution=300, paint=False, save=f)
        cells.append((label, Image.open(f), H))
        f2 = S + f"luf_{name}.png"
        server.look(name, views=["front", "three_quarter"], size=300, focus=[0, -0.03, float(J["lm_nose_tip"][2])], zoom=6.5 * 1.7 / max(H, 0.6) * 0.75, resolution=200, paint=False, save=f2)
        faces.append((label, Image.open(f2)))
    except Exception as e:
        rows.append(f"{label:12s} FAILED: {e!r}"[:400])
    print(rows[-1], flush=True)
open(S + "lineup.txt", "w").write("\n".join(rows))
if cells:
    # each look sheet: front | side panels; crop the middle strip of the front panel
    w = 230
    sh = Image.new("RGB", (w * len(cells), 720), (30, 32, 36))
    for i, (label, im, H) in enumerate(cells):
        pw = im.width // 2
        fr = im.crop((pw // 2 - w // 2 + 15, 0, pw // 2 + w // 2 + 15, min(im.height, 720)))
        sh.paste(fr, (i * w, 0))
        ImageDraw.Draw(sh).text((i * w + 6, 4), f"{label}  {H * 100:.0f} cm", fill=(255, 255, 0))
    fw = sum(f.width for _, f in faces)
    sheet = Image.new("RGB", (max(sh.width, 1), sh.height + 2 * 330), (30, 32, 36))
    sheet.paste(sh, (0, 0))
    x, y = 0, sh.height
    for label, f in faces:
        if x + f.width > sheet.width:
            x, y = 0, y + 330
        sheet.paste(f.crop((0, 0, f.width, min(f.height, 330))), (x, y))
        ImageDraw.Draw(sheet).text((x + 40, y + 4), label, fill=(255, 255, 0))
        x += f.width
    sheet.save(OUT + "sk_21_ages_lineup_clay.png")
    print(sheet.size)
