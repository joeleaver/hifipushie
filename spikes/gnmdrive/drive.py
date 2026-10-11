"""drive.py: the DRIVER's tool (sees renders only, never B's numbers).

  drive.py show <case> [feature]          sheet: CURRENT vs TARGET (clay, raking light, tracing of the target's
                                          silhouette over the current), front / 3/4 / profile; feature = head (default)
                                          | eyes | brows | nose | mouth | chin_jaw | cheeks
  drive.py try <case> '<moves json>' [feature] [--seen "..."] [--why "..."]
                                          a TRIAL from the current head: before | trial | target sheet (head + the
                                          feature's crops). Nothing is committed.
  drive.py keep <case> ["verdict"]        commit the last trial (the move is logged with seen / why / verdict)
  drive.py reject <case> ["verdict"]      drop the last trial (logged as rejected)
  drive.py done <case> ["note"]           the driver stops on this case
  drive.py log <case>                     the moves so far
  drive.py atlas "<words>" [sort]         gnm_controls.query (the atlas): controls that move a zone
  drive.py describe <control>             one control described
  drive.py vocab                          the block-in move vocabulary
  drive.py macros                         what each macro means (+ / - in an artist's words)
Moves are block-in moves: <macro> (free), <macro>! (held), nd:<gap>, pc:<region><k>, sculpt:<zone> / relief:<zone> (mm,
with |hold=..|free=..), gnm:<control>. Sheets are written to cases/<case>/ and the path is printed."""
import json
import sys
import time

import numpy as np

import drv
import gnmc
from hifipushie import blockin as bi, gnm_controls as gcm, humanmacro as hm

PX = 240


def _mmpx(feature):
    return 2000.0 * (0.135 if feature == "head" else drv.FOCUS[feature][1]) / PX


def _load(case):
    d = drv.CASES / case
    st = json.loads((d / "state.json").read_text())
    tgt = np.load(d / "target.npy") if (d / "target.npy").exists() else None
    if tgt is None:   # the target's identity is stored hidden; a driver-safe copy of the RENDERS only is made here
        h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
        tgt = np.asarray(h["B"], float)
    return d, st, tgt


def _save(d, st):
    (d / "state.json").write_text(json.dumps(st))


def apply(c, moves):
    c = np.asarray(c, float).copy()
    for k, v in moves.items():
        c = c + float(v) * bi.direction(k)
    return c


def _rows(heads, labels, cB, feature):
    rows, rl = [], []
    for h, lab in zip(heads, labels):
        rows.append(drv.view_imgs(h, cB, feature, px=PX))
        rl.append(lab)
    work = [(h, lab) for h, lab in zip(heads, labels) if not lab.startswith("TARGET")][-1:]   # the newest head only
    for h, lab in work:
        rows.append(drv.view_imgs(h, cB, feature, px=PX, light="rake"))
        rl.append(lab + "\nraking light")
    rows.append(drv.view_imgs(cB, cB, feature, px=PX, light="rake"))
    rl.append("TARGET\nraking light")
    # tracing: the target's silhouette (red) over each non-target head (green = its own); onion skin (50 % blend)
    tg, tf = drv.view_imgs(cB, cB, feature, px=PX, fg=True)
    for h, lab in work:
        im, fg = drv.view_imgs(h, cB, feature, px=PX, fg=True)
        rows.append([drv.trace(a, f, g) for a, f, g in zip(im, fg, tf)])
        rl.append(lab + "\ntrace: red =\ntarget outline,\ngreen = this")
        rows.append([drv.blend(a, b) for a, b in zip(im, tg)])
        rl.append(lab + "\nonion skin:\n50 % with target")
    return rows, rl


CHUNK = 3   # rows per PNG: tall sheets (6-8 rows, ~1750 px) are mis-seen when viewed (identical rows read as different
            # heads: three drivers thought the BEFORE row was stale; the pixels were identical), so sheets are split


def _save_sheet(rows, rl, cols, title, base):
    paths = []
    for k in range(0, len(rows), CHUNK):
        S = gnmc.grid(rows[k:k + CHUNK], cols_labels=cols, rows_labels=rl[k:k + CHUNK],
                      title=title + (f" [part {k // CHUNK + 1}]" if len(rows) > CHUNK else ""), lw=120)
        p = base.with_name(base.stem + f"_p{k // CHUNK + 1}.png")
        S.save(p)
        paths.append(str(p))
    return paths


def show(case, feature="head"):
    d, st, cB = _load(case)
    rows, rl = _rows([st["c"], cB], ["CURRENT", "TARGET"], cB, feature)
    cols = drv.FOCUS[feature][2]
    ps = _save_sheet(rows, rl, cols, f"{case}: current vs target ({feature}; 1 px = {_mmpx(feature):.2f} mm)",
                     d / f"show_{len(st['moves']):02d}_{feature}.png")
    print("\n".join(ps))


