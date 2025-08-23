// Centralized env and constants for tests
export const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8080/api/v1';
export const RUN_API_TESTS = process.env.RUN_API_TESTS === '1';
export const RUN_E2E_HTTP = process.env.RUN_E2E_HTTP === '1';
export const RUN_E2E_SSH = process.env.RUN_E2E_SSH === '1';

// Helpful test identities and defaults (can be overridden via env)
export const TEST_USER = {
  email: process.env.TEST_EMAIL || 'owner@example.local',
  name: process.env.TEST_NAME || 'Local Owner',
  password: process.env.TEST_PASSWORD || 'Password!123'
};

export const TEST_PAT = {
  name: process.env.TEST_PAT_NAME || 'e2e-token',
  scopes: (process.env.TEST_PAT_SCOPES || 'git:read,git:write,api:read').split(',')
};

export const TEST_REPO = {
  name: process.env.TEST_REPO_NAME || 'hello-world',
  visibility: (process.env.TEST_REPO_VISIBILITY || 'private') as 'private' | 'internal' | 'public'
};
