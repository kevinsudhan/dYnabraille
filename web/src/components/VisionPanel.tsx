import { Aperture, Camera, Loader2, ScanEye, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useServer } from '../lib/server'
import type { Prefs } from '../lib/types'
import { BrailleCell } from './BrailleCell'
import { DetectionLabels, DetectionList, DetectionOverlay, describe } from './Detections'
import { Card, Slider, Toggle, cx, timeAgo } from './ui'

export function VisionPanel({ onConnectPhone }: { onConnectPhone: () => void }) {
  const { state } = useServer()
  const [capturing, setCapturing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confidence, setConfidence] = useState(0.45)
  const [streamKey, setStreamKey] = useState(0)
  const vision = state?.vision
  const online = Boolean(vision?.camera_online)

  const serverConfidence = state?.prefs.min_confidence
  useEffect(() => {
    if (serverConfidence != null) setConfidence(serverConfidence)
  }, [serverConfidence])

  // Reconnect the MJPEG stream whenever the camera comes (back) online.
  useEffect(() => {
    if (online) setStreamKey((k) => k + 1)
  }, [online])

  const capture = async () => {
    setError(null)
    setCapturing(true)
    try {
      await api.capture()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCapturing(false)
    }
  }

  const setPref = (changes: Partial<Prefs>) => void api.setPrefs(changes).catch((e) => setError(String(e)))
  const detector = vision?.detector
  const detectorText =
    detector === 'ready' ? `${vision?.model} · ${vision?.device}`
      : detector === 'loading' ? 'Loading model…'
        : detector === 'disabled' ? 'Detection off' : `Detection unavailable`

  return (
    <Card
      title="Vision"
      icon={<ScanEye className="size-4" />}
      actions={
        <span className="text-xs text-muted">
          {online ? `${vision?.fps ?? 0} fps · ${Math.round(state?.infer_ms ?? 0)} ms` : 'camera offline'}
        </span>
      }
    >
      <div className="space-y-4">
        <div className="relative overflow-hidden rounded-xl border border-line bg-black">
          {online ? (
            // Height is capped so a portrait iPhone frame doesn't push the controls off screen;
            // the wrapper shrinks to the image so the overlay stays aligned.
            <div className="relative mx-auto w-fit">
              <img key={streamKey} src={`/api/vision/stream?k=${streamKey}`} alt="Live view from the iPhone camera"
                className="block max-h-[min(62vh,620px)] w-auto max-w-full" />
              <DetectionOverlay detections={state?.detections ?? []} focus={state?.focus} />
              <DetectionLabels detections={state?.detections ?? []} focus={state?.focus} />
            </div>
          ) : (
            <div className="grid aspect-[4/3] place-items-center p-6 text-center">
              <div className="flex max-w-xs flex-col items-center gap-3">
                <div className="grid size-14 place-items-center rounded-2xl border border-line-strong bg-raised">
                  <Smartphone className="size-6 text-accent" />
                </div>
                <p className="font-display text-base font-semibold">No camera connected</p>
                <p className="text-sm text-muted">Open the camera page on the iPhone. Its live view and detections appear here.</p>
                <button type="button" className="btn btn-primary" onClick={onConnectPhone}>Connect iPhone</button>
              </div>
            </div>
          )}
          {/* bottom corner, so it never covers the detection labels along the top */}
          <span className="absolute bottom-3 left-3 flex items-center gap-1.5 rounded-full bg-bg/80 px-2.5 py-1 text-[11px] text-muted ring-1 ring-line">
            {detector === 'loading' && <Loader2 className="size-3 animate-spin" />}
            {detectorText}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button" className="btn btn-primary h-11 px-5 text-base" onClick={capture} disabled={!online || capturing}
            title="Same as the tactile button: freeze this frame, spell the objects on the cell and say them (C)"
          >
            {capturing ? <Loader2 className="size-5 animate-spin" /> : <Aperture className="size-5" />}
            Capture scene
          </button>
          <div className="min-w-0 flex-1 text-sm" aria-live="polite">
            {state?.focus ? (
              <p className="truncate"><span className="text-faint">In focus </span><span className="font-medium text-ink">{describe(state.focus)}</span></p>
            ) : (
              <p className="text-muted">{online ? 'Nothing recognised yet' : 'Waiting for the camera'}</p>
            )}
          </div>
        </div>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}

        {online && (state?.detections.length ?? 0) > 0 && (
          <DetectionList detections={state!.detections} focus={state?.focus} />
        )}

        <LastCapture />

        <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
          <Toggle
            label="Continuous camera braille" hint="Spell whatever is in front of the camera without pressing the button"
            checked={Boolean(state?.prefs.auto_braille)} onChange={(v) => setPref({ auto_braille: v })}
          />
          <Toggle
            label="Announce changes" hint="Say it out loud when a new object comes into view"
            checked={Boolean(state?.prefs.announce)} onChange={(v) => setPref({ announce: v })}
          />
          <div className="sm:col-span-2">
            <Slider
              label="Detection confidence" min={0.2} max={0.9} step={0.05} value={confidence}
              format={(v) => `${Math.round(v * 100)}%`} onChange={setConfidence}
              onCommit={(v) => setPref({ min_confidence: v })}
            />
          </div>
        </div>
      </div>
    </Card>
  )
}

function LastCapture() {
  const { state } = useServer()
  const capture = state?.capture
  if (!capture) return null
  return (
    <div className="flex gap-4 rounded-xl border border-line bg-bg/40 p-3">
      <div className="relative w-36 shrink-0 overflow-hidden rounded-lg bg-black sm:w-44">
        <img src={`/api/vision/capture.jpg?at=${capture.at}`} alt="Captured frame" className="block w-full" />
        <DetectionOverlay detections={capture.detections} />
        <DetectionLabels detections={capture.detections} detail={false} />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="eyebrow flex items-center gap-1.5"><Camera className="size-3" />Last capture · {timeAgo(capture.at)} · {capture.trigger}</p>
        <p className="text-sm leading-relaxed text-ink">{capture.summary}</p>
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="text-xs text-faint">Cell:</span>
          <span className="truncate font-display text-sm text-accent">{capture.braille_text}</span>
        </div>
        <CaptureCells text={capture.braille_text} />
      </div>
    </div>
  )
}

function CaptureCells({ text }: { text: string }) {
  const { state } = useServer()
  const job = state?.job
  if (!job || job.text !== text) return null
  return (
    <div className="flex flex-wrap gap-1">
      {job.cells.map((cell, i) => (
        <span key={i} className={cx('rounded-md', job.active && i === job.index && 'ring-2 ring-accent')}>
          <BrailleCell mask={cell.mask} size="xs" />
        </span>
      ))}
    </div>
  )
}
