import React, { useCallback, useEffect, useState } from 'react'
import { Activity, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import { api } from '../api'

function Row({ label, value, ok }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-800 last:border-0">
      <span className="text-sm text-gray-400">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-white">{String(value ?? '—')}</span>
        {ok !== undefined && (
          ok
            ? <CheckCircle2 className="w-4 h-4 text-green-400" />
            : <XCircle className="w-4 h-4 text-red-400" />
        )}
      </div>
    </div>
  )
}

export default function SystemHealth() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.health()
      setHealth(data)
      setLastUpdated(new Date())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  const isOperational = health?.status === 'operational'

  return (
    <div className="p-6 space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-400" /> System Health
        </h1>
        <button onClick={load} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading && !health ? (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        </div>
      ) : (
        <>
          <div className={`flex items-center gap-3 p-4 rounded-2xl border ${
            isOperational ? 'bg-green-950 border-green-800' : 'bg-red-950 border-red-800'
          }`}>
            {isOperational
              ? <CheckCircle2 className="w-6 h-6 text-green-400" />
              : <XCircle className="w-6 h-6 text-red-400" />}
            <div>
              <p className="text-base font-semibold text-white capitalize">{health?.status ?? 'Unknown'}</p>
              <p className="text-xs text-gray-400">
                FINDLEAKS v{health?.version ?? '1.0.0'}
                {lastUpdated && ` · Updated ${lastUpdated.toLocaleTimeString()}`}
              </p>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-2xl px-5 py-1">
            <Row label="Database" value={health?.db_status} ok={health?.db_status === 'connected'} />
            <Row label="Exams Monitored" value={health?.exams_monitored} />
            <Row label="Active Leaks" value={health?.active_leaks} />
            <Row label="FAISS Indexes Loaded" value={health?.indexes_loaded} ok={(health?.indexes_loaded ?? 0) >= 0} />
            <Row label="App Version" value={health?.version ?? '1.0.0'} />
          </div>
        </>
      )}
    </div>
  )
}
