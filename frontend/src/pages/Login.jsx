import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldAlert, Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const STATE = { IDLE: 'idle', LOADING: 'loading', SUCCESS: 'success', ERROR: 'error', LOCKOUT: 'lockout' }

export default function Login() {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [status, setStatus] = useState(STATE.IDLE)
  const [errorMsg, setErrorMsg] = useState('')
  const [attempts, setAttempts] = useState(0)
  const { login } = useAuth()
  const navigate = useNavigate()

  const locked = attempts >= 5

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (locked) { setStatus(STATE.LOCKOUT); return }
    setStatus(STATE.LOADING)
    setErrorMsg('')
    try {
      await login(username, password)
      setStatus(STATE.SUCCESS)
      setTimeout(() => navigate('/dashboard'), 600)
    } catch (err) {
      setAttempts(a => a + 1)
      if (attempts + 1 >= 5) {
        setStatus(STATE.LOCKOUT)
        setErrorMsg('Too many attempts. Please wait before retrying.')
      } else {
        setStatus(STATE.ERROR)
        setErrorMsg(err?.detail?.error === 'invalid_credentials'
          ? 'Invalid username or password.'
          : 'Login failed. Please try again.')
      }
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8 gap-3">
          <div className="p-3 bg-indigo-600 rounded-2xl">
            <ShieldAlert className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">FINDLEAKS</h1>
          <p className="text-sm text-gray-400">Exam Integrity Platform</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-gray-900 rounded-2xl p-6 space-y-4 border border-gray-800 shadow-xl">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Username</label>
            <input
              data-testid="username-input"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
              required
              disabled={status === STATE.LOADING}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Password</label>
            <div className="relative">
              <input
                data-testid="password-input"
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 pr-10 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
                required
                disabled={status === STATE.LOADING}
              />
              <button
                type="button"
                onClick={() => setShowPw(v => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
              >
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {(status === STATE.ERROR || status === STATE.LOCKOUT) && (
            <div data-testid="error-message" className="flex items-start gap-2 text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-3 py-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              {errorMsg}
            </div>
          )}

          {status === STATE.SUCCESS && (
            <div className="flex items-center gap-2 text-sm text-green-400 bg-green-950 border border-green-800 rounded-lg px-3 py-2">
              <CheckCircle2 className="w-4 h-4" />
              Login successful!
            </div>
          )}

          <button
            data-testid="login-button"
            type="submit"
            disabled={status === STATE.LOADING || locked}
            className="w-full py-2 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-white transition-colors flex items-center justify-center gap-2"
          >
            {status === STATE.LOADING && <Loader2 className="w-4 h-4 animate-spin" />}
            {status === STATE.LOADING ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <p className="text-center text-xs text-gray-600 mt-4">FINDLEAKS v1.0.0 · Sacumen</p>
      </div>
    </div>
  )
}
