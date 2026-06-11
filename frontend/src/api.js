const BASE = '/api'

function getToken() {
  return localStorage.getItem('fl_token')
}

async function request(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    localStorage.removeItem('fl_token')
    window.location.href = '/login'
    return
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(err?.detail?.message || res.statusText), { status: res.status, detail: err?.detail })
  }

  if (res.status === 204) return null
  return res.json()
}

async function upload(path, formData) {
  const token = getToken()
  const headers = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers, body: formData })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(err?.detail?.message || res.statusText), { status: res.status })
  }
  return res.json()
}

export const api = {
  login: (username, password) => request('POST', '/auth/login', { username, password }),
  logout: () => request('POST', '/auth/logout'),
  me: () => request('GET', '/auth/me'),

  getExams: () => request('GET', '/exams'),
  createExam: (body) => request('POST', '/exams', body),
  getExam: (id) => request('GET', `/exams/${id}`),

  uploadQuestions: (examId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return upload(`/exams/${examId}/upload-questions`, fd)
  },
  scanImage: (examId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return upload(`/exams/${examId}/scan`, fd)
  },

  getLeaks: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request('GET', `/leaks${qs ? '?' + qs : ''}`)
  },
  patchLeak: (id, body) => request('PATCH', `/leaks/${id}`, body),

  getAlerts: () => request('GET', '/alerts'),
  getScanners: () => request('GET', '/scanners'),
  startScanner: (id) => request('POST', `/scanners/${id}/start`),
  stopScanner: (id) => request('POST', `/scanners/${id}/stop`),
  patchScanner: (id, body) => request('PATCH', `/scanners/${id}`, body),

  health: () => request('GET', '/health'),
}
