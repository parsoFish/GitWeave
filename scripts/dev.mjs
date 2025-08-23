// Start API and UI concurrently with clean shutdown (no extra deps)
import { spawn } from 'node:child_process';

function npmSpawn(args, opts = {}) {
  return spawn('npm', args, { stdio: 'inherit', shell: true, ...opts });
}

const procs = [];

function start(name, args, opts = {}) {
  const p = npmSpawn(args, opts);
  procs.push({ name, p });
  p.on('exit', (code) => {
    console.log(`[${name}] exited with code ${code}`);
  });
}

function shutdown() {
  for (const { p } of procs) {
    if (!p.killed) {
      try { p.kill(); } catch {}
    }
  }
}

process.on('SIGINT', () => { shutdown(); process.exit(130); });
process.on('SIGTERM', () => { shutdown(); process.exit(143); });
process.on('exit', shutdown);

console.log('Starting GitWeave dev environment...');
console.log('- API:    http://localhost:8080');
console.log('- UI:     http://localhost:5173');
console.log('- Proxy:  UI -> /api -> http://localhost:8080');

start('api', ['--prefix', 'app', 'run', 'dev']);
start('ui', ['--prefix', 'ui', 'run', 'dev']);

// Keep process alive until children exit
setInterval(() => {}, 1 << 30);
