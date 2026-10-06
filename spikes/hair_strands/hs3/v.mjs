import v from 'gltf-validator';
import fs from 'fs';
for (const p of process.argv.slice(2)) {
  const r = await v.validateBytes(new Uint8Array(fs.readFileSync(p)));
  const i = r.issues;
  console.log(p.split('/').pop(), 'errors', i.numErrors, 'warnings', i.numWarnings, 'infos', i.numInfos,
    JSON.stringify(i.messages.slice(0, 6).map(m => m.code + ' ' + (m.pointer || ''))));
}
