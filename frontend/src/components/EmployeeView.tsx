import { useCallback, useEffect, useState } from 'react'
import { Flag, Mail, MessageSquare, ShieldAlert, ShieldCheck, TrendingUp } from 'lucide-react'
import { apiFetch, streamSSE, subscribeRealtime } from '../lib/api'
import { EmptyState, ErrorState, LoadingState, SourceBadge } from './States'

interface InboxItem {
  simulation_id: string
  campaign_id: string
  delivered_at: string
  difficulty: number
  source: string
  email: {
    sender_name: string
    sender_email: string
    subject: string
    body: string
    link_label: string
    link_url: string
    planted_flags?: string[]
  }
  actions: string[]
}

interface ProgressData {
  anon_id: string
  arm: 'control' | 'treatment'
  department: string
  role_name: string
  risk_score: number
  risk_band: string
  next_difficulty: number
  simulations_received: number
  reported_count: number
  clicked_count: number
  submitted_count: number
  coaching_sessions_count: number
}

export function EmployeeView({ token }: { token: string }) {
  const [tab, setTab] = useState<'inbox' | 'chat' | 'progress'>('inbox')
  const [inbox, setInbox] = useState<InboxItem[]>([])
  const [progress, setProgress] = useState<ProgressData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<InboxItem | null>(null)

  // Fake landing modal (never captures typed input)
  const [landingSim, setLandingSim] = useState<InboxItem | null>(null)

  // Coaching stream state
  const [coachText, setCoachText] = useState('')
  const [coachSource, setCoachSource] = useState<string | undefined>(undefined)
  const [coachFlags, setCoachFlags] = useState<string[]>([])
  const [coachingBusy, setCoachingBusy] = useState(false)

  // Practice chat state (treatment arm only)
  const [chatSessionId, setChatSessionId] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<{ role: string; content: string }[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [chatOutcome, setChatOutcome] = useState<string | null>(null)
  const [chatDebrief, setChatDebrief] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [inboxRes, progRes] = await Promise.all([
        apiFetch<InboxItem[]>('/me/inbox', token),
        apiFetch<ProgressData>('/me/progress', token),
      ])
      setInbox(inboxRes)
      setProgress(progRes)
      if (inboxRes.length > 0 && !selected) {
        setSelected(inboxRes[0])
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [token, selected])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    return subscribeRealtime(token, (topic) => {
      if (topic.startsWith('inbox:')) {
        loadData()
      }
    })
  }, [token, loadData])

  const triggerCoaching = async (simulationId: string, action: string) => {
    setCoachingBusy(true)
    setCoachText('')
    setCoachSource(undefined)
    setCoachFlags([])
    try {
      await streamSSE(`/coach/${simulationId}?action=${encodeURIComponent(action)}`, token, null, (ev, data) => {
        if (ev === 'meta') {
          setCoachSource(data.source as string)
          setCoachFlags((data.planted_flags as string[]) || [])
        } else if (ev === 'token') {
          setCoachText((prev) => prev + ((data.token as string) || ''))
        } else if (ev === 'error') {
          setError((data.detail as string) || 'Coaching stream failed')
        }
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCoachingBusy(false)
    }
  }

  const recordAction = async (sim: InboxItem, type: 'opened' | 'clicked' | 'submitted' | 'reported') => {
    try {
      await apiFetch('/events', token, {
        method: 'POST',
        body: JSON.stringify({ simulation_id: sim.simulation_id, type }),
      })
      if (type === 'clicked') {
        setLandingSim(sim)
      }
      if (type === 'clicked' || type === 'submitted' || type === 'reported') {
        await triggerCoaching(sim.simulation_id, type)
      }
      await loadData()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const startPracticeChat = async () => {
    setChatBusy(true)
    setError(null)
    setChatOutcome(null)
    setChatDebrief(null)
    try {
      const session = await apiFetch<{ id: string; messages_json: { role: string; content: string }[] }>(
        '/chat/sessions',
        token,
        { method: 'POST', body: JSON.stringify({ simulation_id: selected?.simulation_id || null }) }
      )
      setChatSessionId(session.id)
      setChatMessages(session.messages_json || [])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setChatBusy(false)
    }
  }

  const sendChatMessage = async () => {
    if (!chatSessionId || !chatInput.trim() || chatBusy) return
    const text = chatInput.trim()
    setChatInput('')
    setChatMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }])
    setChatBusy(true)
    try {
      await streamSSE(`/chat/sessions/${chatSessionId}/messages`, token, { content: text }, (ev, data) => {
        if (ev === 'token') {
          const tok = (data.token as string) || ''
          setChatMessages((prev) => {
            const copy = [...prev]
            const last = copy[copy.length - 1]
            copy[copy.length - 1] = { ...last, content: last.content + tok }
            return copy
          })
        } else if (ev === 'done') {
          if (data.outcome) setChatOutcome(data.outcome as string)
          if (data.debrief) setChatDebrief(data.debrief as string)
        } else if (ev === 'error') {
          setError((data.detail as string) || 'Chat stream failed')
        }
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setChatBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-xl border border-indigo-500/30 bg-indigo-950/30 px-4 py-2.5 text-xs text-indigo-200">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-indigo-400" />
          <span>
            <strong>Transparency Notice:</strong> This mailbox contains simulated security-awareness training exercises. Feedback is supportive and never punitive.
          </span>
        </div>
        {progress && (
          <span className="rounded bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
            ID: {progress.anon_id} ({progress.arm})
          </span>
        )}
      </div>

      <div className="flex gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setTab('inbox')}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ${tab === 'inbox' ? 'bg-indigo-600 text-black' : 'text-slate-300 hover:bg-slate-800'}`}
        >
          <Mail className="h-4 w-4" /> Simulated Inbox
        </button>
        {progress?.arm === 'treatment' && (
          <button
            onClick={() => setTab('chat')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ${tab === 'chat' ? 'bg-indigo-600 text-black' : 'text-slate-300 hover:bg-slate-800'}`}
          >
            <MessageSquare className="h-4 w-4" /> Practice Chat
          </button>
        )}
        <button
          onClick={() => setTab('progress')}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ${tab === 'progress' ? 'bg-indigo-600 text-black' : 'text-slate-300 hover:bg-slate-800'}`}
        >
          <TrendingUp className="h-4 w-4" /> My Progress
        </button>
      </div>

      {error && <ErrorState message={error} onRetry={loadData} />}
      {loading && <LoadingState label="Loading your training workspace..." />}

      {!loading && tab === 'inbox' && (
        inbox.length === 0 ? (
          <EmptyState
            title="No simulations delivered yet"
            description="When your security team deploys a campaign targeting your department, simulated emails will appear here."
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/60 p-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Inbox ({inbox.length})</h3>
              {inbox.map((item) => (
                <button
                  key={item.simulation_id}
                  onClick={() => {
                    setSelected(item)
                    if (!item.actions.includes('opened')) {
                      recordAction(item, 'opened')
                    }
                  }}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selected?.simulation_id === item.simulation_id
                      ? 'border-indigo-500 bg-indigo-950/40'
                      : 'border-slate-800 bg-slate-900 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-slate-100">{item.email.sender_name}</span>
                    <SourceBadge source={item.source} />
                  </div>
                  <p className="mt-1 truncate text-xs text-slate-300">{item.email.subject}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {item.actions.map((a) => (
                      <span key={a} className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                        {a}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>

            <div className="space-y-4 lg:col-span-2">
              {selected && (
                <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 pb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-semibold text-slate-100">{selected.email.subject}</h2>
                        <SourceBadge source={selected.source} />
                      </div>
                      <p className="mt-1 text-xs text-slate-400">
                        From: <span className="text-slate-200">{selected.email.sender_name}</span> &lt;{selected.email.sender_email}&gt;
                      </p>
                    </div>
                    <button
                      onClick={() => recordAction(selected, 'reported')}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-emerald-500"
                    >
                      <Flag className="h-4 w-4" /> Report Phishing
                    </button>
                  </div>

                  <div className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                    {selected.email.body}
                  </div>

                  <div className="mt-5">
                    <button
                      onClick={() => recordAction(selected, 'clicked')}
                      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-500"
                      title={selected.email.link_url}
                    >
                      {selected.email.link_label}
                    </button>
                    <span className="ml-3 text-xs text-slate-500">Destination: {selected.email.link_url}</span>
                  </div>
                </div>
              )}

              {(coachingBusy || coachText) && (
                <div className="rounded-xl border border-indigo-500/30 bg-slate-900/90 p-5">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-indigo-300">Instant Coaching</h3>
                    <SourceBadge source={coachSource} />
                  </div>
                  {coachFlags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {coachFlags.map((f) => (
                        <span key={f} className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
                          {f}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                    {coachText || 'Generating coaching feedback...'}
                  </p>
                </div>
              )}
            </div>
          </div>
        )
      )}

      {!loading && tab === 'chat' && progress?.arm === 'treatment' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-slate-100">Attacker Persona Practice Chat</h3>
              <p className="text-xs text-slate-400">Spot the social-engineering tactics and call them out.</p>
            </div>
            <button
              onClick={startPracticeChat}
              disabled={chatBusy}
              className="rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-black hover:bg-indigo-500 disabled:opacity-50"
            >
              {chatSessionId ? 'New Scenario' : 'Start Practice Chat'}
            </button>
          </div>

          {chatMessages.length === 0 ? (
            <EmptyState
              title="Ready to practice"
              description="Click Start Practice Chat to interact with a sandboxed attacker persona tailored to your role."
            />
          ) : (
            <div className="space-y-3">
              <div className="max-h-80 space-y-2 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 p-3">
                {chatMessages.map((m, i) => (
                  <div
                    key={i}
                    className={`rounded-lg p-3 text-sm ${
                      m.role === 'user'
                        ? 'ml-8 bg-indigo-600/20 text-indigo-100'
                        : 'mr-8 bg-slate-800/80 text-slate-200'
                    }`}
                  >
                    <span className="mb-1 block text-[10px] font-semibold uppercase text-slate-400">{m.role}</span>
                    <span className="whitespace-pre-wrap">{m.content}</span>
                  </div>
                ))}
              </div>

              {chatDebrief && (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/30 p-3 text-sm text-emerald-200">
                  <strong>Debrief ({chatOutcome}):</strong> {chatDebrief}
                </div>
              )}

              {!chatOutcome && (
                <div className="flex gap-2">
                  <input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && sendChatMessage()}
                    placeholder="Reply or call out the phishing attempt..."
                    className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
                  />
                  <button
                    onClick={sendChatMessage}
                    disabled={chatBusy}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-500 disabled:opacity-50"
                  >
                    Send
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!loading && tab === 'progress' && progress && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <span className="text-xs text-slate-400">Personal Risk Band</span>
            <p className="mt-1 text-2xl font-bold text-slate-100">{progress.risk_band}</p>
            <span className="text-xs text-slate-400">Score: {progress.risk_score}</span>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <span className="text-xs text-slate-400">Simulations Received</span>
            <p className="mt-1 text-2xl font-bold text-slate-100">{progress.simulations_received}</p>
            <span className="text-xs text-slate-400">Next difficulty: Tier {progress.next_difficulty}</span>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <span className="text-xs text-slate-400">Phishing Reported</span>
            <p className="mt-1 text-2xl font-bold text-emerald-400">{progress.reported_count}</p>
            <span className="text-xs text-slate-400">Clicked: {progress.clicked_count}</span>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <span className="text-xs text-slate-400">Coaching Sessions</span>
            <p className="mt-1 text-2xl font-bold text-indigo-400">{progress.coaching_sessions_count}</p>
            <span className="text-xs text-slate-400">Submitted: {progress.submitted_count}</span>
          </div>
        </div>
      )}

      {landingSim && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-2xl border border-amber-500/40 bg-slate-900 p-6 shadow-xl">
            <div className="flex items-center gap-2 text-amber-300">
              <ShieldAlert className="h-5 w-5" />
              <h3 className="text-base font-semibold">Simulated Verification Page (Training Exercise)</h3>
            </div>
            <p className="mt-2 text-xs text-slate-300">
              This is a harmless training page. Do <strong>not</strong> enter real passwords. Nothing typed here is ever stored.
            </p>
            <div className="mt-4 space-y-3">
              <input
                type="text"
                placeholder="Simulated field (not stored)"
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setLandingSim(null)}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Close Safely
                </button>
                <button
                  onClick={async () => {
                    const target = landingSim
                    setLandingSim(null)
                    await recordAction(target, 'submitted')
                  }}
                  className="rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-amber-500"
                >
                  Simulate Submit
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
