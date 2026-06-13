import React, { useCallback, useEffect, useState } from 'react'
import { Loader2, Pause, Play, Plus, Radio, RefreshCw, X, Zap } from 'lucide-react'
import { api } from '../api'

const PLATFORM_COLORS = {
  twitter:  'bg-sky-900 text-sky-300 border-sky-700',
  telegram: 'bg-blue-900 text-blue-300 border-blue-700',
  reddit:   'bg-orange-900 text-orange-300 border-orange-700',
  discord:  'bg-violet-900 text-violet-300 border-violet-700',
  pastebin: 'bg-green-900 text-green-300 border-green-700',
  telethon: 'bg-teal-900 text-teal-300 border-teal-700',
}

function AddScannerModal({ onCreated, onClose }) {
  const [exams, setExams] = useState([])
  const [examId, setExamId] = useState('')
  const [platform, setPlatform] = useState('twitter')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getExams().then(d => { setExams(Array.isArray(d) ? d : []); })
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const row = await api.createScanner({ exam_id: Number(examId), platform })
      onCreated(row)
    } catch (err) {
      const detail = err?.detail
      setError(detail?.error === 'scanner_already_exists'
        ? 'A scanner for this exam+platform already exists.'
        : err.message || 'Failed to create scanner')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-sm space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Add Scanner</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Exam *</label>
            <select value={examId} onChange={e => setExamId(e.target.value)} required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
              <option value="">Select exam…</option>
              {exams.map(ex => <option key={ex.id} value={ex.id}>{ex.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Platform *</label>
            <select value={platform} onChange={e => setPlatform(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
              <option value="twitter">Twitter / X</option>
              <option value="telegram">Telegram (Bot)</option>
              <option value="telethon">Telegram (User / Telethon)</option>
              <option value="reddit">Reddit</option>
              <option value="discord">Discord</option>
              <option value="pastebin">Pastebin</option>
            </select>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={loading || !examId}
              className="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-medium text-white flex items-center justify-center gap-2">
              {loading && <Loader2 className="w-4 h-4 animate-spin" />} Add Scanner
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Scanners() {
  const [scanners, setScanners] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionId, setActionId] = useState(null)
  const [showAdd, setShowAdd] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await api.getScanners()
      setScanners(Array.isArray(data) ? data : data?.scanners || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const createDemoPaste = async () => {
    const pasteText = `JEE Main 2025 - Physics Question

A particle moves in a straight line with velocity v = 3t² + 2t + 1 m/s.
Find its displacement after 2 seconds.

Options:
A) 10 m
B) 12 m  
C) 14 m
D) 16 m

#JEE #Physics #ExamLeaks`

    // Open Pastebin in new tab with pre-filled content
    const form = document.createElement('form')
    form.method = 'POST'
    form.action = 'https://pastebin.com/api/api_post.php'
    form.target = '_blank'
    
    // For demo, we'll just open Pastebin with instructions
    window.open('https://pastebin.com', '_blank')
    
    // Copy to clipboard for easy pasting
    navigator.clipboard.writeText(pasteText).then(() => {
      alert('Demo paste text copied to clipboard!\n\n1. Pastebin will open in new tab\n2. Paste the text (Ctrl+V)\n3. Title: "JEE Physics Question"\n4. Click "Create New Paste"\n5. Wait 30 seconds for scanner to detect it')
    })
  }

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

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Radio className="w-5 h-5 text-indigo-400" /> Scanners
        </h1>
        <div className="flex items-center gap-2">
          <button onClick={load} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
          <button onClick={createDemoPaste}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 border border-purple-600/50 text-purple-400 transition-colors">
            <Zap className="w-4 h-4" /> Demo Paste
          </button>
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors">
            <Plus className="w-4 h-4" /> Add Scanner
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        </div>
      ) : scanners.length === 0 ? (
        <div className="text-center py-16 text-gray-600">
          <Radio className="w-10 h-10 mx-auto mb-2 text-gray-700" />
          <p>No scanners yet. Click <strong className="text-gray-500">Add Scanner</strong> to create one.</p>
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
                    Processed: {sc.images_processed ?? 0} · Leaks: {sc.leaks_detected ?? 0}
                    {sc.last_run && ` · Last: ${new Date(sc.last_run).toLocaleTimeString()}`}
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

      {showAdd && (
        <AddScannerModal
          onCreated={row => { setScanners(ss => [...ss, { ...row, running: false, images_processed: 0, leaks_detected: 0, error_count: 0 }]); setShowAdd(false) }}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  )
}
