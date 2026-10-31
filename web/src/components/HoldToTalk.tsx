import { Loader2, Mic, PhoneOff, Volume2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from 'react'
import { api } from '../lib/api'
import { MicRecorder } from '../lib/recorder'
import { useLatest, useServer } from '../lib/server'
import { speaker } from '../lib/speech'
import { useAssistant, useAssistantStatus } from './Assistant'
import { cx } from './ui'

type Phase = 'idle' | 'opening' | 'listening' | 'transcribing' | 'thinking'

const MIN_SPEECH_MS = 350
const REPLY_TIMEOUT_MS = 25_000
const IDLE_END_MS = 120_000 // close the agent session after two quiet minutes; it reconnects on the next press

function useSpeaking(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      speaker.addEventListener('change', onChange)
      return () => speaker.removeEventListener('change', onChange)
    },
    () => speaker.isSpeaking,
  )
}

function micProblem(e: unknown): string {
  const name = e instanceof DOMException ? e.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone access is blocked. Settings → Safari → Microphone → Allow, then reload this page.'
  }
  if (name === 'NotFoundError') return 'No microphone found.'
  return e instanceof Error ? e.message : String(e)
}

/**
 * Walkie-talkie style chat with the agent: the mic records only while the button
 * is held, the recording is transcribed on the server and sent to the agent, and
 * the reply is spoken through the phone's speaker (or connected headphones).
 */
