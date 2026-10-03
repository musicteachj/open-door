// Regenerates the API client from openapi.json and fails if that changed anything, which means
// the committed client was stale. The regenerated file is left in place, ready to review and commit.
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

const client = 'src/api/generated.ts'
const before = readFileSync(client, 'utf8')
execSync('npm run generate:api', { stdio: 'inherit' })
const after = readFileSync(client, 'utf8')

if (before !== after) {
  console.error(`${client} was out of date with openapi.json and has been regenerated. Commit it.`)
  process.exit(1)
}
console.log(`${client} is up to date with openapi.json.`)
