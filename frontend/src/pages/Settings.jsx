import React, { useState } from 'react'
import { CheckCircle2, Eye, EyeOff, KeyRound, Copy } from 'lucide-react'
import { api } from '../api'

export default function Settings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setResult(null)
    if (next !== confirm) { setError('New passwords do not match.'); return }
    if (next.length < 8) { setError('New password must be at least 8 characters.'); return }
    setLoading(true)
    try {
      const data = await api.changePassword(current, next)
      setResult(data)
      setCurrent(''); setNext(''); setConfirm('')
    } catch (err) {
      setError(err?.detail?.error === 'wrong_current_password'
        ? 'Current password is incorrect.'
        : 'Password change failed. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-lg mx-auto space-y-6">
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <KeyRound className="w-5 h-5 text-indigo-400" /> Settings
      </h1>

      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <h2 className="text-sm font-semibold text-white mb-4">Change Password</h2>
        <form onSubmit={submit} className="space-y-4">
          {['Current password', 'New password (min 8 chars)', 'Confirm new password'].map((label, idx) => {
            const val = [current, next, confirm][idx]
            const setter = [setCurrent, setNext, setConfirm][idx]
            return (
              <div key={idx}>
                <label className="block text-xs text-gray-500 mb-1">{label}</label>
                <div className="relative">
                  <input
                    type={showPw ? 'text' : 'password'}
                    value={val}
                    onChange={e => setter(e.target.value)}
                    required
                    className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:border-indigo-500"
                  />
                  {idx === 0 && (
                    <button type="button" onClick={() => setShowPw(s => !s)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white">
                      {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  )}
                </div>
              </div>
            )
          })}

          {error && <p className="text-xs text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Updating…' : 'Update Password'}
          </button>
        </form>

        {result && (
          <div className="mt-4 p-4 bg-green-950 border border-green-800 rounded-xl">
            <p className="text-xs text-green-400 flex items-center gap-1 mb-2">
              <CheckCircle2 className="w-3.5 h-3.5" /> {result.message}
            </p>
            <div className="flex items-center gap-2 bg-gray-900 rounded-lg px-3 py-2">
              <code className="text-xs text-gray-300 break-all flex-1">{result.new_hash}</code>
              <button
                onClick={() => navigator.clipboard.writeText(result.new_hash)}
                className="shrink-0 text-gray-500 hover:text-white transition-colors"
                title="Copy hash"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Copy this hash and set it as <code className="text-indigo-400">ADMIN_PASSWORD_HASH</code> in your Railway environment variables.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
