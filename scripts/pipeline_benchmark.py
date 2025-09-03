import os
import time
from pathlib import Path
import json

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

DG = os.getenv("DEEPGRAM_API_KEY")
GQ = os.getenv("GROQ_API_KEY")
EL = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
EL_BASE = (os.getenv("ELEVENLABS_BASE_URL") or "https://api.elevenlabs.io").rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-70b-8192")

voices = {
    "en": os.getenv("ELEVENLABS_VOICE_EN"),
    "fr": os.getenv("ELEVENLABS_VOICE_FR_BE"),
    "de": os.getenv("ELEVENLABS_VOICE_DE_DE"),
    "nl": os.getenv("ELEVENLABS_VOICE_NL_BE") or os.getenv("ELEVENLABS_VOICE_NL_NL"),
}

LANG_TEXT = {
    "en": "Hello, I have a question about receipt rolls.",
    "fr": "Bonjour, j'ai une question sur les rouleaux de reçus.",
    "de": "Hallo, ich habe eine Frage zu Kassenrollen.",
    "nl": "Hallo, ik heb een vraag over kassarollen.",
}

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--lang", default="en")
parser.add_argument("--runs", type=int, default=3)
args = parser.parse_args()
lang = args.lang.lower()

async def ensure_input_mp3(client: httpx.AsyncClient, lang: str) -> Path:
    """Create a short mp3 utterance to feed STT (one-time)."""
    out = ROOT / f"in-{lang}.mp3"
    if out.exists():
        return out
    voice = voices.get(lang)
    if not EL or not voice:
        # Fall back to English if missing
        v = voices.get("en")
        text = LANG_TEXT.get(lang, LANG_TEXT["en"])
        r = await client.post(
            f"{EL_BASE}/v1/text-to-speech/{(voice or v)}",
            headers={"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"},
            json={"text": text, "model_id": "eleven_flash_v2"},
        )
    else:
        r = await client.post(
            f"{EL_BASE}/v1/text-to-speech/{voice}",
            headers={"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"},
            json={"text": LANG_TEXT.get(lang, LANG_TEXT["en"]), "model_id": "eleven_flash_v2"},
        )
    r.raise_for_status()
    out.write_bytes(r.content)
    return out

async def stt_deepgram_rest(client: httpx.AsyncClient, mp3_path: Path, lang: str) -> tuple[float, str]:
    """Measure Deepgram REST transcription time and return (ms, transcript)."""
    url = f"https://api.deepgram.com/v1/listen?model=nova-2&language={lang}&smart_format=true"
    headers = {"Authorization": f"Token {DG}", "Content-Type": "audio/mpeg"}
    t0 = time.perf_counter()
    with mp3_path.open("rb") as f:
        r = await client.post(url, headers=headers, content=f.read())
    dt = (time.perf_counter() - t0) * 1000
    if r.status_code != 200:
        raise RuntimeError(f"STT failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    # Deepgram response structure
    try:
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    except Exception:
        transcript = json.dumps(data)[:200]
    return dt, transcript

async def llm_groq(client: httpx.AsyncClient, text: str) -> tuple[float, str]:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GQ}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Answer in under 15 words, very fast."},
            {"role": "user", "content": text},
        ],
        "temperature": 0.4,
    }
    t0 = time.perf_counter()
    r = await client.post(url, headers=headers, json=payload)
    dt = (time.perf_counter() - t0) * 1000
    if r.status_code != 200:
        raise RuntimeError(f"LLM failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    reply = data["choices"][0]["message"]["content"].strip()
    return dt, reply

async def tts_stream(client: httpx.AsyncClient, voice_id: str, text: str, out: Path) -> tuple[float, float]:
    url = f"{EL_BASE}/v1/text-to-speech/{voice_id}/stream"
    headers = {"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"}
    payload = {"text": text, "model_id": "eleven_flash_v2"}
    t0 = time.perf_counter()
    ttft = None
    total = None
    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        if resp.status_code != 200:
            body = await resp.aread()
            raise RuntimeError(f"TTS stream failed: {resp.status_code} {body[:200]!r}")
        with out.open("wb") as f:
            async for chunk in resp.aiter_bytes():
                if chunk:
                    if ttft is None:
                        ttft = (time.perf_counter() - t0) * 1000
                    f.write(chunk)
            total = (time.perf_counter() - t0) * 1000
    return ttft or 0.0, total or 0.0

async def one_run(client: httpx.AsyncClient, lang: str) -> None:
    mp3 = await ensure_input_mp3(client, lang)
    stt_ms, transcript = await stt_deepgram_rest(client, mp3, lang)
    llm_ms, reply = await llm_groq(client, transcript or "Say hello")
    voice = voices.get(lang) or voices.get("en")
    ttft_ms, tts_ms = await tts_stream(client, voice, reply, ROOT / f"out-pipeline-{lang}.mp3")
    total = stt_ms + llm_ms + tts_ms
    print(f"{lang}: STT={stt_ms:.0f} ms, LLM={llm_ms:.0f} ms, TTS_TTFT={ttft_ms:.0f} ms, TTS_total={tts_ms:.0f} ms, TOTAL={total:.0f} ms -> out-pipeline-{lang}.mp3")

async def main():
    if not (DG and GQ and EL):
        print("Missing keys: ensure DEEPGRAM_API_KEY, GROQ_API_KEY, ELEVENLABS_API_KEY are set in .env")
        return
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(args.runs):
            await one_run(client, lang)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
