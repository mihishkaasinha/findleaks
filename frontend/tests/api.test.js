import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

describe('api module', () => {
  let api

  beforeEach(async () => {
    vi.resetModules()
    localStorage.clear()
    global.fetch = vi.fn()
    global.window = { location: { href: '' } }
    const mod = await import('../src/api.js')
    api = mod.api
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends POST to /api/auth/login', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ token: 'abc', app: 'FINDLEAKS' }),
    })
    const res = await api.login('admin', 'secret')
    expect(res.token).toBe('abc')
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(opts.method).toBe('POST')
  })

  it('sends Authorization header when token is set', async () => {
    localStorage.setItem('fl_token', 'mytoken123')
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ username: 'admin' }),
    })
    await api.me()
    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.headers['Authorization']).toBe('Bearer mytoken123')
  })

  it('throws on non-ok response', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 422,
      statusText: 'Unprocessable',
      json: async () => ({ detail: { message: 'Validation error' } }),
    })
    await expect(api.getExams()).rejects.toThrow('Validation error')
  })

  it('returns null for 204 responses', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => { throw new Error('no body') },
    })
    const res = await api.logout()
    expect(res).toBeNull()
  })

  it('sends GET to /api/health', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'operational', app: 'FINDLEAKS' }),
    })
    const res = await api.health()
    expect(res.status).toBe('operational')
    const [url] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/health')
  })

  it('builds query string for getLeaks params', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    })
    await api.getLeaks({ status: 'new', page: 1 })
    const [url] = global.fetch.mock.calls[0]
    expect(url).toContain('status=new')
    expect(url).toContain('page=1')
  })
})
