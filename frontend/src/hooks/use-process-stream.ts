"use client"

import { useRef, useState } from "react"
import { useMountEffect } from "@/lib/useMountEffect"
import { API_BASE } from "@/lib/api-client"

interface ProcessState {
  status: string
  progress: number
  message: string
  error?: string
}

const IDLE = { state: null, isConnected: false }

// #525: reconnect with backoff after onerror. A single transient blip
// (proxy idle drop, network timeout) or the backend's 60s inactivity
// timeout used to permanently close the stream — UI froze on the last
// received percentage until the 10-min isStale heuristic. Cap retries
// to avoid hammering; exponential backoff with jitter.
const MAX_RETRIES = 5
const BASE_BACKOFF_MS = 500
const TERMINAL_STATUSES = ["completed", "failed", "cancelled"]

export function useProcessStream(taskId: string | null) {
  const [state, setState] = useState<ProcessState | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const retryCountRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useMountEffect(() => {
    if (!taskId) return

    const connect = () => {
      const es = new EventSource(`${API_BASE}/process/${taskId}/stream`, {
        withCredentials: true,
      })
      esRef.current = es

      es.onopen = () => {
        setIsConnected(true)
        retryCountRef.current = 0
      }
      // #525: wrap JSON.parse in try/catch — a malformed SSE frame used
      // to throw inside onmessage and silently kill the handler.
      es.onmessage = e => {
        let data: ProcessState
        try {
          data = JSON.parse(e.data)
        } catch {
          return
        }
        setState(data)
        if (TERMINAL_STATUSES.includes(data.status)) {
          es.close()
          setIsConnected(false)
        }
      }
      es.onerror = () => {
        setIsConnected(false)
        es.close()
        // #525: schedule reconnect with exponential backoff + jitter.
        // Cap at MAX_RETRIES — beyond that the user should see a
        // permanent "disconnected" state and refresh.
        if (retryCountRef.current < MAX_RETRIES) {
          const attempt = retryCountRef.current
          retryCountRef.current += 1
          const backoff = BASE_BACKOFF_MS * 2 ** attempt
          const jitter = Math.random() * backoff * 0.3
          reconnectTimerRef.current = setTimeout(connect, backoff + jitter)
        }
      }
    }

    connect()

    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      esRef.current?.close()
      setIsConnected(false)
    }
  })

  if (!taskId) return IDLE
  return { state, isConnected }
}
