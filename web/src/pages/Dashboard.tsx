import { Bot, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ActivityLog } from '../components/ActivityLog'
import { AssistantPanel, AssistantProvider, useAssistant, useAssistantStatus } from '../components/Assistant'
import { BraillePanel } from '../components/BraillePanel'
import { ConnectPhone } from '../components/ConnectPhone'
import { DevicePanel } from '../components/DevicePanel'
import { Card, StatusPill } from '../components/ui'
import { VisionPanel } from '../components/VisionPanel'
import { api } from '../lib/api'
import { useServer } from '../lib/server'
import { speaker } from '../lib/speech'

export function Dashboard() {
  const [connectOpen, setConnectOpen] = useState(false)
  return (
    <AssistantProvider>
      <div className="mx-auto max-w-[1680px] px-4 pb-10 pt-5 sm:px-6 lg:px-8">
        <Header onConnectPhone={() => setConnectOpen(true)} />
        <main className="mt-6 grid items-start gap-5 lg:grid-cols-2 2xl:grid-cols-12">
          <div className="lg:col-span-2 2xl:col-span-5"><VisionPanel onConnectPhone={() => setConnectOpen(true)} /></div>
          <div className="2xl:col-span-4">
            <Card title="Assistant" icon={<Bot className="size-4" />}><AssistantPanel /></Card>
          </div>
          <div className="2xl:col-span-3"><BraillePanel /></div>
          <div className="2xl:col-span-7"><DevicePanel /></div>
          <div className="2xl:col-span-5"><ActivityLog /></div>
        </main>
        <Footer />
      </div>
      <ConnectPhone open={connectOpen} onClose={() => setConnectOpen(false)} />
      <Shortcuts />
    </AssistantProvider>
  )
}

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid grid-cols-2 gap-1 rounded-xl border border-line bg-surface p-2" aria-hidden>
        {[1, 0, 0, 1, 1, 0].map((on, i) => (
          <span key={i} className={on ? 'size-1.5 rounded-full bg-accent' : 'size-1.5 rounded-full bg-line-strong'} />
        ))}
      </div>
      <div>
        <h1 className="font-display text-xl font-bold tracking-tight">DynaBraille</h1>
        <p className="text-xs text-muted">Camera to braille, with a voice assistant</p>
      </div>
    </div>
  )
}

function Header({ onConnectPhone }: { onConnectPhone: () => void }) {
  const { state, connected } = useServer()
  const assistant = useAssistantStatus()
  const device = state?.devices[0]
  const vision = state?.vision
  const phonePage = (state?.clients.phone ?? 0) > 0

  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <Logo />
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill label="Server" value={connected ? 'online' : 'reconnecting'} tone={connected ? 'ok' : 'bad'} pulse={!connected} />
        <StatusPill label="Braille cell"
          value={device ? (device.transport === 'wifi' ? 'WiFi' : 'USB') : 'simulated'} tone={device ? 'ok' : 'idle'} />
        <StatusPill label="iPhone camera"
          value={vision?.camera_online ? `${vision.fps} fps` : phonePage ? 'page open' : 'offline'}
          tone={vision?.camera_online ? 'ok' : phonePage ? 'warn' : 'idle'} />
        <StatusPill label="Detection"
          value={vision?.detector ?? '…'} tone={vision?.detector === 'ready' ? 'ok' : vision?.detector === 'loading' ? 'warn' : 'bad'}
          pulse={vision?.detector === 'loading'} />
        <StatusPill label="Assistant"
          value={state?.assistant.ready ? assistant.label : 'not set up'}
          tone={!state?.assistant.ready ? 'warn' : assistant.status === 'connected' ? 'accent' : 'idle'}
          pulse={assistant.status === 'connected'} />
        <button type="button" className="btn btn-primary ml-1" onClick={onConnectPhone}>
          <Smartphone className="size-4" />Connect iPhone
        </button>
      </div>
    </header>
  )
}

function Footer() {
  const { state } = useServer()
  return (
    <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 text-xs text-faint">
      <p>DynaBraille server {state?.server.version ?? ''}</p>
      <p className="flex flex-wrap items-center gap-3">
        <span><span className="kbd">C</span> capture</span>
        <span><span className="kbd">V</span> voice</span>
        <span><span className="kbd">/</span> type braille</span>
        <span><span className="kbd">Esc</span> stop cell</span>
      </p>
    </footer>
  )
}

function Shortcuts() {
  const { state } = useServer()
  const { start, stop, mode } = useAssistant()
  const { status } = useAssistantStatus()
  const ready = Boolean(state?.assistant.ready)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || target.closest('input, textarea, select, dialog[open]')) return
      if (e.key === 'c') void api.capture().catch(() => undefined)
      else if (e.key === 'Escape') void api.stop()
      else if (e.key === '/') {
        e.preventDefault()
        document.getElementById('braille-input')?.focus()
      } else if (e.key === 'v' && ready) {
        speaker.unlock()
        if (status === 'connected' && mode === 'voice') stop()
        else if (status !== 'connecting') void start('voice')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [ready, status, mode, start, stop])
  return null
}
