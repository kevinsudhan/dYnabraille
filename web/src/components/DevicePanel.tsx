import {
  BatteryMedium, Cpu, Hand, Lightbulb, MousePointerClick, Power, RadioTower, Sun, Timer, Usb, Wifi, Zap,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import { useServer, useServerEvent } from '../lib/server'
import type { Device } from '../lib/types'
import { Card, Empty, Slider, cx, duration, timeAgo } from './ui'

function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-bg/40 px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-[11px] text-faint">{icon}{label}</p>
      <p className="mt-0.5 truncate font-display text-sm font-semibold text-ink">{value}</p>
    </div>
  )
}

function signal(rssi: number | null): string {
  if (rssi == null) return '—'
  const quality = rssi > -55 ? 'excellent' : rssi > -67 ? 'good' : rssi > -75 ? 'fair' : 'weak'
  return `${rssi} dBm · ${quality}`
}

/** Solenoids in their physical spots. Each spot shows your S-number and its braille dot. */
function SolenoidTest({ device }: { device: Device }) {
  const [busy, setBusy] = useState<number | null>(null)
  const test = (dot: number) => {
    setBusy(dot)
    void api.testDot(dot).finally(() => setTimeout(() => setBusy(null), 600))
  }
  const rows = [[1, 4], [2, 5], [3, 6]] // braille dot at each position
  return (
    <div className="flex flex-wrap items-center gap-5">
      <div className="grid shrink-0 grid-cols-2 gap-2 rounded-2xl border border-line bg-bg/50 p-3">
        {rows.flat().map((dot) => {
          const solenoid = device.dot_to_solenoid[dot - 1] ?? dot
          return (
            <button
              key={dot} type="button" onClick={() => test(dot)}
              aria-label={`Switch on solenoid S${solenoid} (braille dot ${dot})`}
              className={cx(
                'flex size-14 flex-col items-center justify-center rounded-xl border text-ink transition',
                busy === dot ? 'border-accent bg-accent/20' : 'border-line-strong bg-raised hover:border-accent/60',
              )}
            >
              <span className="font-display text-base font-semibold">S{solenoid}</span>
              <span className="text-[10px] text-faint">dot {dot}</span>
            </button>
          )
        })}
      </div>
      <div className="min-w-0 space-y-2 text-sm text-muted">
        <p>Tap a spot to power that one solenoid for 0.6 s.{' '}
          {device.solenoid_on_raises ? 'Its pin should rise.' : 'Its pin should drop. Unpowered pins stay up.'}</p>
        <p className="text-xs">If a different pin moves, fix <code className="kbd">SOLENOID_PINS</code> in config.h. The pin finder in{' '}
          <code className="kbd">firmware/tools</code> works this out for you.</p>
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="button" className="btn" onClick={() => void api.selfTest()}><Zap className="size-4" />Power-on test</button>
          <button type="button" className="btn" onClick={() => void api.stop()}><Power className="size-4" />All off</button>
        </div>
      </div>
    </div>
  )
}

const HOLD_OPTIONS = [2000, 4000, 8000]

/** Power any combination of solenoids at once, e.g. to find how many the supply can hold. */
function SolenoidControl({ device }: { device: Device }) {
  const { state } = useServer()
  const [hold, setHold] = useState(4000)
  const [error, setError] = useState<string | null>(null)

  // What the cell itself reports as powered right now (not just what was clicked).
  const mask = state?.mask ?? 0
  const powered = state?.rest
    ? []
    : device.dot_to_solenoid
      .filter((_, i) => Boolean(mask & (1 << i)) === device.solenoid_on_raises)
      .sort((a, b) => a - b)

  const apply = (on: number[]) => {
    setError(null)
    const request = on.length ? api.solenoids(on, hold) : api.stop()
    request.catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }
  const toggle = (s: number) => apply(powered.includes(s) ? powered.filter((p) => p !== s) : [...powered, s])

  return (
    <div className="space-y-3 rounded-xl border border-line bg-bg/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display text-sm font-semibold">Actuate solenoids</p>
        <p className="text-xs text-muted" aria-live="polite">
          <span className="font-display text-base font-semibold text-ink">{powered.length}</span> of 6 powered
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-5">
        <div className="grid shrink-0 grid-cols-2 gap-2" role="group" aria-label="Solenoids, as laid out on the cell">
          {[1, 2, 3, 4, 5, 6].map((s) => {
            const on = powered.includes(s)
            return (
              <button
                key={s} type="button" aria-pressed={on} onClick={() => toggle(s)}
                aria-label={`Solenoid ${s} ${on ? 'on' : 'off'}`}
                className={cx(
                  'flex size-16 flex-col items-center justify-center rounded-2xl border transition',
                  on ? 'border-accent bg-accent text-accent-ink shadow-[0_0_20px_-4px] shadow-accent/70'
                    : 'border-line-strong bg-raised text-ink hover:border-accent/60',
                )}
              >
                <span className="font-display text-lg font-semibold">{s}</span>
                <span className={cx('text-[10px] font-semibold uppercase', on ? 'text-accent-ink' : 'text-faint')}>{on ? 'on' : 'off'}</span>
              </button>
            )
          })}
        </div>
        <div className="min-w-48 flex-1 space-y-3 text-sm text-muted">
          <p>Tap to power any mix at once. {device.solenoid_on_raises ? 'Powered pins rise.' : 'Powered pins drop; the rest stay up.'}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" onClick={() => apply([1, 2, 3, 4, 5, 6])}>All on</button>
            <button type="button" className="btn" onClick={() => apply([])}>All off</button>
          </div>
          <div className="flex items-center gap-2">
            <span className="whitespace-nowrap text-xs text-faint">Hold for</span>
            {HOLD_OPTIONS.map((ms) => (
              <button
                key={ms} type="button" aria-pressed={hold === ms} onClick={() => setHold(ms)}
                className={cx('btn whitespace-nowrap px-2.5 py-1 text-xs', hold === ms && 'border-accent bg-accent/15')}
              >
                {ms / 1000} s
              </button>
            ))}
          </div>
          <p className="text-xs text-faint">Everything switches off after the hold time (8 s at most) to protect the coils.</p>
          {error && <p role="alert" className="text-xs text-bad">{error}</p>}
        </div>
      </div>
      <PowerBudget device={device} />
    </div>
  )
}

