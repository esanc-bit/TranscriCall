import argparse
import time
import uuid
import requests
import sounddevice as sd
import numpy as np
import wave
import io


def record_chunk(seconds: float, samplerate: int = 16000, channels: int = 1) -> bytes:
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description="TranscriCall capture client")
    parser.add_argument("--backend", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--call-id", default=None)
    parser.add_argument("--chunk-seconds", type=float, default=5.0)
    parser.add_argument("--device", type=int, default=None, help="Sounddevice input index (use sd.query_devices())")
    args = parser.parse_args()

    if args.device is not None:
        sd.default.device = args.device

    call_id = args.call_id or f"call_{uuid.uuid4().hex[:8]}"
    print(f"Starting capture for agent={args.agent_id} call_id={call_id}")

    try:
        while True:
            wav_bytes = record_chunk(args.chunk_seconds)
            files = {"audio": (f"chunk.wav", wav_bytes, "audio/wav")}
            data = {
                "agent_id": args.agent_id,
                "call_id": call_id,
                "chunk_start_ts": time.time(),
            }
            try:
                r = requests.post(f"{args.backend}/ingest", files=files, data=data, timeout=30)
                r.raise_for_status()
                resp = r.json()
                txt = resp.get("text", "")
                hot = resp.get("hot", False)
                print(("🔥 " if hot else " ") + txt)
            except Exception as e:
                print(f"Upload/transcription error: {e}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Stopping capture")


if __name__ == "__main__":
    main()