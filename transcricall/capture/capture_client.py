import argparse
import time
import uuid
import requests
import sounddevice as sd
import numpy as np
import wave
import io
import sys
from typing import Optional


def find_device_index(name_substring: Optional[str], prefer_monitor: bool) -> Optional[int]:
    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"Error listing devices: {e}")
        return None
    chosen = None
    name_sub = (name_substring or '').lower()
    for idx, dev in enumerate(devices):
        dev_name = str(dev.get('name', '')).lower()
        is_input = dev.get('max_input_channels', 0) > 0
        if not is_input:
            continue
        if prefer_monitor and 'monitor' in dev_name:
            if not name_sub or name_sub in dev_name:
                chosen = idx
                break
        if name_sub and name_sub in dev_name:
            chosen = idx
    if chosen is None and prefer_monitor:
        # fallback to any input device if monitor not found
        for idx, dev in enumerate(devices):
            if dev.get('max_input_channels', 0) > 0:
                return idx
    return chosen


def record_chunk(seconds: float, samplerate: int, channels: int, downmix: bool) -> bytes:
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=channels, dtype='int16')
    sd.wait()
    data = audio
    if downmix and channels > 1:
        # average to mono int16
        data = np.mean(data, axis=1).astype(np.int16).reshape(-1, 1)
        channels_out = 1
    else:
        channels_out = channels
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels_out)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(data.tobytes())
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description="TranscriCall capture client")
    parser.add_argument("--backend", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--agent-id", default=None, help="ID del agente (si no se especifica, usa hostname)")
    parser.add_argument("--call-id", default=None)
    parser.add_argument("--chunk-seconds", type=float, default=5.0)
    parser.add_argument("--device", type=int, default=None, help="sounddevice input index (use sd.query_devices())")
    parser.add_argument("--device-name", type=str, default=None, help="Coincidencia por nombre del dispositivo de entrada")
    parser.add_argument("--prefer-monitor", action="store_true", help="Preferir dispositivos tipo 'Monitor of' (PulseAudio)")
    parser.add_argument("--samplerate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--downmix", action="store_true", help="Si estéreo, convertir a mono promedio")
    parser.add_argument("--api-key", type=str, default=None, help="API key opcional para encabezado Authorization: Bearer ...")
    args = parser.parse_args()

    # Determine agent id
    agent_id = args.agent_id or ("AGT-" + (uuid.getnode().to_bytes(6, 'big').hex()[-6:]))

    # Select device
    if args.device is not None:
        sd.default.device = args.device
    else:
        idx = find_device_index(args.device_name, args.prefer_monitor)
        if idx is not None:
            sd.default.device = idx
        else:
            print("No se encontró dispositivo de entrada adecuado. Use --device o --device-name.")
            sys.exit(1)

    # Validate channels
    if args.channels < 1:
        print("--channels debe ser >= 1")
        sys.exit(1)

    call_id = args.call_id or f"call_{uuid.uuid4().hex[:8]}"
    print(f"Iniciando captura: agent={agent_id} call_id={call_id} device={sd.default.device}")

    sess = requests.Session()
    headers = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    try:
        while True:
            wav_bytes = record_chunk(args.chunk_seconds, args.samplerate, args.channels, args.downmix)
            files = {"audio": ("chunk.wav", wav_bytes, "audio/wav")}
            data = {"agent_id": agent_id, "call_id": call_id, "chunk_start_ts": time.time()}
            try:
                r = sess.post(f"{args.backend}/ingest", files=files, data=data, headers=headers, timeout=30)
                r.raise_for_status()
                resp = r.json()
                txt = resp.get("text", "")
                hot = resp.get("hot", False)
                if txt:
                    print(("🔥 " if hot else "  ") + txt)
            except Exception as e:
                print(f"Error de subida/transcripción: {e}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Deteniendo captura")


if __name__ == "__main__":
    main()