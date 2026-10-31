"""End-to-end over the real WebSocket endpoints, with a scripted fake ESP32."""
import json

import pytest
from fastapi.testclient import TestClient

from dynabraille.app import create_app
from dynabraille.controller import Controller
from dynabraille.settings import PreferenceStore, Settings

TOKEN = "test-token"


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, https_port=0, mdns_enabled=False, vision_enabled=False,
                        device_token=TOKEN, web_dist=tmp_path / "no-web")
    prefs = PreferenceStore(tmp_path / "prefs.json")
    prefs.update({"char_ms": 150, "gap_ms": 60})
    app = create_app(settings, Controller(settings, prefs))
    with TestClient(app) as c:
        yield c


def next_of(ws, kind, limit=60):
    for _ in range(limit):
        message = json.loads(ws.receive_text())
        if message["type"] == kind:
            return message
    raise AssertionError(f"no {kind} message")


def test_health_and_state(client):
    assert client.get("/api/health").json()["ok"]
    state = client.get("/api/state").json()
    assert state["devices"] == [] and state["assistant"]["ready"] is False


def test_device_with_wrong_token_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/device?token=nope&id=x") as ws:
            ws.receive_text()


def test_show_text_reaches_device_and_progress_reaches_ui(client):
    with client.websocket_connect("/ws/ui?role=dashboard") as ui, \
            client.websocket_connect(f"/ws/device?token={TOKEN}&id=cell-1") as dev:
        next_of(ui, "snapshot")
        assert json.loads(dev.receive_text())["type"] == "welcome"
        dev.send_text(json.dumps({"type": "hello", "device_id": "cell-1", "fw": "2.0.0",
                                  "name": "Bench cell", "features": {"button": True}}))
        devices = next_of(ui, "devices")["devices"]
        while not devices or devices[0]["fw"] != "2.0.0":
            devices = next_of(ui, "devices")["devices"]
        assert devices[0]["transport"] == "wifi"

        job = client.post("/api/braille/show", json={"text": "Cup"}).json()
        show = json.loads(dev.receive_text())
        assert show["type"] == "show" and show["id"] == job["id"]
        assert show["cells"] == [32, 9, 37, 15]  # capital sign, c, u, p
        assert show["char_ms"] == 150

        dev.send_text(json.dumps({"type": "progress", "id": job["id"], "index": 2}))
        dev.send_text(json.dumps({"type": "dots", "mask": 37}))
        assert next_of(ui, "braille.progress")["index"] == 2
        assert next_of(ui, "braille.dots")["mask"] == 37
        dev.send_text(json.dumps({"type": "done", "id": job["id"], "cancelled": False}))
        assert next_of(ui, "braille.done")["cancelled"] is False

        # double press replays the last word on the device
        dev.send_text(json.dumps({"type": "button", "event": "double"}))
        replay = json.loads(dev.receive_text())
        assert replay["type"] == "show" and replay["cells"] == show["cells"] and replay["id"] > job["id"]

        # a long press toggles camera braille and is announced
        before = client.get("/api/prefs").json()["auto_braille"]
        dev.send_text(json.dumps({"type": "button", "event": "long"}))
        assert next_of(ui, "prefs")["prefs"]["auto_braille"] is (not before)
        assert next_of(ui, "speak")["intent"] == "notice"


def test_usb_duplicate_of_wifi_device_is_ignored(client):
    ctl = client.app.state.controller
    sent = []

    async def usb_send(message):
        sent.append(message)

    with client.websocket_connect(f"/ws/device?token={TOKEN}&id=cell-3") as dev:
        dev.receive_text()
        ctl.devices.attach("cell-3", "usb", usb_send)
        session = ctl.devices.sessions["cell-3"]
        assert session.transport == "wifi" and session.links.keys() == {"wifi", "usb"}
        client.post("/api/device/test", json={"dot": 1})
        assert json.loads(dev.receive_text())["type"] == "test"
        assert sent == []  # commands only go over the preferred link


def test_simulated_cell_when_no_device(client):
    with client.websocket_connect("/ws/ui") as ui:
        next_of(ui, "snapshot")
        client.post("/api/braille/show", json={"text": "ab"})
        assert next_of(ui, "braille.job")["job"]["text"] == "ab"
        assert next_of(ui, "braille.progress")["index"] == 0
        assert next_of(ui, "braille.dots")["mask"] == 1
        last = next_of(ui, "braille.done")
        assert last["cancelled"] is False
        assert client.get("/api/state").json()["rest"] is True  # cell back at rest


def test_test_dot_and_manual_cell(client):
    with client.websocket_connect(f"/ws/device?token={TOKEN}&id=cell-2") as dev:
        dev.receive_text()  # welcome
        client.post("/api/device/test", json={"dot": 4})
        assert json.loads(dev.receive_text()) == {"type": "test", "dot": 4, "ms": 600}
        client.post("/api/braille/cell", json={"dots": [1, 2, 5]})
        assert json.loads(dev.receive_text())["mask"] == 0b10011
    assert client.post("/api/device/test", json={"dot": 9}).status_code == 422


