"""tfail.py <model> ...: each model's block-in table rows that are OUT (id, view, photo, model, diff, tol), + the count."""
import sys
from hifipushie import blockin as bi
for m in sys.argv[1:]:
    rows = [bi._row(r) for r in bi.rows(m)]
    cnt = [r for r in rows if "flag" not in r]
    bad = [r for r in cnt if not r["ok"]]
    print(f"{m}: {len(cnt) - len(bad)} / {len(cnt)} in; out: " + "; ".join(f"{r['id']} {r['view']} photo {r['photo']:.1f} model {r['model']:.1f} ({r['diff']:+.1f}, tol {r['tol']:.1f})" for r in bad))
