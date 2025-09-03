# Agent2 (Minimal, Stable Baseline)

A clean baseline to validate provider keys and confirm your exact ElevenLabs voice IDs before running any LiveKit/room logic.

## What’s Included
- Provider checks for Groq, Deepgram, ElevenLabs
- TTS dry-run that synthesizes a short sample using your configured voice ID (saves to `out.wav`)
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
  - TTS dry-run: writes `out.wav` with a short sample in your selected voice

## Run Minimal Agent (Standalone)
- Choose a language (en/nl/fr/de) in `CONTACT_LANGUAGE_CODE` or command line
- `uv run --env-file .env python -m src.agent --lang en`

If the voice or checks fail, fix `.env`, ensure the voice is added to “My Voices”, then re-run `smoke.py`.
