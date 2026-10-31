import {
  ConversationProvider, useConversationClientTool, useConversationControls, useConversationInput,
  useConversationMode, useConversationStatus,
} from '@elevenlabs/react'
import { AlertTriangle, Bot, Keyboard, Mic, MicOff, PhoneOff, Send, Sparkles } from 'lucide-react'
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode,
} from 'react'
import { api } from '../lib/api'
import { useLatest, useServer, useServerEvent } from '../lib/server'
import { speaker } from '../lib/speech'
import { cx } from './ui'

type Line = { id: number; role: 'user' | 'agent' | 'system'; text: string }
type Mode = 'voice' | 'text'

type AssistantValue = {
  lines: Line[]
  error: string | null
  mode: Mode | null
  start: (mode: Mode, firstMessage?: string) => Promise<void>
  /** Open a text session ahead of time (no greeting), e.g. while the user is still talking. */
  warmUp: () => void
  stop: () => void
  send: (text: string) => void
}

const AssistantContext = createContext<AssistantValue | null>(null)

export function useAssistant(): AssistantValue {
  const value = useContext(AssistantContext)
  if (!value) throw new Error('useAssistant must be used inside <AssistantProvider>')
  return value
}

/**
 * ElevenLabs conversation + the client tools the agent can call + speech routing.
 * speakReplies reads text-chat replies aloud on this device (the phone's hold-to-talk).
 */
export function AssistantProvider({ children, speakReplies = false }: { children: ReactNode; speakReplies?: boolean }) {
  return (
    <ConversationProvider>
      <AssistantState speakReplies={speakReplies}>{children}</AssistantState>
    </ConversationProvider>
  )
}

/** What was said so far, so a new session (after a timeout or reconnect) picks up the thread. */
function recap(lines: Line[]): string | null {
  const said = lines.filter((l) => l.role !== 'system').slice(-10)
  if (!said.length) return null
  const text = said.map((l) => `${l.role === 'user' ? 'User' : 'You'}: ${l.text}`).join('\n')
  return `This continues an earlier conversation with the same person. Carry on naturally, don't greet them again.\n${text}`
}

function AssistantState({ children, speakReplies }: { children: ReactNode; speakReplies: boolean }) {
  const controls = useConversationControls()
  const [lines, setLines] = useState<Line[]>([])
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode | null>(null)
  // Tracked here rather than read from React state, so a message sent the instant a
  // session connects is never parked in `pending` after it was already flushed.
  const link = useRef<'idle' | 'starting' | 'connected'>('idle')
  const pending = useRef<string | null>(null)
  const lastTyped = useRef<{ text: string; at: number } | null>(null)
  const nextId = useRef(1)
  const linesRef = useLatest(lines)
  const speakRef = useLatest(speakReplies)

  const append = useCallback((role: Line['role'], text: string) => {
    setLines((current) => [...current.slice(-80), { id: nextId.current++, role, text }])
  }, [])

  const open = useCallback(async (next: Mode, firstMessage: string | undefined, greet: boolean) => {
    setError(null)
    if (next === 'voice') speaker.stop()
    link.current = 'starting'
    try {
      const history = recap(linesRef.current.filter((l) => l.text !== firstMessage))
      pending.current = firstMessage ?? null
      setMode(next)
      const creds = await api.assistantSession(next === 'voice' ? 'webrtc' : 'websocket')
      const callbacks = {
        onConnect: () => {
          link.current = 'connected'
          append('system', next === 'voice' ? 'Voice conversation started' : 'Text conversation started')
          if (history) controls.sendContextualUpdate(history)
          if (pending.current) {
            controls.sendUserMessage(pending.current)
            pending.current = null
          }
        },
        onDisconnect: () => {
          link.current = 'idle'
          append('system', 'Conversation ended')
          setMode(null)
        },
        onMessage: ({ message, role }: { message: string; role: 'user' | 'agent' }) => {
          if (!message?.trim()) return
          const typed = lastTyped.current
          if (role === 'user' && typed && typed.text === message.trim() && Date.now() - typed.at < 10000) return
          append(role === 'user' ? 'user' : 'agent', message)
          if (role === 'agent' && next === 'text' && speakRef.current) speaker.say(message, { queue: true, force: true })
        },
        onError: (message: string) => {
          if (link.current === 'starting') link.current = 'idle' // failed to connect; the next send retries
          setError(message)
        },
      }
      // Skip the agent's greeting when the user's words are already on their way.
      const agent = greet && !history ? {} : { agent: { firstMessage: '' } }
      if (next === 'voice') {
        controls.startSession({
          conversationToken: creds.token!, connectionType: 'webrtc', overrides: { ...agent }, ...callbacks,
        })
      } else {
        controls.startSession({
          signedUrl: creds.signed_url!, connectionType: 'websocket', textOnly: true,
          overrides: { conversation: { textOnly: true }, ...agent }, ...callbacks,
        })
      }
    } catch (e) {
      link.current = 'idle'
      setError(e instanceof Error ? e.message : String(e))
      setMode(null)
      pending.current = null
    }
  }, [append, controls, linesRef, speakRef])

  const start = useCallback((next: Mode, firstMessage?: string) => open(next, firstMessage, !firstMessage), [open])

  const warmUp = useCallback(() => {
    if (link.current === 'idle') void open('text', undefined, false)
  }, [open])

  const stop = useCallback(() => controls.endSession(), [controls])

  const send = useCallback((text: string) => {
    const clean = text.trim()
    if (!clean) return
    append('user', clean)
    lastTyped.current = { text: clean, at: Date.now() }
    if (link.current === 'connected') controls.sendUserMessage(clean)
    else if (link.current === 'starting') {
      pending.current = pending.current ? `${pending.current} ${clean}` : clean // goes out on connect
    } else void open('text', clean, false)
  }, [append, controls, open])

  const value = useMemo(
    () => ({ lines, error, mode, start, warmUp, stop, send }), [lines, error, mode, start, warmUp, stop, send])
  return (
    <AssistantContext.Provider value={value}>
      <AgentTools append={append} />
      <SpeechRouter mode={mode} />
      {children}
    </AssistantContext.Provider>
  )
}

