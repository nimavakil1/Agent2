import argparse
import os
import asyncio
import logging
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
    load_dotenv(".env", override=True)

    url = os.getenv("LIVEKIT_URL")
    room_token = os.getenv("AGENT_ROOM_TOKEN")
    if not url or not room_token:
        raise RuntimeError("LIVEKIT_URL and AGENT_ROOM_TOKEN must be set (for standalone test)")

    room = rtc.Room()
    await room.connect(url, room_token)

    session = agents.AgentSession(
        stt=deepgram.STT(
            model="nova-2",
            detect_language=False,
            language=lang,
            smart_format=True,
            interim_results=True,
            api_key=os.getenv("DEEPGRAM_API_KEY"),
        ),
        llm=groq.LLM(model=os.getenv("GROQ_MODEL", "llama3-70b-8192"), temperature=0.4),
        tts=elevenlabs.TTS(
            model="eleven_flash_v2",
            api_key=os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY"),
        ),
        preemptive_generation=True,
    )

    voice = _voice_map_from_env().get(lang)
    if voice:
        try:
            session.tts.voice = voice  # type: ignore[attr-defined]
            logger.info("Selected TTS voice=%s for lang=%s", voice, lang)
        except Exception as e:
            logger.warning("Failed to set TTS voice: %s", e)

    agent = Agent(instructions=f"Always answer in {lang} with short, fast answers.")
    await session.start(room=room, agent=agent)

    logger.info("Agent2 minimal started. Speak in LiveKit room.")
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default=os.getenv("CONTACT_LANGUAGE_CODE", "en"))
    args = parser.parse_args()
    asyncio.run(run(args.lang))
