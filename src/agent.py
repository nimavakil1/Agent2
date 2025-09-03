import argparse
import os
import asyncio
import logging
import aiohttp
import httpx
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent
from livekit.agents import vad as lk_vad
from livekit.plugins import deepgram, elevenlabs
from livekit.plugins import openai as openai_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent2")


def _voice_map_from_env():
    return {
        "en": os.getenv("ELEVENLABS_VOICE_EN"),
        "fr": os.getenv("ELEVENLABS_VOICE_FR_BE"),
        "de": os.getenv("ELEVENLABS_VOICE_DE_DE"),
        "nl": (os.getenv("ELEVENLABS_VOICE_NL_BE") or os.getenv("ELEVENLABS_VOICE_NL_NL")),
    }


async def run(lang: str):
    # Load .env without overriding values passed from the UI (e.g., ELEVENLABS_VOICE_ID)
    load_dotenv(".env", override=False)

    url = os.getenv("LIVEKIT_URL")
    room_token = os.getenv("AGENT_ROOM_TOKEN")
    if not url or not room_token:
        raise RuntimeError("LIVEKIT_URL and AGENT_ROOM_TOKEN must be set (for standalone test)")

    room = rtc.Room()
    await room.connect(url, room_token)

    # Choose voice id up-front and expose via env for plugins that read it at init
    sel_voice_id = (os.getenv("ELEVENLABS_VOICE_ID") or "").strip() or _voice_map_from_env().get(lang)
    if sel_voice_id:
        os.environ["ELEVENLABS_VOICE_ID"] = sel_voice_id

    # Create an HTTP session because we're not running under the worker context
    http = aiohttp.ClientSession()

    # Instantiate a VAD for talk-over/interruptions (WebRTC if available)
    vad_inst = None
    try:
        # Prefer WebRTC VAD if present; fallback is None (library still runs)
        vad_inst = getattr(lk_vad, "WebRTC", None)() if getattr(lk_vad, "WebRTC", None) else None
    except Exception:
        vad_inst = None

    session = agents.AgentSession(
        stt=deepgram.STT(
            model="nova-2",
            detect_language=False,
            language=lang,
            smart_format=True,
            interim_results=True,
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            http_session=http,
        ),
        # TEMP: switch LLM to OpenAI to rule out LLM affecting voice behavior
        llm=openai_llm.LLM(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.4,
        ),
        tts=elevenlabs.TTS(
            model="eleven_flash_v2",
            api_key=os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY"),
            http_session=http,
        ),
        preemptive_generation=True,
        vad=vad_inst,
    )

    # Choose voice: env override (from UI) takes precedence, then per-language mapping
    voice_id = os.getenv("ELEVENLABS_VOICE_ID") or sel_voice_id
    if voice_id:
        # Resolve voice name from ElevenLabs API to satisfy plugins expecting names
        voice_name = None
        el_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
        el_base = (os.getenv("ELEVENLABS_BASE_URL") or "https://api.elevenlabs.io").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10.0) as hc:
                r = await hc.get(f"{el_base}/v1/voices", headers={"xi-api-key": el_key or ""})
                if r.status_code == 200:
                    js = r.json();
                    for v in js.get("voices", []):
                        if v.get("voice_id") == voice_id:
                            voice_name = v.get("name"); break
        except Exception as e:
            logger.warning("Failed to resolve ElevenLabs voice name: %s", e)

        tts = session.tts
        applied = []
        # Try setting by name first (if found), then by id, then id property
        if voice_name:
            try:
                tts.voice = voice_name  # type: ignore[attr-defined]
                applied.append(f"voice(name)={voice_name}")
            except Exception as e:
                logger.warning("Setting .voice(name) failed: %s", e)
        try:
            tts.voice = voice_id  # type: ignore[attr-defined]
            applied.append(f"voice(id)={voice_id}")
        except Exception as e:
            logger.warning("Setting .voice(id) failed: %s", e)
        try:
            setattr(tts, "voice_id", voice_id)  # type: ignore[attr-defined]
            applied.append(f"voice_id={voice_id}")
        except Exception as e:
            logger.warning("Setting .voice_id property failed: %s", e)
        logger.info("Selected TTS voice id=%s name=%s for lang=%s (applied=%s)", voice_id, voice_name, lang, ",".join(applied) or "none")

    agent = Agent(instructions=f"Always answer in {lang} with short, fast answers.")
    await session.start(room=room, agent=agent)
    # Emit a short, fixed phrase so you can verify the actual voice by ear
    session.generate_reply(instructions="Voice check: This is the configured ElevenLabs voice speaking.")

    logger.info("Agent2 minimal started. Speak in LiveKit room.")
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await http.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default=os.getenv("CONTACT_LANGUAGE_CODE", "en"))
    args = parser.parse_args()
    asyncio.run(run(args.lang))
