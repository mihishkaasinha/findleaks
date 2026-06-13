import React, { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileText, Fingerprint, Loader2, Tag, X, Zap } from 'lucide-react'
import { api } from '../api'

const LABEL_STYLES = {
  high: 'bg-red-900/60 text-red-300 border-red-700',
  review: 'bg-yellow-900/60 text-yellow-300 border-yellow-700',
  low: 'bg-blue-900/60 text-blue-300 border-blue-700',
  clean: 'bg-green-900/60 text-green-300 border-green-700',
}

function ConfidenceMeter({ value, label }) {
  const pct = Math.round(value * 100)
  const color = label === 'high' ? '#ef4444' : label === 'review' ? '#eab308' : '#22c55e'
  const circumference = 2 * Math.PI * 34
  const dash = (pct / 100) * circumference
  return (
    <div className="flex flex-col items-center gap-1 shrink-0">
      <svg width="84" height="84" className="-rotate-90">
        <circle cx="42" cy="42" r="34" fill="none" stroke="#1f2937" strokeWidth="7" />
        <circle cx="42" cy="42" r="34" fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={`${dash} ${circumference}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s ease' }} />
      </svg>
      <div className="text-center -mt-14 mb-8">
        <p className="text-xl font-bold text-white">{pct}%</p>
        <p className="text-[10px] text-gray-400">match</p>
      </div>
      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
        label === 'high' ? 'bg-red-500/20 text-red-400 border-red-700' :
        label === 'review' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-700' :
        'bg-green-500/20 text-green-400 border-green-700'
      }`}>
        {label === 'high' ? '⚠ HIGH' : label === 'review' ? '◎ REVIEW' : '✓ CLEAN'}
      </span>
    </div>
  )
}

function highlightCommon(text, otherText) {
  if (!text || !otherText) return text
  const stop = new Set((
    'a an the is are was were be been have has had do does did will would could should may might ' +
    'of in on at to for with by from and or but not no this that these those i we you he she it they ' +
    'which one two three four five six seven eight nine ten following each all any only also just ' +
    'find given value correct option answer question paper section part marks time total maximum ' +
    'zero none both either neither every other such more less most least always never often'
  ).split(' '))
  const other = new Set(otherText.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(w => w.length > 3 && !stop.has(w)))
  return text.split(/(\s+)/).map((tok, i) => {
    const clean = tok.toLowerCase().replace(/[^a-z0-9]/g, '')
    if (clean.length > 3 && other.has(clean))
      return <mark key={i} className="bg-yellow-400/30 text-yellow-200 rounded px-0.5">{tok}</mark>
    return tok
  })
}

