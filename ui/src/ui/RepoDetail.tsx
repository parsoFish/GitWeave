import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'content-type': 'application/json', ...(init?.headers || {}) }
  })
  const text = await res.text()
  let body: any = null
  try { body = text ? JSON.parse(text) : null } catch {}
  return { res, body }
}

export function RepoDetail() {
  const { name = '' } = useParams()
  const navigate = useNavigate()
  const [pat, setPat] = useState('')
  const [repo, setRepo] = useState<any>(null)
  const [rules, setRules] = useState<any[]>([])
  const [newRule, setNewRule] = useState({ pattern: 'main', require_up_to_date: false })
  const [ref, setRef] = useState<string>('')
  const [path, setPath] = useState<string>('')
  const [tree, setTree] = useState<any[]>([])
  const [blob, setBlob] = useState<{ path: string; content: string; encoding: string } | null>(null)

  const authHeader: Record<string, string> = useMemo(() => (pat ? { Authorization: `Bearer ${pat}` } : {} as Record<string, string>), [pat])

  async function loadRepo() {
    if (!name) return
    const out = await api(`/repos/${encodeURIComponent(name)}`, { method: 'GET', headers: authHeader })
    if (out.res.ok) setRepo(out.body)
  }
  async function loadTree(nextPath?: string) {
    if (!name) return
    const p = typeof nextPath === 'string' ? nextPath : path
    const url = `/repos/${encodeURIComponent(name)}/tree?${new URLSearchParams({ ref: ref || '', path: p || '' })}`
    const out = await api(url, { method: 'GET', headers: authHeader })
    if (out.res.ok) {
      setRef(out.body.ref || '')
      setPath(out.body.path || '')
      setTree(out.body.entries || [])
      setBlob(null)
    }
  }
  async function openBlob(p: string) {
    if (!name) return
    const url = `/repos/${encodeURIComponent(name)}/blob?${new URLSearchParams({ ref: ref || '', path: p })}`
    const out = await api(url, { method: 'GET', headers: authHeader })
    if (out.res.ok) setBlob({ path: p, content: out.body.content, encoding: out.body.encoding })
  }
  function goUp() {
    const cur = path.replace(/^\/+|\/+$/g, '')
    if (!cur) return
    const segs = cur.split('/')
    segs.pop()
    const parent = segs.join('/')
    void loadTree(parent)
  }
  async function loadRules() {
    if (!name) return
    const out = await api(`/repos/${encodeURIComponent(name)}/branches/rules`, { method: 'GET', headers: authHeader })
    if (out.res.ok) setRules(out.body.rules)
  }
  async function saveRules() {
    if (!name) return
    const out = await api(`/repos/${encodeURIComponent(name)}/branches/rules`, {
      method: 'PUT',
      headers: authHeader,
      body: JSON.stringify({ rules: [newRule] })
    })
    if (out.res.ok || out.res.status === 204) await loadRules()
  }

  useEffect(() => { loadRepo(); loadRules(); loadTree('') }, [name, pat])

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', margin: 24, lineHeight: 1.5 }}>
      <h1>Repository: {name}</h1>
      <div style={{ marginBottom: 12 }}>
        <Link to="/">← Back</Link>
      </div>
      <div style={{ marginBottom: 12 }}>
        <input placeholder="paste PAT" value={pat} onChange={e => setPat(e.target.value)} style={{ width: 360 }} />
        <button onClick={loadRepo} style={{ marginLeft: 8 }}>Refresh</button>
      </div>
      {repo ? (
        <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 6 }}>
          <div><b>Name:</b> {repo.name}</div>
          <div><b>Visibility:</b> {repo.visibility}</div>
          <div><b>Path:</b> {repo.path}</div>
        </div>
      ) : (
        <div>No repo details yet.</div>
      )}
  <section style={{ marginTop: 24 }}>
        <h3>Branch Rules</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input placeholder="pattern" value={newRule.pattern} onChange={e => setNewRule({ ...newRule, pattern: e.target.value })} />
          <label>
            <input type="checkbox" checked={newRule.require_up_to_date} onChange={e => setNewRule({ ...newRule, require_up_to_date: e.target.checked })} />
            require_up_to_date
          </label>
          <button onClick={saveRules}>Save</button>
          <button onClick={loadRules}>Reload</button>
        </div>
        <ul>
          {rules.map((r, i) => <li key={i}>{r.pattern} — up_to_date: {String(r.require_up_to_date)}</li>)}
        </ul>
      </section>

      <section style={{ marginTop: 24 }}>
        <h3>Files</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          <span><b>ref:</b> {ref || '(auto)'}</span>
          <span><b>path:</b> {path || '/'}</span>
          <button onClick={goUp} disabled={!path}>Up</button>
          <button onClick={() => loadTree(path)}>Refresh</button>
        </div>
        <ul>
          {tree.map((e) => (
            <li key={e.path}>
              {e.type === 'tree' ? (
                <a href="#" onClick={(ev) => { ev.preventDefault(); loadTree(e.path) }}>{e.name}/</a>
              ) : (
                <a href="#" onClick={(ev) => { ev.preventDefault(); openBlob(e.path) }}>{e.name}</a>
              )}
              {typeof e.size === 'number' ? ` (${e.size} B)` : ''}
            </li>
          ))}
        </ul>
        {blob && (
          <div style={{ marginTop: 12 }}>
            <div><b>Viewing:</b> {blob.path}</div>
            <pre style={{ background: '#f6f8fa', padding: 12, borderRadius: 6, overflowX: 'auto' }}>
              {blob.encoding === 'base64' ? '[binary blob]' : blob.content}
            </pre>
          </div>
        )}
      </section>
    </div>
  )
}
