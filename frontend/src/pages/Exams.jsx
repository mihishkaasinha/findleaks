import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Edit2, Loader2, Plus, Trash2, Upload, X } from 'lucide-react'
import { api } from '../api'

function ExamCreateForm({ onCreated, onClose }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [keywords, setKeywords] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const exam = await api.createExam({
        name,
        alert_recipients: email.split(',').map(s => s.trim()).filter(Boolean),
        keywords: keywords ? keywords.split(',').map(s => s.trim()).filter(Boolean) : undefined,
      })
      onCreated(exam)
    } catch (err) {
      setError(err.message || 'Failed to create exam')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-md space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">New Exam</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Exam Name *</label>
            <input value={name} onChange={e => setName(e.target.value)} required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Alert Recipients (comma-separated) *</label>
            <input value={email} onChange={e => setEmail(e.target.value)} required
              placeholder="admin@exam.com, team@exam.com"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Keywords (comma-separated, optional)</label>
            <input value={keywords} onChange={e => setKeywords(e.target.value)}
              placeholder="NEET, biology, chemistry"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={loading}
              className="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-medium text-white flex items-center justify-center gap-2">
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              Create Exam
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function QuestionBankUpload({ exam, onClose, onUploaded }) {
  const [queue, setQueue] = useState([])  // [{id, file, status, progress, message}]
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)
  const processingRef = useRef(false)

  const addFiles = (fileList) => {
    const newEntries = Array.from(fileList).map(f => ({
      id: `${f.name}-${Date.now()}-${Math.random()}`,
      file: f,
      status: 'pending',
      progress: 0,
      message: '',
    }))
    setQueue(q => [...q, ...newEntries])
  }

  const handleDrop = (e) => {
    e.preventDefault()
    addFiles(e.dataTransfer.files)
  }

  const pollProgress = (examId, tid, entryId) => new Promise((resolve) => {
    const token = localStorage.getItem('fl_token')
    const es = new EventSource(`/api/exams/${examId}/upload-progress/${tid}?token=${token}`)
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      if (ev.type === 'progress') {
        setQueue(q => q.map(x => x.id === entryId ? { ...x, progress: ev.percent, message: ev.message } : x))
      }
      if (ev.type === 'complete') {
        setQueue(q => q.map(x => x.id === entryId ? { ...x, status: 'done', progress: 100, message: `+${ev.question_count} questions added` } : x))
        es.close()
        resolve(ev.question_count || 0)
      }
      if (ev.type === 'error') {
        setQueue(q => q.map(x => x.id === entryId ? { ...x, status: 'error', message: ev.message } : x))
        es.close()
        resolve(0)
      }
    }
    es.onerror = () => { es.close(); resolve(0) }
  })

  const uploadAll = async () => {
    if (processingRef.current) return
    processingRef.current = true
    setBusy(true)
    let totalAdded = 0

    setQueue(q => q.map(x => x.status === 'pending' ? { ...x, status: 'queued' } : x))

    for (const entry of queue.filter(x => x.status === 'pending' || x.status === 'queued')) {
      setQueue(q => q.map(x => x.id === entry.id ? { ...x, status: 'uploading', progress: 5 } : x))
      try {
        const res = await api.uploadQuestions(exam.id, entry.file)
        setQueue(q => q.map(x => x.id === entry.id ? { ...x, status: 'processing', progress: 20, message: 'Processing…' } : x))
        const count = await pollProgress(exam.id, res.task_id, entry.id)
        totalAdded += count
      } catch (err) {
        setQueue(q => q.map(x => x.id === entry.id ? { ...x, status: 'error', message: err.message } : x))
      }
    }

    setBusy(false)
    processingRef.current = false
    if (totalAdded > 0 && onUploaded) onUploaded(totalAdded)
  }

  const removeEntry = (id) => setQueue(q => q.filter(x => x.id !== id))

  const pendingCount = queue.filter(x => x.status === 'pending' || x.status === 'queued').length
  const doneCount = queue.filter(x => x.status === 'done').length

  const statusIcon = (s) => {
    if (s === 'done') return <span className="text-green-400 text-xs">✓</span>
    if (s === 'error') return <span className="text-red-400 text-xs">✗</span>
    if (s === 'uploading' || s === 'processing') return <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
    return <span className="text-gray-600 text-xs">○</span>
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-lg space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Upload Question Sets</h2>
            <p className="text-xs text-gray-500 mt-0.5">Each file is added to the existing question bank — nothing is overwritten</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-sm text-gray-400">Exam: <span className="text-white font-medium">{exam.name}</span>
          <span className="text-gray-600 ml-2">({exam.question_count ?? 0} questions already indexed)</span>
        </p>

        <div
          onDrop={handleDrop} onDragOver={e => e.preventDefault()}
          className="border-2 border-dashed border-gray-700 rounded-xl p-5 text-center cursor-pointer hover:border-indigo-500 transition-colors"
          onClick={() => fileRef.current?.click()}
        >
          <Upload className="w-7 h-7 text-gray-600 mx-auto mb-1.5" />
          <p className="text-sm text-gray-400">Drop PDFs or images here, or <span className="text-indigo-400">click to browse</span></p>
          <p className="text-xs text-gray-600 mt-0.5">Select multiple files at once</p>
          <input ref={fileRef} type="file" accept=".pdf,image/*" multiple className="hidden"
            onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
        </div>

        {queue.length > 0 && (
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
            {queue.map(entry => (
              <div key={entry.id} className="bg-gray-800 rounded-lg px-3 py-2 space-y-1">
                <div className="flex items-center gap-2">
                  {statusIcon(entry.status)}
                  <span className="text-xs text-gray-300 flex-1 truncate">{entry.file.name}</span>
                  {entry.status === 'pending' && !busy && (
                    <button onClick={() => removeEntry(entry.id)} className="text-gray-600 hover:text-red-400">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {entry.message && (
                    <span className={`text-xs shrink-0 ${entry.status === 'done' ? 'text-green-400' : entry.status === 'error' ? 'text-red-400' : 'text-gray-500'}`}>
                      {entry.message}
                    </span>
                  )}
                </div>
                {(entry.status === 'uploading' || entry.status === 'processing') && (
                  <div className="w-full bg-gray-700 rounded-full h-1">
                    <div className="bg-indigo-500 h-1 rounded-full transition-all" style={{ width: `${entry.progress}%` }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {doneCount > 0 && !busy && (
          <p className="text-xs text-green-400">✓ {doneCount} file{doneCount > 1 ? 's' : ''} uploaded successfully</p>
        )}

        <div className="flex gap-2">
          <button
            onClick={uploadAll}
            disabled={busy || pendingCount === 0}
            className="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-medium text-white flex items-center justify-center gap-2"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {busy ? 'Uploading…' : `Upload ${pendingCount > 0 ? `${pendingCount} file${pendingCount > 1 ? 's' : ''}` : ''}`}
          </button>
          <button onClick={onClose} disabled={busy}
            className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-sm text-gray-300">
            {doneCount > 0 && !busy ? 'Done' : 'Cancel'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ExamEditModal({ exam, onSaved, onClose }) {
  const [name, setName] = useState(exam.name || '')
  const [keywords, setKeywords] = useState((exam.keywords || []).join(', '))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const updated = await api.updateExam(exam.id, {
        name: name || undefined,
        keywords: keywords ? keywords.split(',').map(s => s.trim()).filter(Boolean) : [],
      })
      onSaved(updated)
    } catch (err) {
      setError(err.message || 'Failed to update exam')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-md space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Edit Exam</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Exam Name</label>
            <input value={name} onChange={e => setName(e.target.value)} required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Keywords (comma-separated)</label>
            <input value={keywords} onChange={e => setKeywords(e.target.value)}
              placeholder="NEET, biology"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500" />
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={loading}
              className="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-medium text-white flex items-center justify-center gap-2">
              {loading && <Loader2 className="w-4 h-4 animate-spin" />} Save
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Exams() {
  const [exams, setExams] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [uploadExam, setUploadExam] = useState(null)
  const [editExam, setEditExam] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await api.getExams()
      setExams(Array.isArray(data) ? data : data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const deleteExam = async (exam) => {
    if (!confirm(`Delete "${exam.name}"? This cannot be undone.`)) return
    await api.deleteExam(exam.id)
    setExams(es => es.filter(e => e.id !== exam.id))
  }

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Exams</h1>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors">
          <Plus className="w-4 h-4" /> New Exam
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" /></div>
      ) : exams.length === 0 ? (
        <div className="text-center py-16 text-gray-600">
          <BookOpen className="w-10 h-10 mx-auto mb-2 text-gray-700" />
          <p>No exams yet. Create one to start monitoring.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {exams.map(exam => (
            <div key={exam.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white">{exam.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {exam.question_count ?? 0} questions · slug: {exam.slug}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Link to={`/exams/${exam.id}/questions`}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-colors">
                    <BookOpen className="w-3.5 h-3.5" /> Questions
                  </Link>
                  <button onClick={() => setUploadExam(exam)}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors">
                    <Upload className="w-3.5 h-3.5" /> Upload
                  </button>
                  <button onClick={() => setEditExam(exam)}
                    className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors">
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => deleteExam(exam)}
                    className="p-1.5 rounded-lg bg-gray-800 hover:bg-red-900 text-gray-500 hover:text-red-400 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <ExamCreateForm onCreated={e => { setExams(es => [e, ...es]); setShowCreate(false) }} onClose={() => setShowCreate(false)} />}
      {uploadExam && (
        <QuestionBankUpload
          exam={uploadExam}
          onClose={() => setUploadExam(null)}
          onUploaded={(added) => setExams(es => es.map(e =>
            e.id === uploadExam.id ? { ...e, question_count: (e.question_count || 0) + added } : e
          ))}
        />
      )}
      {editExam && <ExamEditModal exam={editExam} onSaved={updated => { setExams(es => es.map(e => e.id === updated.id ? { ...e, ...updated } : e)); setEditExam(null) }} onClose={() => setEditExam(null)} />}
    </div>
  )
}
