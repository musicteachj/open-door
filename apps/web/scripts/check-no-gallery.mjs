// Fails if a build contains the component gallery. The gallery is for development and the e2e
// build only; its marker text must never reach a production bundle.
// Usage: node scripts/check-no-gallery.mjs [directory]   (default: dist)
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const MARKER = 'Open Door component gallery'
const dir = process.argv[2] ?? 'dist'

function* files(root) {
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) yield* files(path)
    else yield path
  }
}

let scanned = 0
const found = []
for (const file of files(dir)) {
  scanned += 1
  if (readFileSync(file, 'utf8').includes(MARKER)) found.push(file)
}

if (scanned === 0) {
  console.error(`${dir}/ is empty or missing. Build first.`)
  process.exit(1)
}
if (found.length > 0) {
  console.error(`The component gallery is in the build (found "${MARKER}" in):`)
  for (const file of found) console.error(`  ${file}`)
  process.exit(1)
}
console.log(`No component gallery in ${dir}/ (${scanned} files scanned).`)
