import React, { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, ScanLine, Upload, X } from 'lucide-react'
import { api } from '../api'

const CONFIDENCE_COLORS = {
  high: 'border-red-700 bg-red-950',
  review: 'border-yellow-700 bg-yellow-950',
  clean: 'border-green-700 bg-green-950',
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
      </div>

      {result && (
        <div className={`border rounded-2xl p-5 space-y-3 ${CONFIDENCE_COLORS[result.confidence_label] || CONFIDENCE_COLORS.clean}`}>
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Scan Result</h2>
            <span className={`text-xs font-bold px-2 py-1 rounded-full ${
              result.confidence_label === 'high' ? 'bg-red-500 text-white' :
              result.confidence_label === 'review' ? 'bg-yellow-500 text-black' :
              'bg-green-500 text-black'
            }`}>
              {result.confidence_label?.toUpperCase()}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-xl font-bold text-white">{(result.confidence * 100).toFixed(1)}%</p>
              <p className="text-xs text-gray-400">Confidence</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-xl font-bold text-white">{result.matched_questions}</p>
              <p className="text-xs text-gray-400">Matched Qs</p>
            </div>
            <div className="bg-black/20 rounded-lg p-3">
              <p className="text-xl font-bold text-white">{result.leak_detected ? 'YES' : 'NO'}</p>
              <p className="text-xs text-gray-400">Leak Detected</p>
            </div>
          </div>

          {result.matched_excerpts?.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-400">Matched Excerpts</p>
              {result.matched_excerpts.slice(0, 3).map((ex, i) => (
                <div key={i} className="bg-black/20 rounded-lg px-3 py-2 flex items-start justify-between gap-2">
                  <p className="text-xs text-gray-300 line-clamp-2">{ex.text || `Question #${ex.question_id}`}</p>
                  <span className="text-xs text-indigo-300 shrink-0">{(ex.score * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {result.leak_id && (
            <p className="text-xs text-gray-400">Leak ID: <span className="text-white font-mono">#{result.leak_id}</span></p>
          )}
        </div>
      )}
    </div>
  )
}
