// Fails the build if the production bundle contains anything that looks like
// a secret. The frontend should hold none - only VITE_API_BASE_URL - so any
// hit here means a key was put in a VITE_* variable or imported by mistake.
//
// Run after `vite build`: `npm run check:bundle`.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const DIST = new URL('../dist/', import.meta.url)

const PATTERNS = [
  ['Google API key', /AIza[0-9A-Za-z_-]{20,}/],
  ['NVIDIA API key', /nvapi-[0-9A-Za-z_-]{20,}/],
  ['Supabase secret key', /sb_secret_[0-9A-Za-z_-]{10,}/],
  ['Supabase service role', /service_role/],
  ['JWT', /eyJhbGciOi[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}/],
  ['server env name', /\b(GEMINI_API_KEY|NVIDIA_API_KEY|SUPABASE_SERVICE_ROLE_KEY|PERSISTENCE_HASH_SALT)\b/],
]

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

let failures = 0
for (const file of files(DIST.pathname.replace(/^\/([A-Za-z]:)/, '$1'))) {
  const text = readFileSync(file, 'utf8')
  for (const [label, pattern] of PATTERNS) {
    if (pattern.test(text)) {
      // Name the file and the kind of match; never print the match itself.
      console.error(`bundle check: ${label} pattern found in ${file}`)
      failures += 1
    }
  }
}

if (failures) {
  console.error(`bundle check failed: ${failures} match(es).`)
  process.exit(1)
}
console.log('bundle check: no secret patterns in dist/')