def test_camera_frames_without_detector(client):
    import cv2
    import numpy as np

    ok, jpeg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))
    with client.websocket_connect("/ws/camera") as cam:
        cam.send_bytes((7).to_bytes(4, "big") + jpeg.tobytes())
        result = json.loads(cam.receive_text())
    assert result == {"type": "result", "seq": 7, "detections": [], "focus": None, "infer_ms": 0.0}
    assert client.get("/api/vision/frame.jpg").content == jpeg.tobytes()
    assert "isn't ready" in client.get("/api/scene").json()["summary"]


def test_assistant_requires_configuration(client):
    response = client.get("/api/assistant/session")
    assert response.status_code == 503
    assert "ELEVENLABS" in response.json()["detail"]


def test_hold_to_talk_transcribes_the_recording(client, monkeypatch):
    seen = {}

    async def fake_stt(audio, content_type):
        seen.update(size=len(audio), type=content_type)
        return "what's around me"

    monkeypatch.setattr(client.app.state.controller.elevenlabs, "stt", fake_stt)
    response = client.post("/api/stt", content=b"\0" * 5000, headers={"Content-Type": "audio/mp4"})
    assert response.json() == {"text": "what's around me"}
    assert seen == {"size": 5000, "type": "audio/mp4"}

    assert client.post("/api/stt", content=b"", headers={"Content-Type": "audio/mp4"}).status_code == 422


def test_hold_to_talk_needs_an_api_key(client):
    response = client.post("/api/stt", content=b"\0" * 5000, headers={"Content-Type": "audio/mp4"})
    assert response.status_code == 503
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]


def test_capture_button_brailles_and_speaks_objects(client):
    """Short press on the tactile button: freeze the frame, detect, spell and speak it."""
    import cv2
    import numpy as np

    from dynabraille.scene import Detection

    ctl = client.app.state.controller
    vision = ctl.vision
    vision.detector_state = "ready"

    async def fake_detect(jpeg, min_confidence):
        return [Detection("person", 0.9, (0.0, 0.3, 0.2, 0.9)),
                Detection("cell phone", 0.8, (0.4, 0.4, 0.5, 0.5)),
                Detection("person", 0.9, (0.3, 0.1, 0.7, 0.95))], 12.0

    vision.detect = fake_detect
    ok, jpeg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))

    with client.websocket_connect("/ws/ui") as ui,             client.websocket_connect(f"/ws/device?token={TOKEN}&id=cell-9") as dev,             client.websocket_connect("/ws/camera") as cam:
        next_of(ui, "snapshot")
        dev.receive_text()  # welcome
        cam.send_bytes((1).to_bytes(4, "big") + jpeg.tobytes())
        cam.receive_text()

        dev.send_text(json.dumps({"type": "button", "event": "short"}))
        capture = next_of(ui, "scene.capture")["capture"]
        assert capture["braille_text"] == "2 people, phone"  # nearest first, short braille words
        assert capture["summary"].startswith("I can see 2 people and a cell phone.")
        show = json.loads(dev.receive_text())
        assert show["type"] == "show" and len(show["cells"]) == len("#b people, phone")
        speak = next_of(ui, "speak")
        assert speak["intent"] == "capture" and speak["text"] == capture["summary"]
    assert client.get("/api/vision/capture.jpg").content == jpeg.tobytes()


def test_capture_without_camera_is_explained(client):
    response = client.post("/api/scene/capture")
    assert response.status_code == 409
    assert "camera" in response.json()["detail"].lower()


def test_power_solenoids_uses_the_cells_own_layout(client):
    """S1 S2 / S3 S4 / S5 S6 build, unpowered = pin up: powering 2,4,5,6 leaves dots 1+2 up ("b")."""
    with client.websocket_connect(f"/ws/device?token={TOKEN}&id=cell-7") as dev:
        dev.receive_text()  # welcome
        dev.send_text(json.dumps({"type": "hello", "device_id": "cell-7", "fw": "2.2.0",
                                  "dot_to_solenoid": [1, 3, 5, 2, 4, 6], "solenoid_on_raises": False}))
        client.get("/api/state")  # let the hello land
        r = client.post("/api/device/solenoids", json={"on": [2, 4, 5, 6], "hold_ms": 2000})
        assert r.status_code == 200
        assert json.loads(dev.receive_text()) == {"type": "cell", "mask": 0b000011, "hold_ms": 2000}
        client.post("/api/device/solenoids", json={"on": [1, 2, 3, 4, 5, 6]})
        assert json.loads(dev.receive_text())["mask"] == 0  # all powered = blank cell
        client.post("/api/device/solenoids", json={"on": []})
        assert json.loads(dev.receive_text()) == {"type": "stop"}
    assert client.post("/api/device/solenoids", json={"on": [7]}).status_code == 409  # no cell now


def test_power_settings_are_sent_on_connect_and_on_change(client):
    with client.websocket_connect(f"/ws/device?token={TOKEN}&id=cell-8") as dev:
        dev.receive_text()  # welcome
        assert client.patch("/api/prefs", json={"hold_duty": 45, "pull_in_ms": 80}).status_code == 200
        assert json.loads(dev.receive_text()) == {"type": "config", "hold_duty": 45, "pull_in_ms": 80}
        dev.send_text(json.dumps({"type": "hello", "device_id": "cell-8", "fw": "2.3.0", "hold_duty": 50}))
        assert json.loads(dev.receive_text()) == {"type": "config", "hold_duty": 45, "pull_in_ms": 80}
    assert client.patch("/api/prefs", json={"hold_duty": 5}).status_code == 422  # out of range
