"""sheet05.py: hb_05_neck_fixed.png (REFERENCE | NOW | previous native | old attach; rest front / side / back /
three-quarter raking, then head turned 45 and looking up), hb_06_figures.png (full figures), hb_07_body_range.png."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
from hifipushie import onemesh, resources, store
import sheet04

D, OUT = "/mnt/data/hifipushie/headbody", "/mnt/data/hifipushie/headbody/out"
REF, HR = "/home/joe/dev/hifipushie/workspace/neck_refs", "/home/joe/dev/hifipushie/workspace/human_renders"
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
fit = sheet04.fit
DSC = "DSC_6393_Bald_man_working_out_with_a_15_lb_dumbbell_looking_off_to_the_side_in_a_bright_gym.jpg"
BL = [("TESS", "tess", "nt_N06", (85, 300), {"front": ("Female_neck.jpg", (0.05, 0, 0.8, 1)), "side": ("Young_woman_s_neck.jpg", None), "back": ("Sunburnt_neck_and_shoulders.jpg", None),
                                              "three_quarter": ("Gray1194.png", None), "turned": ("Young_woman_s_neck.jpg", None), "up": ("Female_neck.jpg", (0.05, 0, 0.8, 1))}),
      ("GARRETT", "garrett", "ng_N05", (102, 323), {"front": ("Gray1195.png", None), "side": ("Adam_s_apple_35.jpg", (0, 0, 0.75, 1)), "back": ("Cou.jpg", (0.15, 0, 0.85, 1)),
                                                    "three_quarter": (DSC, (0.25, 0, 0.75, 1)), "turned": ("Adam_s_apple_35.jpg", (0, 0, 0.75, 1)), "up": ("Gray1195.png", None)})]
T = 520
ROWS = ["front", "side", "back", "three_quarter", "turned", "up"]
LAB = {"front": "REST front", "side": "REST side", "back": "REST back", "three_quarter": "REST three-quarter", "turned": "HEAD TURNED 45", "up": "LOOKING UP 35"}


def neck_sheet():
    HEAD = 250
    W = Image.new("RGB", (2 * (4 * T + 30) + 20, HEAD + len(ROWS) * (T + 6) + 20), (250, 250, 250))
    d = ImageDraw.Draw(W)
    with resources.heavy("headbody sheet05 poses", gb=8):
        for bi_, (who, tag, old, prevn, refs) in enumerate(BL):
            x0 = 20 + bi_ * (4 * T + 30)
            rn = onemesh.attach_report(store.load(f"hb_{tag}")["base"])
            ro = onemesh.attach_report(store.load(old)["base"])
            ck = {c["name"]: c for c in rn["checks"]}
            d.text((x0, 8), f"{who}:  REFERENCE  |  NOW  |  PREVIOUS NATIVE  |  OLD ATTACH", font=F(40), fill=(0, 0, 0))
            cp, tp = ck["chin over the pit of the throat"], ck["top of head over the pit of the throat"]
            d.text((x0, 64), f"CHIN over the pit of the throat:  now {rn['chin_over_pit']*1e3:.0f} mm   previous {prevn[0]}   old {ro['chin_over_pit']*1e3:.0f}   ANSUR {cp['expected']*1e3:.0f} +- {cp['sd']*1e3:.0f}", font=F(27), fill=(0, 90, 30))
            d.text((x0, 104), f"TOP OF HEAD over the pit:  now {rn['top_over_pit']*1e3:.0f} mm   previous {prevn[1]}   old {ro['top_over_pit']*1e3:.0f}   ANSUR {tp['expected']*1e3:.0f} +- {tp['sd']*1e3:.0f}", font=F(27), fill=(0, 90, 30))
            ng = ck["neck girth"]
            d.text((x0, 144), f"NECK GIRTH: head {rn['neck']['head']*1e3:.0f} mm, body's own {rn['neck']['body']*1e3:.0f}   ANSUR {ng['expected']*1e3:.0f} +- {ng['sd']*1e3:.0f}     {rn['heads_tall']:.1f} heads tall at {rn['stature']:.3f} m", font=F(27), fill=(0, 90, 30))
            d.text((x0, 190), ("FLAG: " + rn["flags"][0][:118]) if rn["flags"] else "report: all attach checks inside their ranges", font=F(20), fill=(170, 30, 30) if rn["flags"] else (0, 90, 30))
            now = sheet04.tiles(f"{D}/export_{tag}/hb_{tag}.glb", False)
            prev = sheet04.tiles(f"{D}/export_{tag}_prev/hb_{tag}.glb", False)
            pose = {"turned": ("HEAD TURNED 45", 0), "up": ("NECK BENT 35 (looking up)", 1)}
            for r, row in enumerate(ROWS):
                y = HEAD + r * (T + 6)
                rf, box = refs[row]
                cells = [fit(f"{REF}/{rf}", T, T, box)]
                if row in pose:
                    pn, vi = pose[row]
                    cells += [now[(pn, "raking")][vi].resize((T, T)), prev[(pn, "raking")][vi].resize((T, T)), None]
                else:
                    cells += [fit(f"{OUT}/XN_hb_{tag}_{row}.png", T, T, (0.05, 0.03, 1, 0.95)), fit(f"{OUT}/N_hb_{tag}_{row}.png", T, T, (0.05, 0.03, 1, 0.95)),
                              fit(f"{OUT}/N_{old}_{row}.png", T, T, (0.05, 0.03, 1, 0.95))]
                for c, im in enumerate(cells):
                    if im is None:
                        d.text((x0 + c * T + 30, y + T // 2), "(no old-attach export:\n its exports had the\n face-shape regression)", font=F(22), fill=(120, 120, 120))
                        continue
                    W.paste(im, (x0 + c * T, y))
                    d.text((x0 + c * T + 6, y + 4), f"{('REFERENCE', 'NOW', 'PREVIOUS', 'OLD')[c]}  {LAB[row]}", font=F(20), fill=(255, 220, 0))
    W.save(f"{HR}/hb_05_neck_fixed.png")


def figures():
    Tf = 640
    W = Image.new("RGB", (6 * Tf + 40, 2 * (Tf + 110) + 70), (250, 250, 250))
    d = ImageDraw.Draw(W)
    d.text((20, 10), "FULL FIGURES front / side:   NOW (head seated by its own neck base)   |   PREVIOUS NATIVE   |   OLD ATTACH", font=F(38), fill=(0, 0, 0))
    for r, (who, tag, old, _, _) in enumerate(BL):
        y = 70 + r * (Tf + 110)
        for c, (m, pre, lab) in enumerate(((f"hb_{tag}", "XF_", "NOW"), (f"hb_{tag}", "L_", "PREVIOUS NATIVE"), (old, "L_", "OLD ATTACH"))):
            rep = onemesh.attach_report(store.load(m)["base"]) if c != 1 else None
            for v, view in enumerate(("front", "side")):
                W.paste(fit(f"{OUT}/{pre}{m}_{view}.png", Tf, Tf), (20 + (2 * c + v) * Tf, y + 100))
            txt = f"{who} {lab}" + (f":  {rep['heads_tall']:.1f} HEADS TALL, head {rep['head_height']*1e3:.0f} mm, chin {rep['chin_over_pit']*1e3:.0f} mm over the pit" if rep else " (hb_01's)")
            d.text((20 + 2 * c * Tf + 8, y + 30), txt, font=F(24), fill=(0, 90, 30) if c == 0 else (60, 60, 60))
    W.save(f"{HR}/hb_06_figures.png")


def body_range():
    names = ["woman", "man", "heavy", "veryslim", "muscular", "tall", "short", "old", "teen", "child"]
    Tf = 520
    cols = 2
    cw = 3 * Tf + 30
    W = Image.new("RGB", (cols * cw + 20, 80 + 5 * (Tf + 150)), (250, 250, 250))
    d = ImageDraw.Draw(W)
    d.text((20, 10), "BODY RANGE: GNM class-mean heads, the same attach code, nothing per character.  figure front | side | neck", font=F(36), fill=(0, 0, 0))
    for i, nm in enumerate(names):
        m = f"hb_r_{nm}"
        sp = store.load(m)
        rep = onemesh.attach_report(sp["base"])
        x, y = 20 + (i % cols) * cw, 80 + (i // cols) * (Tf + 150)
        bp = {k: v for k, v in sp["base"]["body"].items() if k in ("age", "sex", "weight", "muscle", "height")}
        d.text((x, y), f"{nm.upper()}  {bp}", font=F(26), fill=(0, 0, 0))
        d.text((x, y + 34), f"stature {rep['stature']:.2f} m   {rep['heads_tall']:.1f} HEADS TALL   neck girth head {rep['neck']['head']*1e3:.0f} / body {rep['neck']['body']*1e3:.0f} mm   chin {rep['chin_over_pit']*1e3:.0f} mm over the pit",
               font=F(26), fill=(0, 90, 30))
        fl = [f for f in rep["flags"]]
        d.text((x, y + 70), ("FLAGS: " + " | ".join(f.split(":")[0] if f.startswith(("NECK", "age")) else f.split(" is outside")[0] + " out of range" for f in fl))[:150] if fl else "no flags", font=F(22),
               fill=(170, 30, 30) if fl else (0, 90, 30))
        for c, fn in enumerate((f"RF_{m}_front.png", f"RF_{m}_side.png", f"RN_{m}_three_quarter.png")):
            W.paste(fit(f"{OUT}/{fn}", Tf, Tf, None if c < 2 else (0.05, 0.03, 1, 0.95)), (x + c * Tf, y + 104))
    W.save(f"{HR}/hb_07_body_range.png")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        {"neck": neck_sheet, "figures": figures, "range": body_range}[a]()
        print("saved", a)
