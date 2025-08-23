import { useEffect, useMemo, useRef, useState } from 'react'

// Default to same-origin API path so cookies work in the browser via Vite proxy
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
  credentials: 'include',
    headers: {
      'content-type': 'application/json',
      ...(init?.headers || {})
    }
  })
  const text = await res.text()
  let body: any = null
  try { body = text ? JSON.parse(text) : null } catch {}
  return { res, body }
}

export function App() {
  const [email, setEmail] = useState('owner@example.com')
  const [password, setPassword] = useState('devpass')
  const [name, setName] = useState('Owner')
  const [session, setSession] = useState<any>(null)
  const [pat, setPat] = useState<string>('')
  const [pats, setPats] = useState<any[]>([])
  const [repoName, setRepoName] = useState('hello-world')
  const [repos, setRepos] = useState<any[]>([])

  const authHeader: Record<string, string> = useMemo(() => (pat ? { Authorization: `Bearer ${pat}` } : {} as Record<string, string>), [pat])

  async function signup() {
    const out = await api('/auth/signup', { method: 'POST', body: JSON.stringify({ email, password, name }) })
    if (out.res.status === 201 || out.res.status === 409) await refreshSession()
  }
  async function login() {
    const out = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    if (out.res.ok) await refreshSession()
  }
  async function refreshSession() {
    const out = await api('/auth/session', { method: 'GET' })
    if (out.res.ok) setSession(out.body.user)
    else setSession(null)
  }
  async function createPat() {
    const out = await api('/auth/pat', { method: 'POST', body: JSON.stringify({ name: 'ui', scopes: ['api:read'] }) })
    if (out.res.status === 201) setPat(out.body.token)
  }
  async function listPats() {
    const out = await api('/auth/pat', { method: 'GET', headers: authHeader })
    if (out.res.ok) setPats(out.body.tokens)
  }
  async function createRepo() {
    const out = await api('/repos', { method: 'POST', headers: authHeader, body: JSON.stringify({ name: repoName, visibility: 'private' }) })
    if (out.res.ok) await listRepos()
  }
  async function listRepos() {
    const out = await api('/repos', { method: 'GET', headers: authHeader })
    if (out.res.ok) setRepos(out.body.repos)
  }

  useEffect(() => { refreshSession() }, [])

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', margin: 24, lineHeight: 1.5 }}>
      <h1>GitWeave UI (MVP)</h1>
      <section style={{ marginBottom: 24 }}>
        <h2>Auth</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input placeholder="email" value={email} onChange={e => setEmail(e.target.value)} />
          <input placeholder="password" type="password" value={password} onChange={e => setPassword(e.target.value)} />
          <input placeholder="name" value={name} onChange={e => setName(e.target.value)} />
          <button onClick={signup}>Sign up</button>
          <button onClick={login}>Login</button>
          <button onClick={refreshSession}>Session</button>
        </div>
        <div>Session: {session ? `${session.email} (${session.role})` : 'None'}</div>
      </section>

      <section style={{ marginBottom: 24 }}>
        <h2>PATs</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button onClick={createPat}>Create PAT</button>
          <button onClick={listPats}>List PATs</button>
          <input placeholder="paste PAT" value={pat} onChange={e => setPat(e.target.value)} style={{ width: 360 }} />
        </div>
        <ul>
          {pats.map(p => <li key={p.id}>{p.token_prefix}…</li>)}
        </ul>
      </section>

      <section>
        <h2>Repos</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input placeholder="repo name" value={repoName} onChange={e => setRepoName(e.target.value)} />
          <button onClick={createRepo}>Create Repo</button>
          <button onClick={listRepos}>List Repos</button>
        </div>
        <ul>
          {repos.map(r => <li key={r.name}>{r.name} — {r.visibility}</li>)}
        </ul>
      </section>
    </div>
  )
}
