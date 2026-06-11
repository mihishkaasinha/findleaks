import React from 'react'
import { Link } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-950 px-4 text-center">
      <ShieldAlert className="w-16 h-16 text-indigo-500 mb-4" />
      <h1 className="text-6xl font-bold text-white mb-2">404</h1>
      <p className="text-gray-400 mb-6">Page not found</p>
      <Link
        to="/dashboard"
        className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm font-medium text-white transition-colors"
      >
        Go to Dashboard
      </Link>
    </div>
  )
}
