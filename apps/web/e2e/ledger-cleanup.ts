import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

// A browser run leaves AI reservations in the daily ledger (`ai_spend_daily`) of the database it
// ran against: a stopped or failed turn keeps its reservation, and that ledger has no tenant, so
// removing the run's sandboxes doesn't remove them. A full run adds about $10, which pushes the
// day past the real $3 cap and then fails the API's own tests. This is the run's global setup:
// it notes the time, and returns the global teardown, which deletes the rows made since.
//
// The time is the DATABASE's clock (the script's `--now`), not this machine's: `created_at` is set
// by the database, and a Docker host's clock can differ from the machine's by more than a run.
//
// Skipped on CI, whose database is made fresh for each job and thrown away. A cleanup that fails
// only warns: it must never turn a green run red. Rows from anything else using the same database
// during the run go too, which is fine for a local test database (see the script).

const API_DIR = resolve(import.meta.dirname, '../../api')
const SCRIPT = ['run', 'python', 'scripts/clear_browser_test_spend.py']

function runScript(...args: string[]): string {
  // An agent shell may export ANTHROPIC_API_KEY as an empty string, which the API's settings
  // ignore, but leave it out all the same, as the API's own server command does.
  const { ANTHROPIC_API_KEY: _empty, ...env } = process.env
  return execFileSync('uv', [...SCRIPT, ...args], { cwd: API_DIR, env, encoding: 'utf8' })
}

export default function globalSetup(): (() => void) | undefined {
  if (process.env.CI) return undefined
  let since: string
  try {
    since = runScript('--now').trim()
  } catch (error) {
    console.warn(`The daily AI ledger will not be cleaned after this run: ${String(error)}`)
    return undefined
  }
  return () => {
    try {
      console.log(runScript('--since', since).trim())
    } catch (error) {
      console.warn(`Could not clean the daily AI ledger (rows since ${since}): ${String(error)}`)
    }
  }
}
