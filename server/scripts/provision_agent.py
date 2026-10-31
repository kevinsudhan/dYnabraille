"""Create or update the DynaBraille voice agent on ElevenLabs.

    cd server
    .venv\\Scripts\\python scripts\\provision_agent.py              # Windows
    .venv/bin/python scripts/provision_agent.py                    # macOS / Linux

Needs ELEVENLABS_API_KEY in server/.env. It creates (or updates, matched by name)
the client tools the web app implements, creates the agent - or updates the one in
ELEVENLABS_AGENT_ID - and writes the agent id back into server/.env. Safe to re-run
after editing the prompt below.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dynabraille.settings import ENV_FILE, SERVER_DIR, Settings  # noqa: E402

API = "https://api.elevenlabs.io"
AGENT_NAME = "DynaBraille Assistant"

FIRST_MESSAGE = "Hey, it's DynaBraille! How's your day going?"
TEMPERATURE = 0.7  # 0 made it sound stiff and scripted
# Seconds of silence before the agent re-engages ("are you still there?"). With the phone's
# hold-to-talk the user is quiet between presses, so keep it from nagging.
TURN_TIMEOUT = 30

PROMPT = """\
# Who you are
You are DynaBraille: a warm, easygoing friend who happens to be built into the user's
braille cell and phone camera. You are a companion first and a gadget second. You're
curious about the person, quick with a joke, honest, and genuinely glad to talk to them.

# Who you're talking with
A blind or low-vision person. They carry an iPhone whose camera faces forward and hold a
one-cell refreshable braille display: six pins that form one braille character at a time.
On the phone they hold a button while they speak; their words reach you through speech
recognition and your replies are read aloud, so expect the odd misheard word and ask if
something doesn't make sense.

# Talk about anything
- Chat like a friend would. Small talk, how their day went, jokes, stories, music, sport,
  films, food and recipes, trivia, homework, ideas, advice, learning braille, or just
  keeping them company: all of it is welcome.
- Never refuse a topic because it isn't about braille or the camera, and never say you can
  only help with braille. If you don't know something, say so the way a friend would.
- Be interested in them. Use their name once they tell you, remember what they said
  earlier in the conversation, and now and then ask a follow-up question. Don't end every
  reply with "anything else?".
- If they sound down or stressed, slow down, be kind and listen before offering ideas.
- You can't browse the internet, so for live news, scores or weather be upfront that you
  can't check right now instead of guessing.

# How you sound
Everything you say is spoken aloud. Talk naturally with contractions, keep most replies to
one to three sentences, and go longer only when they ask for a story, an explanation or a
list of ideas. Light humour is good; match their mood. No markdown, bullet points, emoji or
symbols.

# Your tools (use them whenever they help, not only when asked)
- get_surroundings: what the camera sees right now. Call it when they ask what's around
  them, what's in front of them, or about obstacles, and answer from it. Lead with what
  matters for moving safely (people, vehicles, things in their path). Use "on your left",
  "ahead", "on your right" and the distance hints.
- show_in_braille: spells text on the braille cell, about one second per letter, so keep it
  to a word or short phrase. Use it when they want something spelled, written or felt in
  braille, and feel free to offer it while chatting, for example to spell a new word or a
  name. Tell them what you're sending.
- set_camera_braille pauses or resumes automatic braille of the object in front of the
  camera, stop_braille clears the cell, and get_device_status answers questions about the
  cell's battery, connection or light level.
- You may get context messages about what the camera just noticed. Bring them up only if
  they matter, like something in their path. Don't interrupt a good conversation for them.
- If the camera isn't connected, say so and suggest opening the camera page on their iPhone.

# Keep them safe
- Object recognition only knows common objects and distances are rough. Never tell them a
  road or crossing is safe; for traffic, they should rely on their cane, guide dog or
  another person.
- If they mention an emergency, being hurt, or being in danger, tell them to call emergency
  services or someone nearby right away. For medical or legal questions, be supportive and
  share general information, and suggest checking with a professional for anything serious.
