import { describe, it, expect } from 'vitest';
import { RUN_E2E_HTTP, TEST_REPO } from '../utils/env';
import { spawnSync } from 'node:child_process';

const run = RUN_E2E_HTTP;

// NOTE: This test assumes:
// - docker compose is up and API+git-http are running on localhost:8080
// - you have a PAT with git:read/write stored in GITWEAVE_PAT
// - git is installed on the host

describe(run ? 'E2E - Git over HTTP (MVP)' : 'E2E - Git over HTTP (MVP) [SKIPPED]', () => {
  it('clones and pushes over HTTP using PAT', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = process.env.GITWEAVE_PAT;
    if (!pat) throw new Error('Set GITWEAVE_PAT with git:read,git:write scopes');
    const origin = `http://x-token-auth:${encodeURIComponent(pat)}@localhost:8080/git/${encodeURIComponent(TEST_REPO.name)}.git`;

    // Init temp repo
    const tmp = process.cwd() + '/.tmp-http-e2e';
    spawnSync('powershell.exe', [ '-NoProfile', '-Command', `Remove-Item -Recurse -Force ${tmp} -ErrorAction SilentlyContinue; New-Item -ItemType Directory ${tmp} | Out-Null` ]);

    let r = spawnSync('git', ['clone', origin, tmp], { stdio: 'pipe' });
    expect(r.status).toBe(0);

    r = spawnSync('powershell.exe', ['-NoProfile', '-Command', `Set-Content -Path ${tmp}/README.md -Value 'hello'; cd ${tmp}; git add README.md; git commit -m "e2e"; git push origin HEAD`], { stdio: 'pipe' });
    expect(r.status).toBe(0);
  });
});
