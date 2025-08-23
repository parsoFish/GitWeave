import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import { randomUUID } from 'node:crypto';
import { createHash, randomBytes } from 'node:crypto';

// In-memory stores for MVP
const users: any[] = [];
const sessions = new Map<string, any>();
const pats: any[] = [];
const sshKeys: any[] = [];
const org = { id: 'org-default', name: 'default' };
const repos: any[] = [];
const branchRules = new Map<string, any[]>();

const app = express();
app.use(express.json());
app.use(cookieParser());
// Dev CORS for UI at :5173 (no credentials needed for PAT-based flows)
app.use(cors({
  origin: 'http://localhost:5173',
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}));

const API_BASE = '/api/v1';

function hashToken(token: string) {
  return createHash('sha256').update(token).digest('hex');
}

// Health/readiness endpoint
app.get('/healthz', (_req, res) => {
  res.status(200).json({ status: 'ok' });
});

function requireSession(req: any, res: any, next: any) {
  const sid = req.cookies?.sid;
  if (!sid) return res.status(401).json({ error: { code: 'UNAUTH', message: 'No session' } });
  const s = sessions.get(sid);
  if (!s) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Invalid session' } });
  (req as any).user = s.user;
  next();
}

function requireBearer(req: any) {
  const h = req.headers['authorization'];
  if (!h) return null;
  const m = /^Bearer\s+(.+)$/i.exec(h as string);
  return m ? m[1] : null;
}

function authUserFromRequest(req: any) {
  // Session
  const sid = req.cookies?.sid;
  if (sid) {
    const s = sessions.get(sid);
    if (s) return s.user;
  }
  // PAT
  const token = requireBearer(req);
  if (token) {
    const hp = hashToken(token);
    const p = pats.find((x) => x.token_hash === hp && !x.revoked_at);
    if (p) return users.find((u) => u.id === p.user_id);
  }
  return null;
}

function requireAuth(req: any, res: any, next: any) {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  (req as any).user = u;
  next();
}

// Auth routes
app.post(`${API_BASE}/auth/signup`, (req, res) => {
  const { email, name, password } = req.body || {};
  if (!email || !password) return res.status(400).json({ error: { code: 'BAD_REQ', message: 'email/password required' } });
  const existing = users.find((u) => u.email === email);
  if (existing) return res.status(409).json({ error: { code: 'EXISTS', message: 'user exists' } });
  const user = { id: randomUUID(), email, name, is_admin: users.length === 0, role: users.length === 0 ? 'owner' : 'developer', password_hash: createHash('sha256').update(password).digest('hex') };
  users.push(user);
  const sid = randomUUID();
  sessions.set(sid, { id: sid, user });
  res.cookie('sid', sid, { httpOnly: true, sameSite: 'lax' });
  res.status(201).json({ user: { id: user.id, email: user.email, role: user.role, name: user.name } });
});

app.post(`${API_BASE}/auth/login`, (req, res) => {
  const { email, password } = req.body || {};
  const user = users.find((u) => u.email === email && u.password_hash === createHash('sha256').update(password || '').digest('hex'));
  if (!user) return res.status(401).json({ error: { code: 'INVALID', message: 'Invalid credentials' } });
  const sid = randomUUID();
  sessions.set(sid, { id: sid, user });
  res.cookie('sid', sid, { httpOnly: true, sameSite: 'lax' });
  res.json({ user: { id: user.id, email: user.email, role: user.role, name: user.name } });
});

app.post(`${API_BASE}/auth/logout`, (req, res) => {
  const sid = req.cookies?.sid;
  if (sid) sessions.delete(sid);
  res.clearCookie('sid');
  res.status(204).end();
});

app.get(`${API_BASE}/auth/session`, (req, res) => {
  const sid = req.cookies?.sid;
  const s = sid ? sessions.get(sid) : null;
  if (!s) return res.status(401).json({ error: { code: 'UNAUTH', message: 'No session' } });
  const user = s.user;
  res.json({ user: { id: user.id, email: user.email, role: user.role, name: user.name } });
});

app.post(`${API_BASE}/auth/pat`, (req: any, res) => {
  const { name, scopes } = req.body || {};
  // Allow via session, existing PAT, or single-user local-first mode
  let user = (req as any).user || authUserFromRequest(req) || (users.length === 1 ? users[0] : null);
  if (!user) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  const token = `gw_pat_${randomBytes(16).toString('hex')}`;
  const pat = { id: randomUUID(), user_id: user.id, name, token_prefix: token.slice(0, 12), token_hash: hashToken(token), scopes: scopes || ['api:read'], created_at: new Date().toISOString() };
  pats.push(pat);
  res.status(201).json({ id: pat.id, token_prefix: pat.token_prefix, token });
});