def trial(case, moves, feature="head", seen="", why=""):
    d, st, cB = _load(case)
    c1 = apply(st["c"], moves)
    st["trial"] = {"moves": moves, "c": c1.tolist(), "seen": seen, "why": why, "feature": feature}
    _save(d, st)
    n = len(st["moves"])
    paths = []
    for f in dict.fromkeys(["head", feature]):
        rows, rl = _rows([st["c"], c1, cB], ["BEFORE", "TRIAL", "TARGET"], cB, f)
        k = len(st["moves"]) + len(st.get("rejected", []))
        paths += _save_sheet(rows, rl, drv.FOCUS[f][2], f"{case} trial {k}: {json.dumps(moves)} ({f}; 1 px = {_mmpx(f):.2f} mm)",
                             d / f"trial{k:02d}_{f}.png")
    dz = hm.read(c1[:hm.K])
    z0 = hm.read(np.asarray(st["c"])[:hm.K])
    ch = sorted(((k, dz[k] - z0[k]) for k in dz if k != "head_size"), key=lambda t: -abs(t[1]))[:6]
    print("\n".join(paths))
    print(f"|move| {np.linalg.norm(c1 - np.asarray(st['c'])):.2f} sd; macros moved most (sd): "
          + ", ".join(f"{k} {v:+.2f}" for k, v in ch))


def keep(case, verdict="", ok=True):
    d, st, _ = _load(case)
    t = st.get("trial")
    if not t:
        raise SystemExit("no trial")
    t["verdict"] = verdict
    t["time"] = time.strftime("%H:%M:%S")
    if ok:
        st["c"] = t["c"]
        st["moves"].append({k: v for k, v in t.items() if k != "c"})
    else:
        st.setdefault("rejected", []).append({k: v for k, v in t.items() if k != "c"})
    st["trial"] = None
    _save(d, st)
    print(("kept" if ok else "rejected"), json.dumps(t["moves"]), f"({len(st['moves'])} kept so far)")


def done(case, note=""):
    d, st, _ = _load(case)
    st["done"] = note or True
    _save(d, st)
    print("done", case)


def logcmd(case):
    d, st, _ = _load(case)
    for i, m in enumerate(st["moves"]):
        print(i, json.dumps(m["moves"]), "|", m.get("seen", ""), "|", m.get("verdict", ""))
    for m in st.get("rejected", []):
        print("rejected", json.dumps(m["moves"]), "|", m.get("verdict", ""))


if __name__ == "__main__":
    a = sys.argv[1:]
    kw = {}
    for flag in ("--seen", "--why"):
        if flag in a:
            i = a.index(flag)
            kw[flag[2:]] = a[i + 1]
            del a[i:i + 2]
    cmd = a[0]
    if cmd == "show":
        show(a[1], *(a[2:3]))
    elif cmd == "try":
        trial(a[1], json.loads(a[2]), *(a[3:4]), **kw)
    elif cmd == "keep":
        keep(a[1], " ".join(a[2:]))
    elif cmd == "reject":
        keep(a[1], " ".join(a[2:]), ok=False)
    elif cmd == "done":
        done(a[1], " ".join(a[2:]))
    elif cmd == "log":
        logcmd(a[1])
    elif cmd == "atlas":
        print(gcm.text(gcm.query(a[1], sort=a[2] if len(a) > 2 else "score", top=10)))
    elif cmd == "describe":
        print(gcm.text(gcm.describe(a[1])))
    elif cmd == "vocab":
        print(bi.vocabulary())
    elif cmd == "macros":
        for k, (u, t) in hm.MACROS.items():
            print(f"{k} ({u}): {t}")
    elif cmd == "ruler":
        # the RULER (gnmdrive2): the 23 mm measures, target - current (or - the pending trial with `ruler <case> trial`).
        # The target's readings carry a fixed error per case and measure, N(0, 1 mm): what a photo reader gives
        # (clay / photo readers drift 1-1.5 mm), so a driver cannot close below ~1 mm with the ruler alone.
        import zlib
        from hifipushie import gnm_mm
        d, st, cB = _load(a[1])
        cur = st["trial"]["c"] if (len(a) > 2 and a[2] == "trial" and st.get("trial")) else st["c"]
        pair = a[1].split("_")[1]
        bias = np.random.default_rng(zlib.crc32(("ruler" + pair).encode())).normal(0, 1.0, len(gnm_mm.NAMES))
        print(f"ruler {a[1]} ({'TRIAL' if cur is not st['c'] else 'CURRENT'} vs TARGET; the target's readings are good "
              "to about +-1 mm: do not chase gaps under 1.5 mm with it)")
        print(gnm_mm.gaps_text(gnm_mm.gaps(drv.verts(cur), drv.verts(cB), bias)))
    elif cmd == "manual":
        print((drv.G / "manual.md").read_text() if (drv.G / "manual.md").exists() else "no manual yet")
    else:
        print(__doc__)
