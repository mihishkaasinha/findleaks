import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Bell, CheckCircle2, Clock, RefreshCw, Shield, TrendingUp } from 'lucide-react'
import { api } from '../api'
import LeakDetailModal from '../components/LeakDetailModal'
import { useNotifications } from '../hooks/useNotifications'

const CONFIDENCE_COLORS = {
  high: 'text-red-400 bg-red-950 border-red-800',
  review: 'text-yellow-400 bg-yellow-950 border-yellow-800',
  clean: 'text-green-400 bg-green-950 border-green-800',
}

function LeakCard({ leak, onAck, onFP, onOpen }) {
  return (
    <div onClick={onOpen} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3 hover:border-gray-700 transition-colors cursor-pointer">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-white">{leak.exam_name || `Exam #${leak.exam_id}`}</p>
          <p className="text-xs text-gray-500 mt-0.5">{leak.platform} · {new Date(leak.timestamp).toLocaleString()}</p>
        </div>
        <span className={`shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full border ${CONFIDENCE_COLORS[leak.confidence_label] || CONFIDENCE_COLORS.clean}`}>
          {(leak.confidence * 100).toFixed(0)}% {leak.confidence_label}
        </span>
      </div>

      {leak.ocr_text && (
        <p className="text-xs text-gray-400 bg-gray-800 rounded-lg px-3 py-2 line-clamp-3">
          {leak.ocr_text}
        </p>
      )}

      {leak.status === 'new' && (
        <div className="flex gap-2">
          <button
            onClick={() => onAck(leak.id)}
            className="text-xs px-3 py-1 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
          >
            Acknowledge
          </button>
          <button
            onClick={() => onFP(leak.id)}
            className="text-xs px-3 py-1 rounded-md bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
          >
            False Positive
          </button>
        </div>
      )}
      {leak.status !== 'new' && (
        <span className="text-xs text-gray-500 italic">{leak.status}</span>
      )}
    </div>
  )
}

function StatCard({ label, value, icon: Icon, color = 'text-indigo-400' }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-4">
      <div className={`p-2 rounded-lg bg-gray-800 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-white">{value ?? '—'}</p>
        <p className="text-xs text-gray-500">{label}</p>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [leaks, setLeaks] = useState([])
  const [health, setHealth] = useState(null)
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [selectedLeak, setSelectedLeak] = useState(null)
  const [toast, setToast] = useState(null)
  const PAGE_SIZE = 10

  const notifConnected = useNotifications((event) => {
    setToast(event)
    setTimeout(() => setToast(null), 6000)
    load()
  })

  const load = useCallback(async () => {
    try {
      const [leakData, healthData] = await Promise.all([
        api.getLeaks(),
        api.health(),
      ])
      setLeaks(Array.isArray(leakData) ? leakData : leakData?.items || [])
      setHealth(healthData)
    } catch {
      /* silently retry on next interval */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  const handleAck = async (id) => {
    await api.patchLeak(id, { status: 'acknowledged' })
    setLeaks(ls => ls.map(l => l.id === id ? { ...l, status: 'acknowledged' } : l))
    setSelectedLeak(s => s?.id === id ? { ...s, status: 'acknowledged' } : s)
  }

  const handleFP = async (id) => {
    await api.patchLeak(id, { status: 'false_positive' })
    setLeaks(ls => ls.map(l => l.id === id ? { ...l, status: 'false_positive' } : l))
    setSelectedLeak(s => s?.id === id ? { ...s, status: 'false_positive' } : s)
  }

  const filtered = filter === 'all' ? leaks : leaks.filter(l => l.status === filter)
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      {toast && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-3 bg-red-950 border border-red-700 rounded-xl px-4 py-3 shadow-xl animate-in slide-in-from-right">
          <Bell className="w-4 h-4 text-red-400 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-red-300">New Leak Detected</p>
            <p className="text-xs text-gray-400">{toast.exam_name} · {(toast.confidence * 100).toFixed(0)}% {toast.confidence_label}</p>
          </div>
          <button onClick={() => setToast(null)} className="text-gray-600 hover:text-white ml-2">✕</button>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold text-white">Dashboard</h1>
          {notifConnected && <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" title="Live notifications active" />}
        </div>
        <button onClick={load} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Leaks" value={health?.active_leaks} icon={AlertTriangle} color="text-red-400" />
        <StatCard label="Exams Monitored" value={health?.exams_monitored} icon={Shield} color="text-indigo-400" />
        <StatCard label="Indexes Loaded" value={health?.indexes_loaded} icon={TrendingUp} color="text-green-400" />
        <StatCard label="DB Status" value={health?.db_status} icon={CheckCircle2}
          color={health?.db_status === 'connected' ? 'text-green-400' : 'text-red-400'} />
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          {['all', 'new', 'acknowledged', 'false_positive'].map(f => (
            <button key={f} onClick={() => { setFilter(f); setPage(1) }}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                filter === f ? 'border-indigo-500 bg-indigo-600 text-white' : 'border-gray-700 text-gray-400 hover:border-gray-500'
              }`}
            >
              {f === 'all' ? 'All' : f.replace('_', ' ')}
              {f === 'new' && leaks.filter(l => l.status === 'new').length > 0 && (
                <span className="ml-1.5 bg-red-500 text-white text-[10px] rounded-full px-1.5">
                  {leaks.filter(l => l.status === 'new').length}
                </span>
              )}
            </button>
          ))}
          <span className="ml-auto text-xs text-gray-500">{filtered.length} leaks</span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
          </div>
        ) : paged.length === 0 ? (
          <div className="text-center py-16 text-gray-600">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-2 text-gray-700" />
            <p>No leaks {filter !== 'all' ? `with status "${filter}"` : 'detected yet'}</p>
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {paged.map(leak => (
              <LeakCard key={leak.id} leak={leak} onAck={handleAck} onFP={handleFP}
                onOpen={e => { e.stopPropagation(); setSelectedLeak(leak) }} />
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 pt-2">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
              className="text-xs px-3 py-1 rounded-md border border-gray-700 text-gray-400 hover:border-gray-500 disabled:opacity-40">
              Previous
            </button>
            <span className="text-xs text-gray-500">{page} / {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
              className="text-xs px-3 py-1 rounded-md border border-gray-700 text-gray-400 hover:border-gray-500 disabled:opacity-40">
              Next
            </button>
          </div>
        )}
      </div>

      {selectedLeak && (
        <LeakDetailModal
          leak={selectedLeak}
          onClose={() => setSelectedLeak(null)}
          onPatched={updated => {
            setLeaks(ls => ls.map(l => l.id === updated.id ? { ...l, ...updated } : l))
            setSelectedLeak(null)
          }}
        />
      )}
    </div>
  )
}