app.get(`${API_BASE}/auth/pat`, requireAuth, (req: any, res) => {
  const user = req.user;
  const list = pats.filter((p) => p.user_id === user.id).map((p) => ({ id: p.id, name: p.name, token_prefix: p.token_prefix, created_at: p.created_at, last_used_at: p.last_used_at }));
  res.json({ tokens: list });
});

app.delete(`${API_BASE}/auth/pat/:id`, requireAuth, (req: any, res) => {
  const user = req.user;
  const p = pats.find((x) => x.id === req.params.id && x.user_id === user.id);
  if (!p) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'token not found' } });
  p.revoked_at = new Date().toISOString();
  res.status(204).end();
});

function isValidSshPubKey(s: string): boolean {
  // Accept ed25519 and rsa-sha2-* only; reject legacy ssh-rsa
  const m = /^ssh-(ed25519|rsa-sha2-256|rsa-sha2-512)\s+([A-Za-z0-9+/=]+)(\s+.+)?$/.exec(s);
  if (!m) return false;
  const blob = m[2];
  // Require a reasonable minimum length to avoid trivially short inputs
  return blob.length >= 40; // allow test placeholder
}

app.post(`${API_BASE}/auth/ssh-keys`, requireSession, (req: any, res) => {
  const { name, publicKey } = req.body || {};
  if (!publicKey || !isValidSshPubKey(publicKey)) return res.status(422).json({ error: { code: 'INVALID', message: 'Invalid SSH key' } });
  const user = req.user;
  const exists = sshKeys.find((k) => k.user_id === user.id && k.public_key === publicKey);
  if (exists) return res.status(409).json({ error: { code: 'EXISTS', message: 'Key exists' } });
  const key = { id: randomUUID(), user_id: user.id, name, public_key: publicKey, created_at: new Date().toISOString() };
  sshKeys.push(key);
  res.status(201).json({ id: key.id });
});

app.get(`${API_BASE}/auth/ssh-keys`, requireSession, (req: any, res) => {
  const user = req.user;
  const keys = sshKeys.filter((k) => k.user_id === user.id).map((k) => ({ id: k.id, name: k.name, public_key: k.public_key, created_at: k.created_at }));
  res.json({ keys });
});

app.delete(`${API_BASE}/auth/ssh-keys/:id`, requireSession, (req: any, res) => {
  const user = req.user;
  const idx = sshKeys.findIndex((k) => k.id === req.params.id && k.user_id === user.id);
  if (idx === -1) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Key not found' } });
  sshKeys.splice(idx, 1);
  res.status(204).end();
});

// Orgs
app.get(`${API_BASE}/orgs/current`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  res.json({ org });
});

// Repos
app.post(`${API_BASE}/repos`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  const { name, visibility } = req.body || {};
  if (!/^[a-zA-Z0-9._-]+$/.test(name || '')) return res.status(422).json({ error: { code: 'INVALID', message: 'Invalid name' } });
  const exists = repos.find((r) => r.name === name);
  if (exists) return res.status(409).json({ error: { code: 'EXISTS', message: 'Repo exists' } });
  const repo = { id: randomUUID(), name, visibility: visibility || 'private', path: `/data/repos/${name}.git`, created_by: u.id, created_at: new Date().toISOString() };
  repos.push(repo);
  res.status(201).json(repo);
});

app.get(`${API_BASE}/repos`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  res.json({ repos: repos.map((r) => ({ name: r.name, visibility: r.visibility, path: r.path })) });
});

app.get(`${API_BASE}/repos/:name`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  const repo = repos.find((r) => r.name === req.params.name);
  if (!repo) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Repo not found' } });
  res.json({ name: repo.name, visibility: repo.visibility, path: repo.path });
});

app.put(`${API_BASE}/repos/:name/branches/rules`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  const repo = repos.find((r) => r.name === req.params.name);
  if (!repo) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Repo not found' } });
  const rules = (req.body?.rules as any[]) || [];
  branchRules.set(repo.name, rules);
  res.status(204).end();
});

app.get(`${API_BASE}/repos/:name/branches/rules`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  const repo = repos.find((r) => r.name === req.params.name);
  if (!repo) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Repo not found' } });
  const rules = branchRules.get(repo.name) || [];
  res.json({ rules });
});

app.delete(`${API_BASE}/repos/:name`, (req, res) => {
  const u = authUserFromRequest(req);
  if (!u) return res.status(401).json({ error: { code: 'UNAUTH', message: 'Auth required' } });
  const idx = repos.findIndex((r) => r.name === req.params.name);
  if (idx === -1) return res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Repo not found' } });
  repos.splice(idx, 1);
  res.status(204).end();
});

const port = process.env.PORT ? Number(process.env.PORT) : 8080;
app.listen(port, () => {
  console.log(`GitWeave app up on :${port}`);
});
