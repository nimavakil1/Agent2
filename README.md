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
- Streaming TTS latency (TTFT + total) per language (saves `out-stream-<lang>.mp3`):
  - `uv run --env-file .env python scripts/stream_tts_benchmark.py --langs en,fr,de,nl --runs 3`
  - Reports Time-To-First-Byte (approx TTFT) and total generation time.
- End-to-end pipeline (STT→LLM→streaming TTS) latency:
  - `uv run --env-file .env python scripts/pipeline_benchmark.py --lang en --runs 3`
  - Measures STT (Deepgram REST), LLM (Groq), and streaming TTS (ElevenLabs) times, and writes `out-pipeline-<lang>.mp3`.
- LLM latency (Groq) quick benchmark:
  - `uv run --env-file .env python scripts/llm_benchmark.py --runs 5`
  - Prints min/avg/max latency for a short prompt.

### EU Region
- To use ElevenLabs EU servers, set in `.env`:
  - `ELEVENLABS_BASE_URL=https://api.eu.elevenlabs.io`
- The smoke and benchmark scripts will use this base URL.
- Note: the LiveKit ElevenLabs plugin may not expose a base URL toggle. If needed, we will upgrade or patch to support EU endpoints for the agent path.

Tip: ensure every voice ID is in your ElevenLabs “My Voices”, or the TTS calls will fail.

## Minimal Live Test (Mic → Agent → Voice)
Run a tiny UI to mint a LiveKit token, capture your microphone, and spawn the minimal agent for true end‑to‑end streaming latency.

1) Start the UI
   - `cd ui && npm ci && node server.js`
   - Server prints: `UI listening on http://localhost:3001`
2) Open the simulator
   - On the server: `curl http://localhost:3001/health` should return `OK`.
   - From your laptop: `http://YOUR_SERVER_IP:3001/simulate` (use http, not https).
   - Or SSH tunnel: `ssh -N -L 9301:localhost:3001 ubuntu@YOUR_SERVER` then open `http://localhost:9301/simulate`.
3) Click Start (English/French/German/Dutch)
   - UI mints a browser token and an agent token, starts the agent with the selected language, and connects your mic.
   - You should hear the voice you configured in `.env`.

Requirements
- `.env` must contain correct LiveKit credentials: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
- ElevenLabs voices must be in “My Voices”.
