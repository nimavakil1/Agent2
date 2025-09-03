# Agent2 (Minimal, Stable Baseline)

A clean baseline to validate provider keys and confirm your exact ElevenLabs voice IDs before running any LiveKit/room logic.

## What’s Included
- Provider checks for Groq, Deepgram, ElevenLabs
- TTS dry-run that synthesizes a short sample using your configured voice ID (saves to `out.mp3`)
- Minimal agent that sets ElevenLabs voice safely (via property) before starting
- Pinned Python deps via `pyproject.toml` (use `uv`)

## Setup
1) Install uv (https://docs.astral.sh/uv/)
2) Clone repo, then run:
   - `uv sync`
3) Copy env and fill values:
   - `cp .env.example .env`
   - Fill: LIVEKIT_*, GROQ_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY
   - Set voices you want (must be in your ElevenLabs “My Voices”):
     - `ELEVENLABS_VOICE_EN`, `ELEVENLABS_VOICE_FR_BE`, `ELEVENLABS_VOICE_DE_DE`, `ELEVENLABS_VOICE_NL_BE`, `ELEVENLABS_VOICE_NL_NL`

## Verify Providers + Voice
- `uv run --env-file .env python scripts/smoke.py`
  - Checks keys (200 responses)
  - Resolves your voice IDs to names
  - TTS dry-run: writes `out.mp3` with a short sample in your selected voice

## Test Each Voice + Latency
- TTS latency per language (saves `out-<lang>.mp3`):
  - `uv run --env-file .env python scripts/tts_benchmark.py --langs en,fr,de,nl --runs 1`
  - Output shows per-language duration (ms) and total.
- LLM latency (Groq) quick benchmark:
  - `uv run --env-file .env python scripts/llm_benchmark.py --runs 5`
  - Prints min/avg/max latency for a short prompt.

Tip: ensure every voice ID is in your ElevenLabs “My Voices”, or the TTS calls will fail.
