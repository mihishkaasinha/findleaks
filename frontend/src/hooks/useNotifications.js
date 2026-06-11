import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

export function useNotifications(onNewLeak) {
  const esRef = useRef(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('fl_token')
    if (!token) return

    const url = api.notificationsUrl()
    const es = new EventSource(`${url}?token=${token}`)
    esRef.current = es

    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        if (event.type === 'new_leak') onNewLeak?.(event)
      } catch {}
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [])

  return connected
}