export default function LeakDetailModal({ leak, onClose, onPatched }) {
  const [detail, setDetail] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [patching, setPatching] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getLeak(leak.id).then(setDetail).catch(() => setDetail(null)),
      api.getAlerts({ leak_id: leak.id }).then(d => setAlerts(d?.items || [])).catch(() => {}),
    ]).finally(() => setLoadingDetail(false))
  }, [leak.id])

  const d = detail || leak
  const top = detail?.matched_excerpts?.[0]

  const patch = async (newStatus) => {
    setPatching(true)
    try {
      await api.patchLeak(leak.id, { status: newStatus })
      onPatched?.({ ...leak, status: newStatus })
    } finally {
      setPatching(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-3xl max-h-[92vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <h2 className="text-base font-semibold text-white">Leak #{leak.id}</h2>
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${LABEL_STYLES[d.confidence_label] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
              {d.confidence_label}
            </span>
            {loadingDetail && <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-500" />}
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* Verdict bar */}
          <div className={`border rounded-2xl p-4 flex items-center gap-4 ${
            d.confidence_label === 'high' ? 'border-red-700 bg-red-950/30' :
            d.confidence_label === 'review' ? 'border-yellow-700 bg-yellow-950/30' :
            'border-green-700 bg-green-950/30'
          }`}>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white capitalize">{d.platform} · {d.exam_name || `Exam #${d.exam_id}`}</p>
              <p className="text-xs text-gray-400 mt-0.5">{d.matched_question_count ?? detail?.matched_excerpts?.length ?? 0} question(s) matched · {new Date(d.timestamp).toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5 capitalize">Status: {d.status}</p>
            </div>
            <ConfidenceMeter value={d.confidence} label={d.confidence_label} />
          </div>

          {/* Side-by-side comparison */}
          {top && (
            <div className="border border-gray-700 rounded-2xl overflow-hidden">
              <div className="grid grid-cols-2 divide-x divide-gray-700">
                <div className="p-4 space-y-2 bg-gray-900">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                    <Zap className="w-3.5 h-3.5" /> Detected Content
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed max-h-52 overflow-y-auto whitespace-pre-wrap font-mono text-xs">
                    {d.ocr_text
                      ? highlightCommon(d.ocr_text.slice(0, 800), top.text || '')
                      : <span className="text-gray-600 italic">No text available</span>}
                  </p>
                </div>
                <div className="p-4 space-y-2 bg-gray-900/60">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-yellow-400 uppercase tracking-wider">
                      <Fingerprint className="w-3.5 h-3.5" /> Best Match in Question Bank
                    </div>
                    <span className="text-xs font-bold text-yellow-300 bg-yellow-500/20 px-2 py-0.5 rounded-full border border-yellow-700">
                      {(top.score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed max-h-52 overflow-y-auto whitespace-pre-wrap font-mono text-xs">
                    {top.text
                      ? highlightCommon(top.text.slice(0, 800), d.ocr_text || '')
                      : <span className="text-gray-500 italic">Question #{top.question_id}</span>}
                  </p>
                </div>
              </div>
              <div className="bg-gray-800/50 px-4 py-2 flex items-center gap-3">
                <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                  <div className={`h-1.5 rounded-full transition-all duration-1000 ${
                    d.confidence_label === 'high' ? 'bg-red-500' :
                    d.confidence_label === 'review' ? 'bg-yellow-500' : 'bg-green-500'
                  }`} style={{ width: `${(top.score * 100).toFixed(0)}%` }} />
                </div>
                <span className="text-xs text-gray-500 shrink-0">Similarity score</span>
              </div>
            </div>
          )}

          {/* All matches ranked */}
          {detail?.matched_excerpts?.length > 1 && (
            <div className="border border-gray-800 rounded-2xl p-4 space-y-2.5 bg-gray-900">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" /> All Matched Questions ({detail.matched_excerpts.length})
              </p>
              {detail.matched_excerpts.map((ex, i) => (
                <div key={i} className="flex items-start gap-3">
                  <span className="text-xs text-gray-600 w-4 shrink-0 mt-0.5">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-400 line-clamp-2">
                      {ex.text?.slice(0, 140) || `Question #${ex.question_id}`}
                    </p>
                    <div className="mt-1.5 h-1 bg-gray-800 rounded-full">
                      <div className="h-1 rounded-full bg-indigo-500 transition-all duration-700"
                        style={{ width: `${(ex.score * 100).toFixed(0)}%` }} />
                    </div>
                  </div>
                  <span className="text-xs font-mono text-indigo-300 shrink-0 mt-0.5">{(ex.score * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Alerts sent */}
          {alerts.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2 flex items-center gap-1"><Tag className="w-3 h-3" /> Alerts Sent</p>
              <div className="space-y-1.5">
                {alerts.map(a => (
                  <div key={a.id} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2 text-xs">
                    <span className="text-gray-300">{a.method} → {a.sent_to}</span>
                    <span className={a.status === 'sent' ? 'text-green-400' : 'text-red-400'}>{a.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          {d.status === 'new' && (
            <div className="flex gap-3 pt-1">
              <button onClick={() => patch('acknowledged')} disabled={patching}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-green-900 hover:bg-green-800 text-green-300 border border-green-700 text-sm font-medium transition-colors disabled:opacity-50">
                <CheckCircle2 className="w-4 h-4" /> Acknowledge
              </button>
              <button onClick={() => patch('false_positive')} disabled={patching}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-600 text-sm font-medium transition-colors disabled:opacity-50">
                <X className="w-4 h-4" /> False Positive
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
