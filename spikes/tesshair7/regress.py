"""regress.py [run|accept|sheet] [only=<name,..>] [tag=<run tag>]: the HAIR REGRESSION SHEET (tesshair7; the coordinator:
"re-renders the current best styles after any change and puts them beside the last accepted renders, so a fix can't
silently break what worked. Run it before every gate").

The accepted set is spikes/tesshair7/accepted.json: [{"name", "head", "style", "look", "views", "stage"}]: Tess's best
(through the fitted reference cameras, shots7) and the riffs on two other heads (look_hair views through a synced copy
of the head: `stage`). Each is regrown THROUGH THE TOOL (server.tie_hair on a fresh copy th_RG_<name> of its head) with
the code as it is now, so every change to hair code, style defaults or look defaults shows.

  run     regrow + render every entry -> $TOUT/reg/<tag>/<name>_<view>.png      (HEAVY: one job; run through run.sh)
  accept  the run <tag> becomes the accepted renders ($TOUT/reg/accepted/)       (only after a human look)
  sheet   $TOUT/reg/sheet_<tag>.png: per entry and view ACCEPTED | NOW | difference (x4), and the mean absolute
          difference per entry (0-255): renders are deterministic (two runs: 0.00), so over 0.3 = something moved; the table is printed and saved as .txt
`run` then `sheet` is the gate check; `accept` when the new look is the one wanted."""
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).parent
OUT = Path(os.environ.get("TOUT", "/mnt/data/hifipushie/tesshair7/out")) / "reg"
mode = sys.argv[1] if len(sys.argv) > 1 and "=" not in sys.argv[1] else "run"
kw = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
tag = kw.get("tag", "now")
entries = json.loads((HERE / "accepted.json").read_text())
if kw.get("only"):
    entries = [e for e in entries if e["name"] in kw["only"].split(",")]


def arg(v):
    if v is None:
        return None
    if isinstance(v, str):
        return json.loads((HERE / v).read_text())
    return v


def run():
    import runpy

    from hifipushie import resources, server, store
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    with resources.heavy("tesshair7 regress", gb=8):
        for e in entries:
            m = f"th_RG_{e['name']}"
            md = store.HOME / m
            md.mkdir(exist_ok=True)
            sp = json.loads((store.HOME / e["head"] / "spec.json").read_text())
            sp.pop("hair", None)
            (md / "spec.json").write_text(json.dumps(sp, indent=1))
            if (store.HOME / e["head"] / "human_refs.json").exists():
                shutil.copy(store.HOME / e["head"] / "human_refs.json", md / "human_refs.json")
            server.tie_hair(m, arg(e["style"]), carry_from=e.get("carry_from"), look=arg(e.get("look")))
            if e.get("seed") is not None:
                server.groom_hair(m, groom={"seed": int(e["seed"])}, replace=True)
            if e.get("shots"):  # through the reference's fitted cameras on the shared dressed stage
                old = sys.argv
                sys.argv = [str(HERE / "shots7.py"), m, f"size={e.get('size', 768)}", "views=" + ",".join(e["views"])]
                if e.get("stage"):
                    sys.argv.append(f"stage={e['stage']}")
                os.environ["TOUT"] = str(d)
                try:
                    runpy.run_path(str(HERE / "shots7.py"), run_name="__main__")
                finally:
                    sys.argv = old
                for v in e["views"]:
                    os.replace(d / f"s_{m}_{v}.png", d / f"{e['name']}_{v}.png")
            else:  # look_hair through a synced copy of the head
                r = server.look_hair(m, views=e["views"], size=int(e.get("size", 420)), clay=False, stage=e["stage"],
                                     save=str(d / f"{e['name']}_all.png"))
                del r
            print("rendered", e["name"], flush=True)


def accept():
    a = OUT / "accepted"
    a.mkdir(parents=True, exist_ok=True)
    for f in (OUT / tag).glob("*.png"):
        shutil.copy(f, a / f.name)
    print("accepted", tag, "->", a)


def sheet():
    try:
        F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except OSError:
        F = ImageFont.load_default()
    rows, lines = [], []
    for e in entries:
        names = [f"{e['name']}_{v}.png" for v in e["views"]] if e.get("shots") else [f"{e['name']}_all.png"]
        diffs = []
        for n in names:
            fa, fn = OUT / "accepted" / n, OUT / tag / n
            if not fn.exists():
                lines.append(f"{e['name']:12s} {n}: NOT RENDERED")
                continue
            now = Image.open(fn).convert("RGB")
            acc = Image.open(fa).convert("RGB").resize(now.size) if fa.exists() else Image.new("RGB", now.size, (128, 128, 128))
            df = ImageChops.difference(acc, now)
            mad = float(np.asarray(df, float).mean())
            diffs.append(mad)
            h = 360
            tiles = [im.resize((int(im.width * h / im.height), h)) for im in (acc, now, df.point(lambda x: min(255, 4 * x)))]
            row = Image.new("RGB", (sum(t.width for t in tiles), h + 44), "white")
            x = 0
            for t in tiles:
                row.paste(t, (x, 44))
                x += t.width
            ImageDraw.Draw(row).text((8, 6), f"{n}   ACCEPTED | NOW | DIFF x4   mean |diff| {mad:.2f}"
                                     + ("" if fa.exists() else "   (no accepted render yet)"), fill="black", font=F)
            rows.append(row)
        if diffs:
            flag = "MOVED" if max(diffs) > 0.3 else "same"  # (the noise floor is 0: grooms and EEVEE renders are deterministic)
            lines.append(f"{e['name']:12s} mean |diff| {np.mean(diffs):5.2f}  max {max(diffs):5.2f}  {flag}")
    if rows:
        W = max(r.width for r in rows)
        S = Image.new("RGB", (W, sum(r.height for r in rows)), "white")
        y = 0
        for r in rows:
            S.paste(r, (0, y))
            y += r.height
        S.save(OUT / f"sheet_{tag}.png")
    txt = "\n".join(lines)
    (OUT / f"sheet_{tag}.txt").write_text(txt + "\n")
    print(txt)
    print("sheet", OUT / f"sheet_{tag}.png")


{"run": run, "accept": accept, "sheet": sheet}[mode]()
