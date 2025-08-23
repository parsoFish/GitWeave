import { describe, it, expect, afterAll } from 'vitest';
import { API_BASE_URL, RUN_API_TESTS, TEST_REPO, TEST_PAT, TEST_USER } from '../utils/env';
import { HttpClient } from '../utils/http';

const run = RUN_API_TESTS;

describe(run ? 'Epic 3 - Repos API (MVP)' : 'Epic 3 - Repos API (MVP) [SKIPPED]', () => {
  const client = new HttpClient(API_BASE_URL);
  let token: string | null = null;
  let createdPatId: string | null = null;
  const REPO_NAME = `${TEST_REPO.name}-core`;

  async function ensurePat() {
    if (!run) return null;
    if (token) return token;
  // Ensure user exists (idempotent)
  await client.request('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email: TEST_USER.email, name: TEST_USER.name, password: TEST_USER.password })
    });
  // Establish session
  const login = await client.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: TEST_USER.email, password: TEST_USER.password })
    });
  expect([200]).toContain(login.res.status);
  // Create PAT via session
  const out = await client.request('/auth/pat', { method: 'POST', body: JSON.stringify(TEST_PAT) });
  if (out.res.status === 201) {
      token = out.body.token;
      createdPatId = out.body.id || createdPatId;
    }
    return token;
  }

  // Revoke the PAT created by this suite to avoid accumulating tokens in persistent state
  afterAll(async () => {
    if (!run) return;
    if (!createdPatId) return;
    try {
  const headers: any = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const del = await client.request(`/auth/pat/${encodeURIComponent(createdPatId)}`, { method: 'DELETE', headers } as any);
      // Accept 204 or 404 (already gone)
      expect([204, 404]).toContain((del.res as any).status);
    } catch {
      // best-effort cleanup
    }
  });

  it('creates a bare repository', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
    expect(pat).toBeTruthy();
    const { res, body } = await client.request('/repos', {
      method: 'POST',
      headers: { Authorization: `Bearer ${pat}` },
      body: JSON.stringify({ name: REPO_NAME, visibility: TEST_REPO.visibility })
    } as any);
    expect([201, 409]).toContain(res.status); // 409 if already exists
    if (res.status === 201) {
  expect(body?.name).toBe(REPO_NAME);
      expect(body?.path).toMatch(/\.git$/);
      // Optional: HEAD request to file URL isn't possible; rely on API's returned path shape for now.
    }
  });

  it('lists repositories and shows the created one', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
  const { res, body } = await client.request('/repos', {
      method: 'GET',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect(res.status).toBe(200);
    expect(Array.isArray(body?.repos)).toBe(true);
  const found = body.repos.find((r: any) => r.name === REPO_NAME);
    expect(found).toBeTruthy();
  });

  it('gets repo details', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
  const { res, body } = await client.request(`/repos/${encodeURIComponent(REPO_NAME)}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect(res.status).toBe(200);
  expect(body?.name).toBe(REPO_NAME);
  });

  it('stores and retrieves branch rules (placeholder)', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
    const rules = [{ pattern: 'main', require_up_to_date: false }];
  const put = await client.request(`/repos/${encodeURIComponent(REPO_NAME)}/branches/rules`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${pat}` },
      body: JSON.stringify({ rules })
    } as any);
    expect([200, 204]).toContain(put.res.status);
  const get = await client.request(`/repos/${encodeURIComponent(REPO_NAME)}/branches/rules`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect(get.res.status).toBe(200);
    expect(Array.isArray(get.body?.rules)).toBe(true);
  });

  it('archives/deletes a repository', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
  const del = await client.request(`/repos/${encodeURIComponent(REPO_NAME)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect([200, 204]).toContain(del.res.status);
  });
});
