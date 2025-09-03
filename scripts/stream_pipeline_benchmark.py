import os
import time
import json
from pathlib import Path

import aiohttp
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

DG = os.getenv("DEEPGRAM_API_KEY")
GQ = os.getenv("GROQ_API_KEY")
EL = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
EL_BASE = (os.getenv("ELEVENLABS_BASE_URL") or "https://api.elevenlabs.io").rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

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
    out = ROOT / f"in-{lang}.mp3"
    if out.exists():
        return out
    voice = voices.get(lang) or voices.get("en")
    text = LANG_TEXT.get(lang, LANG_TEXT["en"])
    r = await client.post(
        f"{EL_BASE}/v1/text-to-speech/{voice}",
        headers={"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"},
        json={"text": text, "model_id": "eleven_flash_v2"},
    )
    r.raise_for_status()
    out.write_bytes(r.content)
    return out

async def stt_deepgram_stream(mp3_path: Path, lang: str) -> tuple[float, float, str]:
    """Stream mp3 to Deepgram WS, return (ttft_ms, total_ms, transcript)."""
    url = f"wss://api.deepgram.com/v1/listen?model=nova-2&language={lang}&interim_results=true&smart_format=false&encoding=mp3"
    headers = {"Authorization": f"Token {DG}"}
    ttft = None
    t0 = time.perf_counter()
    transcript = ""
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, headers=headers, timeout=30) as ws:
            # send audio in chunks
            data = mp3_path.read_bytes()
            chunk = 32_000  # bytes
            for i in range(0, len(data), chunk):
                await ws.send_bytes(data[i : i + chunk])
            await ws.send_json({"type": "CloseStream"})

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        evt = json.loads(msg.data)
                    except Exception:
                        continue
                    # look for transcript in channel alternatives
                    ch = (evt.get("channel") or {})
                    alt = (ch.get("alternatives") or [{}])[0]
                    text = alt.get("transcript") or ""
                    is_final = bool((evt.get("is_final") or False))
                    if text:
                        transcript = text
                        if ttft is None:
                            ttft = (time.perf_counter() - t0) * 1000
                        if is_final:
                            total = (time.perf_counter() - t0) * 1000
                            return ttft, total, transcript
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    # ignore
                    pass
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break
    # fallback if no final
    total = (time.perf_counter() - t0) * 1000
    return ttft or total, total, transcript

async def llm_groq_stream(client: httpx.AsyncClient, prompt: str) -> tuple[float, float, str]:
    """Stream Groq chat completions, return (ttft_ms, total_ms, text)."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GQ}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "Answer in under 15 words, very fast."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "stream": True,
    }
    t0 = time.perf_counter()
    ttft = None
    out = []
    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        async for line in resp.aiter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content")
                    if delta:
                        out.append(delta)
                        if ttft is None:
                            ttft = (time.perf_counter() - t0) * 1000
                except Exception:
                    continue
    total = (time.perf_counter() - t0) * 1000
    return ttft or total, total, "".join(out)

async def tts_stream(client: httpx.AsyncClient, voice_id: str, text: str, out_path: Path) -> tuple[float, float]:
    url = f"{EL_BASE}/v1/text-to-speech/{voice_id}/stream"
    headers = {"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"}
    payload = {"text": text, "model_id": "eleven_flash_v2"}
    t0 = time.perf_counter()
    ttft = None
    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        if resp.status_code != 200:
            body = await resp.aread()
            raise RuntimeError(f"TTS stream failed: {resp.status_code} {body[:200]!r}")
        with out_path.open("wb") as f:
            async for chunk in resp.aiter_bytes():
                if chunk:
                    if ttft is None:
                        ttft = (time.perf_counter() - t0) * 1000
                    f.write(chunk)
    total = (time.perf_counter() - t0) * 1000
    return ttft or total, total

async def one_run(client_http: httpx.AsyncClient, lang: str):
    # Prepare input audio
    mp3 = await ensure_input_mp3(client_http, lang)

    # STT streaming
    stt_ttft, stt_total, transcript = await stt_deepgram_stream(mp3, lang)

    # LLM streaming
    llm_ttft, llm_total, reply = await llm_groq_stream(client_http, transcript or "Say hello")

    # TTS streaming
    voice = voices.get(lang) or voices.get("en")
    tts_ttft, tts_total = await tts_stream(client_http, voice, reply, ROOT / f"out-stream-pipeline-{lang}.mp3")

    total = stt_total + llm_total + tts_total
    print(
        f"{lang}: STT_TTFT={stt_ttft:.0f} ms, STT_total={stt_total:.0f} ms, "
        f"LLM_TTFT={llm_ttft:.0f} ms, LLM_total={llm_total:.0f} ms, "
        f"TTS_TTFT={tts_ttft:.0f} ms, TTS_total={tts_total:.0f} ms, "
        f"SEQ_TOTAL={total:.0f} ms -> out-stream-pipeline-{lang}.mp3"
    )

async def main():
    if not (DG and GQ and EL):
        print("Missing keys: ensure DEEPGRAM_API_KEY, GROQ_API_KEY, ELEVENLABS_API_KEY are set in .env")
        return
    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(args.runs):
            await one_run(client, lang)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
