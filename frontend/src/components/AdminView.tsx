import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Activity, AlertTriangle, Check, Download, FlaskConical, Play, RefreshCw, Settings, X } from 'lucide-react'
import { apiFetch, authHeaders, getExportUrl, subscribeRealtime } from '../lib/api'
import { EmptyState, ErrorState, LoadingState, SourceBadge } from './States'

interface DashboardData {
  include_synthetic: boolean
  summary: {
    total_users: number
    delivered: number
    click_rate: number
    submit_rate: number
    report_rate: number
    median_time_to_report_min: number | null
    repeat_failure_rate: number
    coaching_views: number
    chat_sessions: number
    chat_completed: number
  }
  risk_bands: Record<string, number>
  recent_events?: { anon_id: string; department: string; type: string; ts: string }[]
  by_department: {
    department: string
    user_count: number
    delivered: number
    clicked: number
    submitted: number
    reported: number
    avg_risk_score: number
  }[]
  queries?: string[]
}

interface CampaignItem {
  id: string
  wave_no: number
  status: string
  brief_json: { theme: string; department: string; difficulty: number }
  templates: {
    id: string
    status: string
    source: string
    planted_flags: string[]
    email_json: { sender_name: string; sender_email: string; subject: string; body: string; link_label: string; link_url: string }
  }[]
}

interface RemediationItem {
  id: string
  anon_id: string
  department: string
  role_name: string
  reason: string
  status: string
}

interface PilotData {
  sample_size_users: number
  diff_in_diff_click_rate: number
  interpretation_note: string
  arms: Record<string, Record<string, { delivered: number; clicked: number; click_rate: number; click_ci_95: [number, number]; reported: number; report_rate: number; report_ci_95: [number, number] }>>
}

