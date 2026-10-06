// Fails if a build contains the component gallery. The gallery is for development and the e2e
// build only; its marker text must never reach a production bundle.
// Usage: node scripts/check-no-gallery.mjs [directory]   (default: dist)
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

// The marker is the gallery's heading, kept in one JSON file that Gallery.tsx renders and this
// check reads, so renaming the heading renames the check with it. If the gallery stops rendering
// the file's text the check would pass on anything, so that is checked first.
const MARKER_FILE = new URL('../src/app/gallery/gallery-marker.json', import.meta.url)
const GALLERY_FILE = new URL('../src/app/gallery/Gallery.tsx', import.meta.url)
const { marker: MARKER } = JSON.parse(readFileSync(MARKER_FILE, 'utf8'))
if (typeof MARKER !== 'string' || MARKER.trim().length < 8) {
  console.error(`${MARKER_FILE.pathname} has no usable "marker" text.`)
  process.exit(1)
}
const gallerySource = readFileSync(GALLERY_FILE, 'utf8')
if (!gallerySource.includes('./gallery-marker.json') || !gallerySource.includes('{marker}')) {
  console.error(
    'Gallery.tsx no longer renders the marker from gallery-marker.json, so this check would find nothing.',
  )
  process.exit(1)
}
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
