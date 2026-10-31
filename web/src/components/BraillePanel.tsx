import { Grid2x2, RotateCcw, Send, Square, Type } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { usePinLabels, useServer } from '../lib/server'
import type { Cell } from '../lib/types'
import { BrailleCell } from './BrailleCell'
import { Card, Slider, cx } from './ui'

const SOURCE_LABEL: Record<string, string> = {
  camera: 'Camera', capture: 'Capture button', assistant: 'Assistant', manual: 'Typed', replay: 'Replay',
}

export function cellName(cell: Cell): string {
  if (cell.kind === 'space') return 'space'
  if (cell.kind === 'indicator') {
    return cell.char === '#' ? 'number sign' : cell.char === ';' ? 'letter sign' : 'capital sign'
  }
  return cell.char
}

export function BraillePanel() {
  const { state } = useServer()
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<Cell[]>([])
  const [error, setError] = useState<string | null>(null)
  const [charMs, setCharMs] = useState(900)
  const [gapMs, setGapMs] = useState(250)
  const [composer, setComposer] = useState<number[]>([])

  const job = state?.job
  const device = state?.devices[0]
  const rest = state?.rest ?? true
  const pinLabels = usePinLabels()
  const mask = state?.mask ?? 0
  const pinsUp = [1, 2, 3, 4, 5, 6].filter((d) => mask & (1 << (d - 1))).map((d) => pinLabels[d - 1]).sort((a, b) => a - b)
  const current = job?.active && job.index >= 0 ? job.cells[job.index] : null

  const prefsChar = state?.prefs.char_ms
  const prefsGap = state?.prefs.gap_ms
  useEffect(() => {
    if (prefsChar) setCharMs(prefsChar)
    if (prefsGap) setGapMs(prefsGap)
  }, [prefsChar, prefsGap])

  useEffect(() => {
    if (!text.trim()) {
      setPreview([])
      return
    }
    const timer = setTimeout(() => {
      api.preview(text).then((r) => setPreview(r.cells)).catch(() => setPreview([]))
    }, 200)
    return () => clearTimeout(timer)
  }, [text])

  const run = (action: Promise<unknown>) => {
    setError(null)
    action.catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }

  const caption = current
    ? `${cellName(current)} · ${job!.index + 1} of ${job!.cells.length}`
    : rest
      ? device ? (device.rest_mask === 63 ? 'Resting: solenoids off, all pins up' : 'Resting: solenoids off') : 'Idle'
      : 'Holding'

  return (
    <Card title="Braille cell" icon={<Grid2x2 className="size-4" />}
      actions={<span className="text-xs text-muted">{device ? device.name : 'Simulated on screen'}</span>}>
      <div className="space-y-5">
        <div className="flex flex-col items-center gap-3">
          <BrailleCell mask={mask} rest={rest} size="xl" numbers pinLabels={pinLabels} active={Boolean(current)} />
          <div className="text-center">
            <p className="font-display text-lg font-semibold" aria-live="polite">{caption}</p>
            {!rest && <p className="text-sm text-muted">Pins up: {pinsUp.length ? pinsUp.join(' · ') : 'none'}</p>}
          </div>
        </div>

        {job && (
          <div className="space-y-2 rounded-xl border border-line bg-bg/40 p-3">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate text-muted">
                <span className="chip mr-2 py-0.5">{SOURCE_LABEL[job.source] ?? job.source}</span>
                <span className="text-ink">{job.text}</span>
              </span>
              <span className="shrink-0 text-faint">{job.active ? 'playing' : 'done'}</span>
            </div>
            <div className="scrollbar-thin flex gap-1.5 overflow-x-auto pb-1">
              {job.cells.map((cell, i) => (
                <div key={i} className="flex shrink-0 flex-col items-center gap-1">
                  <BrailleCell mask={cell.mask} size="sm" active={job.active && i === job.index} label={cellName(cell)} />
                  <span className={cx('text-[10px]', job.active && i === job.index ? 'text-accent' : 'text-faint')}>
                    {cell.kind === 'letter' || cell.kind === 'digit' || cell.kind === 'punct' ? cell.char : cell.kind === 'space' ? '␣' : '·'}
                  </span>
                </div>
              ))}
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-accent transition-all duration-300"
                style={{ width: `${job.active ? ((job.index + 1) / job.cells.length) * 100 : 100}%` }}
              />
            </div>
          </div>
        )}

        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (text.trim()) run(api.showText(text).then(() => setText('')))
          }}
        >
          <label htmlFor="braille-input" className="eyebrow flex items-center gap-1.5"><Type className="size-3" />Send text</label>
          <div className="flex gap-2">
            <input id="braille-input" className="field" value={text} onChange={(e) => setText(e.target.value)}
              placeholder="e.g. exit" maxLength={200} autoComplete="off" />
            <button type="submit" className="btn btn-primary" disabled={!text.trim()} aria-label="Send to braille cell"><Send className="size-4" /></button>
          </div>
          {preview.length > 0 && (
            <p className="truncate font-mono text-xl tracking-[0.2em] text-accent" aria-label="Braille preview">
              {preview.map((c) => c.unicode).join('')}
            </p>
          )}
        </form>

        <div className="flex gap-2">
          <button type="button" className="btn flex-1" onClick={() => run(api.replay())} disabled={!job}>
            <RotateCcw className="size-4" />Repeat
          </button>
          <button type="button" className="btn flex-1" onClick={() => run(api.stop())}>
            <Square className="size-4" />Stop
          </button>
        </div>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}

        <div className="space-y-4 border-t border-line pt-4">
          <Slider label="Time per letter" min={300} max={2500} step={50} value={charMs}
            format={(v) => `${(v / 1000).toFixed(2)} s`} onChange={setCharMs}
            onCommit={(v) => run(api.setPrefs({ char_ms: v }))} />
          <Slider label="Gap between letters" min={60} max={1000} step={10} value={gapMs}
            format={(v) => `${v} ms`} onChange={setGapMs}
            onCommit={(v) => run(api.setPrefs({ gap_ms: v }))} />
        </div>

        <div className="flex items-center gap-4 border-t border-line pt-4">
          <div className="grid grid-cols-2 gap-1.5" role="group" aria-label="Compose a cell">
            {[1, 4, 2, 5, 3, 6].map((dot) => {
              const on = composer.includes(dot)
              return (
                <button
                  key={dot} type="button" aria-pressed={on} aria-label={`Pin ${pinLabels[dot - 1]}`}
                  onClick={() => setComposer((c) => (on ? c.filter((d) => d !== dot) : [...c, dot]))}
                  className={cx('grid size-8 place-items-center rounded-full border text-xs font-semibold transition',
                    on ? 'border-accent bg-accent text-accent-ink' : 'border-line-strong bg-raised text-muted hover:border-accent/50')}
                >
                  {pinLabels[dot - 1]}
                </button>
              )
            })}
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-sm text-muted">Pick pins and hold them up on the cell (up to 8 s).</p>
            <div className="flex gap-2">
              <button type="button" className="btn" onClick={() => run(api.showCell(composer))}>Show on cell</button>
              <button type="button" className="btn btn-ghost" onClick={() => setComposer([])} disabled={!composer.length}>Clear</button>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}
