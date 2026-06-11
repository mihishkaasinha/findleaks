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

function QuestionBankUpload({ exam, onClose }) {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('idle')
  const [progress, setProgress] = useState(0)
  const [taskId, setTaskId] = useState(null)
  const [message, setMessage] = useState('')
  const fileRef = useRef(null)

  const handleDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }

  const upload = async () => {
    if (!file) return
    setStatus('uploading')
    try {
      const res = await api.uploadQuestions(exam.id, file)
      setTaskId(res.task_id)
      setStatus('processing')
      pollProgress(res.task_id)
    } catch (err) {
      setStatus('error')
      setMessage(err.message)
    }
  }

  const pollProgress = (tid) => {
    const token = localStorage.getItem('fl_token')
    const es = new EventSource(`/api/exams/${exam.id}/upload-progress/${tid}?token=${token}`)
    es.onmessage = (e) => {
      const ev = JSON.parse(e.data)
      if (ev.type === 'progress') { setProgress(ev.percent); setMessage(ev.message) }
      if (ev.type === 'complete') { setStatus('done'); setProgress(100); setMessage(`${ev.question_count} questions indexed`); es.close() }
      if (ev.type === 'error') { setStatus('error'); setMessage(ev.message); es.close() }
    }
    es.onerror = () => { es.close() }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-40 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-md space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Upload Question Bank</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-sm text-gray-400">Exam: <span className="text-white">{exam.name}</span></p>

        <div
          onDrop={handleDrop} onDragOver={e => e.preventDefault()}
          className="border-2 border-dashed border-gray-700 rounded-xl p-6 text-center cursor-pointer hover:border-indigo-500 transition-colors"
          onClick={() => fileRef.current?.click()}
        >
          <Upload className="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p className="text-sm text-gray-400">{file ? file.name : 'Drop PDF or image here, or click to browse'}</p>
          <input ref={fileRef} type="file" accept=".pdf,image/*" className="hidden" onChange={e => setFile(e.target.files[0])} />
        </div>

        {status === 'processing' || status === 'uploading' ? (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-gray-400">
              <span>{message || 'Processing…'}</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5">
              <div className="bg-indigo-500 h-1.5 rounded-full transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>
        ) : null}

        {status === 'done' && <p className="text-sm text-green-400">✓ {message}</p>}
        {status === 'error' && <p className="text-sm text-red-400">✗ {message}</p>}

        <div className="flex gap-2">
          <button onClick={upload} disabled={!file || status === 'processing' || status === 'uploading' || status === 'done'}
            className="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm font-medium text-white flex items-center justify-center gap-2">
            {(status === 'uploading' || status === 'processing') && <Loader2 className="w-4 h-4 animate-spin" />}
            Upload
          </button>
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-300">Close</button>
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
      {uploadExam && <QuestionBankUpload exam={uploadExam} onClose={() => setUploadExam(null)} />}
      {editExam && <ExamEditModal exam={editExam} onSaved={updated => { setExams(es => es.map(e => e.id === updated.id ? { ...e, ...updated } : e)); setEditExam(null) }} onClose={() => setEditExam(null)} />}
    </div>
  )
}
