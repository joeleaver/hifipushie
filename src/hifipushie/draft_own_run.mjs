// Drafts the AGENT'S OWN FreeSewing design (draft_own.py runs it: cwd = a scratch dir holding design.mjs and a
// node_modules link to the pack; no network, fs reads only, a timeout). stdin: {"measurements": {...}, "options": {...},
// "sa": mm}. design.mjs: `export default new Design({...})` (or `export const design`). stdout: {"parts": {name:
// {"points", "paths", "snippets"}}, "measurements", "logs", "store"} (freesewing_draft.mjs's form) or {"error", "line"}.
import fs from 'fs'
import path from 'path'

const fail = (e) => {
  const s = String((e && e.stack) || e)
  const m = s.match(/design\.mjs:(\d+)(?::(\d+))?/)
  process.stdout.write(JSON.stringify({ error: String((e && e.message) || e).split('\n')[0],
    line: m ? Number(m[1]) : null, col: m && m[2] ? Number(m[2]) : null }))
  process.exit(0)
}
let mod, pattern
const req = JSON.parse(fs.readFileSync(0, 'utf8'))
try {
  mod = await import(path.resolve('design.mjs'))
} catch (e) { fail(e) }
const D = mod.default ?? mod.design
if (typeof D !== 'function') fail(new Error('design.mjs exports no design: end it with `export default new Design({ parts: [...] })`'))
try {
  pattern = new D({ measurements: req.measurements, options: req.options || {}, sa: req.sa ?? 10, complete: true,
    paperless: false })
  pattern.draft()
} catch (e) { fail(e) }
const xy = (p) => (p ? [p.x, p.y] : null)
const out = { parts: {}, logs: {}, store: {}, measurements: [] }
const set = pattern.setStores[0]
const logs = (k) => [].concat(pattern.store.logs?.[k] || [], set.logs?.[k] || []).flat(3)
  .map((v) => String(v?.stack || v))
for (const k of ['error', 'warn', 'warning']) {
  const v = logs(k)
  if (v.length) out.logs[k] = v.slice(0, 40)
}
const err = (out.logs.error || []).join('\n')
const at = err.match(/design\.mjs:(\d+)/)
if (at) out.logs.line = Number(at[1])
out.measurements = [...new Set(Object.values(pattern.config?.parts || {}).flatMap((p) => p.measurements || []))]
for (const [pn, part] of Object.entries(pattern.parts[0] || {})) {
  if (part.hidden) continue
  const points = {}
  for (const [k, p] of Object.entries(part.points)) points[k] = xy(p)
  const paths = {}
  for (const [k, p] of Object.entries(part.paths)) {
    if (k.startsWith('__')) continue
    paths[k] = { hidden: !!p.hidden, class: p.attributes?.get?.('class') || '',
      ops: p.ops.map((o) => ({ type: o.type, to: xy(o.to), cp1: xy(o.cp1), cp2: xy(o.cp2) })) }
  }
  const snippets = Object.entries(part.snippets).map(([k, s]) => ({ name: k, def: s.def, at: xy(s.anchor) }))
  out.parts[pn] = { points, paths, snippets }
}
process.stdout.write(JSON.stringify(out))