/** Hold power and pull-in time: how the firmware spends a small supply's current. */
function PowerBudget({ device }: { device: Device }) {
  const [duty, setDuty] = useState(device.hold_duty ?? 100)
  const [pullIn, setPullIn] = useState(device.pull_in_ms ?? 60)
  const reportedDuty = device.hold_duty
  const reportedPullIn = device.pull_in_ms
  useEffect(() => { if (reportedDuty != null) setDuty(reportedDuty) }, [reportedDuty])
  useEffect(() => { if (reportedPullIn != null) setPullIn(reportedPullIn) }, [reportedPullIn])

  if (device.pwm === false) {
    return <p className="border-t border-line pt-3 text-xs text-faint">This cell switches through relays, so hold power can't be reduced.</p>
  }
  return (
    <div className="space-y-3 border-t border-line pt-3">
      <Slider
        label="Hold power" min={10} max={100} step={5} value={duty} format={(v) => `${v}%`}
        onChange={setDuty} onCommit={(v) => void api.setPrefs({ hold_duty: v })}
      />
      <Slider
        label="Pull-in at full power" min={20} max={300} step={10} value={pullIn} format={(v) => `${v} ms`}
        onChange={setPullIn} onCommit={(v) => void api.setPrefs({ pull_in_ms: v })}
      />
      <p className="text-xs text-faint">
        Each solenoid pulls in at full power, one at a time, then drops to the hold power. Lower hold power lets more
        stay down together. Use <span className="text-muted">All on</span> to find the lowest value where all six stay down.
      </p>
    </div>
  )
}

function ButtonSimulator() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-faint">Tactile button:</span>
      <button type="button" className="btn" onClick={() => void api.button('short').catch(() => undefined)}>Press (capture)</button>
      <button type="button" className="btn" onClick={() => void api.button('double')}>Double (repeat)</button>
      <button type="button" className="btn" onClick={() => void api.button('long')}>Hold (camera braille)</button>
    </div>
  )
}

export function DevicePanel() {
  const { state } = useServer()
  const [lastPress, setLastPress] = useState<{ event: string; at: number } | null>(null)
  useServerEvent('button', (e) => setLastPress({ event: e.event, at: Date.now() / 1000 }))
  const devices = state?.devices ?? []

  return (
    <Card title="Hardware" icon={<Cpu className="size-4" />}
      actions={lastPress && (
        <span className="chip"><Hand className="size-3 text-accent" />{lastPress.event} press · {timeAgo(lastPress.at)}</span>
      )}>
      {devices.length === 0 ? (
        <div className="space-y-4">
          <Empty icon={<RadioTower className="size-5" />} title="No braille cell connected">
            Power the ESP32. It joins WiFi and finds this server by itself (the LED goes solid).
            Until then, braille is simulated on screen.
          </Empty>
          <div className="rounded-xl border border-line bg-bg/40 p-3"><ButtonSimulator /></div>
        </div>
      ) : (
        <div className="space-y-5">
          {devices.map((d) => (
            <div key={d.id} className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-display font-semibold">{d.name}</p>
                  <p className="text-xs text-faint">{d.id} · firmware {d.fw}</p>
                </div>
                <span className="chip">
                  {d.transport === 'wifi' ? <Wifi className="size-3 text-accent" /> : <Usb className="size-3 text-accent" />}
                  {d.transport === 'wifi' ? `WiFi · ${d.ip ?? ''}` : 'USB serial'}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Stat icon={<Wifi className="size-3" />} label="Signal" value={signal(d.rssi)} />
                <Stat icon={<Timer className="size-3" />} label="Uptime" value={d.uptime_ms != null ? duration(d.uptime_ms) : '—'} />
                <Stat icon={<BatteryMedium className="size-3" />} label="Battery"
                  value={d.battery_pct != null ? `${d.battery_pct}% · ${d.battery_v?.toFixed(2)} V` : 'not fitted'} />
                <Stat icon={<Sun className="size-3" />} label="Light" value={d.lux != null ? `${Math.round(d.lux)} lux` : 'no sensor'} />
                <Stat icon={<Lightbulb className="size-3" />} label="Light aid" value={d.features.light_aid ? (d.light_aid ? 'on' : 'off') : 'not fitted'} />
                <Stat icon={<MousePointerClick className="size-3" />} label="Button" value={d.features.button ? 'fitted' : 'not fitted'} />
              </div>
              <SolenoidControl device={d} />
              <SolenoidTest device={d} />
              {d.features.light_aid && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-faint">Light aid:</span>
                  {(['auto', 'on', 'off'] as const).map((m) => (
                    <button key={m} type="button" className="btn" onClick={() => void api.light(m)}>{m}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div className="border-t border-line pt-4"><ButtonSimulator /></div>
        </div>
      )}
    </Card>
  )
}
