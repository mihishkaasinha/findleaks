import React, { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, X, FileText, Clock, Tag } from 'lucide-react'
import { api } from '../api'

const LABEL_STYLES = {
  high: 'bg-red-900 text-red-300 border-red-700',
  medium: 'bg-yellow-900 text-yellow-300 border-yellow-700',
  low: 'bg-blue-900 text-blue-300 border-blue-700',
}

export default function LeakDetailModal({ leak, onClose, onPatched }) {
  const [alerts, setAlerts] = useState([])
  const [patching, setPatching] = useState(false)

  useEffect(() => {
    api.getAlerts({ leak_id: leak.id }).then(d => setAlerts(d?.items || []))
  }, [leak.id])

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
      <div
        className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <h2 className="text-base font-semibold text-white">Leak #{leak.id}</h2>
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${LABEL_STYLES[leak.confidence_label] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
              {leak.confidence_label}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="bg-gray-800 rounded-xl p-3">
              <p className="text-gray-500 text-xs mb-1">Exam</p>
              <p className="text-white font-medium">{leak.exam_name || `#${leak.exam_id}`}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-3">
              <p className="text-gray-500 text-xs mb-1">Platform</p>
              <p className="text-white font-medium capitalize">{leak.platform}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-3">
              <p className="text-gray-500 text-xs mb-1">Confidence</p>
              <p className="text-white font-medium">{(leak.confidence * 100).toFixed(1)}%</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-3">
              <p className="text-gray-500 text-xs mb-1">Status</p>
              <p className="text-white font-medium capitalize">{leak.status}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-3">
              <p className="text-gray-500 text-xs mb-1">Matched Questions</p>
              <p className="text-white font-medium">{leak.matched_question_count}</p>
            </div>
            <div className="bg-gray-800 rounded-xl p-3">
              <p className="text-gray-500 text-xs mb-1">Detected</p>
              <p className="text-white font-medium">{new Date(leak.timestamp).toLocaleString()}</p>
            </div>
          </div>

          {leak.ocr_text_preview && (
            <div className="bg-gray-800 rounded-xl p-4">
              <p className="text-xs text-gray-500 mb-2 flex items-center gap-1"><FileText className="w-3 h-3" /> OCR Text</p>
              <p className="text-sm text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">{leak.ocr_text_preview}</p>
            </div>
          )}

          {alerts.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2 flex items-center gap-1"><Tag className="w-3 h-3" /> Alerts Sent</p>
              <div className="space-y-2">
                {alerts.map(a => (
                  <div key={a.id} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2 text-xs">
                    <span className="text-gray-300">{a.method} → {a.sent_to}</span>
                    <span className={a.status === 'sent' ? 'text-green-400' : 'text-red-400'}>{a.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {leak.status === 'new' && (
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => patch('acknowledged')}
                disabled={patching}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-green-900 hover:bg-green-800 text-green-300 border border-green-700 text-sm font-medium transition-colors disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4" /> Acknowledge
              </button>
              <button
                onClick={() => patch('false_positive')}
                disabled={patching}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-600 text-sm font-medium transition-colors disabled:opacity-50"
              >
                <X className="w-4 h-4" /> False Positive
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
