import { readFileSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { resolve } from 'node:path'

const root = resolve('dist')
const manifest = JSON.parse(readFileSync(resolve(root, '.vite/manifest.json'), 'utf8'))
const keys = Object.keys(manifest)
const entry = keys.find(key => manifest[key].isEntry)
const french = keys.find(key => key.endsWith('/locales/fr.json'))
const login = keys.find(key => key.endsWith('/views/LoginView.vue'))
const files = new Set()
function collect(key) {
  if (!key) return
  const chunk = manifest[key]
  if (files.has(chunk.file)) return
  if (chunk.file.endsWith('.js')) files.add(chunk.file)
  for (const dependency of chunk.imports ?? []) collect(dependency)
}
collect(entry); collect(french); collect(login)
let total = 0
for (const file of files) {
  const size = gzipSync(readFileSync(resolve(root, file))).byteLength
  total += size
  console.log(`${file}: ${size} octets gzip`)
}
console.log(`JavaScript premier affichage connexion (entrée + imports statiques + français + route connexion): ${total} octets gzip (${(total / 1024).toFixed(2)} Kio).`)
if (total > 250 * 1024) process.exitCode = 1