/** Tools the agent calls; names and parameters match server/scripts/provision_agent.py. */
function AgentTools({ append }: { append: (role: Line['role'], text: string) => void }) {
  const { state } = useServer()
  const latest = useLatest(state)
  const failed = (e: unknown) => `That didn't work: ${e instanceof Error ? e.message : String(e)}`

  useConversationClientTool('get_surroundings', async () => {
    try {
      const scene = await api.scene()
      append('system', 'Looked through the camera')
      return JSON.stringify(scene)
    } catch (e) {
      return failed(e)
    }
  })

  useConversationClientTool('show_in_braille', async (params: Record<string, unknown>) => {
    const text = String(params.text ?? '').slice(0, 200)
    try {
      const job = await api.showText(text, 'assistant')
      append('system', `Sent “${text}” to the braille cell`)
      const seconds = Math.round(job.duration_ms / 1000)
      const connected = (latest.current?.devices.length ?? 0) > 0
      return `Showing "${text}" on the braille cell: ${job.cells.length} cells, about ${seconds} seconds.` +
        (connected ? '' : ' Note: no braille cell is connected right now, so it only appears on screen.')
    } catch (e) {
      return failed(e)
    }
  })

  useConversationClientTool('stop_braille', async () => {
    try {
      await api.stop()
      append('system', 'Cleared the braille cell')
      return 'The braille cell is cleared.'
    } catch (e) {
      return failed(e)
    }
  })

  useConversationClientTool('set_camera_braille', async (params: Record<string, unknown>) => {
    const enabled = params.enabled === true || params.enabled === 'true'
    try {
      await api.setPrefs({ auto_braille: enabled })
      append('system', `Camera braille ${enabled ? 'on' : 'paused'}`)
      return enabled ? 'Camera braille is on.' : 'Camera braille is paused.'
    } catch (e) {
      return failed(e)
    }
  })

  useConversationClientTool('get_device_status', () => {
    const s = latest.current
    if (!s) return 'The server is not reachable.'
    if (!s.devices.length) return 'No braille cell is connected. Braille is only shown on screen.'
    return s.devices.map((d) => [
      `${d.name} is connected over ${d.transport === 'wifi' ? 'WiFi' : 'USB'}`,
      d.battery_pct != null && `battery ${d.battery_pct}%`,
      d.rssi != null && `signal ${d.rssi} dBm`,
      d.lux != null && `light level ${Math.round(d.lux)} lux`,
    ].filter(Boolean).join(', ')).join('. ') + '.'
  })

  return null
}

