import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

EL = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
EL_BASE = (os.getenv("ELEVENLABS_BASE_URL") or "https://api.elevenlabs.io").rstrip("/")
voices = {
    "en": os.getenv("ELEVENLABS_VOICE_EN"),
    "fr": os.getenv("ELEVENLABS_VOICE_FR_BE"),
    "de": os.getenv("ELEVENLABS_VOICE_DE_DE"),
    "nl": os.getenv("ELEVENLABS_VOICE_NL_BE") or os.getenv("ELEVENLABS_VOICE_NL_NL"),
}

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--langs", default="en,fr,de,nl")
parser.add_argument("--runs", type=int, default=3)
args = parser.parse_args()

langs = [s.strip() for s in args.langs.split(",") if s.strip()]

async def synth_stream(client: httpx.AsyncClient, voice_id: str, text: str, out: Path):
    url = f"{EL_BASE}/v1/text-to-speech/{voice_id}/stream"
    headers = {"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"}
    payload = {"text": text, "model_id": "eleven_flash_v2", "optimize_streaming_latency": 2}

    t0 = time.perf_counter()
    ttft = None
    total = None

    async with client.stream("POST", url, headers=headers, json=payload) as resp:
        if resp.status_code != 200:
            body = await resp.aread()
            return None, None, f"HTTP {resp.status_code}: {body[:200]!r}"
        with out.open("wb") as f:
            async for chunk in resp.aiter_bytes():
                if chunk:
                    if ttft is None:
                        ttft = (time.perf_counter() - t0) * 1000
                    f.write(chunk)
            total = (time.perf_counter() - t0) * 1000

    return ttft, total, None

async def main():
    if not EL:
        print("Missing ELEVENLABS_API_KEY")
        return
    async with httpx.AsyncClient(timeout=30.0) as client:
        for lang in langs:
            v = voices.get(lang)
            if not v:
                print(f"{lang}: no voice configured")
                continue
            best_ttft = None
            best_total = None
            for i in range(args.runs):
                ttft, total, err = await synth_stream(
                    client,
                    v,
                    f"Streaming latency test in {lang}, run {i+1}",
                    ROOT / f"out-stream-{lang}.mp3",
                )
                if err:
                    print(f"{lang}: FAIL {err}")
                    break
                best_ttft = ttft if best_ttft is None else min(best_ttft, ttft)
                best_total = total if best_total is None else min(best_total, total)
            if best_ttft is not None and best_total is not None:
                print(f"{lang}: TTFT={best_ttft:.0f} ms, total={best_total:.0f} ms -> out-stream-{lang}.mp3")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
