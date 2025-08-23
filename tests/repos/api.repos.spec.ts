import { describe, it, expect } from 'vitest';
import { API_BASE_URL, RUN_API_TESTS, TEST_REPO, TEST_PAT, TEST_USER } from '../utils/env';
import { HttpClient } from '../utils/http';

const run = RUN_API_TESTS;

describe(run ? 'Epic 3 - Repos API (MVP)' : 'Epic 3 - Repos API (MVP) [SKIPPED]', () => {
  const client = new HttpClient(API_BASE_URL);
  let token: string | null = null;

  async function ensurePat() {
    if (!run) return null;
    if (token) return token;
    // Establish session first in case PAT creation requires it
    await client.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: TEST_USER.email, password: TEST_USER.password })
    });
    const out = await client.request('/auth/pat', { method: 'POST', body: JSON.stringify(TEST_PAT) });
    if (out.res.status === 201) token = out.body.token;
    return token;
  }

  it('creates a bare repository', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
    expect(pat).toBeTruthy();
    const { res, body } = await client.request('/repos', {
      method: 'POST',
      headers: { Authorization: `Bearer ${pat}` },
      body: JSON.stringify({ name: TEST_REPO.name, visibility: TEST_REPO.visibility })
    } as any);
    expect([201, 409]).toContain(res.status); // 409 if already exists
    if (res.status === 201) {
      expect(body?.name).toBe(TEST_REPO.name);
      expect(body?.path).toMatch(/\.git$/);
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
    const found = body.repos.find((r: any) => r.name === TEST_REPO.name);
    expect(found).toBeTruthy();
  });

  it('gets repo details', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
    const { res, body } = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect(res.status).toBe(200);
    expect(body?.name).toBe(TEST_REPO.name);
  });

  it('stores and retrieves branch rules (placeholder)', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
    const rules = [{ pattern: 'main', require_up_to_date: false }];
    const put = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}/branches/rules`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${pat}` },
      body: JSON.stringify({ rules })
    } as any);
    expect([200, 204]).toContain(put.res.status);
    const get = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}/branches/rules`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect(get.res.status).toBe(200);
    expect(Array.isArray(get.body?.rules)).toBe(true);
  });

  it('archives/deletes a repository', async () => {
    if (!run) return expect(true).toBe(true);
    const pat = await ensurePat();
    const del = await client.request(`/repos/${encodeURIComponent(TEST_REPO.name)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${pat}` }
    } as any);
    expect([200, 204]).toContain(del.res.status);
  });
});
