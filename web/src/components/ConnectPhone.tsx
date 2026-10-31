import QRCode from 'qrcode'
import { ShieldCheck, Smartphone, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useServer } from '../lib/server'

function Qr({ url, label }: { url: string; label: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    QRCode.toDataURL(url, { margin: 1, width: 200, color: { dark: '#070b14', light: '#ffffff' } })
      .then(setSrc)
      .catch(() => setSrc(null))
  }, [url])
  return (
    <figure className="flex flex-col items-center gap-2">
      <div className="rounded-xl bg-white p-2">
        {src ? <img src={src} alt={`QR code: ${label}`} className="size-40" /> : <div className="size-40" />}
      </div>
      <figcaption className="max-w-48 break-all text-center font-mono text-[11px] text-muted">{url}</figcaption>
    </figure>
  )
}

const pickIp = (urls: string[]) => urls.find((u) => /\/\/\d+\.\d+\.\d+\.\d+/.test(u)) ?? urls[0]

export function ConnectPhone({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { state } = useServer()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const urls = state?.server.urls
  const camera = urls ? pickIp(urls.camera) : undefined
  const cert = urls?.ca_certificate[0]
  const mdns = urls?.camera.find((u) => u.includes('.local'))

  return (
    <dialog
      ref={ref} onClose={onClose}
      className="m-auto w-[min(760px,calc(100vw-2rem))] rounded-2xl border border-line bg-surface p-0 text-ink backdrop:bg-black/70 backdrop:backdrop-blur-sm"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="card-title flex items-center gap-2"><Smartphone className="size-4 text-accent" />Connect the iPhone camera</h2>
        <button type="button" className="btn btn-ghost px-2" onClick={onClose} aria-label="Close"><X className="size-4" /></button>
      </div>
      {!camera ? (
        <p className="p-6 text-sm text-muted">HTTPS is turned off on the server (HTTPS_PORT=0), and iOS only allows the camera over HTTPS.</p>
      ) : (
        <div className="grid gap-6 p-5 sm:grid-cols-2">
          <section className="space-y-3">
            <p className="eyebrow flex items-center gap-1.5"><ShieldCheck className="size-3" />Once: trust this server</p>
            {cert && <Qr url={cert} label="download certificate" />}
            <ol className="list-decimal space-y-1.5 pl-4 text-sm text-muted">
              <li>Join the <span className="text-ink">same WiFi</span> as this computer.</li>
              <li>Scan, then tap <span className="text-ink">Allow</span> to download the profile.</li>
              <li>Settings → General → VPN &amp; Device Management → <span className="text-ink">DynaBraille Local CA</span> → Install.</li>
              <li>Settings → General → About → Certificate Trust Settings → turn on <span className="text-ink">DynaBraille Local CA</span>.</li>
            </ol>
          </section>
          <section className="space-y-3">
            <p className="eyebrow flex items-center gap-1.5"><Smartphone className="size-3" />Every time: open the camera</p>
            <Qr url={camera} label="camera page" />
            <ol className="list-decimal space-y-1.5 pl-4 text-sm text-muted">
              <li>Scan with the Camera app and open it in Safari.</li>
              <li>Tap <span className="text-ink">Start camera</span> and allow camera access.</li>
              <li>Share → <span className="text-ink">Add to Home Screen</span> for one-tap launch.</li>
            </ol>
            {mdns && mdns !== camera && (
              <p className="text-xs text-faint">Also works: <span className="font-mono">{mdns}</span></p>
            )}
          </section>
        </div>
      )}
    </dialog>
  )
}
