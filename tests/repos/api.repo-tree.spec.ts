import { describe, it, expect } from 'vitest'
import { API_BASE_URL, RUN_API_TESTS, TEST_REPO, TEST_PAT, TEST_USER } from '../utils/env'
import { HttpClient } from '../utils/http'
import { promises as fs } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFile } from 'node:child_process'

const run = RUN_API_TESTS

async function execGit(args: string[], cwd?: string) {
  return await new Promise<{ stdout: string; stderr: string }>((resolve, reject) => {
    execFile('git', args, { cwd }, (err, stdout, stderr) => {
      if (err) return reject(Object.assign(err, { stdout: String(stdout||''), stderr: String(stderr||'') }))
      resolve({ stdout: String(stdout||''), stderr: String(stderr||'') })
    })
  })
}

describe(run ? 'Epic 3 - Repos API: tree/blob browsing (MVP)' : 'Epic 3 - Repos API: tree/blob browsing (MVP) [SKIPPED]', () => {
  const client = new HttpClient(API_BASE_URL)
  let token: string | null = null

  async function ensurePat() {
    if (!run) return null
    if (token) return token
    // Ensure user exists and login
    await client.request('/auth/signup', { method: 'POST', body: JSON.stringify({ email: TEST_USER.email, name: TEST_USER.name, password: TEST_USER.password }) })
    const login = await client.request('/auth/login', { method: 'POST', body: JSON.stringify({ email: TEST_USER.email, password: TEST_USER.password }) })
    expect([200]).toContain(login.res.status)
    const out = await client.request('/auth/pat', { method: 'POST', body: JSON.stringify(TEST_PAT) })
    expect([201, 409]).toContain(out.res.status)
    token = out.body?.token || token
    expect(token).toBeTruthy()
    return token
  }

  it('lists tree entries and fetches blob content after seeding a commit', async () => {
    if (!run) return expect(true).toBe(true)
    const pat = await ensurePat()
    // Create repo
    const create = await client.request('/repos', { method: 'POST', headers: { Authorization: `Bearer ${pat}` }, body: JSON.stringify({ name: TEST_REPO.name, visibility: TEST_REPO.visibility }) } as any)
    expect([201, 409]).toContain(create.res.status)
  // Get repo path
  const det = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}`, { method: 'GET', headers: { Authorization: `Bearer ${pat}` } } as any)
    expect(det.res.status).toBe(200)
    const repoPath: string = det.body?.path
    expect(repoPath).toMatch(/\.git$/)
    // Ensure the bare repo is initialized (in case API fallback created a plain dir)
    try {
      await execGit(['rev-parse', '--git-dir'], repoPath)
    } catch {
      await execGit(['init', '--bare', repoPath])
    }
  // Seed a commit using git CLI
    const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'gw-repo-'))
  await execGit(['clone', repoPath, tmp])
    const readmePath = path.join(tmp, 'README.md')
    await fs.writeFile(readmePath, '# Hello from tests\n\nThis is a repo browser test.\n', 'utf8')
    // Align local branch with remote main if present
    await execGit(['fetch', 'origin'], tmp).catch(() => ({} as any))
    // Try to base on origin/main; if it doesn't exist, just create main
    await execGit(['checkout', '-B', 'main', 'origin/main'], tmp).catch(async () => {
      await execGit(['checkout', '-B', 'main'], tmp)
    })
  await execGit(['pull', '--rebase', 'origin', 'main'], tmp).catch(() => ({} as any))
  await execGit(['add', 'README.md'], tmp)
  await execGit(['-c', 'user.name=GitWeave Test', '-c', 'user.email=test@gitweave.local', 'commit', '-m', 'test: add README for tree/blob'], tmp)
  await execGit(['push', '--force-with-lease', 'origin', 'main'], tmp)
  // List tree at root (server will resolve ref automatically)
  const tree = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}/tree?path=`, { method: 'GET', headers: { Authorization: `Bearer ${pat}` } } as any)
    expect(tree.res.status).toBe(200)
    const entry = (tree.body?.entries || []).find((e: any) => e.name === 'README.md')
    expect(entry?.type).toBe('blob')
    // Fetch blob
  const blob = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}/blob?path=${encodeURIComponent('README.md')}`, { method: 'GET', headers: { Authorization: `Bearer ${pat}` } } as any)
    expect(blob.res.status).toBe(200)
    expect(blob.body?.encoding).toBe('utf8')
    expect(String(blob.body?.content || '')).toMatch(/Hello from tests/)
  })
})
