// Orchestrate building the app, starting the server, waiting for readiness,
// running API tests, and cleaning up the server process.
import { spawn } from 'node:child_process';
import { setTimeout as sleep } from 'node:timers/promises';

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8080/api/v1';

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: 'inherit', ...opts });
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0) resolve(undefined);
      else reject(new Error(`${cmd} ${args.join(' ')} exited with code ${code}`));
    });
  });
}

function npmSpawn(args, opts = {}) {
  // Use shell to resolve npm on Windows reliably
  const cmd = 'npm';
  return spawn(cmd, args, { stdio: 'inherit', shell: true, ...opts });
}

async function waitForServer(url, timeoutMs = 30000, intervalMs = 500) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url, { method: 'GET' });
      // Any HTTP response means the server is up (this endpoint may 401)
      if (res) return;
    } catch (_) {
      // ignore until timeout
    }
    await sleep(intervalMs);
  }
  throw new Error(`Server did not become ready at ${url} within ${timeoutMs}ms`);
}

async function main() {
  // Remove stale lockfile entries that reference the old local package (prevents .gitweave* temp dirs)
  try {
    const { promises: fsp } = await import('node:fs');
    const { join } = await import('node:path');
    const lockPath = join(process.cwd(), 'app', 'package-lock.json');
    const txt = await fsp.readFile(lockPath, 'utf8').catch(() => '');
    if (txt.includes('"gitweave": "file:.."') || txt.includes('node_modules/gitweave')) {
      await fsp.rm(lockPath, { force: true });
    }
  } catch {}

  // Pre-clean any leftover local-file package artifacts that can cause EACCES on Windows
  try {
    const { promises: fsp } = await import('node:fs');
    const { join } = await import('node:path');
    const nm = join(process.cwd(), 'app', 'node_modules');
    const entries = await fsp.readdir(nm, { withFileTypes: true }).catch(() => []);
    for (const ent of entries) {
      const name = ent.name;
      if (name === 'gitweave' || name.startsWith('.gitweave')) {
        const p = join(nm, name);
        await fsp.rm(p, { recursive: true, force: true }).catch(() => {});
      }
    }
  } catch {}

  // 0) Ensure app dependencies are installed (dev deps include typescript/tsx)
  // Only use `npm ci` when a lockfile exists; otherwise use `npm install` to avoid EUSAGE noise.
  await new Promise(async (resolve) => {
    const { promises: fsp } = await import('node:fs');
    const { join } = await import('node:path');
    const lockPath = join(process.cwd(), 'app', 'package-lock.json');
    const hasLock = await fsp.access(lockPath).then(() => true).catch(() => false);
    const args = hasLock ? ['--prefix', 'app', 'ci', '--no-fund', '--no-audit']
                         : ['--prefix', 'app', 'install', '--no-fund', '--no-audit'];
    const p = npmSpawn(args);
    p.on('exit', (code) => resolve());
  });

  // 1) Build the app
  await new Promise((resolve, reject) => {
    const p = npmSpawn(['--prefix', 'app', 'run', 'build']);
    p.on('error', reject);
    p.on('exit', (code) => (code === 0 ? resolve() : reject(new Error(`npm run build exited with ${code}`))));
  });

  // 2) Start the app server
  const appProc = spawn(process.execPath, ['dist/index.js'], {
    cwd: 'app',
    stdio: 'inherit',
  });

  const cleanup = () => {
    if (!appProc.killed) {
      try { appProc.kill(); } catch {}
    }
  };
  process.on('exit', cleanup);
  process.on('SIGINT', () => { cleanup(); process.exit(130); });
  process.on('SIGTERM', () => { cleanup(); process.exit(143); });

  // 3) Wait for readiness using health endpoint
  const base = new URL(API_BASE_URL);
  const healthz = `${base.origin}/healthz`;
  await waitForServer(healthz).catch(async (err) => {
    cleanup();
    throw err;
  });

  // 4) Run tests
  try {
    // Ensure env flags for API tests
    const testEnv = { ...process.env, RUN_API_TESTS: '1', API_BASE_URL };
    await new Promise((resolve, reject) => {
  const t = npmSpawn(['run', 'test:api'], { env: testEnv });
      t.on('error', reject);
      t.on('exit', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`API tests failed with code ${code}`));
      });
    });
  } finally {
    cleanup();
  }
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