/** Speech the server wants said here goes through the agent when a voice chat is open. */
function SpeechRouter({ mode }: { mode: Mode | null }) {
  const { state } = useServer()
  const { status } = useConversationStatus()
  const controls = useConversationControls()

  useEffect(() => {
    speaker.useElevenLabs = Boolean(state?.assistant.tts)
  }, [state?.assistant.tts])

  useServerEvent('speak', (event) => {
    const live = status === 'connected'
    if (live && mode === 'voice') {
      if (event.intent === 'describe') controls.sendUserMessage("What's around me right now?")
      else if (event.intent === 'capture') {
        controls.sendUserMessage(`I pressed the capture button. It found: ${event.text} Tell me briefly.`)
      } else controls.sendContextualUpdate(event.intent === 'announce' ? `The camera now sees: ${event.text}.` : event.text)
      return
    }
    if (live) controls.sendContextualUpdate(`Camera update: ${event.text}`)
    speaker.say(event.text, { interrupt: event.intent !== 'announce' })
  })
  return null
}

// ---------------------------------------------------------------------------- UI

export function useAssistantStatus() {
  const { status, message } = useConversationStatus()
  const { isSpeaking } = useConversationMode()
  const { mode } = useAssistant()
  const label =
    status === 'connecting' ? 'Connecting…'
      : status === 'connected' ? (mode === 'text' ? 'Text chat' : isSpeaking ? 'Speaking' : 'Listening')
        : status === 'error' ? 'Error' : 'Off'
  return { status, message, isSpeaking, label }
}

export function VoiceOrb({ size = 168, onClick, disabled }: { size?: number; onClick: () => void; disabled?: boolean }) {
  const controls = useConversationControls()
  const { status, isSpeaking, label } = useAssistantStatus()
  const { mode } = useAssistant()
  const ref = useRef<HTMLButtonElement>(null)
  const live = status === 'connected' && mode === 'voice'

  useEffect(() => {
    if (!live) {
      ref.current?.style.setProperty('--level', '0')
      return
    }
    let frame = 0
    const tick = () => {
      const level = isSpeaking ? controls.getOutputVolume() : controls.getInputVolume()
      ref.current?.style.setProperty('--level', Math.min(1, level * 2.5).toFixed(3))
      frame = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(frame)
  }, [live, isSpeaking, controls])

  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={live ? 'End voice conversation' : 'Start voice conversation'}
      style={{ width: size, height: size, '--level': 0 } as CSSProperties}
      className="group relative grid shrink-0 place-items-center rounded-full disabled:opacity-40"
    >
      <span
        aria-hidden
        className={cx('absolute inset-0 rounded-full blur-2xl transition-opacity', live ? 'opacity-70' : 'opacity-25')}
        style={{
          background: isSpeaking ? 'var(--color-sky)' : 'var(--color-accent)',
          transform: 'scale(calc(0.85 + var(--level) * 0.5))',
        }}
      />
      <span
        aria-hidden
        className={cx(
          'absolute inset-[6%] rounded-full border border-white/10 transition-transform duration-75',
          status === 'connecting' && 'animate-pulse',
        )}
        style={{
          background: live
            ? `radial-gradient(circle at 32% 28%, #e9fffb, ${isSpeaking ? 'var(--color-sky)' : 'var(--color-accent)'} 42%, #0b3b4a 100%)`
            : 'radial-gradient(circle at 32% 28%, #2a3a58, #111a2d 60%, #070b14 100%)',
          transform: 'scale(calc(1 + var(--level) * 0.12))',
          boxShadow: live ? '0 0 60px -10px var(--color-accent)' : 'inset 0 2px 12px rgb(255 255 255 / 0.05)',
        }}
      />
      <span className="relative flex flex-col items-center gap-1">
        {live ? <PhoneOff className="size-7 text-accent-ink" /> : <Mic className="size-8 text-accent transition group-hover:scale-110" />}
        <span className={cx('text-xs font-semibold', live ? 'text-accent-ink' : 'text-muted')}>
          {live ? label : 'Tap to talk'}
        </span>
      </span>
    </button>
  )
}

