"""Print the method table kept in D/out/table.json (or another json given)."""
import json
import sys

import rs
import table

f = rs.D / "out" / (sys.argv[1] if len(sys.argv) > 1 else "table.json")
table.show(json.loads(f.read_text()))
