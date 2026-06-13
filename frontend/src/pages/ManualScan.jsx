import React, { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, FileText, Fingerprint, Loader2, ScanLine, ShieldAlert, ShieldCheck, Upload, X, Zap, Play } from 'lucide-react'
import { api } from '../api'

function highlightCommon(text, otherText) {
  if (!text || !otherText) return text
  const stopwords = new Set('a an the is are was were be been have has had do does did will would could should may might of in on at to for with by from and or but not no this that these those i we you he she it they'.split(' '))
  const otherWords = new Set(
    otherText.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(w => w.length > 2 && !stopwords.has(w))
  )
  const tokens = text.split(/(\s+)/)
  return tokens.map((token, i) => {
    const clean = token.toLowerCase().replace(/[^a-z0-9]/g, '')
    if (clean.length > 2 && otherWords.has(clean)) {
      return <mark key={i} className="bg-yellow-400/30 text-yellow-200 rounded px-0.5">{token}</mark>
    }
    return token
  })
}

function ConfidenceMeter({ value, label }) {
  const pct = Math.round(value * 100)
  const color = label === 'high' ? '#ef4444' : label === 'review' ? '#eab308' : '#22c55e'
  const circumference = 2 * Math.PI * 40
  const dash = (pct / 100) * circumference
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="100" height="100" className="-rotate-90">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#1f2937" strokeWidth="8" />
        <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s ease' }} />
      </svg>
      <div className="text-center -mt-16 mb-10">
        <p className="text-2xl font-bold text-white">{pct}%</p>
        <p className="text-xs text-gray-400">match</p>
      </div>
      <span className={`text-xs font-bold px-3 py-1 rounded-full ${
        label === 'high' ? 'bg-red-500/20 text-red-400 border border-red-700' :
        label === 'review' ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-700' :
        'bg-green-500/20 text-green-400 border border-green-700'
      }`}>
        {label === 'high' ? '⚠ HIGH RISK' : label === 'review' ? '◎ REVIEW' : '✓ CLEAN'}
      </span>
    </div>
  )
}

