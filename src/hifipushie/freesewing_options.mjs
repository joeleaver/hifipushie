// Prints a design's options with their defaults/ranges (run from the pack directory).
const design = process.argv[2]
const mod = await import('@freesewing/' + design)
const D = mod[design.charAt(0).toUpperCase() + design.slice(1)]
const out = {}
for (const [k, o] of Object.entries(D.patternConfig.options)) {
  if (typeof o === 'object') out[k] = { pct: o.pct, deg: o.deg, mm: o.mm, bool: o.bool, count: o.count, list: o.list, dflt: o.dflt, min: o.min, max: o.max, menu: o.menu }
  else out[k] = { constant: o }
}
console.log(JSON.stringify({ measurements: D.patternConfig.measurements, optional: D.patternConfig.optionalMeasurements, options: out }))
