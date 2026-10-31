import { Aperture, Camera, CameraOff, Loader2, RotateCcw, SwitchCamera, Volume2, VolumeX } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { AssistantProvider } from '../components/Assistant'
import { DetectionLabels, DetectionOverlay, describe } from '../components/Detections'
import { HoldToTalk } from '../components/HoldToTalk'
import { Dot, cx } from '../components/ui'
import { api, wsUrl } from '../lib/api'
import { useServer, useServerEvent } from '../lib/server'
import { speaker } from '../lib/speech'
import type { Detection } from '../lib/types'

const MAX_WIDTH = 640 // frames are scaled down to this before upload; plenty for YOLO
const JPEG_QUALITY = 0.7
const MIN_INTERVAL_MS = 60 // at most ~15 frames a second
const REPLY_TIMEOUT_MS = 2000

type FrameResult = { seq: number; detections: Detection[]; focus: Detection | null; infer_ms: number }

/** Streams frames from <video> to the server, one in flight at a time, so it never builds a backlog. */
function useFrameStreamer(video: RefObject<HTMLVideoElement | null>, enabled: boolean, onResult: (r: FrameResult) => void) {
  const [link, setLink] = useState<'off' | 'connecting' | 'up'>('off')
  const [fps, setFps] = useState(0)
  const [rtt, setRtt] = useState(0)
  const resultRef = useRef(onResult)
  resultRef.current = onResult

  useEffect(() => {
    if (!enabled) {
      setLink('off')
      return
    }
    let stopped = false
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let seq = 0
    let inflight: { seq: number; at: number } | null = null
    let replies: number[] = []
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')

    const schedule = (ms: number) => {
      clearTimeout(timer)
      timer = setTimeout(send, ms)
    }

    const send = () => {
      if (stopped || socket?.readyState !== WebSocket.OPEN || !ctx) return
      if (inflight && performance.now() - inflight.at < REPLY_TIMEOUT_MS) return schedule(50)
      const v = video.current
      if (!v || v.readyState < 2 || !v.videoWidth) return schedule(200)
      const scale = Math.min(1, MAX_WIDTH / v.videoWidth)
      canvas.width = Math.round(v.videoWidth * scale)
      canvas.height = Math.round(v.videoHeight * scale)
      ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
      canvas.toBlob(async (blob) => {
        if (!blob || stopped || socket?.readyState !== WebSocket.OPEN) return
        const body = new Uint8Array(4 + blob.size)
        new DataView(body.buffer).setUint32(0, ++seq) // big-endian sequence number
        body.set(new Uint8Array(await blob.arrayBuffer()), 4)
        inflight = { seq, at: performance.now() }
        socket.send(body)
        schedule(REPLY_TIMEOUT_MS) // watchdog in case a reply is lost
      }, 'image/jpeg', JPEG_QUALITY)
    }

    const connect = () => {
      setLink('connecting')
      socket = new WebSocket(wsUrl('/ws/camera'))
      socket.onopen = () => {
        setLink('up')
        inflight = null
        schedule(0)
      }
      socket.onmessage = (message) => {
        const result = JSON.parse(message.data) as FrameResult
        if (!inflight || result.seq !== inflight.seq) return
        const now = performance.now()
        setRtt(Math.round(now - inflight.at))
        replies = [...replies.filter((t) => now - t < 2000), now]
        setFps(Math.round(replies.length / 2))
        inflight = null
        resultRef.current(result)
        schedule(MIN_INTERVAL_MS)
      }
      socket.onclose = () => {
        setLink('connecting')
        inflight = null
        if (!stopped) timer = setTimeout(connect, 1500)
      }
    }

    connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      socket?.close()
      setLink('off')
    }
  }, [enabled, video])

  return { link, fps, rtt }
}

function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    const acquire = () => {
      navigator.wakeLock.request('screen').then((l) => (lock = l)).catch(() => undefined)
    }
    const onVisible = () => document.visibilityState === 'visible' && acquire()
    acquire()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      void lock?.release()
    }
  }, [active])
}

export function CameraPage() {
  return (
    <AssistantProvider speakReplies>
      <PhoneCamera />
    </AssistantProvider>
  )
}

