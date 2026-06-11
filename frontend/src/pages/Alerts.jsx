import React, { useCallback, useEffect, useState } from 'react'
import { Bell, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import { api } from '../api'

const STATUS_COLORS = {
  sent: 'text-green-400',
  failed: 'text-red-400',
  rate_limited: 'text-yellow-400',
  not_configured: 'text-gray-500',
}

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await api.getAlerts()
      setAlerts(Array.isArray(data) ? data : data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Bell className="w-5 h-5 text-indigo-400" /> Alert Log
        </h1>
        <button onClick={load} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-16 text-gray-600">
          <Bell className="w-10 h-10 mx-auto mb-2 text-gray-700" />
          <p>No alerts sent yet</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert, i) => (
            <div key={alert.id ?? i} className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                {alert.status === 'sent'
                  ? <CheckCircle2 className="w-4 h-4 text-green-400 shrink-0" />
                  : <XCircle className="w-4 h-4 text-red-400 shrink-0" />}
                <div>
                  <p className="text-sm text-white">{alert.channel || alert.method || 'alert'} → {alert.recipient || alert.url || alert.to}</p>
                  <p className="text-xs text-gray-500">{alert.exam_name} · {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : ''}</p>
                </div>
              </div>
              <span className={`text-xs font-medium shrink-0 ${STATUS_COLORS[alert.status] || 'text-gray-400'}`}>
                {alert.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
