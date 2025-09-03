import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

EL = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
voices = {
    "en": os.getenv("ELEVENLABS_VOICE_EN"),
    "fr": os.getenv("ELEVENLABS_VOICE_FR_BE"),
    "de": os.getenv("ELEVENLABS_VOICE_DE_DE"),
    "nl": os.getenv("ELEVENLABS_VOICE_NL_BE") or os.getenv("ELEVENLABS_VOICE_NL_NL"),
}

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--langs", default="en,fr,de,nl")
parser.add_argument("--runs", type=int, default=1)
args = parser.parse_args()

langs = [s.strip() for s in args.langs.split(",") if s.strip()]

async def synth(client: httpx.AsyncClient, voice_id: str, text: str, out: Path):
    t0 = time.perf_counter()
    r = await client.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": EL, "accept": "audio/mpeg", "content-type": "application/json"},
        json={"text": text, "model_id": "eleven_flash_v2"},
    )
    dt = (time.perf_counter() - t0) * 1000
    if r.status_code != 200:
        print("FAIL", voice_id, r.status_code, r.text[:200])
        return None
    out.write_bytes(r.content)
    return dt

async def main():
    if not EL:
        print("Missing ELEVENLABS_API_KEY")
        return
    async with httpx.AsyncClient(timeout=20.0) as client:
        total = 0.0
        for lang in langs:
            v = voices.get(lang)
            if not v:
                print(f"{lang}: no voice configured")
                continue
            best = None
            for i in range(args.runs):
                dt = await synth(client, v, f"Latency test in {lang} run {i+1}", ROOT / f"out-{lang}.mp3")
                if dt is None:
                    break
                best = dt if best is None else min(best, dt)
            if best is not None:
                print(f"{lang}: {best:.0f} ms (best of {args.runs}) -> out-{lang}.mp3")
                total += best
        if total:
            print(f"Total (sum best): {total:.0f} ms")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
