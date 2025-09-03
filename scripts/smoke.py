import os
import sys
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

DG = os.getenv("DEEPGRAM_API_KEY")
EL = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
EL_BASE = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")
GQ = os.getenv("GROQ_API_KEY")

voices = {
    "en": os.getenv("ELEVENLABS_VOICE_EN"),
    "fr": os.getenv("ELEVENLABS_VOICE_FR_BE"),
    "de": os.getenv("ELEVENLABS_VOICE_DE_DE"),
    "nl": os.getenv("ELEVENLABS_VOICE_NL_BE") or os.getenv("ELEVENLABS_VOICE_NL_NL"),
}
lang = (os.getenv("CONTACT_LANGUAGE_CODE") or "en").lower()
if lang not in voices:
    lang = "en"

print("== Provider checks ==")

async def main():
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Groq models
        if not GQ:
            print("Groq: missing key");
        else:
            r = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {GQ}"},
            )
            print("Groq:", r.status_code)

        # Deepgram
        if not DG:
            print("Deepgram: missing key")
        else:
            r = await client.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {DG}"},
            )
            print("Deepgram:", r.status_code)

        # ElevenLabs user and voices
        if not EL:
            print("ElevenLabs: missing key")
        else:
            u = await client.get(
                f"{EL_BASE}/v1/user",
                headers={"xi-api-key": EL},
            )
            print("ElevenLabs:", u.status_code)
            v = await client.get(
                f"{EL_BASE}/v1/voices",
                headers={"xi-api-key": EL},
            )
            data = v.json()
            by_id = {vv["voice_id"]: vv for vv in data.get("voices", [])}
            chosen = voices[lang]
            print(f"Language={lang} voice_id={chosen}")
            if not chosen:
                print("Voice not set for language; set ELEVENLABS_VOICE_* in .env")
                return
            info = by_id.get(chosen)
            if not info:
                print("Voice id not found in your 'My Voices' — add it in ElevenLabs and retry")
                return
            print("Voice name:", info.get("name"))

            # TTS dry-run: synthesize to WAV file
            text = f"This is a quick test in {lang}. Your selected voice should play."
            tts = await client.post(
                f"{EL_BASE}/v1/text-to-speech/{chosen}",
                headers={"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"},
                json={"text": text, "model_id": "eleven_flash_v2"},
            )
            if tts.status_code != 200:
                print("TTS failed:", tts.status_code, tts.text)
                return
            out = ROOT / "out.mp3"
            out.write_bytes(tts.content)
            print("Wrote:", out)

if __name__ == "main__":
    pass

import asyncio
asyncio.run(main())
