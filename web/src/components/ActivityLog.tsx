import { Activity, AlertTriangle, Camera, Cpu, Grid2x2, Hand, ScanEye, Server } from 'lucide-react'
import type { ReactNode } from 'react'
import { useServer } from '../lib/server'
import { Card, Empty, cx } from './ui'

const ICONS: Record<string, ReactNode> = {
  device: <Cpu className="size-3.5" />,
  camera: <Camera className="size-3.5" />,
  vision: <ScanEye className="size-3.5" />,
  capture: <Camera className="size-3.5" />,
  braille: <Grid2x2 className="size-3.5" />,
  button: <Hand className="size-3.5" />,
  server: <Server className="size-3.5" />,
}

export function ActivityLog() {
  const { state } = useServer()
  const events = [...(state?.events ?? [])].reverse()
  return (
    <Card title="Activity" icon={<Activity className="size-4" />} bodyClassName="p-0">
      {events.length === 0 ? (
        <Empty icon={<Activity className="size-5" />} title="Nothing yet" />
      ) : (
        <ol className="scrollbar-thin max-h-[420px] divide-y divide-line overflow-y-auto">
          {events.map((e, i) => (
            <li key={`${e.t}-${i}`} className="flex items-start gap-3 px-4 py-2.5 sm:px-5">
              <span className={cx('mt-0.5 grid size-6 shrink-0 place-items-center rounded-lg',
                e.level === 'warn' ? 'bg-warn/10 text-warn' : 'bg-raised text-muted')}>
                {e.level === 'warn' ? <AlertTriangle className="size-3.5" /> : ICONS[e.kind] ?? <Activity className="size-3.5" />}
              </span>
              <p className="min-w-0 flex-1 text-sm text-ink">{e.text}</p>
              <time className="shrink-0 pt-0.5 text-[11px] tabular-nums text-faint">
                {new Date(e.t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </time>
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
