let token = ''
try { token = sessionStorage.getItem('saarthi_token') || '' } catch { /* storage unavailable */ }

export function setToken(t) {
  token = t || ''
  try { t ? sessionStorage.setItem('saarthi_token', t) : sessionStorage.removeItem('saarthi_token') } catch { /* ignore */ }
}

export async function api(path, opts = {}) {
  const res = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    const e = new Error(msg)
    e.status = res.status
    throw e
  }
  return res.json()
}