export function HoldToTalk() {
  const { state } = useServer()
  const { send, warmUp, stop, lines, error: chatError, mode } = useAssistant()
  const { status } = useAssistantStatus()
  const speaking = useSpeaking()
  const [phase, setPhase] = useState<Phase>('idle')
  const [hint, setHint] = useState<string | null>(null)
  const recorder = useRef(new MicRecorder())
  const button = useRef<HTMLButtonElement>(null)
  const held = useRef(false)
  const interrupted = useRef(false)
  const lastPress = useRef(0)
  const repliesAtSend = useRef(0)
  const latestLines = useLatest(lines)
  const ready = Boolean(state?.assistant.ready)
  const replies = lines.filter((l) => l.role === 'agent').length

  const fail = useCallback((message: string, say = false) => {
    setPhase('idle')
    setHint(message)
    speaker.cue('error')
    if (say) speaker.say(message, { interrupt: true, force: true })
  }, [])

  // Level meter while listening.
  useEffect(() => {
    if (phase !== 'listening') {
      button.current?.style.setProperty('--level', '0')
      return
    }
    let frame = 0
    const tick = () => {
      button.current?.style.setProperty('--level', recorder.current.level().toFixed(3))
      frame = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(frame)
  }, [phase])

  // The agent answered.
  useEffect(() => {
    if (phase === 'thinking' && replies > repliesAtSend.current) setPhase('idle')
  }, [phase, replies])

  useEffect(() => {
    if (phase !== 'thinking') return
    const timer = setTimeout(() => fail('No reply from the assistant. Try again.', true), REPLY_TIMEOUT_MS)
    return () => clearTimeout(timer)
  }, [phase, fail])

  useEffect(() => {
    if (chatError && phase === 'thinking') fail(chatError)
  }, [chatError, phase, fail])

  // Don't keep a session (and its billing) open while nobody is talking.
  useEffect(() => {
    if (status !== 'connected' || mode !== 'text' || phase !== 'idle' || speaking) return
    const timer = setTimeout(stop, IDLE_END_MS)
    return () => clearTimeout(timer)
  }, [status, mode, phase, speaking, lines.length, stop])

  useEffect(() => () => recorder.current.cancel(), [])

  const press = async () => {
    if (held.current) return
    held.current = true
    lastPress.current = Date.now()
    interrupted.current = speaker.isSpeaking
    setHint(null)
    speaker.unlock()
    speaker.stop() // pressing always cuts the agent off
    if (!ready) return
    warmUp() // connect to the agent while the user is still talking
    setPhase('opening')
    try {
      await recorder.current.start(speaker.context)
    } catch (e) {
      held.current = false
      fail(micProblem(e))
      return
    }
    if (!held.current) {
      // Let go before the mic was open (often the first time, at the permission prompt).
      recorder.current.cancel()
      setPhase('idle')
      if (!interrupted.current) setHint('Microphone ready. Hold the button down while you talk.')
      return
    }
    speaker.cue('listen')
    setPhase('listening')
  }

  const release = async () => {
    if (!held.current) return
    held.current = false
    if (!recorder.current.active) return // still opening; press() finishes up
    const recording = await recorder.current.stop()
    if (!recording || recording.ms < MIN_SPEECH_MS || recording.blob.size < 800) {
      setPhase('idle')
      // A quick tap while it was talking just means "stop talking".
      if (!interrupted.current) fail('Hold the button down while you talk, then let go.', true)
      return
    }
    speaker.cue('sent')
    setPhase('transcribing')
    try {
      const text = await api.stt(recording.blob)
      if (!text) {
        fail("Sorry, I didn't catch that.", true)
        return
      }
      repliesAtSend.current = latestLines.current.filter((l) => l.role === 'agent').length
      setPhase('thinking')
      send(text)
    } catch (e) {
      fail(e instanceof Error ? e.message : String(e))
    }
  }

  if (!ready) {
    return (
      <section className="card flex items-center gap-3 p-4 text-sm text-muted">
        <Mic className="size-5 shrink-0 text-faint" />
        The voice assistant isn't set up on the server yet (ElevenLabs key and agent in server/.env).
      </section>
    )
  }

  const listening = phase === 'listening'
  const busy = phase === 'opening' || phase === 'transcribing' || phase === 'thinking'
  const title =
    listening ? 'Listening…'
      : phase === 'opening' ? 'Opening mic…'
        : phase === 'transcribing' ? 'Got it…'
          : phase === 'thinking' ? 'Thinking…'
            : speaking ? 'Speaking'
              : 'Hold to talk'
  const subtitle =
    listening ? 'Let go when you’re done'
      : busy ? 'One moment'
        : speaking ? 'Hold to interrupt, tap to stop'
          : 'Ask anything, or just chat'
  const recent = lines.filter((l) => l.role !== 'system').slice(-3)

  return (
    <section className={cx('card flex flex-col gap-3 p-3', (listening || speaking) && 'border-accent/40')} aria-label="Assistant">
      <button
        ref={button}
        type="button"
        aria-label="Hold to talk to DynaBraille"
        aria-describedby="ptt-help"
        className={cx(
          'relative flex h-36 w-full select-none flex-col items-center justify-center gap-1.5 overflow-hidden rounded-2xl border-2 transition-colors',
          listening ? 'border-accent bg-accent text-accent-ink'
            : speaking ? 'border-sky/60 bg-sky/10 text-ink'
              : 'border-accent/50 bg-accent/10 text-ink active:bg-accent/20',
        )}
        style={{ touchAction: 'none', WebkitTouchCallout: 'none', WebkitUserSelect: 'none', '--level': 0 } as CSSProperties}
        onPointerDown={(e) => {
          e.preventDefault()
          try {
            e.currentTarget.setPointerCapture(e.pointerId) // so sliding off the button still counts as holding
          } catch {
            /* not capturable */
          }
          void press()
        }}
        onPointerUp={() => void release()}
        onPointerCancel={() => void release()}
        onLostPointerCapture={() => void release()}
        onContextMenu={(e) => e.preventDefault()}
        onKeyDown={(e) => {
          if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
            e.preventDefault()
            void press()
          }
        }}
        onKeyUp={(e) => {
          if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault()
            void release()
          }
        }}
        onClick={() => {
          // A click with no press before it is VoiceOver's plain double-tap.
          if (Date.now() - lastPress.current > 1500) {
            setHint('With VoiceOver: double-tap and hold, talk, then let go.')
          }
        }}
      >
        {listening && (
          <span
            aria-hidden
            className="absolute inset-0 origin-bottom bg-white/25"
            style={{ transform: 'scaleY(calc(0.08 + var(--level) * 0.92))', transition: 'transform 60ms linear' }}
          />
        )}
        <span className="relative">
          {busy ? <Loader2 className="size-9 animate-spin" />
            : speaking && !listening ? <Volume2 className="size-9 text-sky" />
              : <Mic className={cx('size-9', !listening && 'text-accent')} />}
        </span>
        <span className="relative font-display text-2xl font-bold" aria-live="polite">{title}</span>
        <span className={cx('relative text-sm', listening ? 'text-accent-ink/80' : 'text-muted')}>{subtitle}</span>
      </button>

      <p id="ptt-help" className="sr-only">
        Hold the button while you talk and let go to send. The reply is spoken through your speaker or headphones.
      </p>

      {hint && <p role="alert" className="rounded-xl border border-warn/30 bg-warn/10 px-3 py-2 text-sm text-warn">{hint}</p>}

      {recent.length > 0 && (
        // Captions only: replies are already spoken, so no aria-live here.
        <div className="space-y-1.5 px-1">
          {recent.map((line) => (
            <p key={line.id} className={cx('text-base leading-snug', line.role === 'user' ? 'text-muted' : 'text-ink')}>
              <span className="mr-1.5 text-xs font-semibold uppercase tracking-wide text-faint">
                {line.role === 'user' ? 'You' : 'DynaBraille'}
              </span>
              {line.text}
            </p>
          ))}
        </div>
      )}

      {status === 'connected' && (
        <button type="button" className="btn h-10 self-end rounded-xl text-sm" onClick={() => { speaker.stop(); stop() }}>
          <PhoneOff className="size-4" />End chat
        </button>
      )}
    </section>
  )
}
