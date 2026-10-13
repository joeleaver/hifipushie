"""summ.py: the solvecams tables from out/*.json (markdown on stdout). Shape errors are chinread's errmap terms (after a
similarity, mm); camera errors common.cam_err. Every number is the LAST call of its chain unless said."""
import glob, json, os, re
import numpy as np
S = "/mnt/data/hifipushie/solvecams/out"
R = {os.path.basename(f)[:-5]: json.load(open(f)) for f in glob.glob(f"{S}/sc_*.json")}
rms = lambda x: float(np.sqrt(np.mean(np.square(x)))) if len(x) else float("nan")
mean = lambda x: float(np.mean(x)) if len(x) else float("nan")


def get(h, s, code):
    return R.get(f"sc_{h}_{s}{code}")


def shape_row(lab, cs):
    if not cs:
        return None
    f = lambda k: mean([c[k] for c in cs])
    m = lambda k: mean([abs(c["meas"][k]) for c in cs])
    b = lambda k: mean([c["meas"][k] for c in cs])
    return (f"| {lab} | {len(cs)} | {f('face'):.2f} | {f('low'):.2f} | {f('chin'):.2f} | {f('jaw body'):.2f} | {f('jaw angle'):.2f} | {m('jaw_width'):.1f} ({b('jaw_width'):+.1f}) | {m('gonial_width'):.1f} ({b('gonial_width'):+.1f}) | "
            f"{m('chin_width'):.1f} ({b('chin_width'):+.1f}) | {m('cheekbone_width'):.1f} ({b('cheekbone_width'):+.1f}) | {mean([c.get('relax', 1) for c in cs]):.2f} | {mean([c['dct'] for c in cs]):.1f} |")


SH = "| run | n | face | lower face | chin | jaw body | jaw angle | jaw_width abs (bias) | gonial_width | chin_width | cheekbone_width | sigma x | \\|c - ct\\| |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|"
print("### Shape after the chain (mean over the heads; mm after a similarity; widths: mean |error| (mean error))")
for s in "AB":
    print(f"\nset {s}\n" + SH)
    st = [get(h, s, "fr")["calls"][0] for h in "abcd" if get(h, s, "fr")]
    print(shape_row("start (class mean)", st))
    for code, lab in (("fr", "free (first call refit)"), ("tr", "trust"), ("frd", "free + dense"), ("trd", "trust + dense"), ("tc", "TRUE cameras, frozen"), ("tcd", "TRUE cameras, frozen + dense")):
        r = shape_row(lab, [get(h, s, code)["calls"][-1] for h in "abcd" if get(h, s, code)])
        if r:
            print(r)
print("\nper head, set A: face / lower face / jaw_width error / gonial_width error")
print("| run | a | b | c | d |\n|---|---|---|---|---|")
for code in ("start", "fr", "tr", "frd", "trd", "tc", "tcd", "r0", "tf", "tt"):
    cells = []
    for h in "abcd":
        r = get(h, "A", "fr" if code == "start" else code)
        if not r:
            cells.append("-"); continue
        c = r["calls"][0 if code == "start" else -1]
        cells.append(f"{c['face']:.2f} / {c['low']:.2f} / {c['meas']['jaw_width']:+.1f} / {c['meas']['gonial_width']:+.1f}")
    print(f"| {code} | " + " | ".join(cells) + " |")

print("\n### Camera recovery (rms over the heads of each view's error; deg, %, mm)")
print("| set | view | stage | yaw | pitch | roll | scale % | distance % | centre mm | worst yaw | worst pitch |\n|---|---|---|---|---|---|---|---|---|---|---|")
for s, vs in (("A", ("f", "q45", "s90")), ("B", ("f", "q23", "s72"))):
    for v in vs:
        for code, idx, lab in (("fr", 0, "block_in_start refit"), ("tr", -1, "after trust chain"), ("fr", -1, "after free chain"), ("trd", -1, "trust + dense"), ("frd", -1, "free + dense")):
            E = [get(h, s, code)["calls"][idx]["cams"][v] for h in "abcd" if get(h, s, code)]
            if E:
                g = lambda k: rms([e[k] for e in E])
                w = lambda k: max([e[k] for e in E], key=abs)
                print(f"| {s} | {v} | {lab} ({len(E)}) | {g('yaw'):.1f} | {g('pitch'):.1f} | {g('roll'):.1f} | {g('scale'):.1f} | {g('dist'):.0f} | {rms([np.hypot(e['dx'], e['dy']) for e in E]):.1f} | {w('yaw'):+.1f} | {w('pitch'):+.1f} |")

print("\n### Start-error sweep (set A, TRUE cameras as the start, one freedom moved; the moved freedom's error after 3 calls, per head a / c)")
print("| start error | free: end error a / c | trust: end error a / c | free: face, jaw_width a / c | trust: face, jaw_width a / c | free + dense | trust + dense |\n|---|---|---|---|---|---|---|")
SW = [("none", "", "s90", "yaw"), ("s90 yaw -5", "s5m", "s90", "yaw"), ("s90 yaw -10", "s10m", "s90", "yaw"), ("s90 yaw -15", "s15m", "s90", "yaw"), ("s90 yaw +10", "s10p", "s90", "yaw"),
      ("q45 yaw -5", "q5m", "q45", "yaw"), ("q45 yaw -10", "q10m", "q45", "yaw"), ("q45 yaw -15", "q15m", "q45", "yaw"), ("q45 yaw +10", "q10p", "q45", "yaw"),
      ("front pitch +5", "p5p", "f", "pitch"), ("front pitch +10", "p10p", "f", "pitch"), ("front pitch -5", "p5m", "f", "pitch"),
      ("front distance -50 %", "dm50", "f", "dist"), ("front distance -30 %", "dm30", "f", "dist"), ("front distance +40 %", "dp40", "f", "dist"), ("front distance +100 %", "dp100", "f", "dist")]
