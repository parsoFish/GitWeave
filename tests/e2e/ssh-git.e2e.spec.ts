import { describe, it, expect } from 'vitest';
import { RUN_E2E_SSH, TEST_REPO } from '../utils/env';
import { spawnSync } from 'node:child_process';

const run = RUN_E2E_SSH;

// NOTE: This test assumes:
// - sshd is running at localhost:2222 (per docker-compose), with your SSH key authorized
// - you have SSH key loaded into agent or available via default path

describe(run ? 'E2E - Git over SSH (MVP)' : 'E2E - Git over SSH (MVP) [SKIPPED]', () => {
  it('clones and pushes over SSH using authorized key', async () => {
    if (!run) return expect(true).toBe(true);
    const origin = `ssh://git@localhost:2222/${encodeURIComponent(TEST_REPO.name)}.git`;
    const tmp = process.cwd() + '/.tmp-ssh-e2e';
    spawnSync('powershell.exe', [ '-NoProfile', '-Command', `Remove-Item -Recurse -Force ${tmp} -ErrorAction SilentlyContinue; New-Item -ItemType Directory ${tmp} | Out-Null` ]);

    let r = spawnSync('git', ['clone', origin, tmp], { stdio: 'pipe' });
    expect(r.status).toBe(0);

    r = spawnSync('powershell.exe', ['-NoProfile', '-Command', `Set-Content -Path ${tmp}/README.md -Value 'hello-ssh'; cd ${tmp}; git add README.md; git commit -m "e2e-ssh"; git push origin HEAD`], { stdio: 'pipe' });
    expect(r.status).toBe(0);
  });
});
