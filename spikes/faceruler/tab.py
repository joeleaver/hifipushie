"""tab.py <set>...: arms_<set>.json (+ rescore_<set>.json if there) as tables: per case, by difficulty, by region."""
import json
import os
import sys

G = os.environ["G"] + "/out"
ARMS = ("mesh:all", "mesh:top8", "pic:all", "pic:top8", "pic:top8x2", "pic:top4", "hair:top8", "cam:top8", "cam:all", "fit")
rows = {}
for s in sys.argv[1:]:
    d = json.load(open(f"{G}/arms_{s}.json"))
    try:
        rs = json.load(open(f"{G}/rescore_{s}.json"))
    except Exception:  # noqa: BLE001
        rs = {}
    for k, v in d.items():
        v["driver"] = (rs.get(k) or {}).get("driver")
        v["oracle"] = (rs.get(k) or {}).get("oracle")
        rows[k] = v
arms = ARMS + tuple(a for a in ("driver", "oracle") if any(r.get(a) for r in rows.values()))
print("case | grade | regions | " + " | ".join(arms) + "   (region closed / ID closed, * = PASS new rule, o = old rule)")
for k, r in rows.items():
    cells = []
    for a in arms:
        x = r.get(a)
        cells.append("-" if not x else f"{x['region']:.2f}/{x['id']:.2f}{'*' if x['pass'] else ''}{'o' if x['pass_old'] else ''}")
    print(f"{k} | {r['difficulty']} | {'+'.join(r['regions'])} | " + " | ".join(cells))


def count(sel, a, key="pass"):
    R = [r for r in rows.values() if sel(r) and r.get(a)]
    return f"{sum(r[a][key] for r in R)}/{len(R)}"


print("\nby difficulty (new rule):")
for dif in ("easy", "medium", "hard", "all"):
    print(f"  {dif:7s} " + ", ".join(f"{a} {count(lambda r: dif in ('all', r['difficulty']), a)}" for a in arms))
print("old rule, all: " + ", ".join(f"{a} {count(lambda r: True, a, 'pass_old')}" for a in arms))
print("\nby region (new rule; a pair counts under each of its regions):")
for reg in ("skull", "jaw", "jaw_full", "chin", "mouth", "nose", "eyes", "brows", "cheeks"):
    print(f"  {reg:9s} " + ", ".join(f"{a} {count(lambda r: reg in r['regions'], a)}" for a in arms))
print("\nruler rms error over the 23 measures (mm): " + ", ".join(
    f"{k} {sum(r['ruler_rms_err'][k] for r in rows.values()) / len(rows):.2f}" for k in ("pic", "hair", "cam")))
