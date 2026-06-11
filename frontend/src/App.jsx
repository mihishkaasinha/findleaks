import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import PrivateRoute from './components/PrivateRoute'
import Navbar from './components/Navbar'

import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Exams from './pages/Exams'
import Questions from './pages/Questions'
import ManualScan from './pages/ManualScan'
import Alerts from './pages/Alerts'
import Scanners from './pages/Scanners'
import SystemHealth from './pages/SystemHealth'
import Settings from './pages/Settings'
import NotFound from './pages/NotFound'

function AppLayout({ children }) {
  return (
    <div className="flex min-h-screen">
      <Navbar />
      <main className="flex-1 ml-56 min-h-screen overflow-y-auto bg-gray-950">
        {children}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          <Route path="/dashboard" element={
            <PrivateRoute>
              <AppLayout><Dashboard /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/exams" element={
            <PrivateRoute>
              <AppLayout><Exams /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/scan" element={
            <PrivateRoute>
              <AppLayout><ManualScan /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/alerts" element={
            <PrivateRoute>
              <AppLayout><Alerts /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/scanners" element={
            <PrivateRoute>
              <AppLayout><Scanners /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/health" element={
            <PrivateRoute>
              <AppLayout><SystemHealth /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/exams/:examId/questions" element={
            <PrivateRoute>
              <AppLayout><Questions /></AppLayout>
            </PrivateRoute>
          } />
          <Route path="/settings" element={
            <PrivateRoute>
              <AppLayout><Settings /></AppLayout>
            </PrivateRoute>
          } />

          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
