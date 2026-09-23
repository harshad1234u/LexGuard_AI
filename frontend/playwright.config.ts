import { defineConfig, devices } from '@playwright/test'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

/**
 * The backend's virtualenv interpreter, as an absolute path.
 *
 * A relative `../backend/...` is not runnable by cmd.exe, and the bare name
 * `python` would silently pick up whatever interpreter is on PATH - which is
 * how a test suite ends up running against a different set of dependencies
 * than the application.
 */
const PYTHON = [
  resolve(here, '..', 'backend', '.venv', 'Scripts', 'python.exe'),
  resolve(here, '..', 'backend', '.venv', 'bin', 'python'),
].find(existsSync)

if (!PYTHON) {
  throw new Error(
    'backend/.venv not found. Create it first - the browser tests start the stub backend with it.',
  )
}

/**
 * Browser tests for the safety-critical flows.
 *
 * Both servers are started by the runner, so the whole suite is one command and
 * nobody has to remember the order. The backend is the stub in `e2e/`, not the
 * real one: these tests exist to check that the browser shows the right thing
 * when the backend reports a given safety state, and reaching states like
 * "provider failed" or "nothing verified" through the real system would mean a
 * real model call that may or may not produce that state today. The backend's
 * own behaviour is covered by 1400+ deterministic Python tests.
 *
 * No NVIDIA key is read and no network call leaves the machine.
 */
export default defineConfig({
  testDir: './e2e/specs',
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'list',
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: 'http://127.0.0.1:5273',
    trace: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  // Ports deliberately differ from the development defaults (5173/8000) so a
  // test run cannot collide with, or silently talk to, a dev server someone
  // already has open.
  webServer: [
    {
      command: `"${PYTHON}" ./e2e/stub_backend.py 8273`,
      url: 'http://127.0.0.1:8273/api/v1/health',
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // `--host 127.0.0.1` matters: Vite otherwise binds ::1 only, and the
      // health check below (and the browser) would never reach it.
      command: 'npx vite --port 5273 --strictPort --host 127.0.0.1',
      url: 'http://127.0.0.1:5273',
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'ignore',
      env: { VITE_API_PROXY_TARGET: 'http://127.0.0.1:8273' },
    },
  ],
})