export default function ManualScan() {
  const [exams, setExams] = useState([])
  const [examId, setExamId] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const fileRef = useRef(null)

  useEffect(() => {
    api.getExams().then(data => setExams(Array.isArray(data) ? data : data?.items || [])).catch(() => {})
  }, [])

  const handleFile = (f) => {
    if (!f) return
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setResult(null)
    setError('')
  }

  const handleScan = async () => {
    if (!file || !examId) return
    setLoading(true)
    setError('')
    try {
      const res = await api.scanImage(Number(examId), file)
      setResult(res)
    } catch (err) {
      setError(err.message || 'Scan failed')
    } finally {
      setLoading(false)
    }
  }

  const reset = () => { setFile(null); setPreview(null); setResult(null); setError('') }

  const loadDemoImage = async () => {
    if (!examId) { setError('Select an exam first'); return }
    setError('')
    try {
      // Fetch a real question from the bank so the demo guarantees a match
      const data = await api.getQuestions(Number(examId), { page: 1, page_size: 10 })
      const questions = Array.isArray(data) ? data : (data?.items || [])
      // API returns question_text field
      const q = questions.find(q => (q.question_text || q.text)?.trim().length > 20) || questions[0]
      const questionText = (q?.question_text || q?.text)?.trim() || null
      if (!questionText) { setError('No questions found in bank — upload questions first'); return }

      // Wrap text to ~60 chars per line for canvas rendering
      const wrapText = (text, maxLen = 60) => {
        const words = text.split(' ')
        const lines = []
        let current = ''
        for (const word of words) {
          if ((current + ' ' + word).trim().length <= maxLen) {
            current = (current + ' ' + word).trim()
          } else {
            if (current) lines.push(current)
            current = word
          }
        }
        if (current) lines.push(current)
        return lines
      }

      const wrappedLines = wrapText(questionText)
      const canvasHeight = Math.max(300, 160 + wrappedLines.length * 28)

      const canvas = document.createElement('canvas')
      canvas.width = 700
      canvas.height = canvasHeight
      const ctx = canvas.getContext('2d')

      // White background — best for OCR
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, 700, canvasHeight)

      // Border
      ctx.strokeStyle = '#cccccc'
      ctx.lineWidth = 2
      ctx.strokeRect(20, 20, 660, canvasHeight - 40)

      // Header
      ctx.fillStyle = '#111111'
      ctx.font = 'bold 18px Georgia'
      ctx.fillText('Confidential Exam Paper — Leaked Copy', 30, 55)

      ctx.fillStyle = '#888888'
      ctx.font = '12px Arial'
      ctx.fillText('Source: Telegram channel @examdrops2025  |  DO NOT SHARE', 30, 75)

      // Divider
      ctx.strokeStyle = '#aaaaaa'
      ctx.beginPath(); ctx.moveTo(30, 85); ctx.lineTo(670, 85); ctx.stroke()

      // Question text from actual bank
      ctx.fillStyle = '#111111'
      ctx.font = '16px Georgia'
      ctx.fillText('Q1.', 30, 115)
      wrappedLines.forEach((line, i) => {
        ctx.fillText(line, 55, 115 + i * 28)
      })

      // Footer watermark
      ctx.fillStyle = '#cccccc'
      ctx.font = '11px Arial'
      ctx.fillText('Strictly Confidential — For Examiner Use Only', 30, canvasHeight - 25)

      canvas.toBlob(blob => {
        const file = new File([blob], 'demo-leak.jpg', { type: 'image/jpeg' })
        handleFile(file)
      }, 'image/jpeg', 0.95)
    } catch (err) {
      console.error('Demo image error:', err)
      setError('Demo mode failed — make sure an exam with questions is selected')
    }
  }

  
  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <ScanLine className="w-5 h-5 text-indigo-400" /> Manual Scan
      </h1>

      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Select Exam</label>
          <select
            value={examId}
            onChange={e => setExamId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
          >
            <option value="">— choose an exam —</option>
            {exams.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </div>

        <div
          onDrop={e => { e.preventDefault(); handleFile(e.dataTransfer.files[0]) }}
          onDragOver={e => e.preventDefault()}
          onClick={() => !file && fileRef.current?.click()}
          className={`relative border-2 border-dashed rounded-xl transition-colors ${
            file ? 'border-indigo-600' : 'border-gray-700 hover:border-indigo-600 cursor-pointer'
          } flex items-center justify-center min-h-48 overflow-hidden`}
        >
          {preview ? (
            <>
              <img src={preview} alt="preview" className="max-h-64 object-contain rounded-lg" />
              <button onClick={e => { e.stopPropagation(); reset() }}
                className="absolute top-2 right-2 p-1 bg-black/60 rounded-full text-gray-300 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </>
          ) : (
            <div className="text-center py-8 px-4">
              <Upload className="w-8 h-8 text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-400">Drop an image or click to browse</p>
              <p className="text-xs text-gray-600 mt-1">PNG, JPEG, WebP supported</p>
            </div>
          )}
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => handleFile(e.target.files[0])} />
        </div>

        {error && (
          <p className="text-sm text-red-400 flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" />{error}</p>
        )}

        <button
          onClick={handleScan}
          disabled={!file || !examId || loading}
          className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium text-white flex items-center justify-center gap-2 transition-colors"
        >
          {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Scanning…</> : <><ScanLine className="w-4 h-4" />Run Scan</>}
        </button>

        <div className="flex gap-2">
          <button
            onClick={loadDemoImage}
            disabled={loading}
            className="flex-1 py-2 rounded-lg bg-purple-600/20 hover:bg-purple-600/30 border border-purple-600/50 disabled:opacity-50 text-xs font-medium text-purple-400 flex items-center justify-center gap-1.5 transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            Demo Mode: Load Test Image
          </button>
          {exams.length > 0 && !examId && (
            <button
              onClick={() => setExamId(exams[0].id)}
              className="px-3 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-xs text-gray-300"
            >
              Select First Exam
            </button>
          )}
        </div>
      </div>

      {result && (() => {
        const top = result.matched_excerpts?.[0]
        const isLeak = result.leak_detected
        return (
          <div className="space-y-4">
            {/* Header verdict */}
            <div className={`border rounded-2xl p-5 flex items-center gap-4 ${
              isLeak ? 'border-red-700 bg-red-950/40' : 'border-green-700 bg-green-950/40'
            }`}>
              {isLeak
                ? <ShieldAlert className="w-10 h-10 text-red-400 shrink-0" />
                : <ShieldCheck className="w-10 h-10 text-green-400 shrink-0" />}
              <div className="flex-1 min-w-0">
                <p className="text-lg font-bold text-white">{isLeak ? 'Potential Leak Detected' : 'No Match Found'}</p>
                <p className="text-sm text-gray-400">{result.exam} · {result.matched_questions} question{result.matched_questions !== 1 ? 's' : ''} matched
                  {result.leak_id ? <span className="ml-2 font-mono text-xs text-gray-500">#{result.leak_id}</span> : null}
                </p>
              </div>
              <ConfidenceMeter value={result.confidence} label={result.confidence_label} />
            </div>

            {/* Side-by-side forensic panel */}
            {top && (
              <div className="border border-gray-700 rounded-2xl overflow-hidden">
                <div className="grid grid-cols-2 divide-x divide-gray-700">
                  {/* Left: OCR extracted from uploaded image */}
                  <div className="p-4 space-y-2 bg-gray-900">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-400 uppercase tracking-wider">
                      <Zap className="w-3.5 h-3.5" /> Extracted from Upload
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                      {result.ocr_text
                        ? highlightCommon(result.ocr_text.slice(0, 600), top.text)
                        : <span className="text-gray-600 italic">No text extracted</span>}
                    </p>
                  </div>
                  {/* Right: Best matching question from bank */}
                  <div className="p-4 space-y-2 bg-gray-900/60">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-yellow-400 uppercase tracking-wider">
                        <Fingerprint className="w-3.5 h-3.5" /> Best Match in Question Bank
                      </div>
                      <span className="text-xs font-bold text-yellow-300 bg-yellow-500/20 px-2 py-0.5 rounded-full border border-yellow-700">
                        {(top.score * 100).toFixed(1)}% similar
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                      {highlightCommon(top.text?.slice(0, 600) || `Question #${top.question_id}`, result.ocr_text || '')}
                    </p>
                  </div>
                </div>
                <div className="bg-gray-800/50 px-4 py-2 flex items-center gap-2">
                  <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full transition-all duration-1000 ${
                        result.confidence_label === 'high' ? 'bg-red-500' :
                        result.confidence_label === 'review' ? 'bg-yellow-500' : 'bg-green-500'
                      }`}
                      style={{ width: `${(top.score * 100).toFixed(0)}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-500">Similarity score</span>
                </div>
              </div>
            )}

            {/* All matches ranked */}
            {result.matched_excerpts?.length > 1 && (
              <div className="border border-gray-800 rounded-2xl p-4 space-y-2 bg-gray-900">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5" /> All Matched Questions
                </p>
                {result.matched_excerpts.map((ex, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-gray-600 w-4 shrink-0">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-400 truncate">{ex.text?.slice(0, 120) || `Question #${ex.question_id}`}</p>
                      <div className="mt-1 h-1 bg-gray-800 rounded-full">
                        <div className="h-1 rounded-full bg-indigo-500" style={{ width: `${(ex.score * 100).toFixed(0)}%` }} />
                      </div>
                    </div>
                    <span className="text-xs font-mono text-indigo-300 shrink-0">{(ex.score * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}
