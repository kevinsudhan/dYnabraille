import { ArrowLeft, ArrowRight, ArrowUp, Crosshair } from 'lucide-react'
import type { Detection } from '../lib/types'
import { cx } from './ui'

// Readable on dark video, distinct from each other, and none of them the accent
// green, which is reserved for the object in focus.
const PALETTE = ['#5cc8ff', '#ffb547', '#ff6b8b', '#b18cff', '#9be36d', '#ff8f5a', '#f5e663', '#6ee7f2', '#f08cd8', '#c9d1e0']
const FOCUS = '#2ee6c5'

/** The same object type always gets the same colour, in the boxes and in the list. */
export function colorFor(label: string): string {
  let h = 0
  for (const c of label) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

export function isFocus(d: Detection, focus?: Detection | null): boolean {
  return Boolean(focus && focus.label === d.label &&
    Math.abs(focus.box[0] - d.box[0]) < 0.02 && Math.abs(focus.box[1] - d.box[1]) < 0.02)
}

/** Bounding boxes over an image. Coordinates are normalised (0..1), so it scales with the image. */
export function DetectionOverlay({ detections, focus }: { detections: Detection[]; focus?: Detection | null }) {
  return (
    <svg className="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      {detections.map((d, i) => {
        const [x1, y1, x2, y2] = d.box
        const focused = isFocus(d, focus)
        const color = focused ? FOCUS : colorFor(d.label)
        return (
          <g key={i}>
            {/* dark halo first so the box stays visible on bright backgrounds */}
            <rect
              x={x1 * 100} y={y1 * 100} width={(x2 - x1) * 100} height={(y2 - y1) * 100}
              fill="none" stroke="rgb(0 0 0 / 0.55)" strokeWidth={focused ? 6 : 4.5} vectorEffect="non-scaling-stroke" rx={0.8}
            />
            <rect
              x={x1 * 100} y={y1 * 100} width={(x2 - x1) * 100} height={(y2 - y1) * 100}
              fill={color} fillOpacity={focused ? 0.14 : 0.06} stroke={color}
              strokeWidth={focused ? 3.5 : 2.5} vectorEffect="non-scaling-stroke" rx={0.8}
            />
          </g>
        )
      })}
    </svg>
  )
}

const ARROW = { left: '←', ahead: '↑', right: '→' } as const

/** Labels positioned over the boxes (HTML, so text isn't stretched like SVG would be). */
export function DetectionLabels({ detections, focus, detail = true }: {
  detections: Detection[]; focus?: Detection | null; detail?: boolean
}) {
  const placed: { x: number; y: number }[] = []
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {detections.slice(0, 12).map((d, i) => {
        const [x1, y1, x2] = d.box
        const focused = isFocus(d, focus)
        const color = focused ? FOCUS : colorFor(d.label)
        const inside = y1 < 0.09 // no room above the box: put the tag inside its top edge
        const alignRight = x1 > 0.6
        // Boxes that start in nearly the same spot would stack their tags on top of each
        // other; shift each later tag one row (down inside the box, up above it).
        const anchor = { x: alignRight ? x2 : x1, y: y1 }
        const row = placed.filter((p) => Math.abs(p.x - anchor.x) < 0.2 && Math.abs(p.y - anchor.y) < 0.06).length
        placed.push(anchor)
        return (
          <span
            key={i}
            className={cx(
              'absolute flex max-w-[60%] items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-semibold text-black shadow-md',
              !inside && '-translate-y-full',
            )}
            style={{
              background: color,
              top: `${y1 * 100}%`,
              marginTop: `${(inside ? row : -row) * 24}px`,
              ...(alignRight ? { right: `${(1 - x2) * 100}%` } : { left: `${x1 * 100}%` }),
            }}
          >
            {focused && <Crosshair className="size-3 shrink-0" />}
            <span className="truncate">{d.label}</span>
            <span className="font-medium opacity-70">{Math.round(d.confidence * 100)}%</span>
            {detail && <span className="font-medium opacity-70">· {ARROW[d.position]} {d.distance}</span>}
          </span>
        )
      })}
    </div>
  )
}

const POSITION = {
  left: { icon: ArrowLeft, text: 'Left' },
  ahead: { icon: ArrowUp, text: 'Ahead' },
  right: { icon: ArrowRight, text: 'Right' },
} as const

/** Plain-language tally, e.g. "2 people, 1 chair". */
export function tally(detections: Detection[]): string {
  const counts = new Map<string, number>()
  for (const d of detections) counts.set(d.label, (counts.get(d.label) ?? 0) + 1)
  return [...counts].sort((a, b) => b[1] - a[1])
    .map(([label, n]) => `${n} ${n > 1 && label === 'person' ? 'people' : n > 1 ? `${label}s` : label}`)
    .join(', ')
}

/** What the camera is detecting right now, as a table that matches the box colours. */
export function DetectionList({ detections, focus }: { detections: Detection[]; focus?: Detection | null }) {
  const rows = [...detections].sort((a, b) => Number(isFocus(b, focus)) - Number(isFocus(a, focus)) || b.confidence - a.confidence)
  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <div className="flex items-center justify-between border-b border-line bg-raised/60 px-3 py-2">
        <p className="eyebrow">Detecting now</p>
        <p className="truncate pl-3 text-xs text-muted">{tally(detections)}</p>
      </div>
      <ul className="divide-y divide-line">
        {rows.slice(0, 8).map((d, i) => {
          const focused = isFocus(d, focus)
          const color = focused ? FOCUS : colorFor(d.label)
          const { icon: Arrow, text } = POSITION[d.position]
          return (
            <li key={i} className={cx('grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 px-3 py-2 text-sm', focused && 'bg-accent/5')}>
              <span className="size-3 rounded-sm ring-2 ring-black/30" style={{ background: color }} aria-hidden />
              <span className="min-w-0 truncate font-medium text-ink">
                {d.label}
                {focused && <span className="ml-2 rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-semibold text-accent">in focus</span>}
              </span>
              <span className="flex items-center gap-1 text-muted"><Arrow className="size-3.5" />{text} · {d.distance}</span>
              <span className="flex w-20 items-center gap-1.5" title={`${Math.round(d.confidence * 100)}% confident`}>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
                  <span className="block h-full rounded-full" style={{ width: `${d.confidence * 100}%`, background: color }} />
                </span>
                <span className="w-8 text-right text-xs tabular-nums text-muted">{Math.round(d.confidence * 100)}%</span>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function describe(d: Detection): string {
  const where = d.position === 'ahead' ? 'ahead' : `on the ${d.position}`
  return `${d.label} · ${where} · ${d.distance}`
}