"""

TOOLS = [
    {
        "type": "client",
        "name": "get_surroundings",
        "description": ("Returns what the user's camera sees right now: a one-sentence summary and "
                        "each detected object with its position (left, ahead, right) and rough "
                        "distance. Call it whenever the user asks about their surroundings."),
        "expects_response": True,
        "response_timeout_secs": 10,
    },
    {
        "type": "client",
        "name": "show_in_braille",
        "description": ("Shows text on the user's handheld braille cell, one character at a time. "
                        "Use it when the user wants something spelled, written or shown in braille."),
        "expects_response": True,
        "response_timeout_secs": 10,
        "parameters": {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text": {"type": "string",
                         "description": "Short text to show, ideally one word or a short phrase."},
            },
        },
    },
    {
        "type": "client",
        "name": "stop_braille",
        "description": "Stops whatever the braille cell is showing and lowers all pins.",
        "expects_response": True,
        "response_timeout_secs": 10,
    },
    {
        "type": "client",
        "name": "set_camera_braille",
        "description": ("Turns automatic braille of the object in front of the camera on or off. "
                        "Use it when the user asks to pause, mute, resume or restart it."),
        "expects_response": True,
        "response_timeout_secs": 10,
        "parameters": {
            "type": "object",
            "required": ["enabled"],
            "properties": {
                "enabled": {"type": "boolean", "description": "true to turn it on, false to pause it."},
            },
        },
    },
    {
        "type": "client",
        "name": "get_device_status",
        "description": ("Returns whether the braille cell is connected, its battery level, signal "
                        "strength and ambient light level when available."),
        "expects_response": True,
        "response_timeout_secs": 10,
    },
]


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def check(response: httpx.Response, what: str) -> dict:
    if response.status_code >= 400:
        fail(f"{what} failed ({response.status_code}): {response.text[:800]}")
    return response.json()


def upsert_tools(client: httpx.Client) -> list[str]:
    existing: dict[str, str] = {}
    cursor = None
    while True:
        params = {"page_size": 100} | ({"cursor": cursor} if cursor else {})
        page = check(client.get("/v1/convai/tools", params=params), "listing tools")
        for tool in page.get("tools", []):
            existing.setdefault(tool["tool_config"]["name"], tool["id"])
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            break

    ids = []
    for config in TOOLS:
        name = config["name"]
        if name in existing:
            response = client.patch(f"/v1/convai/tools/{existing[name]}", json={"tool_config": config})
            if response.status_code < 400:
                ids.append(existing[name])
                print(f"  updated tool  {name}")
                continue
            print(f"  could not update {name} ({response.status_code}); creating a new one")
        created = check(client.post("/v1/convai/tools", json={"tool_config": config}), f"creating {name}")
        ids.append(created["id"])
        print(f"  created tool  {name}")
    return ids


def agent_body(settings: Settings, tool_ids: list[str], voice_id: str, overrides: bool) -> dict:
    prompt = {"prompt": PROMPT, "tool_ids": tool_ids, "temperature": TEMPERATURE}
    if settings.elevenlabs_llm:
        prompt["llm"] = settings.elevenlabs_llm
    platform = {"auth": {"enable_auth": True}}  # only our server can start conversations
    if overrides:
        # Typing-only sessions (dashboard chat, phone hold-to-talk), and no greeting when the
        # user's first words are already on their way.
        platform["overrides"] = {"conversation_config_override": {
            "conversation": {"text_only": True},
            "agent": {"first_message": True},
        }}
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {"first_message": FIRST_MESSAGE, "language": "en", "prompt": prompt},
            "tts": {"voice_id": voice_id},
            "turn": {"turn_timeout": TURN_TIMEOUT},
        },
        "platform_settings": platform,
    }


def save_agent_id(agent_id: str) -> None:
    if not ENV_FILE.exists():
        example = SERVER_DIR / ".env.example"
        ENV_FILE.write_text(example.read_text("utf-8") if example.exists() else "", "utf-8")
    text = ENV_FILE.read_text("utf-8")
    line = f"ELEVENLABS_AGENT_ID={agent_id}"
    if re.search(r"^ELEVENLABS_AGENT_ID=.*$", text, flags=re.M):
        text = re.sub(r"^ELEVENLABS_AGENT_ID=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV_FILE.write_text(text, "utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voice", help="ElevenLabs voice id (default: ELEVENLABS_VOICE_ID)")
    parser.add_argument("--new", action="store_true", help="create a new agent even if one is configured")
    args = parser.parse_args()

    settings = Settings()
    if not settings.elevenlabs_api_key:
        fail(f"set ELEVENLABS_API_KEY in {ENV_FILE} first")
    if not settings.elevenlabs_api_key.startswith("sk_"):
        fail("ELEVENLABS_API_KEY should start with 'sk_'. The long hex value on the API keys page is the "
             "key's ID; the key itself is shown once when you create or rotate it.")
    voice_id = args.voice or settings.elevenlabs_voice_id

    with httpx.Client(base_url=API, headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=30) as client:
        print("Tools:")
        tool_ids = upsert_tools(client)

        agent_id = None if args.new else settings.elevenlabs_agent_id
        for overrides in (True, False):
            body = agent_body(settings, tool_ids, voice_id, overrides)
            if agent_id:
                response = client.patch(f"/v1/convai/agents/{agent_id}", json=body)
            else:
                response = client.post("/v1/convai/agents/create", json=body)
            if response.status_code == 422 and overrides:
                print("  (text-only override not accepted; continuing without it)")
                continue
            data = check(response, "saving the agent")
            agent_id = agent_id or data["agent_id"]
            break

    save_agent_id(agent_id)
    print(f"\nAgent ready: {agent_id}")
    print(f"Saved ELEVENLABS_AGENT_ID to {ENV_FILE}. Restart the server to use it.")


if __name__ == "__main__":
    main()
