import { useCallback, useEffect, useState } from 'react'
import { Shield } from 'lucide-react'
import { apiFetch, subscribeRealtime } from '../lib/api'
import { EmptyState, ErrorState, LoadingState } from './States'

interface HRCohort {
  department: string
  user_count: number
  delivered: number
  click_rate: number
  submit_rate: number
  report_rate: number
  avg_risk_score: number
}

interface HRResponse {
  min_cohort_size: number
  suppressed_departments: number
  cohorts: HRCohort[]
}

export function HRView({ token }: { token: string }) {
  const [data, setData] = useState<HRResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch<HRResponse>('/hr/aggregates', token)
      setData(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    return subscribeRealtime(token, (topic) => {
      if (topic === 'metrics') {
        apiFetch<HRResponse>('/hr/aggregates', token).then(setData).catch(() => {})
      }
    })
  }, [token])

  if (loading) return <LoadingState label="Loading HR aggregate readiness..." />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-xs text-slate-300">
        <Shield className="h-4 w-4 text-indigo-400" />
        <span>
          Privacy protection active: Individual employees are never shown. Cohorts smaller than{' '}
          <strong>{data.min_cohort_size}</strong> users are suppressed ({data.suppressed_departments} suppressed).
        </span>
      </div>

      {data.cohorts.length === 0 ? (
        <EmptyState
          title="No cohorts meet the minimum size"
          description={`Departments need at least ${data.min_cohort_size} enrolled employees before aggregate readiness metrics appear.`}
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/70">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-800 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Department</th>
                <th className="px-4 py-3">Users</th>
                <th className="px-4 py-3">Delivered</th>
                <th className="px-4 py-3">Click Rate</th>
                <th className="px-4 py-3">Submit Rate</th>
                <th className="px-4 py-3">Report Rate</th>
                <th className="px-4 py-3">Avg Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {data.cohorts.map((c) => (
                <tr key={c.department} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium text-slate-100">{c.department}</td>
                  <td className="px-4 py-3 text-slate-300">{c.user_count}</td>
                  <td className="px-4 py-3 text-slate-300">{c.delivered}</td>
                  <td className="px-4 py-3 text-amber-300">{(c.click_rate * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-rose-300">{(c.submit_rate * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-emerald-300">{(c.report_rate * 100).toFixed(1)}%</td>
                  <td className="px-4 py-3 text-slate-200">{c.avg_risk_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
