import { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { AdminView } from './components/AdminView'
import { EmployeeView } from './components/EmployeeView'
import { HRView } from './components/HRView'
import { ErrorState, LoadingState } from './components/States'
import { apiFetch, subscribeRealtime } from './lib/api'

type AppRole = 'employee' | 'security_admin' | 'hr_viewer'

interface Persona {
  id: string
  anon_id: string
  app_role: AppRole
  arm: string
  department: string
  role_name: string
}

interface LlmStatus {
  primary: string
  last_used: string | null
  fallback_active: boolean
}

/** One plain sentence per role + the 3 steps of their journey. Shown on every screen. */
const ROLES: { role: AppRole; label: string; goal: string; steps: string[] }[] = [
  {
    role: 'security_admin',
    label: 'Security Admin',
    goal: 'Prove training reduces risk, then launch the next campaign.',
    steps: ['Impact: treatment vs control', 'Campaigns: AI-generate, approve, deploy', 'Remediation: help high-risk users'],
  },
  {
    role: 'hr_viewer',
    label: 'HR Viewer',
    goal: 'See readiness by department. Individuals are never shown.',
    steps: ['Scan department risk', 'Spot weak cohorts', 'Plan training with Security'],
  },
  {
    role: 'employee',
    label: 'Employee',
    goal: 'Practise spotting phishing and get coached the moment you slip.',
    steps: ['Open an email in your inbox', 'Report it or click it', 'Read your instant coaching'],
  },
]

export default function App() {
  const [personas, setPersonas] = useState<Persona[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [role, setRole] = useState<AppRole>(() => {
    const r = new URLSearchParams(window.location.search).get('role')
    return r === 'employee' || r === 'hr_viewer' || r === 'security_admin' ? r : 'security_admin'
  })
  const [employeeId, setEmployeeId] = useState<string>('')
  const [llm, setLlm] = useState<LlmStatus | null>(null)
  const [live, setLive] = useState(false)

  const loadPersonas = () => {
    setError(null)
    apiFetch<Persona[]>('/demo/personas', '')
      .then((p) => {
        setPersonas(p)
        setEmployeeId((cur) => cur || p.find((x) => x.app_role === 'employee')?.id || '')
      })
      .catch((e: Error) => setError(e.message))
  }

  // Real-time: personas + model status refresh on a timer; data views refresh over SSE.
  useEffect(() => {
    loadPersonas()
    const t = setInterval(() => {
      apiFetch<Persona[]>('/demo/personas', '').then(setPersonas).catch(() => {})
    }, 15000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const load = () => apiFetch<LlmStatus>('/demo/llm', '').then(setLlm).catch(() => {})
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [])

  const token = role === 'employee' ? `employee|${employeeId}` : role

  useEffect(() => {
    if (role === 'employee' && !employeeId) return
    return subscribeRealtime(token, () => {}, setLive)
  }, [token, role, employeeId])

  if (error) return <ErrorState message={error} onRetry={loadPersonas} />
  if (!personas) return <LoadingState label="Connecting to live backend..." />

  const employees = personas.filter((p) => p.app_role === 'employee')
  const active = ROLES.find((r) => r.role === role)!

  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-100 antialiased">
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
              <ShieldCheck className="h-4 w-4 text-black" />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-bold tracking-tight">PhishCoach AI</div>
              <div className="text-[11px] text-slate-500">Human-risk training platform</div>
            </div>
          </div>

          <nav className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900 p-1" role="tablist" aria-label="Switch role">
            {ROLES.map((r) => (
              <button
                key={r.role}
                role="tab"
                aria-selected={role === r.role}
                onClick={() => {
                  setRole(r.role)
                  window.history.replaceState(null, '', `?role=${r.role}`)
                }}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                  role === r.role ? 'bg-indigo-600 text-black shadow-sm' : 'text-slate-400 hover:text-slate-100'
                }`}
              >
                {r.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2 text-[11px]">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-800 px-2.5 py-1 text-slate-300">
              <span className={`h-1.5 w-1.5 rounded-full ${live ? 'animate-pulse bg-emerald-500' : 'bg-slate-600'}`} />
              {live ? 'Live' : 'Reconnecting'}
            </span>
            {llm && (
              <span
                className={`rounded-full border px-2.5 py-1 ${
                  llm.fallback_active ? 'border-amber-500/40 bg-amber-900 text-amber-200' : 'border-slate-800 text-slate-300'
                }`}
                title="Active AI model"
              >
                {llm.last_used ?? llm.primary} · {llm.fallback_active ? 'fallback' : 'primary'}
              </span>
            )}
          </div>
        </div>
      </header>

      <section className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">{active.label}</h1>
            <p className="text-sm text-slate-400">{active.goal}</p>
          </div>
          <ol className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
            {active.steps.map((s, i) => (
              <li key={s} className="flex items-center gap-2 rounded-full border border-slate-700 bg-slate-950 px-3 py-1">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-indigo-600 text-[10px] font-bold text-black">{i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          {role === 'employee' && employees.length > 0 && (
            <label className="flex items-center gap-2 text-xs text-slate-400">
              Viewing as
              <select
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
              >
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.anon_id} · {e.department} · {e.arm}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </section>

      <main className="mx-auto max-w-7xl p-6">
        {role === 'security_admin' && <AdminView key={token} token={token} />}
        {role === 'hr_viewer' && <HRView key={token} token={token} />}
        {role === 'employee' && employeeId && <EmployeeView key={token} token={token} />}
        {role === 'employee' && !employeeId && <ErrorState message="No employees enrolled yet. Sync from the HR system." />}
      </main>
    </div>
  )
}
