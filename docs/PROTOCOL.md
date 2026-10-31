# Protocol reference

Braille cells are 6-bit masks: bit 0 = dot 1 … bit 5 = dot 6, the same bit order as Unicode
braille, so `chr(0x2800 + mask)` renders the cell. Dot numbers are always **braille** numbers.
The firmware maps them onto solenoids.

## ESP32 ↔ server

WiFi: `ws://<server>:8000/ws/device?token=<DEVICE_TOKEN>&id=<device id>`, JSON text frames.
USB serial: the same JSON, one message per line at 115200 baud. Lines starting with `#` are logs.

### Server → device

| Message | Meaning |
|---|---|
| `{"type":"welcome","proto":2}` | Sent on connect |
| `{"type":"show","id":7,"cells":[32,9,37,15],"char_ms":900,"gap_ms":250}` | Play the cells one after another: letter → gap (rest) → … → rest |
| `{"type":"cell","mask":5,"hold_ms":4000}` | Show one cell (or `"dots":[1,3]`), then rest after the hold time (at most `STATIC_HOLD_MS`) |
| `{"type":"test","dot":4,"ms":600}` | Power only the solenoid under braille dot 4 (or `"solenoid":2`, your numbering) |
| `{"type":"selftest"}` | S1…S6 on/off, one at a time |
| `{"type":"replay"}` / `{"type":"stop"}` | Play the last word again / stop and rest |
| `{"type":"config","char_ms":900,"gap_ms":250,"hold_duty":50,"pull_in_ms":60}` | Default timing and the solenoid power budget (any subset). The server sends its stored `hold_duty` / `pull_in_ms` right after every `hello` |
| `{"type":"light","mode":"auto"\|"on"\|"off"}` | Light aid |
| `{"type":"status"}` / `{"type":"ping","t":1}` | Ask for a status / a pong |
| `{"type":"braille","dots":[1,2]}`, `{"type":"character",...}` | v1 commands, same as `cell` |

### Device → server

| Message | Meaning |
|---|---|
| `{"type":"hello","device_id","name","fw","dots":6,"max_on_ms","rest_mask","dot_to_solenoid":[1,3,5,2,4,6],"solenoid_on_raises":false,"hold_duty":50,"pull_in_ms":60,"pwm":true,"features":{...}}` | After connecting (or when the server sends `{"type":"hello"}` over USB) |
| `{"type":"status","mask","rest","energized","rssi","ip","uptime_ms","heap","lux","light_aid","battery_v","battery_pct","hold_duty","pull_in_ms"}` | Every 5 s |
| `{"type":"dots","mask":37,"rest":false}` | The dots felt right now changed |
| `{"type":"progress","id":7,"index":2,"count":4}` | Started cell `index` of job `id` |
| `{"type":"done","id":7,"cancelled":false}` | Job finished or was replaced |
| `{"type":"button","event":"short"\|"double"\|"long"}` | Tactile button |
| `{"type":"error","message":"..."}` | e.g. the on-time safety limit was hit |

## iPhone camera → server

`wss://<server>:8443/ws/camera`. Each binary message is a 4-byte big-endian sequence
number followed by one JPEG. The server replies with text:

```json
{"type":"result","seq":12,"infer_ms":54.1,"focus":{...},
 "detections":[{"label":"bus","confidence":0.94,"box":[x1,y1,x2,y2],"position":"ahead","distance":"very close"}]}
```

Boxes are normalised (0–1). The page sends the next frame only after the reply (or after a
2 s timeout), so frames never pile up.

## Browser live events

`/ws/ui?role=dashboard|phone`. The first message is a `snapshot` of the whole state, then:
`devices`, `vision.status`, `vision.detections`, `scene.focus`, `scene.capture`,
`braille.job`, `braille.progress`, `braille.dots`, `braille.done`, `prefs`, `button`,
`event` (activity log), `clients` and `speak`.

`speak` (`{"text","intent":"announce"|"capture"|"describe"|"notice"}`) goes to phone pages if
one is connected, otherwise to dashboards, so speech only comes out of one device.

## REST

Interactive docs at `http://localhost:8000/docs`. The main endpoints:

| | |
|---|---|
| `POST /api/scene/capture` | Capture, braille and speak (the button) |
| `GET /api/scene` | Current scene report (what the `get_surroundings` tool returns) |
| `POST /api/braille/show` `{text}` · `/cell` `{dots}` · `/stop` · `/replay` | Braille output |
| `GET /api/braille/preview?text=` | Cells for a text, without sending them |
| `POST /api/device/test` `{dot}` · `/selftest` · `/light` · `/button?event=` | Hardware |
| `POST /api/device/solenoids` `{on:[1,2,3], hold_ms}` | Power exactly these solenoids (hardware numbering) together, e.g. to test the supply |
| `GET/PATCH /api/prefs` | Timing, continuous mode, announcements, confidence, `hold_duty`, `pull_in_ms` |
| `GET /api/assistant/session?connection=webrtc\|websocket` | Short-lived ElevenLabs credentials |
| `POST /api/tts` `{text}` | MP3 from ElevenLabs (cached) |
| `POST /api/stt` (raw audio body, e.g. `audio/mp4`) | Transcript of one hold-to-talk recording: `{"text": "..."}` |
| `GET /api/vision/stream` · `/frame.jpg` · `/capture.jpg` | MJPEG live view and stills |
| `GET /ca.crt` | Local CA certificate for the iPhone |

## Hold to talk (phone)

```
press      mic opens (getUserMedia), a text session with the agent starts connecting
release    mic closes → POST /api/stt (ElevenLabs Scribe) → transcript sent to the agent
reply      agent text → POST /api/tts → played through the phone's media output
```

The mic is only open while the button is held. Releasing it before the reply plays matters on
iOS: while a page holds the microphone, audio is routed like a phone call (quiet earpiece);
once it's released, replies play through the loudspeaker or connected headphones. A session
that stays quiet for two minutes is closed; the next press opens a new one and sends the
recent conversation as context, so the agent picks up where it left off.