export function AdminView({ token }: { token: string }) {
  const [tab, setTab] = useState<'dashboard' | 'campaigns' | 'remediation' | 'pilot' | 'config'>(() => {
    const t = new URLSearchParams(window.location.search).get('tab')
    return t === 'dashboard' || t === 'campaigns' || t === 'remediation' || t === 'config' ? t : 'pilot'
  })
  const [includeSynthetic, setIncludeSynthetic] = useState(false)
  const [showQuery, setShowQuery] = useState(false)

  const [dash, setDash] = useState<DashboardData | null>(null)
  const [campaigns, setCampaigns] = useState<CampaignItem[]>([])
  const [remediation, setRemediation] = useState<RemediationItem[]>([])
  const [pilot, setPilot] = useState<PilotData | null>(null)
  const [configData, setConfigData] = useState<{ config: Record<string, unknown>; llm_budget: Record<string, unknown> } | null>(null)
  const [configEdits, setConfigEdits] = useState<Record<string, string>>({})
  const [depHealth, setDepHealth] = useState<{ name: string; ok: boolean; detail: string }[]>([])
  const [liveConnected, setLiveConnected] = useState(false)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyMsg, setBusyMsg] = useState<string | null>(null)

  // Brief form
  const [theme, setTheme] = useState('')
  const [department, setDepartment] = useState('all')
  const [difficulty, setDifficulty] = useState(1)
  const [waveNo, setWaveNo] = useState(1)

  const loadAll = useCallback(async () => {
    setError(null)
    try {
      const [d, c, r, p, cfg] = await Promise.all([
        apiFetch<DashboardData>(`/admin/dashboard?include_synthetic=${includeSynthetic}&show_query=${showQuery}`, token),
        apiFetch<CampaignItem[]>('/campaigns', token),
        apiFetch<RemediationItem[]>('/admin/remediation', token),
        apiFetch<PilotData>(`/admin/pilot?include_synthetic=${includeSynthetic}`, token),
        apiFetch<{ config: Record<string, unknown>; llm_budget: Record<string, unknown> }>('/admin/config', token),
      ])
      setDash(d)
      setCampaigns(c)
      setRemediation(r)
      setPilot(p)
      setConfigData(cfg)
      const edits: Record<string, string> = {}
      Object.entries(cfg.config).forEach(([k, v]) => {
        edits[k] = JSON.stringify(v, null, 2)
      })
      setConfigEdits(edits)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [token, includeSynthetic, showQuery])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  // Real-time SSE subscription replaces polling
  useEffect(() => {
    return subscribeRealtime(
      token,
      (topic) => {
        if (topic === 'metrics') {
          apiFetch<DashboardData>(`/admin/dashboard?include_synthetic=${includeSynthetic}&show_query=${showQuery}`, token)
            .then(setDash)
            .catch(() => {})
          apiFetch<PilotData>(`/admin/pilot?include_synthetic=${includeSynthetic}`, token)
            .then(setPilot)
            .catch(() => {})
        } else if (topic === 'campaigns') {
          apiFetch<CampaignItem[]>('/campaigns', token).then(setCampaigns).catch(() => {})
        } else if (topic === 'remediation') {
          apiFetch<RemediationItem[]>('/admin/remediation', token).then(setRemediation).catch(() => {})
        } else if (topic === 'config') {
          apiFetch<{ config: Record<string, unknown>; llm_budget: Record<string, unknown> }>('/admin/config', token)
            .then(setConfigData)
            .catch(() => {})
        }
      },
      setLiveConnected
    )
  }, [token, includeSynthetic, showQuery])

  useEffect(() => {
    if (tab === 'config') {
      apiFetch<{ checks: { name: string; ok: boolean; detail: string }[] }>('/health/deps', token)
        .then((r) => setDepHealth(r.checks || []))
        .catch(() => {})
    }
  }, [tab, token])

  const createCampaign = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!theme.trim()) return
    setBusyMsg('Generating role-aware simulation with guardrails...')
    setError(null)
    try {
      await apiFetch('/campaigns', token, {
        method: 'POST',
        body: JSON.stringify({ theme: theme.trim(), department, difficulty, wave_no: waveNo }),
      })
      setTheme('')
      await loadAll()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusyMsg(null)
    }
  }

  const handleTemplateAction = async (cid: string, tid: string, action: 'approve' | 'reject') => {
    try {
      await apiFetch(`/campaigns/${cid}/templates/${tid}/${action}`, token, { method: 'POST' })
      await loadAll()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDeploy = async (cid: string) => {
    setBusyMsg('Deploying campaign...')
    try {
      await apiFetch(`/campaigns/${cid}/deploy`, token, { method: 'POST' })
      await loadAll()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyMsg(null)
    }
  }

  const handleLaunchRemediation = async (id: string) => {
    try {
      await apiFetch(`/admin/remediation/${id}/launch`, token, { method: 'POST' })
      await loadAll()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleSaveConfig = async (key: string) => {
    try {
      const parsed = JSON.parse(configEdits[key])
      await apiFetch(`/admin/config/${key}`, token, {
        method: 'PUT',
        body: JSON.stringify({ value_json: parsed }),
      })
      await loadAll()
    } catch (e) {
      setError(`Invalid JSON or save failed for ${key}: ${(e as Error).message}`)
    }
  }

  const handleSyncHR = async () => {
    setBusyMsg('Syncing employees via HR adapter...')
    try {
      await apiFetch('/integrations/hr/sync', token, { method: 'POST' })
      await loadAll()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyMsg(null)
    }
  }

  const downloadExport = async (format: 'csv' | 'pdf') => {
    try {
      const res = await fetch(getExportUrl(format, includeSynthetic), {
        headers: authHeaders(token),
      })
      if (!res.ok) throw new Error(`Export failed (${res.status})`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `phishcoach_report.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex flex-wrap gap-2">
          {[
            { id: 'dashboard', label: 'Live Risk', icon: Activity },
            { id: 'campaigns', label: 'Campaigns', icon: Play },
            { id: 'remediation', label: `Remediation (${remediation.filter((r) => r.status === 'pending').length})`, icon: AlertTriangle },
            { id: 'pilot', label: 'Impact', icon: FlaskConical },
            { id: 'config', label: 'Settings', icon: Settings },
          ].map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                onClick={() => setTab(item.id as typeof tab)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium ${
                  tab === item.id ? 'bg-indigo-600 text-black' : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                <Icon className="h-4 w-4" /> {item.label}
              </button>
            )
          })}
        </div>

        <div className="flex items-center gap-3 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              liveConnected ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${liveConnected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
            {liveConnected ? 'Live' : 'Reconnecting'}
          </span>
          <label className="flex cursor-pointer items-center gap-1.5 text-slate-300">
            <input
              type="checkbox"
              checked={includeSynthetic}
              onChange={(e) => setIncludeSynthetic(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900"
            />
            Include synthetic
          </label>
          <label className="flex cursor-pointer items-center gap-1.5 text-slate-300">
            <input
              type="checkbox"
              checked={showQuery}
              onChange={(e) => setShowQuery(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900"
            />
            Show SQL
          </label>
          <button
            onClick={loadAll}
            className="flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1 text-slate-300 hover:bg-slate-800"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {busyMsg && <LoadingState label={busyMsg} />}
      {error && <ErrorState message={error} onRetry={loadAll} />}
      {loading && <LoadingState label="Loading security operations console..." />}

      {!loading && tab === 'dashboard' && dash && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <span className="text-xs text-slate-400">Delivered</span>
              <p className="mt-1 text-2xl font-bold text-slate-100">{dash.summary.delivered}</p>
              <span className="text-xs text-slate-400">{dash.summary.total_users} enrolled users</span>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <span className="text-xs text-slate-400">Click Rate</span>
              <p className="mt-1 text-2xl font-bold text-amber-300">{(dash.summary.click_rate * 100).toFixed(1)}%</p>
              <span className="text-xs text-slate-400">Submit: {(dash.summary.submit_rate * 100).toFixed(1)}%</span>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <span className="text-xs text-slate-400">Report Rate</span>
              <p className="mt-1 text-2xl font-bold text-emerald-400">{(dash.summary.report_rate * 100).toFixed(1)}%</p>
              <span className="text-xs text-slate-400">
                Median TTR: {dash.summary.median_time_to_report_min !== null ? `${dash.summary.median_time_to_report_min}m` : 'N/A'}
              </span>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <span className="text-xs text-slate-400">Repeat-Failure Rate</span>
              <p className="mt-1 text-2xl font-bold text-rose-400">{(dash.summary.repeat_failure_rate * 100).toFixed(1)}%</p>
              <span className="text-xs text-slate-400">High Risk: {dash.risk_bands.High || 0}</span>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <span className="text-xs text-slate-400">Coaching Engagement</span>
              <p className="mt-1 text-2xl font-bold text-indigo-400">{dash.summary.coaching_views}</p>
              <span className="text-xs text-slate-400">
                Chats: {dash.summary.chat_completed}/{dash.summary.chat_sessions}
              </span>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-5">
          {dash.by_department.length === 0 ? (
            <EmptyState
              title="No live metrics yet"
              description="Sync employees from HR and deploy an approved campaign to see live department metrics."
            />
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 lg:col-span-3">
              <h3 className="mb-3 text-sm font-semibold text-slate-200">Department Interaction Breakdown</h3>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dash.by_department}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                    <XAxis dataKey="department" stroke="#a3a3a3" fontSize={12} />
                    <YAxis stroke="#a3a3a3" fontSize={12} />
                    <Tooltip contentStyle={{ backgroundColor: "#111111", borderColor: "#404040", color: "#fafafa" }} />
                    <Legend formatter={(v) => <span style={{ color: '#e5e5e5', fontSize: 12 }}>{v}</span>} />
                    <Bar dataKey="delivered" fill="#525252" name="Delivered" />
                    <Bar dataKey="clicked" fill="#fafafa" name="Clicked" />
                    <Bar dataKey="reported" fill="#22c55e" name="Reported" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {dash.recent_events && dash.recent_events.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 lg:col-span-2">
              <h3 className="mb-2 text-sm font-semibold text-slate-200">Live Activity Feed</h3>
              <div className="max-h-64 space-y-1.5 overflow-y-auto text-xs">
                {dash.recent_events.slice(0, 12).map((ev, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg bg-slate-950/70 px-3 py-1.5">
                    <span className="text-slate-300">
                      <span className="font-mono text-indigo-300">{ev.anon_id}</span> ({ev.department}) —{' '}
                      <strong className="text-slate-100">{ev.type}</strong>
                    </span>
                    <span className="text-[11px] text-slate-500">{new Date(ev.ts).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          </div>

          {showQuery && dash.queries && (
            <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-400">
              <p className="mb-1 font-sans font-semibold text-slate-300">Underlying SQL Trace:</p>
              {dash.queries.map((q, i) => (
                <div key={i}>{q}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {!loading && tab === 'campaigns' && (
        <div className="space-y-6">
          <form onSubmit={createCampaign} className="grid gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4 sm:grid-cols-5">
            <input
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              placeholder="Campaign brief (e.g. Q4 Payroll Update)"
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 sm:col-span-2"
              required
            />
            <input
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              placeholder="Department (or all)"
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            />
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(Number(e.target.value))}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              <option value={1}>Difficulty 1 (Basic)</option>
              <option value={2}>Difficulty 2 (Moderate)</option>
              <option value={3}>Difficulty 3 (Subtle)</option>
            </select>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={20}
                value={waveNo}
                onChange={(e) => setWaveNo(Number(e.target.value))}
                className="w-20 rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100"
                title="Wave number"
              />
              <button
                type="submit"
                className="flex-1 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-black hover:bg-indigo-500"
              >
                Generate Draft
              </button>
            </div>
          </form>

          {campaigns.length === 0 ? (
            <EmptyState
              title="No campaigns created"
              description="Enter a brief above to generate a guarded phishing simulation draft."
            />
          ) : (
            <div className="space-y-4">
              {campaigns.map((c) => (
                <div key={c.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                    <div>
                      <h4 className="text-sm font-semibold text-slate-100">
                        {c.brief_json.theme} <span className="text-xs text-slate-400">(Wave {c.wave_no}, Dept: {c.brief_json.department})</span>
                      </h4>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">{c.status}</span>
                      <button
                        onClick={() => handleDeploy(c.id)}
                        className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500"
                      >
                        Deploy
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 space-y-3">
                    {c.templates.map((t) => (
                      <div key={t.id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-200">{t.email_json.subject}</span>
                            <SourceBadge source={t.source} />
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">{t.status}</span>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleTemplateAction(c.id, t.id, 'approve')}
                              className="flex items-center gap-1 rounded bg-emerald-600/20 px-2 py-1 text-emerald-300 hover:bg-emerald-600/30"
                            >
                              <Check className="h-3.5 w-3.5" /> Approve
                            </button>
                            <button
                              onClick={() => handleTemplateAction(c.id, t.id, 'reject')}
                              className="flex items-center gap-1 rounded bg-rose-600/20 px-2 py-1 text-rose-300 hover:bg-rose-600/30"
                            >
                              <X className="h-3.5 w-3.5" /> Reject
                            </button>
                          </div>
                        </div>
                        <p className="mt-1 text-slate-400">
                          From: {t.email_json.sender_name} &lt;{t.email_json.sender_email}&gt; | Flags: {t.planted_flags.join(', ')}
                        </p>
                        <p className="mt-2 whitespace-pre-wrap text-slate-300">{t.email_json.body}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!loading && tab === 'remediation' && (
        remediation.length === 0 ? (
          <EmptyState
            title="Remediation queue is clear"
            description="Users who enter the High risk band or fail in consecutive waves will appear here for targeted follow-up."
          />
        ) : (
          <div className="space-y-2">
            {remediation.map((item) => (
              <div key={item.id} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div>
                  <p className="text-sm font-semibold text-slate-100">
                    {item.anon_id} <span className="text-xs text-slate-400">({item.department} — {item.role_name})</span>
                  </p>
                  <p className="text-xs text-slate-400">Reason: {item.reason} | Status: {item.status}</p>
                </div>
                {item.status === 'pending' && (
                  <button
                    onClick={() => handleLaunchRemediation(item.id)}
                    className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500"
                  >
                    Approve & Launch Follow-up
                  </button>
                )}
              </div>
            ))}
          </div>
        )
      )}

      {!loading && tab === 'pilot' && pilot && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              { label: 'Control click rate (latest wave)', value: `${((pilot.arms.control?.wave_2?.click_rate ?? 0) * 100).toFixed(1)}%` },
              { label: 'Treatment click rate (latest wave)', value: `${((pilot.arms.treatment?.wave_2?.click_rate ?? 0) * 100).toFixed(1)}%` },
              { label: 'Difference-in-differences', value: `${(pilot.diff_in_diff_click_rate * 100).toFixed(1)} pp` },
            ].map((k) => (
              <div key={k.label} className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <div className="text-xs text-slate-400">{k.label}</div>
                <div className="mt-1 text-3xl font-bold tracking-tight text-slate-100">{k.value}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-500">
            N={pilot.sample_size_users} users. {pilot.interpretation_note}
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {(['control', 'treatment'] as const).map((arm) => (
              <div key={arm} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <h4 className="text-sm font-semibold uppercase text-slate-200">{arm} Arm</h4>
                <div className="mt-3 space-y-2 text-xs">
                  {(['wave_1', 'wave_2'] as const).map((w) => {
                    const stats = pilot.arms[arm][w]
                    return (
                      <div key={w} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                        <div className="font-medium text-slate-300">{w.replace('_', ' ').toUpperCase()} (n={stats.delivered})</div>
                        <div className="mt-1 text-slate-400">
                          Click Rate: {(stats.click_rate * 100).toFixed(1)}% [95% CI: {(stats.click_ci_95[0] * 100).toFixed(1)}%–{(stats.click_ci_95[1] * 100).toFixed(1)}%]
                        </div>
                        <div className="text-slate-400">
                          Report Rate: {(stats.report_rate * 100).toFixed(1)}% [95% CI: {(stats.report_ci_95[0] * 100).toFixed(1)}%–{(stats.report_ci_95[1] * 100).toFixed(1)}%]
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && tab === 'config' && configData && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="text-xs text-slate-300">
              <strong>LLM Budget Telemetry:</strong>{' '}
              {JSON.stringify(configData.llm_budget)}
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSyncHR}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-black hover:bg-indigo-500"
              >
                Sync HR Employees
              </button>
              <button
                onClick={() => downloadExport('csv')}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
              >
                <Download className="h-3.5 w-3.5" /> CSV
              </button>
              <button
                onClick={() => downloadExport('pdf')}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
              >
                <Download className="h-3.5 w-3.5" /> PDF
              </button>
            </div>
          </div>

          {depHealth.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-4">
              {depHealth.map((c) => (
                <div key={c.name} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs">
                  <span className="font-medium capitalize text-slate-200">{c.name}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${c.ok ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
                    {c.ok ? 'OK' : c.detail}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            {Object.keys(configEdits).map((key) => (
              <div key={key} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-xs font-semibold text-indigo-300">{key}</span>
                  <button
                    onClick={() => handleSaveConfig(key)}
                    className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-black hover:bg-indigo-500"
                  >
                    Save
                  </button>
                </div>
                <textarea
                  value={configEdits[key]}
                  onChange={(e) => setConfigEdits((prev) => ({ ...prev, [key]: e.target.value }))}
                  rows={4}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950 p-2 font-mono text-xs text-slate-200"
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
