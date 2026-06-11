import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import Login from '../src/pages/Login'

const mockLogin = vi.fn()

vi.mock('../src/context/AuthContext', () => ({
  useAuth: () => ({ login: mockLogin }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => vi.fn() }
})

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

describe('Login page', () => {
  beforeEach(() => {
    mockLogin.mockReset()
  })

  it('renders username and password inputs', () => {
    renderLogin()
    expect(screen.getByTestId('username-input')).toBeTruthy()
    expect(screen.getByTestId('password-input')).toBeTruthy()
    expect(screen.getByTestId('login-button')).toBeTruthy()
  })

  it('shows loading state when submitting', async () => {
    mockLogin.mockReturnValue(new Promise(() => {}))
    renderLogin()
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'secret' } })
    fireEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => {
      expect(screen.getByText(/Signing in/i)).toBeTruthy()
    })
  })

  it('shows error on invalid credentials', async () => {
    mockLogin.mockRejectedValue(
      Object.assign(new Error('bad creds'), { detail: { error: 'invalid_credentials' } })
    )
    renderLogin()
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeTruthy()
    })
  })

  it('redirects on success', async () => {
    mockLogin.mockResolvedValue({ token: 'abc' })
    renderLogin()
    fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'correct' } })
    fireEvent.click(screen.getByTestId('login-button'))
    await waitFor(() => {
      expect(screen.getByText(/Login successful/i)).toBeTruthy()
    })
  })

  it('disables button after 5 failed attempts', async () => {
    mockLogin.mockRejectedValue(
      Object.assign(new Error('bad'), { detail: { error: 'invalid_credentials' } })
    )
    renderLogin()
    for (let i = 0; i < 5; i++) {
      fireEvent.change(screen.getByTestId('password-input'), { target: { value: 'wrong' } })
      fireEvent.click(screen.getByTestId('login-button'))
      await waitFor(() => screen.queryByTestId('error-message'))
    }
    const btn = screen.getByTestId('login-button')
    expect(btn.disabled).toBe(true)
  })
})
