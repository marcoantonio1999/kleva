import { useEffect, useMemo, useRef, useState } from 'react'

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
  insurerId?: string
  insurerName?: string
}

type CallRow = {
  call_sid: string
  stream_sid?: string | null
  from_number?: string | null
  to_number?: string | null
  insurer_id?: string | null
  insurer_name?: string | null
  status: string
  created_at?: string | null
  ended_at?: string | null
}

type InsurerConfig = {
  id: string
  name: string
  phone_number?: string | null
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
  const [insurers, setInsurers] = useState<InsurerConfig[]>([])
  const [cases, setCases] = useState<CasesPayload>({ claims: [], complaints: [], emergencies: [] })
  const [selectedInsurerId, setSelectedInsurerId] = useState<string>('all')
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
        const [healthResp, insurersResp, callsResp, casesResp] = await Promise.all([
          fetch(`${API_BASE}/health`),
          fetch(`${API_BASE}/api/insurers`),
          fetch(`${API_BASE}/api/calls?limit=50`),
          fetch(`${API_BASE}/api/cases?limit=20`),
        ])

        if (!healthResp.ok || !insurersResp.ok || !callsResp.ok || !casesResp.ok) {
          markService('backend', { status: 'down', detail: 'API respondio con error' })
          appendServiceLog('backend', `HTTP no-ok health=${healthResp.status} insurers=${insurersResp.status} calls=${callsResp.status} cases=${casesResp.status}`)
          return
        }

        markService('backend', { status: 'up', detail: 'API disponible y respondiendo' })
        appendServiceLog('backend', 'Chequeo periodico exitoso')

        const insurersData = (await insurersResp.json()) as { items: InsurerConfig[] }
        const callsData = (await callsResp.json()) as { items: CallRow[] }
        const casesData = (await casesResp.json()) as CasesPayload
        if (!cancelled) {
          setInsurers(insurersData.items)
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
    const byInsurer =
      selectedInsurerId === 'all'
        ? events
        : events.filter((event) => {
            if (event.insurerId) {
              return event.insurerId === selectedInsurerId
            }
            const call = calls.find((row) => row.call_sid === event.callSid)
            return call?.insurer_id === selectedInsurerId
          })

    if (!selectedCallSid) {
      return byInsurer
    }
    return byInsurer.filter((event) => event.callSid === selectedCallSid)
  }, [calls, events, selectedCallSid, selectedInsurerId])

  const filteredCalls = useMemo(() => {
    if (selectedInsurerId === 'all') {
      return calls
    }
    return calls.filter((call) => call.insurer_id === selectedInsurerId)
  }, [calls, selectedInsurerId])

  const callSidSet = useMemo(() => new Set(filteredCalls.map((call) => call.call_sid)), [filteredCalls])

  const filteredCaseCounts = useMemo(() => {
    const claims = cases.claims.filter((c) => callSidSet.has(String(c.call_sid ?? ''))).length
    const complaints = cases.complaints.filter((c) => callSidSet.has(String(c.call_sid ?? ''))).length
    const emergencies = cases.emergencies.filter((c) => callSidSet.has(String(c.call_sid ?? ''))).length
    return { claims, complaints, emergencies }
  }, [callSidSet, cases])

  const insurerCards = useMemo(() => {
    const fromConfig = insurers.map((i) => ({
      id: i.id,
      name: i.name,
      phoneNumber: i.phone_number ?? '',
    }))
    const configuredIds = new Set(fromConfig.map((i) => i.id))

    const fromCalls = calls
      .filter((c) => c.insurer_id && !configuredIds.has(c.insurer_id))
      .map((c) => ({
        id: c.insurer_id as string,
        name: c.insurer_name || c.insurer_id || 'Aseguradora',
        phoneNumber: c.to_number || '',
      }))

    return [...fromConfig, ...fromCalls]
  }, [insurers, calls])

  const selectedInsurerName = useMemo(() => {
    if (selectedInsurerId === 'all') {
      return 'Todas las aseguradoras'
    }
    return insurerCards.find((i) => i.id === selectedInsurerId)?.name ?? selectedInsurerId
  }, [insurerCards, selectedInsurerId])

  const transcripts = selectedEvents.filter((event) => event.type === 'transcript')
  const toolEvents = selectedEvents.filter(
    (event) => event.type === 'tool_called' || event.type === 'tool_result' || event.type === 'openai_error'
  )

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#fff7ed,_#ffedd5_40%,_#fff_75%)] px-4 py-6 text-slate-900 md:px-8">
      <header className="mx-auto flex w-full max-w-7xl flex-col gap-4 rounded-3xl border border-orange-200/70 bg-white/80 p-6 shadow-[0_18px_55px_-25px_rgba(180,83,9,0.55)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.28em] text-orange-700">Kleva Voice Control</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">Dashboard Multiaseguradora</h1>
          <p className="mt-1 text-sm text-slate-600">Vista separada por numero de entrada con monitoreo realtime y herramientas</p>
        </div>
        <div className={`rounded-full px-4 py-2 text-sm font-semibold ${connected ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
          {connected ? 'Monitor conectado' : 'Reconectando monitor...'}
        </div>
      </header>

      <section className="mx-auto mt-5 w-full max-w-7xl rounded-3xl border border-orange-200/70 bg-white/85 p-5 shadow-[0_16px_45px_-22px_rgba(15,23,42,0.35)] backdrop-blur">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <button
            className={`rounded-full border px-3 py-1 text-sm transition ${selectedInsurerId === 'all' ? 'border-orange-500 bg-orange-500 text-white' : 'border-orange-200 bg-white text-slate-700 hover:border-orange-300'}`}
            onClick={() => setSelectedInsurerId('all')}
          >
            Todas
          </button>
          {insurerCards.map((insurer) => (
            <button
              key={insurer.id}
              className={`rounded-full border px-3 py-1 text-sm transition ${selectedInsurerId === insurer.id ? 'border-orange-500 bg-orange-500 text-white' : 'border-orange-200 bg-white text-slate-700 hover:border-orange-300'}`}
              onClick={() => setSelectedInsurerId(insurer.id)}
            >
              {insurer.name}
            </button>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article className="rounded-2xl border border-orange-100 bg-orange-50/70 p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-orange-700">Aseguradora activa</p>
            <p className="mt-2 text-lg font-semibold">{selectedInsurerName}</p>
          </article>
          <article className="rounded-2xl border border-orange-100 bg-white p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Llamadas</p>
            <p className="mt-2 text-3xl font-semibold text-orange-700">{filteredCalls.length}</p>
          </article>
          <article className="rounded-2xl border border-orange-100 bg-white p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Quejas</p>
            <p className="mt-2 text-3xl font-semibold text-orange-700">{filteredCaseCounts.complaints}</p>
          </article>
          <article className="rounded-2xl border border-orange-100 bg-white p-4">
            <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Emergencias</p>
            <p className="mt-2 text-3xl font-semibold text-orange-700">{filteredCaseCounts.emergencies}</p>
          </article>
        </div>
      </section>

      <section className="mx-auto mt-5 grid w-full max-w-7xl gap-4 xl:grid-cols-[1.1fr_1.5fr_1.1fr]">
        <div className="rounded-3xl border border-orange-200/70 bg-white/90 p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Llamadas</h2>
          <div className="mt-3 flex max-h-[520px] flex-col gap-2 overflow-auto pr-1">
            {filteredCalls.length === 0 && <p className="text-sm text-slate-500">Sin llamadas registradas para esta aseguradora.</p>}
            {filteredCalls.map((call) => (
              <button
                key={call.call_sid}
                className={`rounded-xl border p-3 text-left transition ${selectedCallSid === call.call_sid ? 'border-orange-400 bg-orange-50' : 'border-slate-200 bg-white hover:border-orange-200'}`}
                onClick={() => setSelectedCallSid(call.call_sid)}
              >
                <p className="font-mono text-xs text-slate-500">{call.call_sid}</p>
                <p className="mt-1 text-sm text-slate-700">
                  {call.from_number || 'desconocido'} -&gt; {call.to_number || 'desconocido'}
                </p>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-slate-500">{call.insurer_name || 'Sin marca'}</span>
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${call.status === 'completed' ? 'bg-emerald-100 text-emerald-700' : 'bg-sky-100 text-sky-700'}`}>{call.status}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-orange-200/70 bg-white/90 p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Transcripcion en vivo</h2>
          <div className="mt-3 flex max-h-[520px] flex-col gap-2 overflow-auto pr-1">
            {transcripts.length === 0 && <p className="text-sm text-slate-500">Esperando transcripciones...</p>}
            {transcripts.map((item, index) => (
              <article
                key={`${item.timestamp}-${index}`}
                className={`rounded-xl border p-3 ${item.role === 'assistant' ? 'border-emerald-200 bg-emerald-50/40' : 'border-sky-200 bg-sky-50/50'}`}
              >
                <header className="mb-1 flex items-center justify-between text-xs text-slate-500">
                  <strong className="text-slate-700">{item.role === 'assistant' ? 'IA' : 'Cliente'}</strong>
                  <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                </header>
                <p className="text-sm text-slate-800">{item.text}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="rounded-3xl border border-orange-200/70 bg-white/90 p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Tools y eventos</h2>
          <div className="mt-3 flex max-h-[520px] flex-col gap-2 overflow-auto pr-1">
            {toolEvents.length === 0 && <p className="text-sm text-slate-500">Sin tools invocadas todavia.</p>}
            {toolEvents.map((item, index) => (
              <article key={`${item.timestamp}-${index}`} className="rounded-xl border border-amber-200 bg-amber-50/40 p-3">
                <header className="mb-1 flex items-center justify-between text-xs text-slate-500">
                  <strong className="text-slate-700">{item.type}</strong>
                  <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                </header>
                <pre className="overflow-auto rounded-lg bg-white/70 p-2 font-mono text-xs text-slate-700">
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

      <section className="mx-auto mt-5 grid w-full max-w-7xl gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="rounded-3xl border border-orange-200/70 bg-white/90 p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Estado de servicios</h2>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {(Object.keys(SERVICE_LABELS) as ServiceKey[]).map((key) => {
              const service = services[key]
              return (
                <article key={key} className="rounded-xl border border-slate-200 bg-white p-3">
                  <header className="flex items-center justify-between gap-2">
                    <strong>{SERVICE_LABELS[key]}</strong>
                    <span
                      className={`rounded-full px-2 py-1 text-[11px] font-semibold uppercase tracking-wide ${
                        service.status === 'up'
                          ? 'bg-emerald-100 text-emerald-700'
                          : service.status === 'down'
                            ? 'bg-rose-100 text-rose-700'
                            : service.status === 'warn'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      {service.status}
                    </span>
                  </header>
                  <p className="mt-1 text-sm text-slate-700">{service.detail}</p>
                  <small className="text-xs text-slate-500">{service.lastSeen ? new Date(service.lastSeen).toLocaleTimeString() : 'sin eventos'}</small>
                </article>
              )
            })}
          </div>
        </div>

        <div className="rounded-3xl border border-orange-200/70 bg-white/90 p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Logs por servicio</h2>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {(Object.keys(SERVICE_LABELS) as ServiceKey[]).map((key) => (
              <article key={key} className="flex min-h-[180px] flex-col rounded-xl border border-slate-200 bg-white p-3">
                <header className="mb-2">
                  <strong>{SERVICE_LABELS[key]}</strong>
                </header>
                <div className="flex flex-col gap-1 overflow-auto">
                  {serviceLogs[key].length === 0 && <p className="text-sm text-slate-500">Sin logs aun.</p>}
                  {serviceLogs[key].map((line, idx) => (
                    <p key={`${key}-${idx}`} className="font-mono text-xs text-slate-700">
                      {line}
                    </p>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto mt-5 grid w-full max-w-7xl gap-4 md:grid-cols-3">
        <div className="rounded-3xl border border-orange-200/70 bg-white p-5 text-center shadow-sm">
          <h2 className="text-sm uppercase tracking-[0.2em] text-slate-500">Ajustes</h2>
          <p className="mt-2 text-4xl font-semibold text-orange-700">{filteredCaseCounts.claims}</p>
        </div>
        <div className="rounded-3xl border border-orange-200/70 bg-white p-5 text-center shadow-sm">
          <h2 className="text-sm uppercase tracking-[0.2em] text-slate-500">Quejas</h2>
          <p className="mt-2 text-4xl font-semibold text-orange-700">{filteredCaseCounts.complaints}</p>
        </div>
        <div className="rounded-3xl border border-orange-200/70 bg-white p-5 text-center shadow-sm">
          <h2 className="text-sm uppercase tracking-[0.2em] text-slate-500">Emergencias</h2>
          <p className="mt-2 text-4xl font-semibold text-orange-700">{filteredCaseCounts.emergencies}</p>
        </div>
      </section>
    </main>
  )
}

export default App
