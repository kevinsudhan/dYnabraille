# iPhone camera setup

The iPhone is the camera, and it's also the microphone and speaker for announcements and the
voice assistant (through its loudspeaker, or AirPods / Bluetooth headphones when connected). It runs a web page from the DynaBraille server, so there's no app to
install.

iOS only allows the camera on **HTTPS** pages. The server makes its own small certificate
authority the first time it runs. Installing that certificate on the iPhone **once** lets
Safari trust the server.

## 1. Same network

Put the PC running the server and the iPhone on the same WiFi. To use the iPhone's hotspot,
join the PC and the ESP32 to the hotspot instead.

When Windows asks whether Python may use the network, allow **Private networks**. If you
missed the prompt: Windows Security → Firewall & network protection → Allow an app through
firewall → Python → Private.

## 2. Trust the server (once)

1. On the dashboard, click **Connect iPhone** and scan the left QR code. Or open
   `http://<PC-IP>:8000/ca.crt` in Safari; the server prints the address when it starts.
2. Tap **Allow** to download the configuration profile.
3. **Settings → General → VPN & Device Management** → *DynaBraille Local CA* → **Install**.
4. **Settings → General → About → Certificate Trust Settings** → turn on
   **DynaBraille Local CA**.

The certificate is only valid for this PC's DynaBraille server. If you delete
`server/data/certs/`, a new CA is created and you have to repeat this step.

## 3. Open the camera page

Scan the right QR code, or open `https://<PC-IP>:8443/camera`.
`https://dynabraille.local:8443/camera` also works and survives the PC's IP changing.

Tap **Start camera** and allow camera access. That tap also unlocks audio, which iOS requires.
Then:

- Use **Share → Add to Home Screen** for a full-screen, one-tap launcher.
- Keep the page in front with the screen on. iOS pauses the camera when the screen locks or
  Safari goes to the background. The page asks iOS to keep the screen awake while streaming.

The page sends 640-pixel JPEG frames, one at a time, at up to about 15 per second. The top
bar shows frames per second and the round-trip time.

## Buttons on the phone

- **Capture scene:** the same as the tactile button. The current frame is analysed, the
  objects are spelled on the cell, and the summary is read out.
- **Hold to talk:** hold the big button, say anything, let go. Your words are transcribed and
  the assistant answers out loud through the speaker or your headphones. You'll hear a rising
  tone when the mic opens and a falling one when it closes. Hold again to interrupt; a quick
  tap stops it talking. With **VoiceOver**, double-tap and hold, talk, then let go.
- **Repeat on cell:** plays the last word again.
- **Speech on/off:** mutes announcements on this phone.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "This Connection Is Not Private" | Step 2 isn't finished. The trust switch in Certificate Trust Settings is the step people miss |
| Page loads but "stream" never turns green | Same fix: Safari blocks secure WebSockets to untrusted certificates |
| "Camera access was denied" | Settings → Safari → Camera → Allow, then reload |
| Can't reach the page at all | Same WiFi? Windows firewall allowed? Try the IP address instead of `.local` |
| No sound | Tap Start camera or Capture once (iOS needs a tap first). Speech plays even with the silent switch on (iOS 17+); check the volume and that Speech is on |
| "Microphone access is blocked" | Settings → Safari → Microphone → Allow, then reload |
| Hold to talk says "Microphone ready" and stops | That first press was the permission prompt. Hold the button again |
| The reply is quiet / comes from the earpiece | Update iOS. The page releases the mic before replying so audio goes to the loudspeaker |
| Low fps | Move closer to the router. YOLO runs on the PC's CPU at about 50 ms per frame |