for lab, k, v, what in SW:
    def cell(mode, kind, dn=""):
        out = []
        for h in "ac":
            r = get(h, "A", (("t" + mode) if not k else mode + k) + dn)
            if not r:
                out.append("-"); continue
            c, c0 = r["calls"][-1], r["calls"][0]
            if kind == "cam":
                out.append(f"{c0['cams'][v][what]:+.1f} -> {c['cams'][v][what]:+.1f}")
            else:
                out.append(f"{c['face']:.2f}, {c['meas']['jaw_width']:+.1f}")
        return " / ".join(out)
    dn = lambda mode: " / ".join((lambda r: "-" if not r else f"{r['calls'][-1]['cams'][v][what]:+.1f}; {r['calls'][-1]['face']:.2f}, {r['calls'][-1]['meas']['jaw_width']:+.1f}")(get(h, "A", ((("t" + mode) if not k else mode + k) + "d"))) for h in "ac")
    print(f"| {lab} | {cell('f', 'cam')} | {cell('t', 'cam')} | {cell('f', 'shape')} | {cell('t', 'shape')} | {dn('f')} | {dn('t')} |")

print("\n### Shape per unit of camera error (set A, TRUE cameras, the error FROZEN in: yaw / pitch frozen, shift / scale / roll free; change against the same chain with no error; mm)")
print("| camera error | heads | face rms | lower face | jaw_width | gonial_width | chin_width | cheekbone_width | chin_length | eyes_forward | sigma x |\n|---|---|---|---|---|---|---|---|---|---|---|")
PR = [("s90 yaw -5", "rs5m"), ("s90 yaw +5", "rs5p"), ("s90 yaw -10", "rs10m"), ("q45 yaw -5", "rq5m"), ("q45 yaw +5", "rq5p"), ("q45 yaw -10", "rq10m"), ("front pitch +5", "rp5p"), ("front pitch -5", "rp5m"), ("front yaw 5", "ry5"),
      ("front distance -50 %", "rdm50"), ("front distance -30 %", "rdm30"), ("front distance +40 %", "rdp40"), ("front distance +100 %", "rdp100"), ("q45 distance -30 %", "rqdm30"), ("s90 distance -30 %", "rsdm30"),
      ("DENSE: s90 yaw -5", "rs5md"), ("DENSE: q45 yaw -5", "rq5md"), ("DENSE: front pitch +5", "rp5pd"), ("DENSE: front distance -50 %", "rdm50d"), ("DENSE: front distance +100 %", "rdp100d")]
for lab, code in PR:
    base = "r0d" if code.endswith("d") and "DENSE" in lab else "r0"
    D = []
    for h in "abcd":
        a, b = get(h, "A", code), get(h, "A", base)
        if a and b:
            ca, cb = a["calls"][-1], b["calls"][-1]
            D.append([ca["face"] - cb["face"], ca["low"] - cb["low"]] + [ca["meas"][m] - cb["meas"][m] for m in ("jaw_width", "gonial_width", "chin_width", "cheekbone_width", "chin_length", "eyes_forward")] + [ca.get("relax", 1)])
    if D:
        D = np.array(D)
        print(f"| {lab} | {len(D)} | " + " | ".join(f"{x:+.2f}" for x in D[:, :8].mean(0)) + f" | {D[:, 8].mean():.2f} |")
b0 = [get(h, "A", "r0")["calls"][-1] for h in "abcd" if get(h, "A", "r0")]
print("\nthe no-error chain itself (r0):\n" + SH)
print(shape_row("true yaw / pitch frozen, shift / scale / roll free", b0))
b1 = [get(h, "A", "r0d")["calls"][-1] for h in "ac" if get(h, "A", "r0d")]
if b1:
    print(shape_row("the same + dense (a, c)", b1))

print("\n### Other front views (heads a, c; sets P = camera pitched +8, M = -8, N = 40 mm lens, F = 200 mm): front camera error at the start -> end, face / jaw_width")
print("| set | run | a | c |\n|---|---|---|---|")
for s, v in (("P", "fu"), ("M", "fd"), ("N", "fn"), ("F", "ff")):
    for code in ("fr", "tr", "tc"):
        cells = []
        for h in "ac":
            r = get(h, s, code)
            if not r:
                cells.append("-"); continue
            c0, c = r["calls"][0], r["calls"][-1]
            cells.append(f"pitch {c0['cams'][v]['pitch']:+.1f} -> {c['cams'][v]['pitch']:+.1f}, dist {c0['cams'][v]['dist']:+.0f} % -> {c['cams'][v]['dist']:+.0f} %; face {c0['face']:.2f} -> {c['face']:.2f}, jaw_width {c['meas']['jaw_width']:+.1f}")
        print(f"| {s} | {code} | " + " | ".join(cells) + " |")
