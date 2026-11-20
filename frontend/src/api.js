let token = ''
try { token = sessionStorage.getItem('saarthi_token') || '' } catch { /* storage unavailable */ }

export const hasToken = () => !!token

export function setToken(t) {
  token = t || ''
  try { t ? sessionStorage.setItem('saarthi_token', t) : sessionStorage.removeItem('saarthi_token') } catch { /* ignore */ }
}

export async function api(path, opts = {}) {
  let res
  try {
    res = await fetch('/api' + path, {
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    })
  } catch {
    throw new Error('Cannot reach the SAARTHI server. Check that run.bat is still open, then try again.')
  }
  if (!res.ok) {
    if (res.status === 401 && token) { setToken(''); window.dispatchEvent(new Event('saarthi-logout')) }
    let msg = res.statusText
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    const e = new Error(msg)
    e.status = res.status
    throw e
  }
  if (res.status === 204) return null
  return res.json()
}
