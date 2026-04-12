import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

type MonitorEvent = {
  timestamp: string
  type: string
  callSid?: string
  streamSid?: string
  role?: 'caller' | 'assistant'
  text?: string
  name?: string
  arguments?: Record<string, unknown>
  result?: Record<string, unknown>
  from?: string
  to?: string
  error?: unknown
}

type CallRow = {
  call_sid: string
  stream_sid?: string | null
  from_number?: string | null
  to_number?: string | null
  status: string
  created_at?: string | null
  ended_at?: string | null
}

type CasesPayload = {
  claims: Array<Record<string, unknown>>
  complaints: Array<Record<string, unknown>>
  emergencies: Array<Record<string, unknown>>
}

type ServiceKey = 'backend' | 'monitor' | 'twilio' | 'openai' | 'tools'

type ServiceState = {
  status: 'up' | 'down' | 'warn' | 'idle'
  detail: string
  lastSeen?: string
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

const SERVICE_LABELS: Record<ServiceKey, string> = {
  backend: 'Backend API',
  monitor: 'Monitor WS',
  twilio: 'Twilio Media',
  openai: 'OpenAI Realtime',
  tools: 'Tools and RAG',
}

const EMPTY_SERVICE_LOGS: Record<ServiceKey, string[]> = {
  backend: [],
  monitor: [],
  twilio: [],
  openai: [],
  tools: [],
}

const EMPTY_SERVICE_STATES: Record<ServiceKey, ServiceState> = {
  backend: { status: 'idle', detail: 'Esperando chequeo inicial' },
  monitor: { status: 'idle', detail: 'Esperando WebSocket' },
  twilio: { status: 'idle', detail: 'Sin stream activo' },
  openai: { status: 'idle', detail: 'Sin sesion activa' },
  tools: { status: 'idle', detail: 'Sin ejecucion de tools' },
}

function toWsUrl(apiBase: string, path: string): string {
  if (apiBase.startsWith('https://')) {
    return `${apiBase.replace('https://', 'wss://')}${path}`
  }
  if (apiBase.startsWith('http://')) {
    return `${apiBase.replace('http://', 'ws://')}${path}`
  }
  return `ws://${apiBase}${path}`
}

function App() {
  const [events, setEvents] = useState<MonitorEvent[]>([])
  const [calls, setCalls] = useState<CallRow[]>([])
  const [cases, setCases] = useState<CasesPayload>({ claims: [], complaints: [], emergencies: [] })
  const [selectedCallSid, setSelectedCallSid] = useState<string>('')
  const [connected, setConnected] = useState(false)
  const [services, setServices] = useState<Record<ServiceKey, ServiceState>>(EMPTY_SERVICE_STATES)
  const [serviceLogs, setServiceLogs] = useState<Record<ServiceKey, string[]>>(EMPTY_SERVICE_LOGS)
  const wsRef = useRef<WebSocket | null>(null)

  const wsUrl = useMemo(() => toWsUrl(API_BASE, '/monitor/ws'), [])

  const appendServiceLog = (service: ServiceKey, message: string) => {
    const line = `[${new Date().toLocaleTimeString()}] ${message}`
    setServiceLogs((prev) => ({
      ...prev,
      [service]: [line, ...prev[service]].slice(0, 80),
    }))
  }

  const markService = (service: ServiceKey, state: Omit<ServiceState, 'lastSeen'>) => {
    setServices((prev) => ({
      ...prev,
      [service]: {
        ...state,
        lastSeen: new Date().toISOString(),
      },
    }))
  }

  useEffect(() => {
    let stop = false
    let retryTimer: number | undefined
    let pingTimer: number | undefined

    const connect = () => {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        markService('monitor', { status: 'up', detail: 'Canal de monitoreo conectado' })
        appendServiceLog('monitor', 'Conexion establecida con /monitor/ws')
        pingTimer = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping')
          }
        }, 15000)
      }

      ws.onmessage = (msg) => {
        try {
          const payload = JSON.parse(msg.data) as MonitorEvent
          setEvents((prev) => [payload, ...prev].slice(0, 600))

          if (payload.type === 'call_started') {
            markService('twilio', { status: 'up', detail: 'Media stream activo' })
            appendServiceLog('twilio', `Llamada iniciada ${payload.callSid ?? ''}`)
          }
          if (payload.type === 'call_ended') {
            markService('twilio', { status: 'warn', detail: 'Ultima llamada finalizada' })
            appendServiceLog('twilio', `Llamada finalizada ${payload.callSid ?? ''}`)
          }
          if (payload.type === 'bridge_error') {
            markService('twilio', { status: 'down', detail: 'Error en bridge Twilio/OpenAI' })
            appendServiceLog('twilio', `Bridge error: ${JSON.stringify(payload.error)}`)
          }
          if (payload.type === 'openai_session_ready') {
            markService('openai', { status: 'up', detail: 'Sesion realtime lista' })
            appendServiceLog('openai', `Sesion lista para call ${payload.callSid ?? ''}`)
          }
          if (payload.type === 'openai_error') {
            markService('openai', { status: 'down', detail: 'OpenAI devolvio error' })
            appendServiceLog('openai', `Error: ${JSON.stringify(payload.error)}`)
          }
          if (payload.type === 'tool_called') {
            markService('tools', { status: 'warn', detail: `Ejecutando ${payload.name ?? 'tool'}` })
            appendServiceLog('tools', `Tool llamada: ${payload.name ?? 'desconocida'}`)
          }
          if (payload.type === 'tool_result') {
            markService('tools', { status: 'up', detail: `Tool completada ${payload.name ?? ''}` })
            appendServiceLog('tools', `Tool resultado: ${payload.name ?? 'desconocida'}`)
          }

          if (payload.type === 'call_started' && payload.callSid) {
            setSelectedCallSid((curr) => curr || payload.callSid || '')
          }
        } catch {
          // Ignore malformed monitor payloads.
        }
      }

      ws.onclose = () => {
        setConnected(false)
        markService('monitor', { status: 'down', detail: 'WebSocket desconectado' })
        appendServiceLog('monitor', 'Conexion cerrada; reintentando')
        if (pingTimer) {
          clearInterval(pingTimer)
        }
        if (!stop) {
          retryTimer = window.setTimeout(connect, 1500)
        }
      }
    }

    connect()

    return () => {
      stop = true
      if (retryTimer) {
        clearTimeout(retryTimer)
      }
      if (pingTimer) {
        clearInterval(pingTimer)
      }
      wsRef.current?.close()
    }
  }, [wsUrl])

  useEffect(() => {
    let cancelled = false

    const fetchData = async () => {
      try {
        const [healthResp, callsResp, casesResp] = await Promise.all([
          fetch(`${API_BASE}/health`),
          fetch(`${API_BASE}/api/calls?limit=50`),
          fetch(`${API_BASE}/api/cases?limit=20`),
        ])

        if (!healthResp.ok || !callsResp.ok || !casesResp.ok) {
          markService('backend', { status: 'down', detail: 'API respondio con error' })
          appendServiceLog('backend', `HTTP no-ok health=${healthResp.status} calls=${callsResp.status} cases=${casesResp.status}`)
          return
        }

        markService('backend', { status: 'up', detail: 'API disponible y respondiendo' })
        appendServiceLog('backend', 'Chequeo periodico exitoso')

        const callsData = (await callsResp.json()) as { items: CallRow[] }
        const casesData = (await casesResp.json()) as CasesPayload
        if (!cancelled) {
          setCalls(callsData.items)
          setCases(casesData)
          if (!selectedCallSid && callsData.items.length > 0) {
            setSelectedCallSid(callsData.items[0].call_sid)
          }
        }
      } catch {
        markService('backend', { status: 'down', detail: 'Sin conexion con backend' })
        appendServiceLog('backend', 'No se pudo contactar API')
        // Keep UI alive even if backend is not yet up.
      }
    }

    void fetchData()
    const timer = window.setInterval(fetchData, 6000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [selectedCallSid])

  const selectedEvents = useMemo(() => {
    if (!selectedCallSid) {
      return events
    }
    return events.filter((event) => event.callSid === selectedCallSid)
  }, [events, selectedCallSid])

  const transcripts = selectedEvents.filter((event) => event.type === 'transcript')
  const toolEvents = selectedEvents.filter(
    (event) => event.type === 'tool_called' || event.type === 'tool_result' || event.type === 'openai_error'
  )

  return (
    <main className="layout">
      <header className="header">
        <div>
          <h1>SeguraNova VoiceOps</h1>
          <p>Monitor en tiempo real de llamadas, transcripciones y tools</p>
        </div>
        <div className={`status ${connected ? 'ok' : 'down'}`}>
          {connected ? 'Monitor conectado' : 'Reconectando monitor...'}
        </div>
      </header>

      <section className="grid">
        <div className="panel">
          <h2>Llamadas</h2>
          <div className="list">
            {calls.length === 0 && <p className="muted">Sin llamadas registradas aun.</p>}
            {calls.map((call) => (
              <button
                key={call.call_sid}
                className={`callRow ${selectedCallSid === call.call_sid ? 'active' : ''}`}
                onClick={() => setSelectedCallSid(call.call_sid)}
              >
                <span className="mono">{call.call_sid}</span>
                <span>
                  {call.from_number || 'desconocido'} -&gt; {call.to_number || 'desconocido'}
                </span>
                <span className={`badge ${call.status}`}>{call.status}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <h2>Transcripcion en vivo</h2>
          <div className="feed">
            {transcripts.length === 0 && <p className="muted">Esperando transcripciones...</p>}
            {transcripts.map((item, index) => (
              <article key={`${item.timestamp}-${index}`} className={`line ${item.role === 'assistant' ? 'assistant' : 'caller'}`}>
                <header>
                  <strong>{item.role === 'assistant' ? 'IA' : 'Cliente'}</strong>
                  <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                </header>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="panel">
          <h2>Tools y eventos</h2>
          <div className="feed">
            {toolEvents.length === 0 && <p className="muted">Sin tools invocadas todavia.</p>}
            {toolEvents.map((item, index) => (
              <article key={`${item.timestamp}-${index}`} className="line system">
                <header>
                  <strong>{item.type}</strong>
                  <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                </header>
                <pre>
                  {JSON.stringify(
                    {
                      name: item.name,
                      arguments: item.arguments,
                      result: item.result,
                      error: item.error,
                    },
                    null,
                    2
                  )}
                </pre>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="services">
        <div className="panel">
          <h2>Estado de servicios</h2>
          <div className="serviceGrid">
            {(Object.keys(SERVICE_LABELS) as ServiceKey[]).map((key) => {
              const service = services[key]
              return (
                <article key={key} className="serviceCard">
                  <header>
                    <strong>{SERVICE_LABELS[key]}</strong>
                    <span className={`svcBadge ${service.status}`}>{service.status}</span>
                  </header>
                  <p>{service.detail}</p>
                  <small>{service.lastSeen ? new Date(service.lastSeen).toLocaleTimeString() : 'sin eventos'}</small>
                </article>
              )
            })}
          </div>
        </div>

        <div className="panel">
          <h2>Logs por servicio</h2>
          <div className="serviceLogs">
            {(Object.keys(SERVICE_LABELS) as ServiceKey[]).map((key) => (
              <article key={key} className="serviceLogBlock">
                <header>
                  <strong>{SERVICE_LABELS[key]}</strong>
                </header>
                <div className="logList">
                  {serviceLogs[key].length === 0 && <p className="muted">Sin logs aun.</p>}
                  {serviceLogs[key].map((line, idx) => (
                    <p key={`${key}-${idx}`} className="mono logLine">
                      {line}
                    </p>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="cases">
        <div className="panel compact">
          <h2>Ajustes</h2>
          <p className="metric">{cases.claims.length}</p>
        </div>
        <div className="panel compact">
          <h2>Quejas</h2>
          <p className="metric">{cases.complaints.length}</p>
        </div>
        <div className="panel compact">
          <h2>Emergencias</h2>
          <p className="metric">{cases.emergencies.length}</p>
        </div>
      </section>
    </main>
  )
}

export default App
