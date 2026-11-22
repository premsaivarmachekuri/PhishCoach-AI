import { AlertCircle, Inbox, Loader2 } from 'lucide-react'

export function LoadingState({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-slate-400">
      <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-900/50 px-6 py-12 text-center">
      <Inbox className="mb-3 h-8 w-8 text-slate-500" />
      <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
      <p className="mt-1 max-w-md text-xs text-slate-400">{description}</p>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-rose-200">
      <div className="flex items-center gap-2 text-sm">
        <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg bg-rose-500/20 px-3 py-1 text-xs font-medium hover:bg-rose-500/30"
        >
          Retry
        </button>
      )}
    </div>
  )
}

export function SourceBadge({ source }: { source?: string }) {
  if (!source) return null
  if (source === 'static_control') {
    return (
      <span className="inline-flex items-center rounded-full bg-slate-700 px-2 py-0.5 text-[11px] font-medium text-slate-300">
        standard guidance
      </span>
    )
  }
  if (source === 'fallback') {
    return (
      <span className="inline-flex items-center rounded-full bg-amber-500/20 px-2 py-0.5 text-[11px] font-medium text-amber-300">
        rules coach (AI offline)
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full bg-indigo-500/20 px-2 py-0.5 text-[11px] font-medium text-indigo-300">
      {source}
    </span>
  )
}
