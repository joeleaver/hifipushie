// The part inspector (pattern_parts.py runs it like draft_own_run.mjs: cwd = a scratch dir holding design.mjs and a
// node_modules link to the pack; no network, fs reads only, a timeout). design.mjs: the agent's own design, or a one-line
// re-export of a pack design. stdin: {"measurements": {...}, "options": {...}, "draft": bool}. stdout: {"config": {
// "measurements", "optional", "options": {name: {pct|deg|mm|bool|count|list, dflt, min, max} | {constant}}, "order",
// "parts": {name: {from, after, hide, measurements, options}}}, "missing": [...], "parts": {name: {hidden, points,
// paths: {name: {hidden, ops: [{type, to, cp1, cp2}]}}}}, "draft_error"} or {"error", "line"}.
import fs from 'fs'
import path from 'path'

const fail = (e) => {
  const s = String((e && e.stack) || e)
  const m = s.match(/design\.mjs:(\d+)/)
  process.stdout.write(JSON.stringify({ error: String((e && e.message) || e).split('\n')[0], line: m ? Number(m[1]) : null }))
  process.exit(0)
}
const req = JSON.parse(fs.readFileSync(0, 'utf8'))
let mod
try { mod = await import(path.resolve('design.mjs')) } catch (e) { fail(e) }
const D = mod.default ?? mod.design
if (typeof D !== 'function' || !D.patternConfig) fail(new Error('design.mjs exports no design: end it with `export default new Design({ parts: [...] })`'))
const pc = D.patternConfig
const nm = (p) => (p ? (typeof p === 'string' ? p : p.name) : null)
const opt = (o) => (typeof o === 'object' && o !== null
  ? { pct: o.pct, deg: o.deg, mm: o.mm, bool: o.bool, count: o.count, list: o.list, dflt: o.dflt, min: o.min, max: o.max }
  : { constant: typeof o === 'function' ? 'f()' : o })
const out = { config: { measurements: pc.measurements || [], optional: pc.optionalMeasurements || [], options: {},
  order: pc.draftOrder || Object.keys(pc.parts), parts: {} }, parts: {} }
for (const [k, o] of Object.entries(pc.options || {})) out.config.options[k] = opt(o)
for (const [k, p] of Object.entries(pc.parts || {})) {
  out.config.parts[k] = { from: nm(p.from), after: [].concat(p.after || []).map(nm), hide: !!(pc.partHide || {})[k],
    measurements: p.measurements || [], optional: p.optionalMeasurements || [], options: Object.keys(p.options || {}) }
}
out.missing = out.config.measurements.filter((m) => !(m in (req.measurements || {})))
if (req.draft && !out.missing.length) {
  try {
    const pattern = new D({ measurements: req.measurements, options: req.options || {}, sa: 10, complete: true })
    pattern.draft()
    const xy = (p) => (p ? [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100] : null)
    for (const [pn, part] of Object.entries(pattern.parts[0] || {})) {
      const points = {}
      for (const [k, p] of Object.entries(part.points)) points[k] = xy(p)
      const paths = {}
      for (const [k, p] of Object.entries(part.paths)) {
        if (k.startsWith('__')) continue
        paths[k] = { hidden: !!p.hidden, ops: p.ops.map((o) => ({ type: o.type, to: xy(o.to), cp1: xy(o.cp1), cp2: xy(o.cp2) })) }
      }
      out.parts[pn] = { hidden: !!part.hidden || !!(pc.partHide || {})[pn], points, paths }
    }
    const errs = [].concat(pattern.store.logs?.error || [], pattern.setStores?.[0]?.logs?.error || []).flat(3)
    if (errs.length) out.draft_error = String(errs[0]?.message || errs[0]).split('\n')[0]
  } catch (e) { out.draft_error = String((e && e.message) || e).split('\n')[0] }
}
process.stdout.write(JSON.stringify(out))
