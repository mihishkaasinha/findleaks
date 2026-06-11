import React, { useCallback, useEffect, useState } from 'react'
import { Loader2, Pause, Play, Radio, RefreshCw } from 'lucide-react'
import { api } from '../api'

export default function Scanners() {
  const [scanners, setScanners] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionId, setActionId] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await api.getScanners()
      setScanners(Array.isArray(data) ? data : data?.scanners || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = async (scanner) => {
    setActionId(scanner.id)
    try {
      if (scanner.running) {
        await api.stopScanner(scanner.id)
        setScanners(ss => ss.map(s => s.id === scanner.id ? { ...s, running: false, enabled: false } : s))
      } else {
        await api.startScanner(scanner.id)
        setScanners(ss => ss.map(s => s.id === scanner.id ? { ...s, running: true, enabled: true } : s))
      }
    } catch (err) {
      console.error(err)
    } finally {
      setActionId(null)
    }
  }

  const PLATFORM_COLORS = {
    twitter: 'bg-sky-900 text-sky-300 border-sky-700',
    telegram: 'bg-blue-900 text-blue-300 border-blue-700',
  }

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Radio className="w-5 h-5 text-indigo-400" /> Scanners
        </h1>
        <button onClick={load} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        </div>
      ) : scanners.length === 0 ? (
        <div className="text-center py-16 text-gray-600">
          <Radio className="w-10 h-10 mx-auto mb-2 text-gray-700" />
          <p>No scanners configured. Create an exam to auto-generate scanners.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {scanners.map(sc => (
            <div key={sc.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center justify-between gap-4 hover:border-gray-700 transition-colors">
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${sc.running ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${PLATFORM_COLORS[sc.platform] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
                      {sc.platform}
                    </span>
                    <span className="text-sm text-white">Exam #{sc.exam_id}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Posts checked: {sc.posts_checked ?? 0} · Leaks found: {sc.leaks_found ?? 0}
                    {sc.last_checked_at && ` · Last: ${new Date(sc.last_checked_at).toLocaleTimeString()}`}
                  </p>
                </div>
              </div>

              <button
                onClick={() => toggle(sc)}
                disabled={actionId === sc.id}
                className={`shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 ${
                  sc.running
                    ? 'bg-red-900 hover:bg-red-800 text-red-300 border border-red-700'
                    : 'bg-green-900 hover:bg-green-800 text-green-300 border border-green-700'
                }`}
              >
                {actionId === sc.id
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : sc.running ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                {sc.running ? 'Stop' : 'Start'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