export function AssistantSetup() {
  const { state } = useServer()
  const a = state?.assistant
  return (
    <div className="space-y-4 text-sm">
      <div className="flex gap-3 rounded-xl border border-warn/30 bg-warn/5 p-3.5 text-warn">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <p>The voice assistant needs an ElevenLabs API key and an agent. Everything else works without it.</p>
      </div>
      <ol className="space-y-3 text-muted">
        <li className={cx(a?.api_key && 'text-ok')}>
          <span className="font-semibold text-ink">1.</span> Put your key in <code className="kbd">server/.env</code> as{' '}
          <code className="kbd">ELEVENLABS_API_KEY=…</code> {a?.api_key && '✓'}
        </li>
        <li className={cx(a?.agent_id && 'text-ok')}>
          <span className="font-semibold text-ink">2.</span> Create the agent and its tools:{' '}
          <code className="kbd">python scripts/provision_agent.py</code> {a?.agent_id && '✓'}
        </li>
        <li>
          <span className="font-semibold text-ink">3.</span> Restart the server.
        </li>
      </ol>
    </div>
  )
}

const QUICK_PROMPTS = ["What's around me?", 'Spell "exit" on my braille cell', 'Tell me a joke', 'Is my braille cell connected?']

export function AssistantPanel() {
  const { state } = useServer()
  const { lines, error, mode, start, stop, send } = useAssistant()
  const { status, label } = useAssistantStatus()
  const { isMuted, setMuted } = useConversationInput()
  const [draft, setDraft] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const ready = Boolean(state?.assistant.ready)
  const connected = status === 'connected'

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [lines.length])

  if (!ready) return <AssistantSetup />

  const toggleVoice = () => {
    speaker.unlock()
    if (connected || status === 'connecting') stop()
    else void start('voice')
  }

  return (
    <div className="flex h-full min-h-[460px] flex-col gap-4">
      <div className="flex items-center gap-5">
        <VoiceOrb size={132} onClick={toggleVoice} />
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <p className="eyebrow">ElevenLabs agent</p>
            <p className="font-display text-xl font-semibold">{label}</p>
            <p className="text-xs text-muted">
              {connected ? (mode === 'voice' ? 'Speak naturally. It can see the camera and use the braille cell.' : 'Typing only, no microphone.')
                : 'A friend to chat with, plus the camera and braille cell.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {connected && mode === 'voice' && (
              <button type="button" className="btn" onClick={() => setMuted(!isMuted)} aria-pressed={isMuted}>
                {isMuted ? <MicOff className="size-4 text-bad" /> : <Mic className="size-4" />}
                {isMuted ? 'Unmute' : 'Mute'}
              </button>
            )}
            {connected ? (
              <button type="button" className="btn btn-danger" onClick={stop}><PhoneOff className="size-4" />End</button>
            ) : (
              <button type="button" className="btn" onClick={() => void start('text')}><Keyboard className="size-4" />Text only</button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>
      )}

      <div ref={listRef} className="scrollbar-thin -mx-1 flex min-h-40 flex-1 flex-col gap-2 overflow-y-auto px-1" aria-live="polite">
        {lines.length === 0 ? (
          <div className="m-auto flex flex-col items-center gap-3 py-6 text-center text-sm text-muted">
            <Bot className="size-6 text-faint" />
            <p>Chat about anything, ask what's around you, or have it spell something on the cell.</p>
            <div className="flex flex-wrap justify-center gap-2">
              {QUICK_PROMPTS.map((prompt) => (
                <button key={prompt} type="button" className="chip hover:border-accent/50 hover:text-ink" onClick={() => send(prompt)}>
                  <Sparkles className="size-3 text-accent" />{prompt}
                </button>
              ))}
            </div>
          </div>
        ) : lines.map((line) => (
          line.role === 'system' ? (
            <p key={line.id} className="self-center rounded-full bg-raised px-3 py-1 text-[11px] text-faint">{line.text}</p>
          ) : (
            <p
              key={line.id}
              className={cx(
                'max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed',
                line.role === 'user' ? 'self-end rounded-br-md bg-accent/15 text-ink' : 'self-start rounded-bl-md border border-line bg-raised text-ink',
              )}
            >
              {line.text}
            </p>
          )
        ))}
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          send(draft)
          setDraft('')
        }}
      >
        <input
          className="field" value={draft} onChange={(e) => setDraft(e.target.value)}
          placeholder={connected ? 'Type a message…' : 'Type to start a text chat…'} aria-label="Message the assistant"
        />
        <button type="submit" className="btn btn-primary" disabled={!draft.trim()} aria-label="Send"><Send className="size-4" /></button>
      </form>
    </div>
  )
}