function PhoneCamera() {
  const { state, connected } = useServer()
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [running, setRunning] = useState(false)
  const [starting, setStarting] = useState(false)
  const [facing, setFacing] = useState<'environment' | 'user'>('environment')
  const [error, setError] = useState<string | null>(null)
  const [detections, setDetections] = useState<Detection[]>([])
  const [focus, setFocus] = useState<Detection | null>(null)
  const [voiceOn, setVoiceOn] = useState(true)
  const [capturing, setCapturing] = useState(false)
  const [lastCapture, setLastCapture] = useState<string | null>(null)

  const onResult = useCallback((r: FrameResult) => {
    setDetections(r.detections)
    setFocus(r.focus)
  }, [])
  const { link, fps, rtt } = useFrameStreamer(videoRef, running, onResult)
  useWakeLock(running)

  useServerEvent('scene.capture', (e) => setLastCapture(e.capture.summary))
  useEffect(() => {
    speaker.enabled = voiceOn
  }, [voiceOn])

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setRunning(false)
    setDetections([])
    setFocus(null)
  }, [])

  const startCamera = useCallback(async (mode = facing) => {
    speaker.unlock() // this tap is what lets the page speak later on iOS
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('This browser blocks the camera on insecure pages. Open the https:// address and trust the certificate.')
      return
    }
    setStarting(true)
    try {
      streamRef.current?.getTracks().forEach((t) => t.stop())
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: mode }, width: { ideal: 1280 }, height: { ideal: 720 } },
      })
      streamRef.current = stream
      const video = videoRef.current!
      video.srcObject = stream
      await video.play()
      setRunning(true)
    } catch (e) {
      const name = e instanceof DOMException ? e.name : ''
      setError(name === 'NotAllowedError'
        ? 'Camera access was denied. Settings → Safari → Camera → Allow, then reload.'
        : `Couldn't start the camera: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setStarting(false)
    }
  }, [facing])

  useEffect(() => () => stopCamera(), [stopCamera])

  const flip = () => {
    const next = facing === 'environment' ? 'user' : 'environment'
    setFacing(next)
    if (running) void startCamera(next)
  }

  const capture = async () => {
    speaker.unlock()
    setCapturing(true)
    try {
      await api.capture('phone')
    } catch (e) {
      setLastCapture(e instanceof Error ? e.message : String(e))
    } finally {
      setCapturing(false)
    }
  }

  const insecure = !window.isSecureContext
  const httpsUrl = state?.server.urls.camera.find((u) => u.includes(location.hostname)) ?? state?.server.urls.camera[0]

  return (
    <div className="mx-auto flex min-h-dvh max-w-xl flex-col gap-4 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))]">
      <header className="flex items-center justify-between">
        <h1 className="font-display text-lg font-bold">DynaBraille <span className="font-normal text-muted">camera</span></h1>
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="flex items-center gap-1.5"><Dot tone={connected ? 'ok' : 'bad'} />server</span>
          <span className="flex items-center gap-1.5">
            <Dot tone={link === 'up' ? 'ok' : link === 'connecting' ? 'warn' : 'idle'} />
            {link === 'up' ? `${fps} fps · ${rtt} ms` : 'stream'}
          </span>
        </div>
      </header>

      <div className={cx('relative overflow-hidden rounded-2xl border border-line bg-black', !running && 'hidden')}>
        <div className="relative mx-auto w-fit">
          <video ref={videoRef} playsInline muted autoPlay className="block max-h-[52dvh] w-auto max-w-full" aria-label="Camera preview" />
          <DetectionOverlay detections={detections} focus={focus} />
          <DetectionLabels detections={detections} focus={focus} />
        </div>
        <button type="button" onClick={flip} className="btn absolute right-3 top-3 bg-bg/70 px-2.5" aria-label="Switch camera">
          <SwitchCamera className="size-5" />
        </button>
      </div>

      {!running && (
        <section className="card flex flex-col items-center gap-4 px-6 py-10 text-center">
          <div className="grid size-16 place-items-center rounded-3xl border border-line-strong bg-raised">
            <Camera className="size-8 text-accent" />
          </div>
          <div className="space-y-1">
            <p className="font-display text-xl font-semibold">Point the camera ahead</p>
            <p className="text-sm text-muted">Frames go to the DynaBraille server on your network. Nothing leaves it.</p>
          </div>
          {insecure ? (
            <div className="space-y-2 text-sm text-warn">
              <p>The camera only works over HTTPS.</p>
              {httpsUrl && <a className="btn btn-primary" href={httpsUrl}>Open secure page</a>}
            </div>
          ) : (
            <button type="button" className="btn btn-primary h-14 w-full max-w-xs text-lg" onClick={() => void startCamera()} disabled={starting}>
              {starting ? <Loader2 className="size-5 animate-spin" /> : <Camera className="size-5" />}Start camera
            </button>
          )}
        </section>
      )}

      {error && <p role="alert" className="rounded-xl border border-bad/30 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}

      {running && (
        <p className="min-h-8 text-center font-display text-2xl font-semibold" aria-live="polite">
          {focus ? describe(focus) : <span className="text-muted">Looking…</span>}
        </p>
      )}

      <button type="button" onClick={() => void capture()} disabled={!running || capturing}
        className="btn btn-primary h-20 w-full rounded-2xl text-xl">
        {capturing ? <Loader2 className="size-6 animate-spin" /> : <Aperture className="size-6" />}Capture scene
      </button>

      <HoldToTalk />

      <div className="grid grid-cols-2 gap-3">
        <button type="button" className="btn h-14 rounded-2xl text-base" onClick={() => void api.replay().catch(() => undefined)}>
          <RotateCcw className="size-5" />Repeat on cell
        </button>
        <button type="button" className="btn h-14 rounded-2xl" aria-pressed={voiceOn} onClick={() => setVoiceOn((v) => !v)}>
          {voiceOn ? <Volume2 className="size-5" /> : <VolumeX className="size-5 text-bad" />}
          {voiceOn ? 'Speech on' : 'Speech off'}
        </button>
        {running && (
          <button type="button" className="btn col-span-2 h-14 rounded-2xl" onClick={stopCamera}><CameraOff className="size-5" />Stop camera</button>
        )}
      </div>

      {lastCapture && (
        <section className="card p-4" aria-live="polite">
          <p className="eyebrow mb-1">Last capture</p>
          <p className="text-base leading-relaxed">{lastCapture}</p>
        </section>
      )}

      <p className="mt-auto text-center text-xs text-faint">
        Keep this page open with the screen on. The tactile button on the cell captures too.
      </p>
    </div>
  )
}
