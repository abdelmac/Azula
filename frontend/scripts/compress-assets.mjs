import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'

// Les variantes sont servies par WhiteNoise lorsque le navigateur accepte gzip.
const directory = join(process.cwd(), 'dist', 'assets')
let count = 0
for (const name of readdirSync(directory)) {
  if (!/\.(js|css|svg)$/.test(name)) continue
  const file = join(directory, name)
  const original = readFileSync(file)
  const compressed = gzipSync(original)
  if (compressed.length < original.length) {
    writeFileSync(`${file}.gz`, compressed)
    count++
  }
}
console.log(`${count} ressources de production précompressées pour WhiteNoise.`)
