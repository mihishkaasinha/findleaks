import React from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  LayoutDashboard, BookOpen, ScanLine, Bell, Radio, Activity, LogOut, Settings, ShieldAlert
} from 'lucide-react'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/exams', label: 'Exams', icon: BookOpen },
  { to: '/scan', label: 'Manual Scan', icon: ScanLine },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/scanners', label: 'Scanners', icon: Radio },
  { to: '/health', label: 'System', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <nav className="fixed inset-y-0 left-0 w-56 bg-gray-900 border-r border-gray-800 flex flex-col z-20">
      <div className="flex items-center gap-2 px-4 py-5 border-b border-gray-800">
        <ShieldAlert className="text-indigo-400 w-6 h-6" />
        <span className="text-lg font-bold tracking-tight text-white">FINDLEAKS</span>
      </div>

      <ul className="flex-1 overflow-y-auto py-4 space-y-1 px-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="px-4 py-4 border-t border-gray-800">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500 truncate">{user?.username}</span>
          <button
            onClick={handleLogout}
            className="p-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors"
            title="Logout"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </nav>
  )
}
