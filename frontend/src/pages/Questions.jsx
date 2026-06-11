import React, { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { BookOpen, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { api } from '../api'

export default function Questions() {
  const { examId } = useParams()
  const [exam, setExam] = useState(null)
  const [data, setData] = useState({ items: [], total: 0, total_pages: 1 })
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [examData, qData] = await Promise.all([
        api.getExam(examId),
        api.getQuestions(examId, { page, page_size: 50 }),
      ])
      setExam(examData)
      setData(qData)
    } finally {
      setLoading(false)
    }
  }, [examId, page])

  useEffect(() => { load() }, [load])

  const filtered = search
    ? data.items.filter(q => q.question_text.toLowerCase().includes(search.toLowerCase()))
    : data.items

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto">
      <div className="flex items-center gap-3">
        <Link to="/exams" className="text-gray-500 hover:text-white transition-colors">
          <ChevronLeft className="w-5 h-5" />
        </Link>
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-indigo-400" />
            {exam?.name || `Exam #${examId}`} — Question Bank
          </h1>
          <p className="text-xs text-gray-500">{data.total} questions indexed</p>
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search questions…"
          className="w-full pl-9 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500"
        />
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-7 w-7 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-600">
          <BookOpen className="w-10 h-10 mx-auto mb-2 text-gray-700" />
          <p>{search ? 'No questions match your search.' : 'No questions indexed yet. Upload a question bank first.'}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((q, i) => (
            <div key={q.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors">
              <div className="flex items-start gap-3">
                <span className="shrink-0 text-xs text-gray-600 font-mono mt-0.5 w-8">
                  {q.page_number ? `p.${q.page_number}` : `#${(page - 1) * 50 + i + 1}`}
                </span>
                <p className="text-sm text-gray-300 leading-relaxed">{q.question_text}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {data.total_pages > 1 && !search && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 disabled:opacity-30 transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-gray-500">Page {page} of {data.total_pages}</span>
          <button
            onClick={() => setPage(p => Math.min(data.total_pages, p + 1))}
            disabled={page === data.total_pages}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 disabled:opacity-30 transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}
