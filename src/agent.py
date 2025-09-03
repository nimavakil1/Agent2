import argparse
import os
import asyncio
import logging
import aiohttp
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent
from livekit.plugins import deepgram, elevenlabs, groq

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

    # Create an HTTP session because we're not running under the worker context
    http = aiohttp.ClientSession()

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
        llm=groq.LLM(model=os.getenv("GROQ_MODEL", "llama3-70b-8192"), temperature=0.4),
        tts=elevenlabs.TTS(
            model="eleven_flash_v2",
            api_key=os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY"),
            http_session=http,
        ),
        preemptive_generation=True,
    )

    # Choose voice: env override (from UI) takes precedence, then per-language mapping
    voice = (os.getenv("ELEVENLABS_VOICE_ID") or "").strip() or _voice_map_from_env().get(lang)
    if voice:
        # Try both properties (some plugin versions expect name vs id)
        tts = session.tts
        ok_any = False
        try:
            tts.voice = voice  # type: ignore[attr-defined]
            ok_any = True
            logger.info("Applied TTS voice via .voice=%s", voice)
        except Exception as e:
            logger.warning("Setting .voice failed: %s", e)
        try:
            setattr(tts, "voice_id", voice)  # type: ignore[attr-defined]
            ok_any = True
            logger.info("Applied TTS voice via .voice_id=%s", voice)
        except Exception as e:
            logger.warning("Setting .voice_id failed: %s", e)
        logger.info("Selected TTS voice=%s for lang=%s (ok_any=%s)", voice, lang, ok_any)

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
