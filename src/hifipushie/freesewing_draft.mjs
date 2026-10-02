// Drafts one FreeSewing design and prints its parts as JSON (run by freesewing.py with NODE_PATH = the pack's
// node_modules). stdin: {"design": "simon", "measurements": {...mm}, "options": {...}, "sa": mm}.
// stdout: {"parts": {name: {"points", "paths", "snippets"}}, "cutlist", "logs"}. Units mm, y down (FreeSewing's).
import fs from 'fs'

const req = JSON.parse(fs.readFileSync(0, 'utf8'))
const mod = await import('@freesewing/' + req.design)
const name = req.design.charAt(0).toUpperCase() + req.design.slice(1)
const Design = mod[name]
if (!Design) throw new Error(`@freesewing/${req.design} has no export ${name}`)
const pattern = new Design({ measurements: req.measurements, options: req.options || {}, sa: req.sa ?? 10,
  complete: true, paperless: false })
pattern.draft()
const xy = (p) => (p ? [p.x, p.y] : null)
const out = { parts: {}, cutlist: {}, logs: {} }
const set = pattern.setStores[0]
out.cutlist = set.get('cutlist') || {}
for (const k of ['error', 'warn', 'warning']) {
  const v = pattern.store.logs?.[k] ?? set.logs?.[k]
  if (v && v.length) out.logs[k] = v.map(String).slice(0, 40)
}
for (const [pn, part] of Object.entries(pattern.parts[0])) {
  if (part.hidden) continue
  const points = {}
  for (const [k, p] of Object.entries(part.points)) points[k] = xy(p)
  const paths = {}
  for (const [k, path] of Object.entries(part.paths)) {
    if (k.startsWith('__')) continue
    paths[k] = { hidden: !!path.hidden, class: path.attributes?.get?.('class') || '',
      ops: path.ops.map((o) => ({ type: o.type, to: xy(o.to), cp1: xy(o.cp1), cp2: xy(o.cp2) })) }
  }
  const snippets = Object.entries(part.snippets).map(([k, s]) => ({ name: k, def: s.def, at: xy(s.anchor) }))
  out.parts[pn] = { points, paths, snippets }
}
process.stdout.write(JSON.stringify(out))
