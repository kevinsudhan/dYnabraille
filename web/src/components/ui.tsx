import type { ReactNode } from 'react'

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

export function Card({
  title, icon, actions, children, className, bodyClassName,
}: {
  title: ReactNode
  icon?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={cx('card flex min-w-0 flex-col', className)}>
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <h2 className="card-title flex items-center gap-2">
          {icon && <span className="text-accent">{icon}</span>}
          {title}
        </h2>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </header>
      <div className={cx('flex-1 p-4 sm:p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

export type Tone = 'ok' | 'warn' | 'bad' | 'idle' | 'accent'

const toneDot: Record<Tone, string> = {
  ok: 'bg-ok shadow-[0_0_10px] shadow-ok/60',
  warn: 'bg-warn shadow-[0_0_10px] shadow-warn/50',
  bad: 'bg-bad shadow-[0_0_10px] shadow-bad/50',
  idle: 'bg-faint',
  accent: 'bg-accent shadow-[0_0_10px] shadow-accent/60',
}

export function Dot({ tone, pulse }: { tone: Tone; pulse?: boolean }) {
  return <span aria-hidden className={cx('inline-block size-2 shrink-0 rounded-full', toneDot[tone], pulse && 'animate-breathe')} />
}

export function StatusPill({ label, value, tone, pulse }: { label: string; value: string; tone: Tone; pulse?: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-surface/80 py-1.5 pl-2.5 pr-3 text-xs">
      <Dot tone={tone} pulse={pulse} />
      <span className="text-faint">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </div>
  )
}

export function Toggle({
  checked, onChange, label, hint, disabled,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  hint?: string
  disabled?: boolean
}) {
  return (
    <label className={cx('flex cursor-pointer items-start justify-between gap-4', disabled && 'cursor-not-allowed opacity-50')}>
      <span className="min-w-0">
        <span className="block text-sm text-ink">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
      </span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          type="checkbox" role="switch" className="peer sr-only" checked={checked} disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="h-6 w-11 rounded-full border border-line-strong bg-raised transition peer-checked:border-accent/60 peer-checked:bg-accent/25 peer-focus-visible:outline-2 peer-focus-visible:outline-accent" />
        <span className="absolute left-1 top-1 size-4 rounded-full bg-muted transition peer-checked:translate-x-5 peer-checked:bg-accent" />
      </span>
    </label>
  )
}

export function Slider({
  label, value, min, max, step = 1, format, onChange, onCommit,
}: {
  label: string
  value: number
  min: number
  max: number
  step?: number
  format: (v: number) => string
  onChange: (v: number) => void
  onCommit: (v: number) => void
}) {
  return (
    <label className="block">
      <span className="flex items-baseline justify-between text-sm">
        <span className="text-ink">{label}</span>
        <span className="font-display tabular-nums text-muted">{format(value)}</span>
      </span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        onKeyUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        className="mt-2 w-full accent-[var(--color-accent)]"
      />
    </label>
  )
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-8 text-center">
      <div className="mb-1 grid size-11 place-items-center rounded-2xl border border-line bg-raised text-muted">{icon}</div>
      <p className="font-display text-sm font-semibold text-ink">{title}</p>
      {children && <div className="max-w-sm text-sm text-muted">{children}</div>}
    </div>
  )
}

export function timeAgo(epochSeconds: number): string {
  const s = Math.max(0, Date.now() / 1000 - epochSeconds)
  if (s < 5) return 'just now'
  if (s < 60) return `${Math.floor(s)}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

export function duration(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}
