// Prints the option table of FreeSewing designs as JSON (design_schema.refresh_freesewing_options copies it into
// the pack directory and runs it there). argv: design names. Out: {design: {option: {type, default, min, max, list, menu}}} with FreeSewing's
// own units: pct options as a FRACTION (pct 25 -> 0.25, the value a draft takes), deg in degrees, mm in mm.
const out = {}
for (const d of process.argv.slice(2)) {
  const mod = await import('@freesewing/' + d)
  const D = mod[d.charAt(0).toUpperCase() + d.slice(1)]
  const opts = {}
  for (const [k, v] of Object.entries(D.patternConfig.options || {})) {
    if (typeof v !== 'object' || v === null) { opts[k] = { type: 'constant', default: v }; continue }
    const e = { menu: typeof v.menu === 'string' ? v.menu : null }
    if ('pct' in v) Object.assign(e, { type: 'pct', default: v.pct / 100, min: v.min / 100, max: v.max / 100 })
    else if ('deg' in v) Object.assign(e, { type: 'deg', default: v.deg, min: v.min, max: v.max })
    else if ('mm' in v) Object.assign(e, { type: 'mm', default: v.mm, min: v.min, max: v.max })
    else if ('count' in v) Object.assign(e, { type: 'count', default: v.count, min: v.min, max: v.max })
    else if ('bool' in v) Object.assign(e, { type: 'bool', default: v.bool })
    else if ('list' in v) Object.assign(e, { type: 'list', default: v.dflt, list: v.list })
    else Object.assign(e, { type: 'other' })
    opts[k] = e
  }
  out[d] = opts
}
process.stdout.write(JSON.stringify(out, null, 1))
