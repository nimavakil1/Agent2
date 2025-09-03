import os
import time
import statistics
from dotenv import load_dotenv
from livekit.plugins import groq

load_dotenv(".env", override=True)

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--runs", type=int, default=5)
args = parser.parse_args()

async def one(llm: groq.LLM):
    t0 = time.perf_counter()
    # very small prompt to reflect typical turn latency
    _ = await llm.chat([{"role": "user", "content": "Say a 3-word greeting."}])
    return (time.perf_counter() - t0) * 1000

async def main():
    llm = groq.LLM(model=os.getenv("GROQ_MODEL", "llama3-70b-8192"), temperature=0.2)
    times = []
    for _ in range(args.runs):
        dt = await one(llm)
        times.append(dt)
    print(f"Groq latency ms: min={min(times):.0f} avg={statistics.mean(times):.0f} max={max(times):.0f}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
